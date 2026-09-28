"""Предразметка 100 кадров ДГП через open-vocabulary детектор.

За один проход получаем две вещи:
  1. YOLO-разметку (labels/*.txt) — её человек правит, а не рисует с нуля;
  2. банк вырезок техники с альфа-каналом (cutouts/<class>/*.png) — сырьё для
     copy-paste аугментации.

Второе возможно потому, что берём seg-версию YOLOE: она отдаёт маски, а не
только рамки, и вырезка получается по контуру машины, а не прямоугольником
с куском фона.

Важно про качество. Проверка глазами (ml/runs/openvocab_examples.jpg) показала:
рамки модель ставит хорошо, КЛАССЫ путает — экскаватор называет pile driver,
подтипы кранов смешивает. Поэтому:
  * в labels/*.txt пишем класс как гипотезу, а не как истину;
  * рядом кладём review.json с исходным именем и уверенностью, чтобы разметчик
    видел, что именно предложила модель;
  * применяем класс-агностичный NMS: YOLOE вешает на один объект по 2-3
    пересекающихся бокса разных классов, и без этого разметчик будет удалять
    дубли вместо исправления классов.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import Counter

import cv2
import numpy as np

# промпт -> класс нашей таксономии (ml/configs/taxonomy.yaml)
PROMPT_TO_CLASS = {
    "excavator": "excavator",
    "tower crane": "tower_crane",
    "mobile crane": "mobile_crane",
    "crawler crane": "crawler_crane",
    "dump truck": "dump_truck",
    "truck": "truck",
    "bulldozer": "bulldozer",
    "road roller": "roller",
    "concrete mixer truck": "concrete_mixer",
    "concrete pump truck": "concrete_pump",
    "drilling rig": "pile_rig",
    "pile driver": "pile_rig",
    "wheel loader": "wheel_loader",
    "construction worker": "worker",
}
CLASSES = ["excavator", "dump_truck", "truck", "bulldozer", "roller", "concrete_mixer",
           "mobile_crane", "knuckle_crane", "pile_rig", "tower_crane", "crawler_crane",
           "concrete_pump", "wheel_loader", "backhoe_loader", "grader", "worker"]
CLASS_ID = {c: i for i, c in enumerate(CLASSES)}


def nms_agnostic(boxes, scores, thr=0.55):
    """Класс-агностичный NMS — убирает дубли на одном объекте."""
    if not boxes:
        return []
    b = np.asarray(boxes, float); s = np.asarray(scores, float)
    x1, y1, x2, y2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    area = (x2 - x1) * (y2 - y1)
    order = s.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]; keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]]); yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]]); yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        # IoU + поглощение: бокс, почти целиком лежащий внутри другого, тоже дубль
        iou = inter / (area[i] + area[order[1:]] - inter + 1e-9)
        contain = inter / np.minimum(area[i], area[order[1:]] + 1e-9)
        order = order[1:][(iou <= thr) & (contain <= 0.80)]
    return keep


def save_cutout(img, mask, path, pad=2):
    """Вырезать объект по маске в PNG с альфой.

    Обрезаем по bbox маски с небольшим запасом: края маски у YOLOE рваные,
    запас оставляет место для последующего сглаживания альфы при вставке.
    """
    ys, xs = np.where(mask > 0)
    if len(xs) < 20:
        return False
    x0, x1 = max(0, xs.min() - pad), min(img.shape[1], xs.max() + 1 + pad)
    y0, y1 = max(0, ys.min() - pad), min(img.shape[0], ys.max() + 1 + pad)
    crop = img[y0:y1, x0:x1]
    alpha = (mask[y0:y1, x0:x1] > 0).astype(np.uint8) * 255
    if crop.shape[0] < 12 or crop.shape[1] < 12:
        return False
    rgba = np.dstack([crop, alpha])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imwrite(path, rgba)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img-dir", default="data/raw/screenshots")
    ap.add_argument("--out", default="data/preannot")
    ap.add_argument("--weights", default="yoloe-26l-seg.pt")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--min-cutout-conf", type=float, default=0.45,
                    help="в банк вырезок берём только уверенные детекции")
    ap.add_argument("--device", default="mps")
    a = ap.parse_args()

    from ultralytics import YOLOE
    prompts = list(PROMPT_TO_CLASS)
    m = YOLOE(a.weights)
    m.set_classes(prompts, m.get_text_pe(prompts))

    files = sorted(glob.glob(f"{a.img_dir}/*.png"),
                   key=lambda x: int("".join(filter(str.isdigit, os.path.basename(x)))))
    os.makedirs(f"{a.out}/labels", exist_ok=True)
    os.makedirs(f"{a.out}/cutouts", exist_ok=True)

    review, stats, n_cut = {}, Counter(), 0
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        img = cv2.imread(f)
        H, W = img.shape[:2]
        r = m.predict(f, imgsz=a.imgsz, conf=a.conf, device=a.device, verbose=False)[0]

        raw = []
        masks = r.masks.data.cpu().numpy() if r.masks is not None else None
        for i, b in enumerate(r.boxes):
            raw.append({"i": i, "prompt": r.names[int(b.cls)], "conf": float(b.conf),
                        "xyxy": [float(v) for v in b.xyxy[0].tolist()]})
        keep = nms_agnostic([d["xyxy"] for d in raw], [d["conf"] for d in raw])
        dets = [raw[i] for i in keep]

        lines, items = [], []
        for d in dets:
            cls = PROMPT_TO_CLASS.get(d["prompt"])
            if cls is None:
                continue
            x1, y1, x2, y2 = d["xyxy"]
            cx, cy = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H
            bw, bh = (x2 - x1) / W, (y2 - y1) / H
            lines.append(f"{CLASS_ID[cls]} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
            items.append({"class": cls, "prompt_as_detected": d["prompt"],
                          "conf": round(d["conf"], 3), "xyxy": [round(v, 1) for v in d["xyxy"]]})
            stats[cls] += 1

            if masks is not None and d["conf"] >= a.min_cutout_conf and d["i"] < len(masks):
                mk = cv2.resize(masks[d["i"]], (W, H), interpolation=cv2.INTER_NEAREST)
                if save_cutout(img, mk, f"{a.out}/cutouts/{cls}/{stem}_{d['i']}.png"):
                    n_cut += 1

        open(f"{a.out}/labels/{stem}.txt", "w").write("\n".join(lines))
        review[f"{stem}.png"] = items

    json.dump(review, open(f"{a.out}/review.json", "w"), ensure_ascii=False, indent=1)
    with open(f"{a.out}/classes.txt", "w") as fh:
        fh.write("\n".join(CLASSES))
    print(f"кадров: {len(files)} | боксов: {sum(stats.values())} | вырезок: {n_cut}")
    for c, n in stats.most_common():
        print(f"  {c:16s} {n}")
    json.dump({"boxes": dict(stats), "cutouts": n_cut, "images": len(files)},
              open("ml/runs/preannot_stats.json", "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
