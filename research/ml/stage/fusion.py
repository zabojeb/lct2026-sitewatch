"""Слияние наблюдений с нескольких камер в картину работ на площадке.

Два уровня, и они отвечают на разные вопросы:

1. Ранее слияние (по уликам). Техника со всех камер за окно сливается в одно
   «что есть на площадке» — noisy-OR по камерам. Верно, когда камеры смотрят на
   одну и ту же работу с разных сторон.

2. Позднее слияние (по решениям). Каждая камера — это обычно своя зона, и на
   площадке одновременно идут РАЗНЫЕ работы: в одной зоне бурят сваи, в другой
   бетонируют. Одна «ближайшая» по объединённому множеству стадия тогда выходит
   ложной: побеждает сводный этап, в который помещается всё сразу. Поэтому
   ищем МАЛЫЙ НАБОР этапов, который вместе объясняет все камеры, — каждая
   камера приписывается тому этапу из набора, что объясняет её лучше. Лишний
   этап добавляется, только если он заметно улучшает объяснение (штраф λ за
   каждый этап — чтобы не выдумывать по этапу на каждую камеру).

Ни камеры, ни время кадров синхронизировать не нужно: этап длится дни и недели,
поэтому единица слияния — смена или день, а не секунда. Это же делает метод
устойчивым к расхождению часов регистратора и камер.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from infer import StageScorer
from matrix import StageMatrix


@dataclass
class Detection:
    camera: str
    frame: str            # идентификатор кадра (время/номер) — для подсчёта устойчивости
    label: str            # класс детектора как есть
    conf: float = 1.0


@dataclass
class CameraEvidence:
    per_camera: dict[str, dict[str, float]]      # камера -> ключ техники -> устойчивость 0..1
    frames: dict[str, int]                       # камера -> число кадров
    unmapped: Counter = field(default_factory=Counter)   # метки без ключа в матрице


def camera_evidence(dets: list[Detection], M: StageMatrix, dataset: str | None = None,
                    frames_per_camera: dict[str, int] | None = None,
                    conf_thr: float = 0.25, min_frac: float = 0.15,
                    extra_labels: dict[str, str] | None = None,
                    key_weights: dict[str, float] | None = None) -> CameraEvidence:
    """Устойчивость присутствия ключа в камере = доля её кадров, где он найден.

    Порог min_frac отсекает мигание: машина, найденная в одном кадре из трёхсот,
    — скорее ложное срабатывание, чем техника на площадке. Доля, а не число
    кадров, — потому что записи камер разной длины (от 33 до 301 кадра).
    extra_labels — ручные дополнения моста «метка → ключ» поверх md.
    key_weights — понижающие веса для «инфраструктурной» техники. Башенный кран
    стоит на площадке весь проект и говорит о самом проекте, а не о текущей
    работе; с полным весом он тянет отдельные камеры к случайным этапам,
    где кран допустим (на данных №8 — к «демонтажу перекрытий»).
    """
    extra = {k.lower(): v for k, v in (extra_labels or {}).items()}
    seen = defaultdict(lambda: defaultdict(set))      # камера -> ключ -> кадры
    frames = defaultdict(set)
    unmapped = Counter()
    for d in dets:
        frames[d.camera].add(d.frame)
        if d.conf < conf_thr:
            continue
        key = extra.get(d.label.lower()) or M.key_for(d.label, dataset)
        if key not in M.keys:            # нет моста или ключа нет в md (md ещё не обновили)
            unmapped[d.label] += 1
            continue
        seen[d.camera][key].add(d.frame)
    n_frames = {c: (frames_per_camera or {}).get(c, len(f)) for c, f in frames.items()}
    per_cam = {}
    for cam in n_frames:
        ev = {}
        for key, fr in seen[cam].items():
            frac = len(fr) / max(n_frames[cam], 1)
            if frac >= min_frac:
                ev[key] = round(frac * (key_weights or {}).get(key, 1.0), 3)
        per_cam[cam] = ev
    return CameraEvidence(per_cam, n_frames, unmapped)


def early_fuse(ev: CameraEvidence, how: str = "noisy_or") -> dict[str, float]:
    """Камеры как независимые свидетели: noisy-OR. Машина, которую видят две
    камеры, достовернее той, что видит одна; union — жёсткое «видел хоть кто-то»."""
    out = defaultdict(float)
    for cam_ev in ev.per_camera.values():
        for k, p in cam_ev.items():
            if how == "noisy_or":
                out[k] = 1 - (1 - out[k]) * (1 - p)
            elif how == "max":
                out[k] = max(out[k], p)
            else:                         # union
                out[k] = 1.0
    return dict(out)


@dataclass
class ActiveStage:
    group: tuple                       # сигнатура (work, delivery) — группа неразличимых этапов
    members: list                      # этапы группы
    cameras: list[str]                 # камеры, чью картину он объясняет
    loglik: float


def late_fuse(ev: CameraEvidence, scorer: StageScorer, max_stages: int = 3,
              penalty: float = 2.0, prior: dict[int, float] | None = None,
              min_evidence: float = 0.5) -> list[ActiveStage]:
    """Минимальный набор этапов, совместно объясняющий все камеры.

    Цель: Σ_камер max_{этап ∈ набор} logP(улики камеры | этап) − λ·|набор|.
    Жадно добавляем этап с наибольшим приростом, пока прирост > λ. Считаем на
    уровне групп неразличимых этапов — внутри группы по технике выбирать нечего.
    Камеры без единой улики (видят только людей или неизвестную технику) в
    объяснении не участвуют, и это явно видно в выводе.
    """
    assert scorer.method == "bayes", "позднее слияние опирается на правдоподобие"
    # Камера, которая видит только слабые улики (например, один башенный кран с
    # пониженным весом), не должна порождать отдельную «зону работ»: иначе под
    # неё найдётся какой-нибудь этап, где такой кран допустим.
    # Какая техника вообще бывает «в работе», берём из самой матрицы: грузовик,
    # самосвал, газель, прицеп там только в доставке. Камера, видящая одну
    # логистику, зону работ не определяет — иначе под неё найдётся этап вроде
    # «отселения домов», где из всей техники допустим только транспорт.
    work_keys = {k for s in scorer.cands for k in s.work}
    cams = {c: e for c, e in ev.per_camera.items()
            if sum(v for k, v in e.items() if k in work_keys) >= min_evidence}
    if not cams:
        return []
    groups = defaultdict(list)
    for s in scorer.cands:
        groups[s.signature].append(s)
    # правдоподобие группы для камеры = правдоподобие любого её члена (они равны)
    ll = {g: {c: scorer._score(m[0], e) for c, e in cams.items()} for g, m in groups.items()}
    # априорное группы относительно равномерного по группам: 0 без плана,
    # >0 у групп, где есть плановый этап
    pri = prior or scorer.group_prior()
    rel = {g: math.log(sum(pri.get(s.row, 0) for s in m) * len(groups) + 1e-12)
           for g, m in groups.items()}

    def total(sel):
        return sum(max(ll[g][c] for g in sel) for c in cams)

    chosen = [max(groups, key=lambda g: total([g]) + rel[g])]
    while len(chosen) < max_stages:
        base = total(chosen)
        gain, g = max(((total(chosen + [g]) - base + rel[g], g) for g in groups if g not in chosen),
                      key=lambda t: t[0])
        if gain <= penalty:                 # лишний этап не окупает своего штрафа
            break
        chosen.append(g)

    out = []
    for g in chosen:
        mine = [c for c in cams if max(chosen, key=lambda h: ll[h][c]) == g]
        if mine:
            out.append(ActiveStage(g, groups[g], sorted(mine), sum(ll[g][c] for c in mine)))
    return out


# --- датасет №8 (const_video): камера и время — в имени файла ------------------
CV_NAME = re.compile(r"^(\d+)_(\d+)_(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})")


def load_const_video(root: str | Path, conf: float = 1.0) -> tuple[list[Detection], dict[str, int]]:
    """Разметка датасета №8 как «идеальный детектор».

    Имя кадра `101_174_2024-07-25-14-13-20_…`: префикс N01 — это «Cam N» из
    экранной надписи, дальше номер кадра и время регистратора. Время экранной
    надписи отстаёт от времени в имени на ~16 минут — часы камер и регистратора
    не синхронны, поэтому дальше работаем окнами, а не точным временем.
    """
    import yaml
    root = Path(root)
    names = yaml.safe_load(open(next(root.rglob("data.yaml"))))["names"]
    names = [names[i] for i in range(len(names))] if isinstance(names, dict) else names
    dets, frames = [], Counter()
    for lp in sorted(root.rglob("labels/*.txt")):
        m = CV_NAME.match(lp.name)
        if not m:                          # мусорный old_aug-кадр и прочее без камеры
            continue
        cam, frame = f"Cam{int(m.group(1)) // 100}", m.group(3)
        frames[cam] += 1
        for ln in lp.read_text().splitlines():
            p = ln.split()
            if p:
                dets.append(Detection(cam, frame, names[int(float(p[0]))], conf))
    return dets, dict(frames)
