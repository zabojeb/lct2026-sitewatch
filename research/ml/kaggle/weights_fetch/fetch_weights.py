# %% [markdown]
# # Пре-стейдж весов YOLO для офлайн-обучения
#
# На обучающем ядре интернета нет, а ultralytics по умолчанию тянет из сети
# веса, шрифт и текстовый энкодер для open-vocab. Это ядро скачивает всё
# заранее; его **выход подключается к обучающему ноутбуку как источник данных**
# (`kernel_sources`), поэтому промежуточная выгрузка на диск не нужна.
#
# Ядро должно запускаться **с интернетом и без GPU**.

# %%
import os, sys, json, hashlib, subprocess, urllib.request, urllib.error
from pathlib import Path

OUT = Path("/kaggle/working")
(OUT / "wheels").mkdir(parents=True, exist_ok=True)

# Релиз ассетов ultralytics. v8.4.0 — первый, где появился YOLO26.
ASSETS = "https://github.com/ultralytics/assets/releases/download/v8.4.0"
FONTS  = "https://github.com/ultralytics/assets/releases/download/v0.0.0"  # шрифт только тут

# Все 5 размеров каждого поколения: zero-shot таблица требует 25 строк
# (5 поколений x n/s/m/l/x). Раньше в бандле были только n/s/m, и на офлайн-ядре
# 10 моделей отваливались с ConnectionError — скачать там нечем.
WEIGHTS = [
    "yolov8n.pt","yolov8s.pt","yolov8m.pt","yolov8l.pt","yolov8x.pt",
    "yolov9t.pt","yolov9s.pt","yolov9m.pt",
    "yolov10n.pt","yolov10s.pt","yolov10m.pt","yolov10l.pt","yolov10x.pt",
    "yolo11n.pt","yolo11s.pt","yolo11m.pt","yolo11l.pt","yolo11x.pt",
    "yolo12n.pt","yolo12s.pt","yolo12m.pt","yolo12l.pt","yolo12x.pt",
    "yolo26n.pt","yolo26s.pt","yolo26m.pt","yolo26l.pt","yolo26x.pt",
    # контекст: легаси-базлайн и представитель DETR
    "yolov5su.pt","rtdetr-l.pt",
    # инициализация от Objects365 (365 классов, есть machinery vehicle и crane)
    "yolo26s-objv1-150.pt","yolo26x-objv1-150.pt",
    # open-vocab для честной колонки zero-shot
    "yolov8s-worldv2.pt","yolov8l-worldv2.pt",
    "yoloe-26s-seg.pt","yoloe-26l-seg.pt",
]
# yolo26n.pt нужен отдельно: без него check_amp() МОЛЧА пропускает проверку AMP
assert "yolo26n.pt" in WEIGHTS

# CLIP ViT-B/32 для YOLO-World. Это ОТДЕЛЬНАЯ зависимость от MobileCLIP:
# YOLOE-26 берёт mobileclip2_b.ts, а YOLO-World жёстко зовёт
# build_text_model("clip:ViT-B/32") -> clip.load(), который качает этот файл
# с CDN OpenAI. Путь важен: clip.load ищет его в download_root, а ultralytics
# передаёт туда WEIGHTS_DIR/"clip", поэтому кладём в подкаталог clip/.
CLIP_VITB32 = ("https://openaipublic.azureedge.net/clip/models/"
               "40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt")
(OUT / "clip").mkdir(parents=True, exist_ok=True)

EXTRA = [
    (f"{FONTS}/Arial.ttf", OUT / "Arial.ttf"),
    (CLIP_VITB32, OUT / "clip" / "ViT-B-32.pt"),
    # Текстовый энкодер YOLOE-26. Лежит в ассетах ultralytics, НЕ на CDN Apple:
    # Apple отдаёт mobileclip_*.pt, а ultralytics использует TorchScript-сборку.
    # mobileclip_blt.ts (600 МБ) нужен только для yoloe-11/v8 — не берём.
    (f"{ASSETS}/mobileclip2_b.ts", OUT / "mobileclip2_b.ts"),
]

def fetch(url: str, dst: Path, retries: int = 3) -> tuple[bool, str]:
    if dst.exists() and dst.stat().st_size > 1024:
        return True, f"уже есть ({dst.stat().st_size/1e6:.1f} МБ)"
    for a in range(retries):
        try:
            urllib.request.urlretrieve(url, dst)
            n = dst.stat().st_size
            if n < 1024:
                dst.unlink(missing_ok=True); raise ValueError(f"слишком мал: {n} Б")
            return True, f"{n/1e6:.1f} МБ"
        except Exception as e:
            if a == retries - 1:
                dst.unlink(missing_ok=True)
                return False, f"{type(e).__name__}: {e}"
    return False, "?"

# %%
report = {"ok": [], "failed": []}
total = 0
for name in WEIGHTS:
    ok, msg = fetch(f"{ASSETS}/{name}", OUT / name)
    (report["ok"] if ok else report["failed"]).append(f"{name}: {msg}")
    print(f"{'+' if ok else '!'} {name:26s} {msg}")
    if ok: total += (OUT / name).stat().st_size

for url, dst in EXTRA:
    ok, msg = fetch(url, dst)
    (report["ok"] if ok else report["failed"]).append(f"{dst.name}: {msg}")
    print(f"{'+' if ok else '!'} {dst.name:26s} {msg}")
    if ok: total += dst.stat().st_size

print(f"\nитого весов: {total/1e9:.2f} ГБ")

# %% [markdown]
# ## Данные для zero-shot оценки
#
# HF-датасет `neogpx/constructionxc7c` отдаёт данные через loading-скрипт,
# который свежие версии `datasets` не поддерживают, поэтому забираем
# `data/test.zip` напрямую.
#
# Зачем вообще класть данные в бандл весов: оценочное ядро привязано к
# соревнованию, а соревновательным ядрам Kaggle запрещает интернет. Скачать
# архив на месте там нельзя ни при каких настройках — только принести готовым.

# %%
HF_TEST = ("https://huggingface.co/datasets/neogpx/constructionxc7c/"
           "resolve/main/data/test.zip")
ok, msg = fetch(HF_TEST, OUT / "constructionxc7c_test.zip")
report["ok" if ok else "failed"].append(f"constructionxc7c_test.zip: {msg}")
print(f"{'+' if ok else '!'} constructionxc7c_test.zip   {msg}")

# Проверяем, что архив целый и внутри есть разметка, — иначе узнаем об этом
# уже на офлайн-ядре, где починить нельзя.
if ok:
    import zipfile as _zf
    with _zf.ZipFile(OUT / "constructionxc7c_test.zip") as z:
        names = z.namelist()
    anns = [n for n in names if n.endswith("_annotations.coco.json")]
    imgs = [n for n in names if n.lower().endswith((".jpg", ".jpeg", ".png"))]
    print(f"   внутри: {len(imgs)} кадров, аннотаций: {anns}")
    if not anns:
        report["failed"].append("в test.zip нет _annotations.coco.json")

# %% [markdown]
# ## Колёса пакетов
#
# `clip` ставится только из git, а на офлайн-ядре это невозможно. YOLOE
# использует его ТОЛЬКО ради токенизатора (`clip.clip.tokenize`), но без
# импорта падает — поэтому wheel нужен обязательно.
#
# `ultralytics` кладём на случай, если в образе Kaggle версия старше 8.4:
# тогда YOLO26 просто не существует.

# %%
def build_wheel(spec: str, out_dir: Path) -> bool:
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", spec,
                        "--no-deps", "-w", str(out_dir)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"! {spec}\n{r.stderr[-600:]}")
        return False
    return True

# ftfy и regex — зависимости clip. Ставим clip через --no-deps (иначе
# потянется torch на 900 МБ), поэтому их надо собрать отдельно, иначе
# `import clip` падает на офлайн-ядре с ModuleNotFoundError: ftfy.
for spec in ["ultralytics", "git+https://github.com/ultralytics/CLIP.git",
             "ftfy", "regex"]:
    ok = build_wheel(spec, OUT / "wheels")
    report["ok" if ok else "failed"].append(f"wheel {spec}")
    print(f"{'+' if ok else '!'} wheel {spec}")

for w in sorted((OUT / "wheels").glob("*.whl")):
    print(f"   {w.name}  {w.stat().st_size/1e6:.1f} МБ")

# %% [markdown]
# ## Проверка
#
# Файл может скачаться целиком и всё равно быть непригодным. Проверяем двумя
# уровнями:
#
# 1. **Целостность архива.** Чекпоинт torch — это zip с `data.pkl` внутри.
#    Проверка не требует распаковки объектов, поэтому работает независимо от
#    того, установлен ли ultralytics.
# 2. **Реальная загрузка.** Ставим ultralytics из только что собранного wheel'а
#    и грузим каждый файл через `YOLO()`. Это заодно проверяет сам wheel —
#    именно он поедет на офлайн-ядро.
#
# Наивная проверка через `torch.load(weights_only=False)` без установленного
# ultralytics даёт ModuleNotFoundError на исправных файлах: unpickle требует
# классов `ultralytics.nn.tasks.*`. Такая «проверка» ловит не битые веса,
# а собственное окружение.

# %%
import zipfile
bad = []
for p in sorted(list(OUT.rglob("*.pt")) + list(OUT.rglob("*.ts"))):
    if not zipfile.is_zipfile(p):
        bad.append(f"{p.name}: не zip — файл повреждён или это HTML-заглушка")
        continue
    with zipfile.ZipFile(p) as z:
        if not any(n.endswith(("data.pkl", "constants.pkl")) for n in z.namelist()):
            bad.append(f"{p.name}: внутри нет data.pkl")
print("уровень 1 (целостность архива):", "все файлы целы" if not bad else bad)

# %%
whls = sorted((OUT / "wheels").glob("ultralytics-*.whl"))
if whls:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--force-reinstall",
                    "--no-deps", str(whls[0])], check=False)

import importlib
try:
    import ultralytics; importlib.reload(ultralytics)
    from ultralytics import YOLO
    print("ultralytics", ultralytics.__version__, "(из собранного wheel)")
    for p in sorted(OUT.glob("*.pt")):   # только корень: в clip/ лежит не YOLO
        try:
            m = YOLO(str(p))
            nc = len(m.model.names) if hasattr(m.model, "names") else "?"
            print(f"  + {p.name:26s} классов: {nc}")
            del m
        except Exception as e:
            bad.append(f"{p.name}: {type(e).__name__}: {e}")
            print(f"  ! {p.name:26s} {type(e).__name__}")
except Exception as e:
    bad.append(f"ultralytics не импортируется: {type(e).__name__}: {e}")

import gc; gc.collect()
report["corrupt"] = bad
print("\nитог проверки:", "всё загружается" if not bad else f"ПРОБЛЕМЫ: {bad}")

manifest = {
    "assets_release": ASSETS.rsplit("/", 1)[-1],
    "weights": sorted(p.name for p in OUT.glob("*.pt")),
    "extras": sorted(p.name for p in OUT.rglob("*.ts")) + ["Arial.ttf", "clip/ViT-B-32.pt",
                                                          "constructionxc7c_test.zip"],
    "wheels": sorted(p.name for p in (OUT / "wheels").glob("*.whl")),
    "total_gb": round(sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()) / 1e9, 2),
    "report": report,
}
json.dump(manifest, open(OUT / "manifest.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in manifest.items() if k != "report"}, ensure_ascii=False, indent=1))
assert not report["failed"], f"не скачалось: {report['failed']}"
assert not bad, f"битые файлы: {bad}"
