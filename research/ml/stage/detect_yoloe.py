"""Настоящий детектор на кадрах датасета №8 — zero-shot YOLOE по текстовым промптам.

Нужен, чтобы проверить весь путь «кадры → детекции → слияние камер → этап» не на
разметке, а на выходе реального детектора с его ошибками. Словарь промптов нарочно
не совпадает с метками датасета: движок этапов должен работать с любым словарём
детектора через мост «метка → ключ техники».
"""
import json, re, sys
from pathlib import Path

# промпт → ключ техники из md. Это единственное, что связывает детектор с матрицей.
PROMPT_TO_KEY = {
    "excavator": "E", "dump truck": "D", "cargo truck": "Q", "bulldozer": "B",
    "road roller": "R", "concrete mixer truck": "X", "concrete pump truck": "P",
    "mobile crane": "C", "truck with knuckle boom crane": "M", "tower crane": "T",
    "drilling rig": "V", "pile driver": "PD", "wheel loader": "L",
    "skid steer loader": "S", "motor grader": "G", "forklift": "F", "tractor": "Y",
    "aerial work platform": "A",
}
PER_CAM = 25
NAME = re.compile(r"^(\d+)_(\d+)_(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})")

if __name__ == "__main__":
    from ultralytics import YOLOE
    root = Path("data/external/const_video")
    by_cam = {}
    for p in sorted(root.rglob("images/*.jpg")):
        m = NAME.match(p.name)
        if m:
            by_cam.setdefault(f"Cam{int(m.group(1)) // 100}", []).append((m.group(3), p))
    picked = []
    for cam, v in sorted(by_cam.items()):
        v.sort()
        step = max(1, len(v) // PER_CAM)
        picked += [(cam, t, p) for t, p in v[::step][:PER_CAM]]
    model = YOLOE("yoloe-26l-seg.pt")
    prompts = list(PROMPT_TO_KEY)
    model.set_classes(prompts, model.get_text_pe(prompts))
    dets = []
    for i, (cam, t, p) in enumerate(picked):
        r = model.predict(str(p), imgsz=960, conf=0.20, device="mps", verbose=False)[0]
        for b in r.boxes:
            dets.append({"camera": cam, "frame": t, "label": r.names[int(b.cls)], "conf": round(float(b.conf), 3)})
        if i % 40 == 0:
            print(f"{i}/{len(picked)}", flush=True)
    frames = {cam: min(PER_CAM, len(v)) for cam, v in by_cam.items()}
    json.dump({"detections": dets, "frames": frames, "prompt_to_key": PROMPT_TO_KEY},
              open("ml/runs/const_video_yoloe.json", "w"), ensure_ascii=False, indent=1)
    print("готово:", len(dets), "детекций на", len(picked), "кадрах")
