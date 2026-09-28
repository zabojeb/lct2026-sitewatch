# %% [markdown]
# # Zero-shot YOLO на двух строительных датасетах
#
# Три оценки для каждой из 25 моделей:
#
# | колонка | данные |
# |---|---|
# | **A** | `neogpx/constructionxc7c` — **test** сплит (757 кадров, 8 классов) |
# | **B** | `xyzyxzzxy/construction-equipment` — **первая половина valid**, отсортированного по имени (1614 из 3228) |
# | **A+B** | объединение обоих сплитов |
#
# ## Две метрики, а не одна
#
# Стандартные YOLO обучены на COCO, где нет ни экскаваторов, ни грейдеров, ни
# катков. Одна цифра «zero-shot mAP» здесь ничего не значит, поэтому считаем два
# протокола на одних и тех же предсказаниях:
#
# * **class-agnostic** — класс игнорируется, меряется только локализация:
#   нашла модель объект или нет. Единственный протокол, дающий осмысленные
#   ненулевые числа для всех 25 моделей.
# * **COCO-mapped** — классо-зависимый: COCO-классы `truck`/`bus`/`car`
#   сопоставляются строительным. Числа будут низкими, и это не ошибка —
#   это и есть ответ на вопрос «годится ли COCO-YOLO из коробки».
#
# ## Общая таксономия для совместной оценки
#
# У датасетов разные наборы классов (8 против 17). Для классо-зависимой метрики
# приводим оба к **8 общим классам** — это пересечение, взятое по HF-датасету.
# Классы, которых нет у обоих (Gazelle, Forklift, Tanker, Trailer, Cleaning
# equipment), в классо-зависимой оценке не участвуют. На class-agnostic это
# никак не влияет.

# %%
import os, sys, json, time, shutil, subprocess, hashlib
from pathlib import Path
from collections import Counter, defaultdict

os.environ["NO_ALBUMENTATIONS_UPDATE"] = "1"
os.environ["WANDB_DISABLED"] = "true"

IN   = Path("/kaggle/input")
WORK = Path("/kaggle/working")
EVAL = WORK / "evalset"; EVAL.mkdir(parents=True, exist_ok=True)

def find_dir(root: Path, name: str):
    """Kaggle монтирует входы по подкаталогам (datasets/<owner>/<slug>,
    notebooks/<owner>/<slug>), причём схема менялась. Ищем по имени."""
    if not root.exists():
        return None
    if (root / name).exists():
        return root / name
    for d in root.rglob(name):
        if d.is_dir():
            return d
    return None

# Бандл весов из ядра lct2026-yolo-weights-offline-bundle, если подключён.
# Не обязателен: при включённом интернете ultralytics докачает недостающее сам.
WB = find_dir(IN, "lct2026-yolo-weights-offline-bundle")
WEIGHTS = WORK / "weights"; WEIGHTS.mkdir(exist_ok=True)
if WB:
    for f in WB.rglob("*.pt"):
        if not (WEIGHTS / f.name).exists():
            shutil.copy2(f, WEIGHTS / f.name)
print("локальных весов:", len(list(WEIGHTS.glob("*.pt"))), "| бандл:", WB)

# В образе Kaggle ultralytics может отсутствовать. Ставим из бандла (быстрее
# и версия та же, что проверена), с откатом на pip — интернет в этом ядре
# включён, он всё равно нужен для HF-датасета.
def ensure_ultralytics():
    try:
        import ultralytics
        if tuple(int(x) for x in ultralytics.__version__.split(".")[:2]) >= (8, 4):
            return
    except ImportError:
        pass
    whls = sorted(WB.rglob("*.whl")) if WB else []
    if whls:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "-q",
                        "--no-deps", *map(str, whls)], check=True)
        print("ultralytics из бандла:", [w.name for w in whls])
    else:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                        "ultralytics>=8.4"], check=True)
        print("ultralytics установлен из pip")

ensure_ultralytics()

import torch
from ultralytics import YOLO, settings
settings.update({"weights_dir": str(WEIGHTS), "runs_dir": str(WORK/"runs"), "sync": False})
import ultralytics
print("ultralytics", ultralytics.__version__, "| torch", torch.__version__)
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "GPU нет")

# %% [markdown]
# ## Общая таксономия и сопоставления

# %%
# 8 общих классов (порядок = порядок HF-датасета)
COMMON = ["bulldozer", "dump_truck", "excavator", "grader",
          "loader", "mixer_truck", "mobile_crane", "roller"]
CID = {c: i for i, c in enumerate(COMMON)}

# HF neogpx/constructionxc7c: 8 классов
HF_NAMES = ["bulldozer", "dump truck", "excavator", "grader",
            "loader", "mixer truck", "mobile crane", "roller"]
HF_MAP = {"bulldozer":"bulldozer", "dump truck":"dump_truck", "excavator":"excavator",
          "grader":"grader", "loader":"loader", "mixer truck":"mixer_truck",
          "mobile crane":"mobile_crane", "roller":"roller",
          # Roboflow добавляет супер-категорию с именем проекта — в GT не идёт
          "construction-vehicle-detection": None, "vehicles": None}

# Kaggle xyzyxzzxy/construction-equipment: 17 классов.
# Порядок взят с карточки датасета — своего data.yaml в выгрузке нет.
# ВНИМАНИЕ: это НЕ тот порядок, что в Roboflow-переэкспорте того же набора
# (там классы отсортированы по алфавиту). Перепутать порядки = сдвинуть все метки.
KG_NAMES = ["Dump truck","Excavator","Motor grader","Roller","Crane manipulator",
            "Gazelle","Forklift Standart","Bucket loader Big","Mixer","Tanker",
            "Bulldozer","Cleaning equipment","Truck","Trailer","Forklift Giraffe",
            "Bucket loader Standart","Autocran"]
KG_MAP = {"Dump truck":"dump_truck", "Excavator":"excavator", "Motor grader":"grader",
          "Roller":"roller", "Bucket loader Big":"loader",
          "Bucket loader Standart":"loader", "Mixer":"mixer_truck",
          "Bulldozer":"bulldozer", "Autocran":"mobile_crane"}
# остальные (Gazelle, Forklift*, Tanker, Trailer, Truck, Cleaning equipment,
# Crane manipulator) общего аналога не имеют -> в классо-зависимой метрике не участвуют

# COCO -> общая таксономия. Соответствие заведомо грубое: в COCO нет ни
# экскаватора, ни грейдера, ни катка, ни погрузчика. Единственное, что можно
# сопоставить честно, — грузовики.
COCO_MAP = {"truck": "dump_truck", "bus": "mixer_truck", "car": None,
            "train": None, "boat": None}

# %% [markdown]
# ## Сплит A: HF-датасет, test
#
# Формат HF-обёрток Roboflow меняется от версии к версии, поэтому не полагаемся
# на конкретную схему полей, а определяем её по `features` на лету.

# %%
from PIL import Image
import numpy as np

GT_ALL = {"images": [], "annotations": [],
          "categories": [{"id": i+1, "name": c} for i, c in enumerate(COMMON)]}
SPLIT_IDS = {"A": set(), "B": set()}
_next_img, _next_ann = [1], [1]

def add_sample(pil_img, boxes_xywh, class_names, src_map, split, stem):
    """Положить кадр на диск и добавить его GT в общий COCO-словарь."""
    img_id = _next_img[0]; _next_img[0] += 1
    dst = EVAL / f"{split}_{stem}.jpg"
    if not dst.exists():
        pil_img.convert("RGB").save(dst, quality=95)
    w, h = pil_img.size
    GT_ALL["images"].append({"id": img_id, "file_name": dst.name, "width": w, "height": h})
    SPLIT_IDS[split].add(img_id)
    for (x, y, bw, bh), cname in zip(boxes_xywh, class_names):
        tgt = src_map.get(cname)
        if tgt is None:          # класс без общего аналога — в GT не попадает
            continue
        GT_ALL["annotations"].append({
            "id": _next_ann[0], "image_id": img_id, "category_id": CID[tgt] + 1,
            "bbox": [float(x), float(y), float(bw), float(bh)],
            "area": float(bw * bh), "iscrowd": 0})
        _next_ann[0] += 1

# %%
# Библиотеку `datasets` не используем: репозиторий отдаёт данные через
# loading-скрипт (constructionxc7c.py), а свежие версии datasets их больше не
# поддерживают — падает с "Dataset scripts are no longer supported".
# Качаем data/test.zip напрямую: внутри Roboflow-экспорт COCO
# (_annotations.coco.json + кадры), парсить его проще, чем чинить совместимость.
import zipfile

# Архив берём ИЗ БАНДЛА, а не из сети: это ядро привязано к соревнованию,
# а соревновательным ядрам Kaggle запрещает интернет — скачать здесь нельзя
# никакими настройками. Загрузчик кладёт constructionxc7c_test.zip заранее.
hf_dir = WORK / "hf_test"
if not hf_dir.exists():
    src_zip = next(WB.rglob("constructionxc7c_test.zip"), None) if WB else None
    assert src_zip, (
        "нет constructionxc7c_test.zip в бандле. Перезапустите ядро "
        "lct2026-yolo-weights-offline-bundle (версия >= 6) и переподключите его выход. "
        f"Сейчас в бандле: {[p.name for p in WB.rglob('*')][:20] if WB else 'бандл не подключён'}")
    with zipfile.ZipFile(src_zip) as z:
        z.extractall(hf_dir)
    print("распаковано из бандла:", sum(1 for _ in hf_dir.rglob("*.jpg")), "кадров")

ann_path = next(hf_dir.rglob("_annotations.coco.json"), None)
assert ann_path, f"нет _annotations.coco.json в {hf_dir}"
hf = json.load(open(ann_path))

# Имена классов берём из самого файла, а не из константы: Roboflow нередко
# добавляет нулевую супер-категорию, и сдвиг на единицу испортил бы все метки.
hf_cat = {c["id"]: c["name"] for c in hf["categories"]}
print("классы HF:", hf_cat)

by_img = defaultdict(list)
for a in hf["annotations"]:
    by_img[a["image_id"]].append(a)

img_root = ann_path.parent
n_skip = 0
for im in hf["images"]:
    fp = img_root / im["file_name"]
    if not fp.exists():
        n_skip += 1; continue
    boxes = [a["bbox"] for a in by_img[im["id"]]]            # COCO: уже xywh
    names = [hf_cat.get(a["category_id"], "") for a in by_img[im["id"]]]
    add_sample(Image.open(fp), boxes, names, HF_MAP, "A", Path(im["file_name"]).stem)
if n_skip:
    print("пропущено кадров без файла:", n_skip)
print(f"сплит A: {len(SPLIT_IDS['A'])} кадров, "
      f"{sum(1 for a in GT_ALL['annotations'] if a['image_id'] in SPLIT_IDS['A'])} аннотаций")

# %% [markdown]
# ## Сплит B: Kaggle valid, первая половина по имени
#
# «Строгая половина» = ровно `len // 2` первых имён после сортировки. Берём
# именно первую половину — это уточнено с постановщиком задачи.

# %%
KG = find_dir(IN, "construction-equipment")
assert KG, f"датасет не подключён. В /kaggle/input: {[d.name for d in IN.iterdir()]}"
val_img = next((p for p in KG.rglob("valid/images") if p.is_dir()), None)
val_lab = next((p for p in KG.rglob("valid/labels") if p.is_dir()), None)
assert val_img and val_lab, f"не найден valid-сплит в {KG}"

names_all = sorted(p.name for p in val_img.iterdir()
                   if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
half = names_all[: len(names_all) // 2]        # СТРОГО первая половина
print(f"valid всего: {len(names_all)} -> берём первые {len(half)} "
      f"({half[0]} ... {half[-1]})")

for nm in half:
    ip = val_img / nm
    im = Image.open(ip); W, H = im.size
    lp = val_lab / (Path(nm).stem + ".txt")
    boxes, cls = [], []
    if lp.exists():
        for ln in lp.read_text().splitlines():
            p = ln.split()
            if len(p) < 5: continue
            c, cx, cy, bw, bh = int(float(p[0])), *map(float, p[1:5])
            boxes.append([(cx-bw/2)*W, (cy-bh/2)*H, bw*W, bh*H])
            cls.append(KG_NAMES[c] if c < len(KG_NAMES) else str(c))
    add_sample(im, boxes, cls, KG_MAP, "B", Path(nm).stem)

print(f"сплит B: {len(SPLIT_IDS['B'])} кадров, "
      f"{sum(1 for a in GT_ALL['annotations'] if a['image_id'] in SPLIT_IDS['B'])} аннотаций")
print(f"всего в оценке: {len(GT_ALL['images'])} кадров, {len(GT_ALL['annotations'])} аннотаций")

# %% [markdown]
# ## Оценка
#
# Предсказания считаются **один раз на модель** по объединению кадров, а потом
# нарезаются по сплитам. Прогонять модель трижды (A, B, A+B) было бы втрое
# дороже и дало бы ровно те же числа.

# %%
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
import contextlib, io as _io

def gt_subset(ids, agnostic):
    cats = ([{"id": 1, "name": "object"}] if agnostic else GT_ALL["categories"])
    anns = []
    for a in GT_ALL["annotations"]:
        if a["image_id"] not in ids: continue
        b = dict(a); b["category_id"] = 1 if agnostic else a["category_id"]
        anns.append(b)
    return {"images": [i for i in GT_ALL["images"] if i["id"] in ids],
            "annotations": anns, "categories": cats}

def coco_eval(gt_dict, dets):
    if not gt_dict["annotations"] or not dets:
        return {"mAP50-95": 0.0, "mAP50": 0.0, "AP_small": 0.0, "AR100": 0.0}
    gp, dp = WORK/"_gt.json", WORK/"_dt.json"
    json.dump(gt_dict, open(gp, "w")); json.dump(dets, open(dp, "w"))
    with contextlib.redirect_stdout(_io.StringIO()):
        gt = COCO(str(gp)); dt = gt.loadRes(str(dp))
        e = COCOeval(gt, dt, "bbox"); e.evaluate(); e.accumulate(); e.summarize()
    s = e.stats
    return {"mAP50-95": round(float(s[0]), 4), "mAP50": round(float(s[1]), 4),
            "AP_small": round(float(s[3]), 4), "AR100": round(float(s[8]), 4)}

IMGSZ, CONF, BATCH = 640, 0.001, 32   # conf низкий: COCO mAP считается по всей PR-кривой

def predict_all(model):
    """Один прогон по всем кадрам. Возвращает два набора детекций:
    class-agnostic (все боксы, category_id=1) и COCO-mapped."""
    id_by_name = {im["file_name"]: im["id"] for im in GT_ALL["images"]}
    files = [EVAL / im["file_name"] for im in GT_ALL["images"]]
    ag, mp = [], []
    for i in range(0, len(files), BATCH):
        chunk = files[i:i+BATCH]
        for f, r in zip(chunk, model.predict(chunk, imgsz=IMGSZ, conf=CONF,
                                             device=0, verbose=False, max_det=300)):
            img_id = id_by_name[f.name]
            for b in r.boxes:
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                box = [x1, y1, x2-x1, y2-y1]; sc = float(b.conf)
                ag.append({"image_id": img_id, "category_id": 1, "bbox": box, "score": sc})
                tgt = COCO_MAP.get(r.names[int(b.cls)])
                if tgt:
                    mp.append({"image_id": img_id, "category_id": CID[tgt]+1,
                               "bbox": box, "score": sc})
    return ag, mp

# %% [markdown]
# ## 25 моделей = 5 поколений × 5 размеров
#
# Ровно 25 без произвольного отбора: YOLOv8, YOLOv10, YOLO11, YOLOv12, YOLO26,
# каждое в размерах n/s/m/l/x. YOLOv9 не включён намеренно — у него другие
# буквы размеров (t/s/m/c/e), и симметрия таблицы сломалась бы.

# %%
FAMILIES = ["yolov8", "yolov10", "yolo11", "yolo12", "yolo26"]
SIZES = ["n", "s", "m", "l", "x"]
ZOO = [(f"{fam}{sz}", f"{fam}{sz}.pt") for fam in FAMILIES for sz in SIZES]
assert len(ZOO) == 25, len(ZOO)

SPLITS = {"A_hf_test": SPLIT_IDS["A"],
          "B_kaggle_valid_half": SPLIT_IDS["B"],
          "AB_joint": SPLIT_IDS["A"] | SPLIT_IDS["B"]}

rows = []
for name, wfile in ZOO:
    src = WEIGHTS / wfile
    t0 = time.time()
    try:
        m = YOLO(str(src) if src.exists() else wfile)   # нет локально -> скачает
        ag, mp = predict_all(m)
    except Exception as e:
        print(f"! {name}: {type(e).__name__}: {e}")
        continue
    row = {"model": name, "sec": round(time.time()-t0, 1)}
    for sname, ids in SPLITS.items():
        a = coco_eval(gt_subset(ids, True),  [d for d in ag if d["image_id"] in ids])
        c = coco_eval(gt_subset(ids, False), [d for d in mp if d["image_id"] in ids])
        row[f"{sname}__agnostic_mAP50-95"] = a["mAP50-95"]
        row[f"{sname}__agnostic_mAP50"]    = a["mAP50"]
        row[f"{sname}__cocomap_mAP50-95"]  = c["mAP50-95"]
    rows.append(row)
    print(f"{name:10s} "
          + "  ".join(f"{s.split('_')[0]}: ag={row[f'{s}__agnostic_mAP50-95']:.3f} "
                      f"map={row[f'{s}__cocomap_mAP50-95']:.3f}" for s in SPLITS)
          + f"   [{row['sec']}s]")
    del m; torch.cuda.empty_cache()

# %% [markdown]
# ## Итоговая таблица 25×3

# %%
import pandas as pd
df = pd.DataFrame(rows)
df.to_csv(WORK / "zeroshot_results.csv", index=False)

for metric, title in [("agnostic_mAP50-95", "class-agnostic mAP@50-95"),
                      ("agnostic_mAP50",    "class-agnostic mAP@50"),
                      ("cocomap_mAP50-95",  "COCO-mapped mAP@50-95")]:
    cols = {s: f"{s}__{metric}" for s in SPLITS}
    t = df[["model"] + list(cols.values())].copy()
    t.columns = ["model", "A (HF test)", "B (Kaggle valid ½)", "A+B"]
    print(f"\n=== {title} ===")
    print(t.to_string(index=False))

print(f"\nсохранено: {WORK/'zeroshot_results.csv'}  ({len(df)} строк)")
