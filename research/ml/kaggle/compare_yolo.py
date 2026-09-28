# %% [markdown]
# # Сравнение весов YOLO на строительных датасетах — ЛЦТ 2026, ДГП Москвы
#
# Три условия для каждой модели:
#
# | | |
# |---|---|
# | **A. zero-shot** | без обучения |
# | **B. trained** | обучение, дефолтные аугментации ultralytics |
# | **C. trained+aug** | обучение + доменные аугментации |
#
# **Метрика одна для всех трёх — COCO mAP через `pycocotools`.** Это принципиально:
# если обученные модели мерить через `model.val()`, а zero-shot — чем-то своим,
# числа окажутся несравнимыми. Любая модель в любом условии проходит один путь:
# предсказания → приведение классов к нашей таксономии → COCO-json → `COCOeval`.
# Оттуда же берётся **AP_small**, а он здесь важнее общего mAP: медианный объект
# на кадрах ДГП около 35 px.
#
# Колонка A разведена на три протокола, иначе получится таблица нулей:
# COCO-предобученные меряются **class-agnostic** (класс игнорируем, меряем
# локализацию); `yolo26*-objv1` — по классам Objects365 `machinery vehicle`/`crane`;
# open-vocab — по текстовым промптам.
#
# Среда: Kaggle, RTX PRO 6000 (96 ГБ), **без интернета**.

# %%
import os, sys, json, time, shutil, subprocess, random, hashlib
from pathlib import Path
from collections import Counter, defaultdict

# Офлайн-режим. YOLO_OFFLINE отключает is_online() и попытки скачивания.
os.environ["YOLO_OFFLINE"] = "1"
os.environ["NO_ALBUMENTATIONS_UPDATE"] = "1"
os.environ["WANDB_DISABLED"] = "true"

IN          = Path("/kaggle/input")
WORK        = Path("/kaggle/working")
# Выход ядра-загрузчика Kaggle монтирует под именем, которое заранее не угадать
# (слаг, заголовок или что-то третье). Поэтому не хардкодим путь, а ищем по
# маркеру — каталогу, где лежит manifest.json или yolo26n.pt.
def find_dir(root: Path, slug: str, depth: int = 4) -> Path | None:
    """Найти каталог датасета, не полагаясь на схему монтирования.

    Kaggle раскладывает входы не в корень /kaggle/input, а по подкаталогам:
    датасеты в `datasets/<owner>/<slug>`, выходы ядер в
    `notebooks/<owner>/<slug>`. Схема менялась и может поменяться снова,
    поэтому ищем по имени, а не по предполагаемому пути.
    """
    if not root.exists():
        return None
    direct = root / slug
    if direct.exists():
        return direct
    for d in root.rglob(slug):
        if d.is_dir():
            return d
    return None


def find_weights_dir(root: Path) -> Path | None:
    if not root.exists():
        return None
    for marker in ("manifest.json", "yolo26n.pt"):
        for hit in root.rglob(marker):
            return hit.parent
    return None

WEIGHTS_SRC = find_weights_dir(IN)
WEIGHTS     = WORK / "weights"              # writable: check_amp пишет сюда
DATA        = WORK / "dataset"
RUNS        = WORK / "runs"
for p in (WEIGHTS, DATA, RUNS): p.mkdir(parents=True, exist_ok=True)

if WEIGHTS_SRC is None:
    print("каталог с весами не найден. Содержимое /kaggle/input:")
    for d in sorted(IN.iterdir()):
        n = len(list(d.rglob("*.pt")))
        print(f"   {d.name}" + (f"   ({n} .pt внутри)" if n else ""))
    raise SystemExit("подключите выход ядра lct2026-yolo-weights-offline-bundle")

print("веса найдены в:", WEIGHTS_SRC)
for f in WEIGHTS_SRC.rglob("*"):
    if f.suffix not in {".pt", ".ts"}:
        continue
    # Файлы из clip/ должны остаться в подкаталоге: clip.load() ищет
    # ViT-B-32.pt именно в download_root/, то есть в WEIGHTS/"clip".
    dst = WEIGHTS / ("clip/" + f.name if f.parent.name == "clip" else f.name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(f, dst)
# Шрифт кладём туда, где его ищет ultralytics, иначе check_font полезет в сеть.
font_src = next(WEIGHTS_SRC.rglob("Arial.ttf"), None)
if font_src:
    fdir = Path.home() / ".config" / "Ultralytics"; fdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(font_src, fdir / "Arial.ttf")
print(f"весов: {len(list(WEIGHTS.glob('*.pt')))} .pt, {len(list(WEIGHTS.glob('*.ts')))} .ts")

# Установка колёс. Два независимых случая, и их нельзя связывать:
#   * ultralytics ставим, ТОЛЬКО если в образе версия старее 8.4 (иначе нет YOLO26);
#   * clip/ftfy/regex ставим ВСЕГДА — они нужны open-vocab моделям, а в образе
#     Kaggle их нет. Если повесить их установку на условие «ultralytics старый»,
#     то на свежем образе колонка zero-shot молча отвалится с ModuleNotFoundError.
def pip_install(paths):
    if not paths:
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "-q",
                    "--no-deps", *map(str, paths)], check=True)
    print("установлены:", [Path(p).name for p in paths])

all_whls = sorted(WEIGHTS_SRC.rglob("*.whl"))
by_name = lambda pref: [w for w in all_whls if w.name.startswith(pref)]

try:
    import ultralytics
    need_install = tuple(int(x) for x in ultralytics.__version__.split(".")[:2]) < (8, 4)
except ImportError:
    need_install = True

pip_install([w for pref in ("clip-", "ftfy-", "regex-") for w in by_name(pref)])
if need_install:
    u = by_name("ultralytics-")
    assert u, (f"нужен wheel ultralytics>=8.4 — без интернета иначе никак. "
               f"Искал в {WEIGHTS_SRC}, нашёл колёса: {[w.name for w in all_whls]}")
    pip_install(u)

import ultralytics, torch
from ultralytics import YOLO, settings
settings.update({"weights_dir": str(WEIGHTS), "datasets_dir": str(DATA),
                 "runs_dir": str(RUNS), "sync": False})
print("ultralytics", ultralytics.__version__, "| torch", torch.__version__)
if torch.cuda.is_available():
    print(torch.cuda.get_device_name(0),
          f"{torch.cuda.get_device_properties(0).total_memory/1e9:.0f} ГБ")

# %% [markdown]
# ## Preflight
#
# Проверяем офлайн-готовность ДО обучения. Часть проблем не падает, а тихо
# деградирует — например, `check_amp()` без `yolo26n.pt` просто пропустит
# проверку AMP и напишет предупреждение в лог, которое легко не заметить.

# %%
def preflight():
    bad = []
    from ultralytics.utils import ONLINE
    if ONLINE:
        bad.append("YOLO_OFFLINE не подействовал — ultralytics считает, что сеть есть")
    if not (WEIGHTS / "yolo26n.pt").exists():
        bad.append("нет weights/yolo26n.pt → check_amp() молча пропустит проверку AMP")
    if not (Path.home() / ".config/Ultralytics/Arial.ttf").exists():
        bad.append("нет Arial.ttf (некритично: кривые подписи на графиках)")
    try:
        import pycocotools  # noqa: F401
    except ImportError:
        bad.append("нет pycocotools → метрика не посчитается")
    return bad

issues = preflight()
print("\n".join(f"  ! {x}" for x in issues) if issues else "preflight пройден")

# %% [markdown]
# ## Таксономия и сведение пяти датасетов
#
# `__drop__` выбрасывает **аннотацию, но не кадр**: на снимке с каской обычно
# есть и размеченная техника других классов.
#
# Порядок классов MOCS взят из `ExtCon/extcon_gt.json` (секция `categories`),
# а не из публикации. `const_video/kran` проверен визуально — в большинстве
# случаев это башенный кран, разметка шумная.

# %%
TARGET = ["excavator","dump_truck","truck","bulldozer","roller","concrete_mixer",
          "mobile_crane","knuckle_crane","pile_rig","tower_crane","crawler_crane",
          "concrete_pump","wheel_loader","backhoe_loader","grader","worker"]
TID = {c: i for i, c in enumerate(TARGET)}
DROP = "__drop__"

MAPPING = {
 "heavy": {"Autocran":"mobile_crane","Bucket loader Big":"wheel_loader",
   "Bucket loader Standart":"wheel_loader","Bulldozer":"bulldozer",
   "Cleaning equipment":DROP,"Crane manipulator":"knuckle_crane","Dump truck":"dump_truck",
   "Excavator":"excavator","Forklift Giraffe":DROP,"Forklift Standart":DROP,
   "Gazelle":"truck","Mixer":"concrete_mixer","Motor grader":"grader","Roller":"roller",
   "Tanker":"truck","Trailer":"truck","Truck":"truck"},
 "video": {"betonomeshalka":"concrete_mixer","betononasos":"concrete_pump",
   "buldozer":"bulldozer","bur_machine":"pile_rig","excavator":"excavator",
   "gruzovik":"truck","human":"worker","kaska":DROP,"katok":"roller",
   "kran":"tower_crane","manipulator":"knuckle_crane","mini_bulldozer":"bulldozer",
   "mobile_kran":"mobile_crane","musorovoz":"truck","podemnik":DROP,
   "samosval":"dump_truck","traktor":DROP,"vil_podemnik":DROP},
 "mocs": {"Worker":"worker","Tower crane":"tower_crane","Hanging hook":DROP,
   "Vehicle crane":"mobile_crane","Roller":"roller","Bulldozer":"bulldozer",
   "Excavator":"excavator","Truck":"truck","Loader":"wheel_loader",
   "Pump truck":"concrete_pump","Concrete mixer":"concrete_mixer",
   "Pile driver":"pile_rig","Other vehicle":DROP},
 "panasia": {"PanAsia engineer":"worker","concrete truck":"concrete_mixer",
   "crane":"tower_crane","excavator-crane":"excavator","pump-truck":"concrete_pump",
   "roller":"roller","smalldigger":"excavator","trailer":"truck"},
 "miniexcav": {"0":"excavator"},
 # Peru Construction (Del Savio et al., Data in Brief 2022). classes.txt в выгрузке
 # нет, порядок взят из публикации.
 "peru": {"Dump_truck":"dump_truck","Excavator":"excavator",
   "Concrete_mixer_truck":"concrete_mixer","Skid_steer":"wheel_loader",
   "Tower_crane":"tower_crane","Truck_crane":"mobile_crane","Truck":"truck",
   "Person":"worker"},
}
PERU_NAMES = ["Dump_truck","Excavator","Concrete_mixer_truck","Skid_steer",
              "Tower_crane","Truck_crane","Truck","Person"]

# Кадры-мусор, выбрасываемые безусловно (проверено глазами).
BLACKLIST_SUBSTR = ["old_aug_1_old_old_1591788579"]

def remap_table(src_names, mapping):
    """src_class_id -> target_class_id; None означает «выбросить аннотацию»."""
    t = {}
    for i, n in enumerate(src_names):
        tgt = mapping.get(n, mapping.get(str(i), DROP))
        t[i] = None if tgt == DROP else TID[tgt]
    return t

# %%
import yaml, cv2

def iter_split(root: Path):
    """Найти пары (каталог кадров, каталог разметки).

    Поддерживаются две раскладки, и обе реально встречаются в наших датасетах:

      1. Roboflow/YOLO:   <split>/images/*.jpg  +  <split>/labels/*.txt
         так лежат heavy, const_video, panasia, MOCS внутри extcon;
      2. Плоская:         <dir>/*.jpg  +  <dir>/*.txt  вперемешку
         так лежат miniexcav и Peru Construction.

    Без второй ветки Peru — а это наш валидационный набор — дал бы ноль кадров,
    причём молча: сборка прошла бы успешно, просто с пустой валидацией.
    """
    seen = set()
    for sub in sorted(root.rglob("images")):
        lab = sub.parent / "labels"
        if lab.is_dir():
            seen.add(sub.resolve()); yield sub, lab
    for d in sorted({p.parent for p in root.rglob("*.jpg")} |
                    {p.parent for p in root.rglob("*.png")}):
        if d.resolve() in seen or d.name == "images":
            continue
        if any(d.glob("*.txt")):      # разметка рядом с кадрами
            yield d, d

def convert(src_root, names, mapping, out_root: Path, split: str, prefix: str,
            limit=None, blacklist=BLACKLIST_SUBSTR, val_fraction=0.0, seed=0):
    """Разложить кадры симлинками, переписать разметку в целевую таксономию.

    val_fraction > 0 отправляет детерминированную долю кадров в val. Делим по
    ХЭШУ ИМЕНИ, а не случайно: кадры const_video идут подряд из видео, соседние
    почти одинаковы, и случайное деление протащило бы почти-дубликаты из train
    в val, завысив метрику.
    """
    rnd_split = lambda stem: (int(hashlib.md5(stem.encode()).hexdigest(), 16) % 1000) / 1000.0
    tbl = remap_table(names, mapping)
    (out_root/"images"/split).mkdir(parents=True, exist_ok=True)
    (out_root/"labels"/split).mkdir(parents=True, exist_ok=True)
    stats, n, dropped = Counter(), 0, 0
    for img_dir, lab_dir in iter_split(Path(src_root)):
        for img in sorted(img_dir.iterdir()):
            if img.suffix.lower() not in {".jpg",".jpeg",".png"}: continue
            if any(b in img.name for b in blacklist):
                dropped += 1; continue
            lines = []
            lab = lab_dir/(img.stem + ".txt")
            if lab.exists():
                for ln in lab.read_text().splitlines():
                    p = ln.split()
                    if len(p) < 5: continue
                    t = tbl.get(int(float(p[0])))
                    if t is None: continue
                    lines.append(" ".join([str(t)] + p[1:5]))
                    stats[TARGET[t]] += 1
            tgt_split = ("val" if val_fraction and rnd_split(img.stem) < val_fraction
                         else split)
            (out_root/"images"/tgt_split).mkdir(parents=True, exist_ok=True)
            (out_root/"labels"/tgt_split).mkdir(parents=True, exist_ok=True)
            dst_img = out_root/"images"/tgt_split/f"{prefix}_{img.stem}{img.suffix}"
            if not dst_img.exists():
                try: dst_img.symlink_to(img.resolve())
                except OSError: shutil.copy2(img, dst_img)
            (out_root/"labels"/tgt_split/f"{prefix}_{img.stem}.txt").write_text("\n".join(lines))
            n += 1
            if limit and n >= limit: break
    return n, stats, dropped

def load_names(yaml_path):
    d = yaml.safe_load(open(yaml_path))
    nm = d["names"]
    return [nm[i] for i in range(len(nm))] if isinstance(nm, dict) else list(nm)

# %% [markdown]
# ### Сборка корпуса
#
# **Валидация — отдельный домен.** Обучаться на китайских кадрах MOCS и там же
# валидироваться бессмысленно: измерим не то, что нужно. Val берём из
# `const_video` — российские стройплощадки с неподвижных камер, ближайший
# доступный аналог кадров ДГП. Синтетика в val не попадает никогда.

# %%
# Пути подставьте под реальные имена каталогов в /kaggle/input.
SLUGS = {
 "heavy":     ("roboflowcontruction-heavy-equipment", "train"),
 "mocs":      ("extcon", "train"),
 "panasia":   ("construction-machinery-v1i-yolo26", "train"),
 "miniexcav": ("miniexcavconstruction-machines-images-dataset", "train"),
 # const_video делится: часть в train (единственный внешний источник bur_machine
 # помимо MOCS), часть в val.
 "video":     ("const-video-v2i-yolo26", "mixed"),
 # Peru целиком в val и никогда в train.
 "peru":      ("dataset-object-identication-training-construction", "val"),
}
SOURCES = {name: dict(root=find_dir(IN, slug), slug=slug, key=name, split=sp)
           for name, (slug, sp) in SLUGS.items()}
MOCS_NAMES = ["Worker","Tower crane","Hanging hook","Vehicle crane","Roller","Bulldozer",
              "Excavator","Truck","Loader","Pump truck","Concrete mixer","Pile driver",
              "Other vehicle"]

# Валидация складывается из двух частей, и ни одна не годится в одиночку:
#   * Peru — 4K, верхний ракурс с неподвижных камер, вшитый timestamp: ближе всего
#     к камерам ДГП по СЪЁМКЕ. Но в его 8 классах НЕТ буровой установки, а это
#     самый частый объект на кадрах ДГП — то есть главный класс останется
#     непроверенным.
#   * const_video — российские площадки, есть bur_machine и katok, то есть
#     покрывает как раз те классы. Но разрешение 960x960, не 4K.
# Поэтому берём обе: Peru целиком + отложенную часть const_video.
VAL_FRACTION = 0.30          # доля const_video, уходящая в валидацию
CORPUS = DATA / "corpus"

def build_corpus():
    total = Counter()
    for name, cfg in SOURCES.items():
        root = cfg["root"]
        if not root.exists():
            print(f"  пропуск {name}: нет {root}"); continue
        if name == "mocs":     names = MOCS_NAMES
        elif name == "peru":   names = PERU_NAMES
        else:
            y = next(root.rglob("data.yaml"), None)
            names = load_names(y) if y else [str(i) for i in range(64)]

        if cfg["split"] == "mixed":
            n, st, dr = convert(root, names, MAPPING[cfg["key"]], CORPUS, "train", name,
                                val_fraction=VAL_FRACTION)
        else:
            n, st, dr = convert(root, names, MAPPING[cfg["key"]], CORPUS,
                                cfg["split"], name)
        total.update(st)
        print(f"  {name:10s} {n:6d} кадров -> {cfg['split']}, аннотаций {sum(st.values()):6d}"
              + (f", выброшено мусорных кадров {dr}" if dr else ""))
    return total

print("проверка источников:")
missing = [n for n, c in SOURCES.items() if c["root"] is None]
for n, c in SOURCES.items():
    print(f"  {'+' if c['root'] else '!'} {n:10s} {c['root'] or c['slug'] + ' — НЕ НАЙДЕН'}")
if missing:
    print("\nчто реально примонтировано (каталоги с изображениями):")
    for d in sorted(IN.rglob("*")):
        if d.is_dir() and any(d.glob("*.jpg")) or (d.is_dir() and len(d.parts) - len(IN.parts) <= 3):
            print("   ", d.relative_to(IN))
    raise SystemExit(f"не найдены источники: {missing}")

print("\nсборка корпуса...")
counts = build_corpus()
print("\nраспределение классов:")
for c in sorted(TARGET, key=lambda x: -counts.get(x, 0)):
    n = counts.get(c, 0)
    flag = "  <-- ПУСТО" if n == 0 else ("  <-- мало" if n < 500 else "")
    print(f"  {c:16s} {n:7d}{flag}")

# Классы без единого примера НЕ портят mAP: pycocotools ставит им AP=-1
# и исключает из среднего. Но знать о них надо — это прямая дыра в покрытии.
empty = [c for c in TARGET if counts.get(c, 0) == 0]
scarce = [c for c in TARGET if 0 < counts.get(c, 0) < 500]
if empty:
    print(f"\nНЕТ НИ ОДНОГО ПРИМЕРА: {empty}")
    print("  эти классы модель не выучит никогда — нужен внешний источник")
if scarce:
    print(f"МАЛО примеров (<500): {scarce}")

(CORPUS/"data.yaml").write_text(yaml.safe_dump(
    {"path": str(CORPUS), "train": "images/train", "val": "images/val",
     "names": {i: c for i, c in enumerate(TARGET)}}, allow_unicode=True))

# %% [markdown]
# ## Единая метрика: COCO mAP через pycocotools
#
# Все три условия проходят один путь. Разница только в том, откуда берутся
# предсказания и как их классы приводятся к нашей таксономии.
#
# `AP_small` (объекты < 32² px) здесь важнее общего mAP — это и есть режим,
# в котором работает решение на кадрах ДГП.

# %%
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
import numpy as np
from PIL import Image

def build_coco_gt(corpus: Path, split="val", agnostic=False):
    """YOLO-разметка -> COCO GT. agnostic=True схлопывает все классы в один."""
    img_dir, lab_dir = corpus/"images"/split, corpus/"labels"/split
    images, anns, ann_id = [], [], 1
    cats = ([{"id": 1, "name": "object"}] if agnostic
            else [{"id": i+1, "name": c} for i, c in enumerate(TARGET)])
    for img_id, ip in enumerate(sorted(img_dir.iterdir()), start=1):
        if ip.suffix.lower() not in {".jpg",".jpeg",".png"}: continue
        w, h = Image.open(ip).size
        images.append({"id": img_id, "file_name": ip.name, "width": w, "height": h})
        lp = lab_dir/(ip.stem + ".txt")
        if not lp.exists(): continue
        for ln in lp.read_text().splitlines():
            p = ln.split()
            if len(p) < 5: continue
            c, cx, cy, bw, bh = int(p[0]), *map(float, p[1:5])
            x, y, bw, bh = (cx-bw/2)*w, (cy-bh/2)*h, bw*w, bh*h
            anns.append({"id": ann_id, "image_id": img_id,
                         "category_id": 1 if agnostic else c+1,
                         "bbox": [x, y, bw, bh], "area": bw*bh, "iscrowd": 0})
            ann_id += 1
    return {"images": images, "annotations": anns, "categories": cats}

def subset_gt(gt_dict, prefix):
    """Срез GT по источнику кадров (имена начинаются с префикса датасета)."""
    ids = {im["id"] for im in gt_dict["images"] if im["file_name"].startswith(prefix)}
    return {"images": [i for i in gt_dict["images"] if i["id"] in ids],
            "annotations": [a for a in gt_dict["annotations"] if a["image_id"] in ids],
            "categories": gt_dict["categories"]}, ids


def coco_eval(gt_dict, dets, label=""):
    """dets — список COCO-детекций. Возвращает срез метрик."""
    if not dets:
        return {"mAP50-95": 0.0, "mAP50": 0.0, "AP_small": 0.0,
                "AP_medium": 0.0, "AP_large": 0.0, "AR100": 0.0, "n_det": 0}
    gt_path, dt_path = WORK/"_gt.json", WORK/"_dt.json"
    json.dump(gt_dict, open(gt_path, "w")); json.dump(dets, open(dt_path, "w"))
    import contextlib, io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        gt = COCO(str(gt_path)); dt = gt.loadRes(str(dt_path))
        e = COCOeval(gt, dt, "bbox"); e.evaluate(); e.accumulate(); e.summarize()
    s = e.stats
    return {"mAP50-95": round(float(s[0]), 4), "mAP50": round(float(s[1]), 4),
            "AP_small": round(float(s[3]), 4), "AP_medium": round(float(s[4]), 4),
            "AP_large": round(float(s[5]), 4), "AR100": round(float(s[8]), 4),
            "n_det": len(dets)}

def predict_to_coco(model, gt_dict, img_dir: Path, remap=None, agnostic=False,
                    imgsz=1280, conf=0.001, batch=16, device=0):
    """Прогон модели -> COCO-детекции.

    conf=0.001 намеренно низкий: COCO mAP считается по полной кривой
    precision-recall, и отсечение по уверенности её обрезает, занижая метрику.
    remap: имя_класса_модели -> имя_нашего_класса (None = классы уже наши).
    """
    id_by_name = {im["file_name"]: im["id"] for im in gt_dict["images"]}
    files = [img_dir/im["file_name"] for im in gt_dict["images"]]
    dets = []
    for i in range(0, len(files), batch):
        chunk = files[i:i+batch]
        for f, r in zip(chunk, model.predict(chunk, imgsz=imgsz, conf=conf,
                                             device=device, verbose=False, max_det=300)):
            img_id = id_by_name[f.name]
            for b in r.boxes:
                name = r.names[int(b.cls)]
                if agnostic:
                    cat = 1
                else:
                    tgt = remap.get(name) if remap else name
                    if tgt is None or tgt not in TID: continue
                    cat = TID[tgt] + 1
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                dets.append({"image_id": img_id, "category_id": cat,
                             "bbox": [x1, y1, x2-x1, y2-y1], "score": float(b.conf)})
    return dets

# %% [markdown]
# ## Модельный зоопарк
#
# Для detect в ultralytics есть ровно эти семейства — список исчерпывающий,
# а не выборочный. `yolo12` и `rtdetr` сегментации не имеют, но нам нужна детекция.

# %%
GRID = [  # основная сетка: обучаем в условиях B и C
    ("yolov8n","yolov8n.pt"), ("yolov8s","yolov8s.pt"), ("yolov8m","yolov8m.pt"),
    ("yolov9t","yolov9t.pt"), ("yolov9s","yolov9s.pt"), ("yolov9m","yolov9m.pt"),
    ("yolov10n","yolov10n.pt"), ("yolov10s","yolov10s.pt"), ("yolov10m","yolov10m.pt"),
    ("yolo11n","yolo11n.pt"), ("yolo11s","yolo11s.pt"), ("yolo11m","yolo11m.pt"),
    ("yolo12n","yolo12n.pt"), ("yolo12s","yolo12s.pt"), ("yolo12m","yolo12m.pt"),
    ("yolo26n","yolo26n.pt"), ("yolo26s","yolo26s.pt"), ("yolo26m","yolo26m.pt"),
]
CONTEXT = [("yolov5su","yolov5su.pt"), ("rtdetr-l","rtdetr-l.pt")]
# Инициализация: COCO против Objects365 при прочих равных.
INIT_PAIR = [("yolo26s-coco","yolo26s.pt"), ("yolo26s-o365","yolo26s-objv1-150.pt")]

# Objects365: наш домен там уже частично есть.
O365_REMAP = {"machinery vehicle": "excavator",   # обобщённая «спецтехника»
              "crane": "tower_crane", "truck": "truck", "pickup truck": "truck",
              "fire truck": "truck", "person": "worker"}
OPENVOCAB_PROMPTS = ["excavator","tower crane","mobile crane","crawler crane",
                     "dump truck","truck","bulldozer","road roller",
                     "concrete mixer truck","concrete pump truck","drilling rig",
                     "pile driver","wheel loader","construction worker"]
OV_REMAP = {"excavator":"excavator","tower crane":"tower_crane",
            "mobile crane":"mobile_crane","crawler crane":"crawler_crane",
            "dump truck":"dump_truck","truck":"truck","bulldozer":"bulldozer",
            "road roller":"roller","concrete mixer truck":"concrete_mixer",
            "concrete pump truck":"concrete_pump","drilling rig":"pile_rig",
            "pile driver":"pile_rig","wheel loader":"wheel_loader",
            "construction worker":"worker"}
ZS_OPENVOCAB = [("yolov8s-worldv2","yolov8s-worldv2.pt"),
                ("yolov8l-worldv2","yolov8l-worldv2.pt")]

# %% [markdown]
# ## A. Zero-shot
#
# Три протокола, потому что одной цифрой это не выражается:
# COCO-модели не знают спецтехники вообще (на наших 16 классах у них был бы
# тождественный ноль), Objects365 знает `machinery vehicle` и `crane`,
# open-vocab понимает текст.

# %%
VAL_IMG = CORPUS/"images"/"val"
GT      = build_coco_gt(CORPUS, "val", agnostic=False)
GT_AG   = build_coco_gt(CORPUS, "val", agnostic=True)
print(f"валидация: {len(GT['images'])} кадров, {len(GT['annotations'])} аннотаций")

RESULTS = []
# Валидация состоит из двух разных режимов съёмки, и усреднять их в одну цифру
# значит терять главное. Peru — 4K с неподвижных камер (объект после ресайза в
# 1280 становится ~12 px), const_video — 960x960 российских площадок. Разрыв
# между этими двумя числами и есть мера доменной устойчивости модели.
VAL_DOMAINS = {"peru": "peru_", "video": "video_"}

def record(model, condition, protocol, metrics, extra=None, dets=None, gt=None):
    row = {"model": model, "condition": condition, "protocol": protocol,
           **metrics, **(extra or {})}
    if dets is not None and gt is not None:
        for dom, pref in VAL_DOMAINS.items():
            sub, ids = subset_gt(gt, pref)
            if not sub["annotations"]:
                continue
            m = coco_eval(sub, [d for d in dets if d["image_id"] in ids])
            row[f"mAP50-95_{dom}"] = m["mAP50-95"]
            row[f"AP_small_{dom}"] = m["AP_small"]
    RESULTS.append(row)
    dom_str = "  ".join(f"{d}={row.get(f'mAP50-95_{d}', float('nan')):.3f}"
                        for d in VAL_DOMAINS if f"mAP50-95_{d}" in row)
    print(f"  {model:18s} {condition:12s} {protocol:14s} "
          f"mAP50-95={metrics['mAP50-95']:.3f}  AP_s={metrics['AP_small']:.3f}"
          + (f"   [{dom_str}]" if dom_str else ""))

def zero_shot(name, weight, protocol, imgsz=1280):
    w = WEIGHTS/weight
    if not w.exists():
        print(f"  пропуск {name}: нет {w.name}"); return
    if protocol == "openvocab":
        from ultralytics import YOLOWorld
        m = YOLOWorld(str(w)); m.set_classes(OPENVOCAB_PROMPTS)
        dets = predict_to_coco(m, GT, VAL_IMG, remap=OV_REMAP, imgsz=imgsz)
        record(name, "A/zero-shot", protocol, coco_eval(GT, dets), dets=dets, gt=GT)
    elif protocol == "objects365":
        m = YOLO(str(w))
        dets = predict_to_coco(m, GT, VAL_IMG, remap=O365_REMAP, imgsz=imgsz)
        record(name, "A/zero-shot", protocol, coco_eval(GT, dets), dets=dets, gt=GT)
    else:  # class-agnostic: класс игнорируем, меряем только локализацию
        m = YOLO(str(w))
        dets = predict_to_coco(m, GT_AG, VAL_IMG, agnostic=True, imgsz=imgsz)
        record(name, "A/zero-shot", "class-agnostic", coco_eval(GT_AG, dets))

# %% [markdown]
# ## B / C. Обучение
#
# Условие **B** — гиперпараметры ultralytics по умолчанию.
# Условие **C** — доменные аугментации. Ключевые отличия от дефолта:
# расширенный диапазон масштаба (главный фактор для объектов в 35 px),
# усиленный HSV (сезон и освещение), `erasing` (перекрытия площадки),
# ранний выход из mosaic (он вредит локализации мелких объектов на финише).

# %%
AUG_BASE = dict()                      # B: как есть
AUG_DOMAIN = dict(                     # C: под наш домен
    hsv_h=0.020, hsv_s=0.80, hsv_v=0.55,     # сезон, время суток, погода
    degrees=6.0, translate=0.12, scale=0.75,  # scale — самый важный параметр
    shear=3.0, perspective=0.0008,            # разная высота/наклон установки камеры
    fliplr=0.5, flipud=0.0,
    mosaic=1.0, close_mosaic=20,              # mosaic мешает мелким объектам под конец
    mixup=0.10, cutmix=0.0,
    erasing=0.35,                             # «часть площадки закрыта»
)

# DRY_RUN: разведка перед боевым прогоном. Проверяет то, что ломается в первую
# очередь — пути к датасетам, сборку корпуса, работу метрики и один цикл
# обучения. Стоит минуты. Узнать про опечатку в пути через час полного прогона
# гораздо дороже, поэтому первый пуск делаем именно так.
DRY_RUN = False

# Батч привязываем к реальной VRAM, а не к предполагаемой. Ядро может достаться
# и на T4 16 ГБ, и на RTX PRO 6000 96 ГБ — жёстко зашитый batch=24 на 1280 px
# на T4 просто упадёт по памяти, причём в середине сетки, а не на первой модели.
VRAM_GB = (torch.cuda.get_device_properties(0).total_memory / 1e9
           if torch.cuda.is_available() else 0)
EPOCHS, IMGSZ = (2, 640) if DRY_RUN else (60, 1280)
BATCH = 8 if DRY_RUN else max(4, int(VRAM_GB // 4))   # ~4 ГБ на образец при 1280
DEVICE = 0
print(f"VRAM {VRAM_GB:.0f} ГБ -> batch={BATCH}, imgsz={IMGSZ}, epochs={EPOCHS}")

def train_and_eval(name, weight, condition, aug, epochs=EPOCHS, imgsz=IMGSZ, batch=BATCH):
    w = WEIGHTS/weight if (WEIGHTS/weight).exists() else weight
    if isinstance(w, Path) and not w.exists() and not str(weight).endswith(".yaml"):
        print(f"  пропуск {name}: нет весов {weight}"); return
    t0 = time.time()
    m = YOLO(str(w))
    m.train(data=str(CORPUS/"data.yaml"), epochs=epochs, imgsz=imgsz, batch=batch,
            device=DEVICE, project=str(RUNS), name=f"{name}_{condition}",
            exist_ok=True, verbose=False, plots=False, val=False, **aug)
    dets = predict_to_coco(m, GT, VAL_IMG, imgsz=imgsz)   # классы уже наши
    record(name, condition, "trained", coco_eval(GT, dets),
           extra={"epochs": epochs, "imgsz": imgsz, "train_min": round((time.time()-t0)/60, 1)},
           dets=dets, gt=GT)
    return m

# %% [markdown]
# ### Порядок запуска
#
# Первым идёт сравнение инициализаций COCO против Objects365 — два прогона,
# а решают они, с каких весов стартует вся остальная сетка. Считать их
# в конце значило бы переучивать всё заново.

# %%
# --- A: zero-shot ---
print("A. zero-shot")
ZS_IMGSZ = 640 if DRY_RUN else 1280
_grid = GRID[:1] if DRY_RUN else GRID
_ov   = ZS_OPENVOCAB[:1] if DRY_RUN else ZS_OPENVOCAB
_o365 = [("yolo26s-o365","yolo26s-objv1-150.pt")] if DRY_RUN else [
         ("yolo26s-o365","yolo26s-objv1-150.pt"), ("yolo26x-o365","yolo26x-objv1-150.pt")]

for n, w in _grid: zero_shot(n, w, "agnostic",   imgsz=ZS_IMGSZ)
for n, w in _ov:   zero_shot(n, w, "openvocab",  imgsz=ZS_IMGSZ)
for n, w in _o365: zero_shot(n, w, "objects365", imgsz=ZS_IMGSZ)

# %%
# --- Инициализация: COCO vs Objects365 ---
print("\nвыбор инициализации")
for n, w in (INIT_PAIR[:1] if DRY_RUN else INIT_PAIR):
    train_and_eval(n, w, "B/init", AUG_BASE)

# %%
# --- B и C по сетке ---
if DRY_RUN:
    print("\nDRY_RUN: полная сетка пропущена, проверяем один цикл с доменными аугами")
    train_and_eval(*GRID[0], "C/trained+aug", AUG_DOMAIN)
else:
    print("\nB. обучение, дефолтные аугментации")
    for n, w in GRID + CONTEXT:
        train_and_eval(n, w, "B/trained", AUG_BASE)

    print("\nC. обучение + доменные аугментации")
    for n, w in GRID + CONTEXT:
        train_and_eval(n, w, "C/trained+aug", AUG_DOMAIN)

# %% [markdown]
# ## Результаты

# %%
import pandas as pd
df = pd.DataFrame(RESULTS)
df.to_csv(WORK/"results.csv", index=False)

if len(df):
    piv = df.pivot_table(index="model", columns="condition",
                         values=["mAP50-95", "AP_small"], aggfunc="max")
    print(piv.to_string())

    # Прирост от аугментаций — то, ради чего условие C и существует
    b = df[df.condition == "B/trained"].set_index("model")
    c = df[df.condition == "C/trained+aug"].set_index("model")
    common = b.index.intersection(c.index)
    if len(common):
        delta = pd.DataFrame({
            "mAP50-95 B": b.loc[common, "mAP50-95"],
            "mAP50-95 C": c.loc[common, "mAP50-95"],
            "Δ mAP": (c.loc[common, "mAP50-95"] - b.loc[common, "mAP50-95"]).round(4),
            "Δ AP_small": (c.loc[common, "AP_small"] - b.loc[common, "AP_small"]).round(4),
        }).sort_values("Δ mAP", ascending=False)
        print("\nвклад доменных аугментаций:")
        print(delta.to_string())
