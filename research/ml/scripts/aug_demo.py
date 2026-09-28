"""Визуальная витрина аугментаций — по две вариации на каждую доменную группу."""
import sys, numpy as np
sys.path.insert(0, "ml/scripts")
import augment
from PIL import Image, ImageDraw, ImageFont

SRC = "data/raw/screenshots/Screenshot_47.png"
OUT = sys.argv[1] if len(sys.argv) > 1 else "ml/runs/augs.jpg"

img = np.array(Image.open(SRC).convert("RGB").resize((640, 426)))
patches = []
for f in ("Screenshot_3.png", "Screenshot_20.png", "Screenshot_75.png", "Screenshot_88.png"):
    a = np.array(Image.open(f"data/raw/screenshots/{f}").convert("RGB"))
    H, W = a.shape[:2]
    patches += [a[int(H*.72):, :W//3], a[:H//5, W//2:], a[H//3:H//2, :W//4]]

np.random.seed(11)
cells = [("оригинал", img)]
for name, t in [("время суток", augment.time_of_day(1.0)),
                ("погода", augment.weather(1.0)),
                ("сезон", augment.season(1.0)),
                ("оптика камеры", augment.camera(1.0)),
                ("ракурс и масштаб", augment.geometry(1.0)),
                ("перекрытие площадки", augment.occlusion(patches, 1.0))]:
    for k in range(2):
        r = t(image=img, bboxes=[], class_labels=[]) if hasattr(t, "bbox_params") else t(image=img)
        cells.append((name if k == 0 else "", r["image"]))
cells.append(("всё вместе", augment.build(patches, "heavy")(image=img, bboxes=[], class_labels=[])["image"]))

cols, tw, th, pad, lab = 4, 380, 253, 6, 22
rows = (len(cells) + cols - 1) // cols
canvas = Image.new("RGB", (cols*(tw+pad)+pad, rows*(th+lab+pad)+pad), (18, 18, 20))
d = ImageDraw.Draw(canvas)
try: font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
except Exception: font = ImageFont.load_default()
for i, (name, arr) in enumerate(cells):
    x = pad + (i % cols)*(tw+pad); y = pad + (i//cols)*(th+lab+pad)
    canvas.paste(Image.fromarray(np.asarray(arr, dtype=np.uint8)).resize((tw, th)), (x, y+lab))
    if name: d.text((x+2, y+2), name, fill=(235, 235, 240), font=font)
canvas.save(OUT, quality=90)
print("saved", OUT, canvas.size)
