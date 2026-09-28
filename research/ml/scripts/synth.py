"""Генерация синтетических кадров: фон площадки + вставленная техника.

Фон и передний план аугментируются РАЗДЕЛЬНО, и это принципиально:
  * фон (весь кадр) — погода, время суток, сезон, оптика камеры;
  * машина (только вставка) — размер, окраска, отражение, дымка по глубине.

Разделение даёт то, чего не даёт аугментация целого кадра: сдвиг фирменной
окраски отдельной машины (оранжевый Hitachi -> бирюзовый Kobelco) и полный
разброс масштабов техники при неизменном масштабе сцены.

Порядок операций выбран не случайно: сначала вставка, потом погода на весь
кадр. Если сделать наоборот, снег ляжет под машину, а не на неё, и композиция
развалится.

Синтетика идёт ТОЛЬКО в train. В val — никогда: иначе измеряем не качество
детектора, а качество собственного генератора.
"""
from __future__ import annotations

import argparse
import glob
import os
import random

import cv2
import numpy as np

import augment as aug_mod
from copypaste import CopyPasteComposer, CutoutBank, fit_size_vs_y
from preannotate import CLASSES

# во сколько раз чаще вставлять редкие классы
RARE_BOOST = {"roller": 3.0, "grader": 3.0, "knuckle_crane": 3.0, "backhoe_loader": 2.5,
              "bulldozer": 2.0, "concrete_mixer": 2.0, "concrete_pump": 2.0,
              "wheel_loader": 2.0, "dump_truck": 1.5}


def read_yolo(path: str, W: int, H: int):
    boxes, ids = [], []
    if not os.path.exists(path):
        return boxes, ids
    for line in open(path):
        p = line.split()
        if len(p) != 5:
            continue
        c, cx, cy, bw, bh = int(p[0]), *map(float, p[1:])
        boxes.append([(cx - bw / 2) * W, (cy - bh / 2) * H,
                      (cx + bw / 2) * W, (cy + bh / 2) * H])
        ids.append(c)
    return boxes, ids


def write_yolo(path: str, boxes, ids, W: int, H: int):
    lines = []
    for (x1, y1, x2, y2), c in zip(boxes, ids):
        cx, cy = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H
        bw, bh = (x2 - x1) / W, (y2 - y1) / H
        if bw <= 0 or bh <= 0:
            continue
        lines.append(f"{c} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    open(path, "w").write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backgrounds", default="data/raw/screenshots")
    ap.add_argument("--labels", default="data/preannot/labels")
    ap.add_argument("--cutouts", default="data/preannot/cutouts")
    ap.add_argument("--out", default="data/synth")
    ap.add_argument("-n", "--count", type=int, default=200)
    ap.add_argument("--paste-range", type=int, nargs=2, default=[1, 5])
    ap.add_argument("--bg-aug", action="store_true", default=True,
                    help="применять погодные/суточные аугментации к готовой композиции")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()

    random.seed(a.seed); np.random.seed(a.seed)
    bank = CutoutBank(a.cutouts, CLASSES)
    if not len(bank):
        raise SystemExit(f"банк вырезок пуст: {a.cutouts}. Сначала запустите preannotate.py")
    print(f"банк: {len(bank)} вырезок, классов {len(bank.by_class)}")
    for c, f in sorted(bank.by_class.items(), key=lambda kv: -len(kv[1])):
        print(f"  {c:16s} {len(f)}")

    bgs = sorted(glob.glob(f"{a.backgrounds}/*.png"))
    os.makedirs(f"{a.out}/images", exist_ok=True)
    os.makedirs(f"{a.out}/labels", exist_ok=True)

    comp = CopyPasteComposer(bank, CLASSES, n_range=tuple(a.paste_range),
                             rare_boost=RARE_BOOST)
    # фоновые аугментации: те же группы, что и в обучении, но применяются
    # ПОСЛЕ вставки, чтобы погода легла и на технику тоже
    bg_groups = [aug_mod.time_of_day(1.0), aug_mod.weather(1.0),
                 aug_mod.season(1.0), aug_mod.camera(1.0)]

    made = 0
    for i in range(a.count):
        src = bgs[i % len(bgs)]
        stem = os.path.splitext(os.path.basename(src))[0]
        img = cv2.imread(src)
        if img is None:
            continue
        H, W = img.shape[:2]
        boxes, ids = read_yolo(os.path.join(a.labels, f"{stem}.txt"), W, H)
        size_model = fit_size_vs_y([((b[1] + b[3]) / 2, b[3] - b[1]) for b in boxes], H)

        out_img, out_boxes, out_ids = comp(img, boxes, ids, size_model)

        if a.bg_aug and random.random() < 0.8:
            g = random.choice(bg_groups)
            rgb = cv2.cvtColor(out_img, cv2.COLOR_BGR2RGB)
            rgb = g(image=rgb)["image"]
            out_img = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2BGR)

        name = f"synth_{i:05d}_{stem}"
        cv2.imwrite(f"{a.out}/images/{name}.jpg", out_img,
                    [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        write_yolo(f"{a.out}/labels/{name}.txt", out_boxes, out_ids, W, H)
        made += 1

    print(f"сгенерировано {made} кадров -> {a.out}")
    print("ВНИМАНИЕ: подмешивать только в train. В val синтетика не идёт.")


if __name__ == "__main__":
    main()
