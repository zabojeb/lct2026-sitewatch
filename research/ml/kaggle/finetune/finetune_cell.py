# ═════════════════════════════════════════════════════════════════════════════
#  Дообучение YOLO на общих 20% train  →  оценка на A / B / A+B
#
#  Kaggle, RTX PRO 6000.  Перед запуском:
#    1. Settings → Internet: On   (нужен для HF-датасета и весов YOLO)
#    2. Add Input → датасет  xyzyxzzxy/construction-equipment
#
#  Train:  20% train HF (neogpx/constructionxc7c) + 20% train Kaggle — ОДИН и тот же
#          набор для всех моделей (детерминированный отбор, списки файлов сохраняются)
#  Val*:   20% valid HF + 20% ВТОРОЙ половины valid Kaggle — только для кривых обучения
#          и выбора best.pt. С оценочными сплитами не пересекается.
#  Оценка: A  = HF test (весь)
#          B  = Kaggle valid, отсортированный по имени, строго первая половина
#          A+B = объединение
#  Выход (/kaggle/working): finetune_results.csv, *.png с кривыми и табло,
#          curves/<модель>.csv, splits/*.txt со списками отобранных файлов
# ═════════════════════════════════════════════════════════════════════════════

# ─── КОНФИГ ──────────────────────────────────────────────────────────────────
# 11 целевых классов — по таблице коллеги, в её порядке (индекс = id класса).
# Первые восемь — из ТЗ, последние три добавлены, потому что встречаются на кадрах.
TARGET_CLASSES = ["dump_truck",         #  1 самосвал
                  "excavator",          #  2 экскаватор
                  "roller",             #  3 каток
                  "crane_manipulator",  #  4 кран-манипулятор
                  "concrete_mixer",     #  5 бетоносмеситель
                  "bulldozer",          #  6 бульдозер
                  "truck",              #  7 грузовик
                  "mobile_crane",       #  8 автокран
                  "tower_crane",        #  9 башенный кран
                  "drilling_rig",       # 10 буровая
                  "concrete_pump"]      # 11 бетононасос
TARGET_RU = ["самосвал", "экскаватор", "каток", "кран-манипулятор", "бетоносмеситель",
             "бульдозер", "грузовик", "автокран", "башенный кран", "буровая", "бетононасос"]

# HF neogpx/constructionxc7c — 8 классов, имена берутся из _annotations.coco.json.
# None = класса нет среди 11: аннотация выбрасывается, объект становится фоном.
HF_TO_TARGET = {"dump truck": "dump_truck", "excavator": "excavator", "roller": "roller",
                "mixer truck": "concrete_mixer", "bulldozer": "bulldozer",
                "mobile crane": "mobile_crane",
                "grader": None, "loader": None}

# Kaggle construction-equipment — 17 классов. data.yaml в датасете нет; порядок
# индексов сверен с тем же набором в Roboflow-переэкспорте (heavy-equipment):
# 29 из 29 боксов совпали, 9 индексов из 17 подтверждены, расхождений нет.
KG_NAMES = ["Dump truck", "Excavator", "Motor grader", "Roller", "Crane manipulator",
            "Gazelle", "Forklift Standart", "Bucket loader Big", "Mixer", "Tanker",
            "Bulldozer", "Cleaning equipment", "Truck", "Trailer", "Forklift Giraffe",
            "Bucket loader Standart", "Autocran"]
KG_TO_TARGET = {"Dump truck": "dump_truck", "Excavator": "excavator", "Roller": "roller",
                "Crane manipulator": "crane_manipulator", "Mixer": "concrete_mixer",
                "Bulldozer": "bulldozer", "Autocran": "mobile_crane",
                "Truck": "truck",
                # Gazelle в этой разметке — любой фургон/бортовой (проверено: так помечен
                # и контейнеровоз), Tanker — автоцистерна, Trailer — прицеп. Все три
                # считаю грузовиком. Если по таблице коллеги это не так — поставьте None.
                "Gazelle": "truck", "Tanker": "truck", "Trailer": "truck",
                "Motor grader": None, "Bucket loader Big": None, "Bucket loader Standart": None,
                "Forklift Standart": None, "Forklift Giraffe": None, "Cleaning equipment": None}

FAMILIES = ["yolov8", "yolov10", "yolo11", "yolo12", "yolo26"]
SIZES = ["n", "s", "m", "l", "x"]

TRAIN_FRAC, VAL_FRAC, SEED = 0.20, 0.20, 0
EPOCHS, IMGSZ, BATCH = 40, 640, 64      # одинаковые для всех моделей — иначе сравнение нечестное
DEVICE = 0
TIME_BUDGET_H = 11.0                    # новые модели не стартуют, если не успеют до лимита сессии
# ─────────────────────────────────────────────────────────────────────────────

import os, sys, json, time, shutil, random, socket, subprocess, zipfile, gc, urllib.request
from pathlib import Path
from collections import Counter, defaultdict
from importlib.metadata import version, PackageNotFoundError

T0 = time.time()
assert len(TARGET_CLASSES) == 11, f"ожидалось 11 классов, задано {len(TARGET_CLASSES)}"
assert len(TARGET_RU) == len(TARGET_CLASSES), "TARGET_RU и TARGET_CLASSES разной длины"
for _m in (HF_TO_TARGET, KG_TO_TARGET):
    _bad = {v for v in _m.values() if v is not None} - set(TARGET_CLASSES)
    assert not _bad, f"в маппинге классы вне TARGET_CLASSES: {_bad}"
TID = {c: i for i, c in enumerate(TARGET_CLASSES)}

# Интернет проверяем сразу: без него упадём не здесь, а через 20 минут на загрузке.
try:
    socket.create_connection(("huggingface.co", 443), timeout=6).close()
except OSError:
    raise SystemExit("Нет интернета. Settings → Internet: On, затем перезапустите ячейку.")

# Версию смотрим через metadata, НЕ импортом: если сначала импортировать старый
# ultralytics, а потом обновить, в памяти останется старый модуль, и YOLO26 не найдётся.
try:
    _uv = tuple(int(x) for x in version("ultralytics").split(".")[:2])
except PackageNotFoundError:
    _uv = (0, 0)
if _uv < (8, 4):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "ultralytics>=8.4"], check=True)

import numpy as np, pandas as pd, yaml, torch
import matplotlib.pyplot as plt
from ultralytics import YOLO, settings
import ultralytics
print(f"ultralytics {ultralytics.__version__} | torch {torch.__version__} | "
      f"{torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")

WORK = Path("/kaggle/working")
TMP = Path("/kaggle/temp") if Path("/kaggle/temp").exists() else Path("/tmp/lct_ft")
DATA, RUNS = TMP / "data", TMP / "runs"
for d in (WORK, DATA, RUNS, WORK / "curves", WORK / "splits"):
    d.mkdir(parents=True, exist_ok=True)
# Данные и веса — во временный каталог: /kaggle/working уходит в выход ядра, и
# тысячи кадров там делают выгрузку результатов неподъёмной.
settings.update({"runs_dir": str(RUNS), "datasets_dir": str(DATA), "sync": False})

def pick(names, frac, seed=SEED):
    """Детерминированная доля: сортировка по имени → перемешивание с фиксированным seed.
    Не «первые 20% по имени»: имена кодируют камеру и время, и срез по алфавиту
    взял бы только часть камер."""
    names = sorted(names)
    idx = list(range(len(names)))
    random.Random(seed).shuffle(idx)
    return sorted(names[i] for i in idx[: round(len(names) * frac)])

def clip01(v):
    return min(max(v, 0.0), 1.0)

SPLITS = {s: DATA / s for s in ("train", "val", "evalA", "evalB")}
for s in SPLITS.values():
    shutil.rmtree(s, ignore_errors=True)
    (s / "images").mkdir(parents=True); (s / "labels").mkdir(parents=True)
STATS = {s: Counter() for s in SPLITS}
DROPPED = Counter()

# ─── 1. HF neogpx/constructionxc7c ───────────────────────────────────────────
HF_BASE = "https://huggingface.co/datasets/neogpx/constructionxc7c/resolve/main/data"

def hf_zip(split):
    """Прямая загрузка архива сплита. Без библиотеки datasets: этот репозиторий
    отдаёт данные через loading-скрипт, который её свежие версии не поддерживают.
    Качаем в .part и переименовываем только при совпадении размера, чтобы
    оборванная загрузка не выдала себя за готовый архив при повторном запуске."""
    dst = TMP / "hf" / f"{split}.zip"
    dst.parent.mkdir(parents=True, exist_ok=True)
    url = f"{HF_BASE}/{split}.zip"
    want = int(urllib.request.urlopen(urllib.request.Request(url, method="HEAD"),
                                      timeout=60).headers["Content-Length"])
    if dst.exists() and dst.stat().st_size == want:
        return dst
    part = dst.with_suffix(".part")
    for attempt in range(1, 4):
        try:
            urllib.request.urlretrieve(url, part)
            if part.stat().st_size == want:
                part.rename(dst)
                return dst
            print(f"   {split}.zip: размер не сошёлся, попытка {attempt}")
        except Exception as e:
            print(f"   {split}.zip: {type(e).__name__}, попытка {attempt}")
    raise SystemExit(f"не удалось скачать {url}")

def add_hf(split_zip, frac, dst, tag):
    """COCO из zip → YOLO. Извлекаем только отобранные кадры, а не весь архив."""
    z = zipfile.ZipFile(split_zip)
    ann = json.load(z.open(next(n for n in z.namelist() if n.endswith("_annotations.coco.json"))))
    cat = {c["id"]: c["name"] for c in ann["categories"]}      # имена — из файла, не по индексу
    by_img = defaultdict(list)
    for a in ann["annotations"]:
        by_img[a["image_id"]].append(a)
    imgs = {im["file_name"]: im for im in ann["images"]}
    chosen = pick(imgs, frac) if frac < 1 else sorted(imgs)
    for fn in chosen:
        im = imgs[fn]; W, H = im["width"], im["height"]
        out = f"hf_{Path(fn).stem}"
        with z.open(fn) as src, open(dst / "images" / f"{out}.jpg", "wb") as f:
            shutil.copyfileobj(src, f)
        lines = []
        for a in by_img[im["id"]]:
            tgt = HF_TO_TARGET.get(cat.get(a["category_id"], ""))
            if tgt is None:
                DROPPED[f"HF:{cat.get(a['category_id'])}"] += 1; continue
            x, y, w, h = a["bbox"]
            if w <= 0 or h <= 0:
                continue
            lines.append(f"{TID[tgt]} {clip01((x + w/2)/W):.6f} {clip01((y + h/2)/H):.6f} "
                         f"{clip01(w/W):.6f} {clip01(h/H):.6f}")
            STATS[dst.name][tgt] += 1
        (dst / "labels" / f"{out}.txt").write_text("\n".join(lines))
    (WORK / "splits" / f"{tag}.txt").write_text("\n".join(chosen))
    return len(chosen)

print("\nзагрузка HF (train 1.6 ГБ, valid, test)…")
n_hf_tr = add_hf(hf_zip("train"), TRAIN_FRAC, SPLITS["train"], "hf_train_20pct")
n_hf_va = add_hf(hf_zip("valid"), VAL_FRAC, SPLITS["val"], "hf_valid_20pct")
n_hf_te = add_hf(hf_zip("test"), 1.0, SPLITS["evalA"], "hf_test_all")

# ─── 2. Kaggle xyzyxzzxy/construction-equipment ──────────────────────────────
def find_kg():
    for d in Path("/kaggle/input").rglob("construction-equipment"):
        if (d / "train" / "images").is_dir():
            return d
    for d in Path("/kaggle/input").rglob("valid"):          # другое имя папки монтирования
        if (d / "images").is_dir() and (d.parent / "train" / "images").is_dir():
            return d.parent
    try:
        import kagglehub
        return Path(kagglehub.dataset_download("xyzyxzzxy/construction-equipment"))
    except Exception as e:
        raise SystemExit(f"Нет датасета construction-equipment: Add Input → xyzyxzzxy/construction-equipment ({e})")

KG = find_kg()
print("Kaggle-датасет:", KG)

def add_kg(split, names, dst, tag):
    src_i, src_l = KG / split / "images", KG / split / "labels"
    for fn in names:
        out = f"kg_{Path(fn).stem}"
        dst_img = dst / "images" / f"{out}{Path(fn).suffix}"
        try:
            dst_img.symlink_to(src_i / fn)      # /kaggle/input только для чтения — копия не нужна
        except OSError:
            shutil.copy2(src_i / fn, dst_img)
        lines = []
        lp = src_l / f"{Path(fn).stem}.txt"
        for ln in (lp.read_text().splitlines() if lp.exists() else []):
            p = ln.split()
            if len(p) < 5:
                continue
            c = int(float(p[0]))
            name = KG_NAMES[c] if c < len(KG_NAMES) else f"#{c}"
            tgt = KG_TO_TARGET.get(name)
            if tgt is None:
                DROPPED[f"KG:{name}"] += 1; continue
            v = list(map(float, p[1:]))
            if len(v) > 4:                      # полигон вместо бокса — берём описывающий бокс
                xs, ys = v[0::2], v[1::2]
                v = [(min(xs)+max(xs))/2, (min(ys)+max(ys))/2, max(xs)-min(xs), max(ys)-min(ys)]
            lines.append(f"{TID[tgt]} " + " ".join(f"{clip01(t):.6f}" for t in v[:4]))
            STATS[dst.name][tgt] += 1
        (dst / "labels" / f"{out}.txt").write_text("\n".join(lines))
    (WORK / "splits" / f"{tag}.txt").write_text("\n".join(names))
    return len(names)

img_ext = {".jpg", ".jpeg", ".png"}
kg_train = [p.name for p in (KG / "train" / "images").iterdir() if p.suffix.lower() in img_ext]
kg_valid = sorted(p.name for p in (KG / "valid" / "images").iterdir() if p.suffix.lower() in img_ext)
half = len(kg_valid) // 2
n_kg_tr = add_kg("train", pick(kg_train, TRAIN_FRAC), SPLITS["train"], "kg_train_20pct")
n_kg_ev = add_kg("valid", kg_valid[:half], SPLITS["evalB"], "kg_valid_first_half")   # СТРОГО первая половина
n_kg_va = add_kg("valid", pick(kg_valid[half:], VAL_FRAC), SPLITS["val"], "kg_valid_2nd_half_20pct")

print(f"\ntrain: HF {n_hf_tr} + KG {n_kg_tr} = {n_hf_tr + n_kg_tr} кадров")
print(f"val*:  HF {n_hf_va} + KG {n_kg_va}   (только кривые и выбор best.pt)")
print(f"A:     HF test {n_hf_te}")
print(f"B:     KG valid {n_kg_ev} из {len(kg_valid)}  ({kg_valid[0]} … {kg_valid[half-1]})")
stat = pd.DataFrame(STATS).reindex(TARGET_CLASSES).fillna(0).astype(int)
stat.columns = ["train", "val*", "A", "B"]
stat.index = [f"{i+1:>2} {ru}" for i, ru in enumerate(TARGET_RU)]
print("\nаннотаций по классам:\n", stat.to_string())
print("выброшено (вне 11 классов):", dict(DROPPED) or "ничего")
empty = [TARGET_RU[i] for i, c in enumerate(TARGET_CLASSES) if STATS["train"][c] == 0]
if empty:
    print(f"\n⚠  В train НЕТ НИ ОДНОГО примера: {', '.join(empty)}.\n"
          f"   Модель их не выучит. В mAP они не входят: в сплитах A/B для них тоже нет разметки,\n"
          f"   а класс без разметки из усреднения исключается. То есть mAP фактически считается\n"
          f"   по классам, у которых есть разметка, — их список для каждого сплита виден выше.")

def write_yaml(name, train_dirs, val_dirs):
    p = DATA / f"{name}.yaml"
    yaml.safe_dump({"train": [str(d / "images") for d in train_dirs],
                    "val": [str(d / "images") for d in val_dirs],
                    "names": {i: n for i, n in enumerate(TARGET_CLASSES)}}, open(p, "w"))
    return str(p)

Y_TRAIN = write_yaml("train", [SPLITS["train"]], [SPLITS["val"]])
EVAL = {"A": write_yaml("evalA", [SPLITS["evalA"]], [SPLITS["evalA"]]),
        "B": write_yaml("evalB", [SPLITS["evalB"]], [SPLITS["evalB"]]),
        "A+B": write_yaml("evalAB", [SPLITS["evalA"]], [SPLITS["evalA"], SPLITS["evalB"]])}

# ─── 3. Обучение и оценка ────────────────────────────────────────────────────
RES_CSV = WORK / "finetune_results.csv"
# Возобновление безопасно только при том же конфиге. Иначе повторный запуск после
# смены классов тихо подхватил бы результаты старой таксономии и пропустил модели.
import hashlib
CFG = [TARGET_CLASSES, HF_TO_TARGET, KG_TO_TARGET, KG_NAMES, TRAIN_FRAC, VAL_FRAC, SEED,
       EPOCHS, IMGSZ, BATCH]
SIG = hashlib.md5(json.dumps(CFG, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
SIG_FILE = WORK / "finetune_config.json"
old_sig = json.load(open(SIG_FILE)).get("sig") if SIG_FILE.exists() else None
if RES_CSV.exists() and old_sig != SIG:
    RES_CSV.rename(WORK / f"finetune_results.stale_{old_sig or 'prev'}.csv")
    shutil.rmtree(WORK / "curves", ignore_errors=True); (WORK / "curves").mkdir()
    print("конфиг изменился — прежние результаты отложены в *.stale_*.csv, считаю заново")
json.dump({"sig": SIG, "classes": TARGET_CLASSES, "classes_ru": TARGET_RU,
           "hf_map": HF_TO_TARGET, "kg_map": KG_TO_TARGET, "train_frac": TRAIN_FRAC,
           "epochs": EPOCHS, "imgsz": IMGSZ, "batch": BATCH, "seed": SEED},
          open(SIG_FILE, "w"), ensure_ascii=False, indent=1)
rows = pd.read_csv(RES_CSV).to_dict("records") if RES_CSV.exists() else []
done = {r["model"] for r in rows}
SIZE_COST = {"n": 1.0, "s": 1.3, "m": 2.0, "l": 2.8, "x": 4.0}

def est_min(size):
    """Прогноз длительности по уже обученным моделям, нормированным на «цену» размера."""
    got = [r["train_min"] / SIZE_COST[r["size"]] for r in rows if r.get("train_min")]
    return float(np.median(got)) * SIZE_COST[size] if got else 0.0

def train_one(wfile, name):
    for bs in (BATCH, BATCH // 2, BATCH // 4):   # запас на случай OOM у attention-моделей
        try:
            YOLO(wfile).train(data=Y_TRAIN, epochs=EPOCHS, imgsz=IMGSZ, batch=bs, device=DEVICE,
                              project=str(RUNS), name=name, exist_ok=True, seed=SEED,
                              patience=EPOCHS * 10, cache="ram", plots=False, verbose=False)
            return bs
        except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
            if "out of memory" not in str(e).lower():
                raise
            print(f"   OOM при batch={bs}, пробую {bs // 2}")
            gc.collect(); torch.cuda.empty_cache()
    raise RuntimeError("OOM даже при batch/4")

def final_losses(csv_path):
    d = pd.read_csv(csv_path); d.columns = [c.strip() for c in d.columns]
    last = d.iloc[-1]
    tr = sum(last[c] for c in d.columns if c.startswith("train/") and "loss" in c)
    va = sum(last[c] for c in d.columns if c.startswith("val/") and "loss" in c)
    return float(tr), float(va)

# Порядок «по размеру, потом по поколению»: если время кончится, останется
# полное сравнение ВСЕХ поколений на меньших размерах, а не одно поколение целиком.
ZOO = [(f"{f}{s}", f, s) for s in SIZES for f in FAMILIES]
print(f"\nмоделей: {len(ZOO)}, уже готово: {len(done)} | {EPOCHS} эпох, imgsz {IMGSZ}, batch {BATCH}")

for name, fam, size in ZOO:
    if name in done:
        continue
    el = (time.time() - T0) / 60
    if el + est_min(size) > TIME_BUDGET_H * 60:
        print(f"⏹  {name}: не успеет до лимита ({el:.0f} + ~{est_min(size):.0f} мин) — пропуск")
        continue
    t1 = time.time()
    try:
        bs = train_one(f"{name}.pt", name)
    except Exception as e:
        print(f"!  {name}: {type(e).__name__}: {str(e)[:200]}"); continue
    tmin = (time.time() - t1) / 60
    run = RUNS / name
    shutil.copy2(run / "results.csv", WORK / "curves" / f"{name}.csv")
    best = run / "weights" / ("best.pt" if (run / "weights" / "best.pt").exists() else "last.pt")
    m = YOLO(str(best))
    row = {"model": name, "family": fam, "size": size, "batch": bs, "train_min": round(tmin, 1)}
    for split, y in EVAL.items():
        r = m.val(data=y, split="val", imgsz=IMGSZ, batch=BATCH, device=DEVICE, plots=False,
                  verbose=False, project=str(TMP / "val"), name=f"{name}_{split}", exist_ok=True)
        row[f"mAP50-95 {split}"] = round(float(r.box.map), 4)
        row[f"mAP50 {split}"] = round(float(r.box.map50), 4)
    row["train_loss_final"], row["val_loss_final"] = final_losses(run / "results.csv")
    rows.append(row)
    pd.DataFrame(rows).to_csv(RES_CSV, index=False)            # сохраняем после КАЖДОЙ модели
    print(f"✓  {name:9s} {tmin:5.1f} мин | mAP50-95  A={row['mAP50-95 A']:.3f}  "
          f"B={row['mAP50-95 B']:.3f}  A+B={row['mAP50-95 A+B']:.3f}")
    if len(rows) == 1:
        left = sum(est_min(z[2]) for z in ZOO if z[0] not in {r["model"] for r in rows})
        print(f"   прогноз на оставшиеся модели: ~{left / 60:.1f} ч "
              f"(бюджет {TIME_BUDGET_H} ч — что не влезет, будет пропущено)")
    del m; gc.collect(); torch.cuda.empty_cache()

# ─── 4. Табло ────────────────────────────────────────────────────────────────
res = pd.DataFrame(rows)
if res.empty:
    raise SystemExit("ни одна модель не обучилась — смотрите ошибки выше")
order = [n for n, _, _ in sorted(ZOO, key=lambda z: (FAMILIES.index(z[1]), SIZES.index(z[2])))]
res = res.set_index("model").reindex([n for n in order if n in set(res["model"])]).reset_index()
for metric in ("mAP50-95", "mAP50"):
    t = res[["model"] + [f"{metric} {s}" for s in EVAL]]
    t.columns = ["model", "A: HF test", "B: Kaggle valid ½", "A+B"]
    print(f"\n══ {metric} ══\n" + t.to_string(index=False))
print("\n══ лосс на последней эпохе (сумма компонент) ══\n"
      + res[["model", "train_loss_final", "val_loss_final", "train_min"]].to_string(index=False))

# ─── 5. Графики ──────────────────────────────────────────────────────────────
# Цвета: размер модели n→x — порядковая величина → одна синяя шкала от светлого
# к тёмному; поколения — категории → фиксированные оттенки. Обе палитры прошли
# проверку на различимость при дальтонизме.
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
SIZE_COL = dict(zip(SIZES, ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"]))
FAM_COL = dict(zip(FAMILIES, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]))
from matplotlib.ticker import MaxNLocator
EPOCH_TICKS = lambda a: a.xaxis.set_major_locator(MaxNLocator(integer=True))   # эпоха — целое число
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
                     "axes.edgecolor": GRID, "axes.labelcolor": INK2, "text.color": INK,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.8, "axes.spines.top": False,
                     "axes.spines.right": False, "font.size": 10, "axes.titlesize": 11,
                     "legend.frameon": False,
                     "axes.formatter.useoffset": False})   # без «+1.232» над осью — только полные значения

def curves(name):
    p = WORK / "curves" / f"{name}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p); d.columns = [c.strip() for c in d.columns]
    return d

def comp_order(cols):
    """Компоненты лосса у поколений разные: box/cls/dfl у v8–v12, у YOLO26 без DFL."""
    comps = sorted({c.split("/")[1] for c in cols if "/" in c and c.endswith("_loss")},
                   key=lambda c: (["box_loss", "cls_loss", "dfl_loss", "l1_loss"] + [c]).index(c))
    return comps

for fam in FAMILIES:
    cv = {s: curves(f"{fam}{s}") for s in SIZES}
    cv = {s: d for s, d in cv.items() if d is not None}
    if not cv:
        continue
    comps = comp_order(set().union(*[set(d.columns) for d in cv.values()]))
    ncol = len(comps) + 1
    fig, ax = plt.subplots(2, ncol, figsize=(3.4 * ncol, 6.2), squeeze=False)
    for r, split in enumerate(("train", "val")):
        for c, comp in enumerate(comps):
            a = ax[r][c]
            for s, d in cv.items():
                col = f"{split}/{comp}"
                if col in d:
                    a.plot(d["epoch"], d[col], color=SIZE_COL[s], lw=1.8, label=f"{fam}{s}")
            a.set_title(f"{split} · {comp.replace('_loss', '')} loss", color=INK)
            a.set_xlabel("эпоха"); EPOCH_TICKS(a)
        metric = "metrics/mAP50-95(B)" if r == 0 else "metrics/mAP50(B)"
        a = ax[r][-1]
        for s, d in cv.items():
            if metric in d:
                a.plot(d["epoch"], d[metric], color=SIZE_COL[s], lw=1.8, label=f"{fam}{s}")
        a.set_title(f"val* · {metric.split('/')[1].replace('(B)', '')}", color=INK)
        a.set_xlabel("эпоха"); EPOCH_TICKS(a)
    h, l = ax[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.02))
    fig.suptitle(f"{fam}: лоссы и mAP по эпохам (val* — отложенная выборка, не A/B)",
                 color=INK, y=1.07, fontsize=12)
    fig.tight_layout()
    fig.savefig(WORK / f"curves_{fam}.png", dpi=130, bbox_inches="tight")
    plt.show()

# Поколения при равном размере — отвечает на «какое семейство лучше», а не «какой размер»
fig, ax = plt.subplots(1, len(SIZES), figsize=(3.6 * len(SIZES), 3.6), sharey=True, squeeze=False)
for i, s in enumerate(SIZES):
    a = ax[0][i]
    for fam in FAMILIES:
        d = curves(f"{fam}{s}")
        if d is not None and "metrics/mAP50-95(B)" in d:
            a.plot(d["epoch"], d["metrics/mAP50-95(B)"], color=FAM_COL[fam], lw=1.8, label=fam)
    a.set_title(f"размер {s}", color=INK); a.set_xlabel("эпоха"); EPOCH_TICKS(a)
ax[0][0].set_ylabel("val* mAP50-95")
h, l = ax[0][0].get_legend_handles_labels()
if l:
    fig.legend(h, l, loc="upper center", ncol=len(l), bbox_to_anchor=(0.5, 1.08))
fig.suptitle("Поколения YOLO при одинаковом размере", color=INK, y=1.16, fontsize=12)
fig.tight_layout(); fig.savefig(WORK / "curves_families_by_size.png", dpi=130, bbox_inches="tight")
plt.show()

# Табло: значения подписаны в каждой ячейке — это таблица, а не декоративная теплокарта
from matplotlib.colors import LinearSegmentedColormap
RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
cmap = LinearSegmentedColormap.from_list("seq", RAMP)
cols = [f"mAP50-95 {s}" for s in EVAL]
M = res[cols].to_numpy(dtype=float)
fig, a = plt.subplots(figsize=(6.4, 0.34 * len(res) + 1.4))
lo, hi = np.nanmin(M), np.nanmax(M)
# pcolormesh с рёбрами цвета фона даёт 2-px зазор между ячейками — соседние
# значения не сливаются в пятно
a.pcolormesh(M, cmap=cmap, vmin=lo, vmax=hi, edgecolors=SURF, linewidth=2)
a.invert_yaxis(); a.grid(False)
a.set_xticks(np.arange(len(cols)) + 0.5, ["A: HF test", "B: Kaggle valid ½", "A+B"])
a.set_yticks(np.arange(len(res)) + 0.5, res["model"])
a.xaxis.tick_top(); a.tick_params(length=0)
for (i, j), v in np.ndenumerate(M):
    r_, g_, b_, _ = cmap((v - lo) / max(hi - lo, 1e-9))
    lum = 0.2126 * r_ + 0.7152 * g_ + 0.0722 * b_      # цвет подписи — по яркости самой ячейки
    a.text(j + 0.5, i + 0.5, f"{v:.3f}", ha="center", va="center", fontsize=9,
           color="#ffffff" if lum < 0.5 else INK)
a.set_title("mAP@50-95 после дообучения", color=INK, pad=28)
for s in a.spines.values():
    s.set_visible(False)
fig.tight_layout(); fig.savefig(WORK / "table_map50-95.png", dpi=140, bbox_inches="tight")
plt.show()

print(f"\nготово за {(time.time() - T0) / 3600:.1f} ч. Файлы в /kaggle/working: "
      f"finetune_results.csv, curves_*.png, table_map50-95.png, curves/, splits/")
