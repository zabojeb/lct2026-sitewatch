"""Контролируемая проверка: где метод находит этап, а где нет.

Правильный ответ на реальных кадрах неизвестен, поэтому методы сравниваем на
синтетике, построенной строго по семантике матрицы:
  * этап задействует НЕСКОЛЬКО из своих альтернатив, а не всю технику сразу;
  * доставка появляется эпизодически;
  * каждая камера видит только часть техники;
  * детектор мигает (ложные срабатывания в отдельных кадрах) и путает похожие
    классы устойчиво (автокран ↔ манипулятор, самосвал ↔ грузовик, …);
  * на площадке бывает посторонняя техника, не относящаяся к этапу.

Главная метрика — точность ПО ГРУППАМ: этапы с одинаковым набором техники по
технике неразличимы в принципе, и штрафовать метод за выбор «соседа по группе»
бессмысленно. Точность до конкретной строки считаем отдельно — с априорным
распределением из плана, который выбирает внутри группы.
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass

from fusion import CameraEvidence, early_fuse, late_fuse
from infer import StageScorer, plan_prior, plan_check
from matrix import StageMatrix

# устойчивые путаницы детектора: визуально похожая техника
CONFUSE = {"C": "M", "M": "C", "D": "Q", "Q": "D", "L": "S", "S": "L", "B": "L",
           "X": "P", "P": "X", "T": "C", "V": "PD", "PD": "V", "Z": "Q", "G": "B", "R": "B"}
# те же пары, что в infer.LOOKALIKE — симулятор и модель согласованы намеренно


@dataclass
class Noise:
    n_cam: int = 4
    n_frames: int = 30
    p_vis: float = 0.6        # камера видит машину
    p_det: float = 0.8        # машина найдена в кадре, если видна
    p_fp: float = 0.01        # мигание: ложная метка в отдельном кадре (на ключ)
    p_conf: float = 0.15      # устойчивая путаница класса в камере
    p_incid: float = 0.3      # посторонняя техника на площадке
    p_sub: float = 0.0        # ПОДМЕНА: машина видна только как её «двойник» (так ошибается
                              # слабый/zero-shot детектор: буровую он называет сваебойной)


def sample_site(stage, keys, noise: Noise, rng, bg_keys, bg_w):
    """Какая техника реально присутствует для этапа."""
    present = set()
    if stage.work:
        present |= set(rng.sample(sorted(stage.work), rng.randint(1, min(3, len(stage.work)))))
    present |= {k for k in sorted(stage.delivery) if rng.random() < 0.3}
    if not present:
        present.add(rng.choice(sorted(stage.delivery)))
    if rng.random() < noise.p_incid:
        present.add(rng.choices(bg_keys, bg_w)[0])
    return present


def observe(present_by_cam: dict[str, set], keys, noise: Noise, rng):
    """Кадровые детекции камер → доли кадров по ключам (сырые, без фильтрации)."""
    per_cam, raw_any = {}, defaultdict(float)
    for cam, present in present_by_cam.items():
        hits = defaultdict(int)
        # подмена: истинная метка пропадает, вместо неё детектор выдаёт «двойника»
        # обход множеств только в sorted(): порядок set у строк меняется от запуска к
        # запуску (PYTHONHASHSEED), и вместе с ним — какие случайные числа кому достаются
        subbed = {k for k in sorted(present) if k in CONFUSE and rng.random() < noise.p_sub}
        present = (present - subbed) | {CONFUSE[k] for k in subbed}
        confused = sorted({CONFUSE[k] for k in sorted(present) if k in CONFUSE and rng.random() < noise.p_conf})
        present = sorted(present)
        for _ in range(noise.n_frames):
            for k in present:
                if rng.random() < noise.p_det:
                    hits[k] += 1
            for k in confused:
                if rng.random() < 0.5:
                    hits[k] += 1
            for k in keys:
                if rng.random() < noise.p_fp:
                    hits[k] += 1
        per_cam[cam] = {k: h / noise.n_frames for k, h in hits.items()}
    return per_cam


def fused_obs(per_cam, mode: str, min_frac: float = 0.15):
    if mode == "cam1":                                   # одна камера
        first = sorted(per_cam)[0]
        return {k: v for k, v in per_cam[first].items() if v >= min_frac}
    if mode == "union_raw":                              # «всё, что хоть раз мелькнуло»
        return {k: 1.0 for c in per_cam.values() for k, v in c.items() if v > 0}
    ev = CameraEvidence({c: {k: v for k, v in e.items() if v >= min_frac}
                         for c, e in per_cam.items()}, {})
    return early_fuse(ev, "noisy_or")


def run(M: StageMatrix, trials: int = 600, noise: Noise = Noise(), seed: int = 0,
        methods=("jaccard", "jaccard_work", "wjaccard", "bayes"),
        fusions=("cam1", "union_raw", "persist_noisyor"), confusion=None):
    rng = random.Random(seed)
    scorers = {m: StageScorer(M, m) for m in methods}
    if confusion is not None:                       # байесовский с матрицей ошибок детектора
        scorers["bayes+conf"] = StageScorer(M, "bayes", confusion=confusion)
    groups = defaultdict(list)
    for s in scorers["bayes"].cands:
        groups[s.signature].append(s)
    glist = list(groups)
    keys = sorted(M.keys)
    bg = scorers["bayes"].bg
    bg_keys, bg_w = zip(*sorted(bg.items()))
    res = defaultdict(lambda: [0, 0, 0])                 # top1, top5, n
    for _ in range(trials):
        g_true = rng.choice(glist)
        stage = rng.choice(groups[g_true])
        present = sample_site(stage, keys, noise, rng, bg_keys, bg_w)
        # каждая камера видит свою часть площадки
        cams = {f"c{i}": {k for k in sorted(present) if rng.random() < noise.p_vis} for i in range(noise.n_cam)}
        per_cam = observe(cams, keys, noise, rng)
        for f in fusions:
            obs = fused_obs(per_cam, f)
            for m, sc in scorers.items():
                # ранжируем группы; ничьи разбиваем случайно, а не порядком строк
                scored = [(sc._score(groups[g][0], obs), rng.random(), g) for g in glist]
                order = [g for _, _, g in sorted(scored, key=lambda t: (-t[0], t[1]))]
                r = res[(m, f)]
                r[0] += order[0] == g_true
                r[1] += g_true in order[:5]
                r[2] += 1
    return {k: (v[0] / v[2], v[1] / v[2]) for k, v in res.items()}


def run_plan(M: StageMatrix, trials: int = 600, noise: Noise = Noise(), seed: int = 1,
             plan_correct: float = 0.8, confusion=None):
    """Сверка с календарным планом: насколько надёжно ловятся отклонения.

    В 80 % случаев план верен, в 20 % на площадке идёт другой этап. Положительный
    случай — отклонение, различимое по технике (у фактического и планового этапов
    разный набор техники: внутри группы отклонение по камерам не видно в принципе).
    Возвращаем пары (LR, есть ли отклонение), чтобы построить кривую и выбрать порог.
    """
    rng = random.Random(seed)
    sc = StageScorer(M, "bayes", confusion=confusion)
    cands = sc.cands
    keys = sorted(M.keys)
    bg_keys, bg_w = zip(*sorted(sc.bg.items()))
    pairs, exact = [], 0
    for _ in range(trials):
        true = rng.choice(cands)
        planned = true if rng.random() < plan_correct else rng.choice(cands)
        present = sample_site(true, keys, noise, rng, bg_keys, bg_w)
        cams = {f"c{i}": {k for k in sorted(present) if rng.random() < noise.p_vis} for i in range(noise.n_cam)}
        obs = fused_obs(observe(cams, keys, noise, rng), "persist_noisyor")
        exact += sc.rank(obs, prior=plan_prior(M, [planned.row]))[0].stage.row == true.row
        pairs.append((plan_check(sc, obs, [planned.row])["lr"], planned.signature != true.signature))
    return pairs, exact / trials


def roc(pairs):
    """TPR/FPR по всем порогам и площадь под кривой."""
    pos = sorted(lr for lr, y in pairs if y)
    neg = sorted(lr for lr, y in pairs if not y)
    thr = sorted({lr for lr, _ in pairs}, reverse=True)
    pts = [(sum(n > t for n in neg) / max(len(neg), 1), sum(p > t for p in pos) / max(len(pos), 1), t)
           for t in thr]
    pts = [(0.0, 0.0, float("inf"))] + pts + [(1.0, 1.0, float("-inf"))]
    auc = sum((x2 - x1) * (y1 + y2) / 2 for (x1, y1, _), (x2, y2, _) in zip(pts, pts[1:]))
    return pts, auc, len(pos), len(neg)


def run_parallel(M: StageMatrix, trials: int = 400, noise: Noise = Noise(), seed: int = 2,
                 n_true: int = 2, penalty: float = 2.0):
    """Площадка, где параллельно идут n_true разных работ в разных зонах.

    Камеры делятся по зонам поровну. Сравниваем, сколько из реально идущих работ
    находит каждый способ, и не выдумывает ли он лишних:
      * early_top1 — одна «ближайшая» стадия по объединённому множеству;
      * early_topN — N лучших групп по объединению (N известно заранее — фора);
      * late — минимальный набор этапов, объясняющий камеры (N не известно).
    n_true=1 — контроль: позднее слияние не должно дробить одну работу на несколько.
    """
    rng = random.Random(seed)
    sc = StageScorer(M, "bayes")
    groups = defaultdict(list)
    for s in sc.cands:
        groups[s.signature].append(s)
    glist = [g for g in groups if g[0]]           # работы с техникой в самой операции
    keys = sorted(M.keys)
    bg_keys, bg_w = zip(*sorted(sc.bg.items()))
    stats = defaultdict(lambda: [0.0, 0.0, 0.0])   # recall, precision, число этапов
    for _ in range(trials):
        true_g = rng.sample(glist, n_true)
        cams = {}
        for i in range(noise.n_cam):
            g = true_g[i * n_true // noise.n_cam]
            present = sample_site(rng.choice(groups[g]), keys, noise, rng, bg_keys, bg_w)
            cams[f"c{i}"] = {k for k in sorted(present) if rng.random() < max(noise.p_vis, 0.8)}
        per_cam = observe(cams, keys, noise, rng)
        per_cam = {c: {k: v for k, v in e.items() if v >= 0.15} for c, e in per_cam.items()}
        ev = CameraEvidence(per_cam, {})
        ranked_groups = [tuple(m[0].signature) for _, m in sc.groups(sc.rank(early_fuse(ev)))]
        found = {"early_top1": ranked_groups[:1], f"early_top{n_true}": ranked_groups[:n_true],
                 "late": [a.group for a in late_fuse(ev, sc, penalty=penalty)]}
        tset = {tuple(g) for g in true_g}
        for name, f in found.items():
            hit = len(set(f) & tset)
            st = stats[name]
            st[0] += hit / n_true; st[1] += hit / max(len(f), 1); st[2] += len(f)
    return {k: tuple(round(x / trials, 3) for x in v) for k, v in stats.items()}
