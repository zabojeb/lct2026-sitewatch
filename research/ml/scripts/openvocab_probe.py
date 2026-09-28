"""Может ли open-vocabulary детектор разметить наши кадры по текстовому промпту?

Это прямая проверка идеи «взять Grounding DINO / YOLOE и получить псевдо-разметку
без ручного труда». Узкое место проекта — отсутствие разметки, и если open-vocab
модель ловит хотя бы буровые установки и башенные краны, ручная работа сводится
к исправлению, а не к разметке с нуля.

YOLOE берём вместо Grounding DINO потому, что веса уже лежат в релизе ultralytics
(никаких внешних зависимостей), а архитектурно это тот же приём: текстовые
эмбеддинги классов подставляются в голову детектора.
"""
import glob, json, os, sys
from collections import Counter

PROMPTS = [
    "excavator", "tower crane", "mobile crane", "crawler crane",
    "dump truck", "truck", "bulldozer", "road roller",
    "concrete mixer truck", "concrete pump truck",
    "drilling rig", "pile driver", "wheel loader", "construction worker",
]

if __name__ == "__main__":
    from ultralytics import YOLOE
    files = sorted(glob.glob("data/raw/screenshots/*.png"),
                   key=lambda x: int("".join(filter(str.isdigit, os.path.basename(x)))))[:40]
    out = {}
    for weights in ["yoloe-26s-seg.pt", "yoloe-26l-seg.pt"]:
        try:
            m = YOLOE(weights)
            m.set_classes(PROMPTS, m.get_text_pe(PROMPTS))
        except Exception as e:
            out[weights] = {"error": f"{type(e).__name__}: {e}"}
            print(weights, "FAILED", e, flush=True)
            continue
        for imgsz in (1280,):
            cnt, sizes, nimg = Counter(), [], 0
            for f in files:
                r = m.predict(f, imgsz=imgsz, conf=0.20, device="mps", verbose=False)[0]
                H, W = r.orig_shape
                nimg += 1
                for b in r.boxes:
                    cnt[r.names[int(b.cls)]] += 1
                    x1, y1, x2, y2 = b.xyxy[0].tolist()
                    sizes.append((x2 - x1) / W)
            key = f"{weights}@{imgsz}"
            out[key] = {"images": nimg, "detections": sum(cnt.values()),
                        "per_image": round(sum(cnt.values()) / nimg, 2),
                        "median_rel_width_pct": round(sorted(sizes)[len(sizes)//2]*100, 2) if sizes else 0,
                        "by_class": dict(cnt.most_common())}
            print(key, json.dumps(out[key], ensure_ascii=False), flush=True)
    json.dump(out, open("ml/runs/openvocab.json", "w"), indent=2, ensure_ascii=False)
    print("DONE")
