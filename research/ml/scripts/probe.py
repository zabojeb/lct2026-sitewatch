"""Probe #1 — what regime are we in?

Three questions, answered on the organisers' own 100 screenshots:
  1. How small are the objects? (drives input resolution / tiling decisions)
  2. Does a stock COCO detector see anything useful? (it has no construction classes,
     but `truck`/`car` hits tell us whether the scale is even reachable)
  3. How much does tiled inference recover? (the SAHI argument, measured not assumed)

Output: ml/runs/probe.json + a per-model latency figure for the comparison table.
"""
import argparse, glob, json, os, time
import numpy as np
from PIL import Image

COCO_VEHICLE = {2: "car", 5: "bus", 7: "truck"}


def tiles(W, H, tile=640, overlap=0.25):
    """Yield (x0, y0, x1, y1) windows covering the frame with `overlap` fraction."""
    step = int(tile * (1 - overlap))
    xs = list(range(0, max(W - tile, 0) + 1, step)) or [0]
    ys = list(range(0, max(H - tile, 0) + 1, step)) or [0]
    if xs[-1] + tile < W: xs.append(W - tile)
    if ys[-1] + tile < H: ys.append(H - tile)
    for y in ys:
        for x in xs:
            yield x, y, min(x + tile, W), min(y + tile, H)


def nms(boxes, scores, thr=0.5):
    if not boxes: return []
    b = np.array(boxes, dtype=float); s = np.array(scores)
    x1, y1, x2, y2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    area = (x2 - x1) * (y2 - y1); order = s.argsort()[::-1]; keep = []
    while order.size:
        i = order[0]; keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]]); yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]]); yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / (area[i] + area[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= thr]
    return keep


def summarise(dets, files, key, secs):
    veh = [d for d in dets if d["cls"] in COCO_VEHICLE]
    if not veh:
        return {"n_det": len(dets), "n_vehicle": 0, "sec_per_img": round(secs / len(files), 3)}
    areas = np.array([d["area_frac"] for d in veh])
    rel_w = np.array([d["rel_w"] for d in veh])
    return {
        "n_det": len(dets), "n_vehicle": len(veh),
        "vehicle_per_img": round(len(veh) / len(files), 2),
        "sec_per_img": round(secs / len(files), 3),
        # COCO calls an object "small" below 32x32 px = 1024 px^2
        "pct_smaller_than_32px": round(float((areas * np.array([d["px"] for d in veh]) < 1024).mean()) * 100, 1),
        "area_frac_pct": {str(p): round(float(np.percentile(areas, p)) * 100, 3) for p in (10, 50, 90)},
        "rel_width_pct": {str(p): round(float(np.percentile(rel_w, p)) * 100, 2) for p in (10, 50, 90)},
        "classes": dict(sorted({n: sum(1 for d in veh if d["name"] == n)
                                for n in {d["name"] for d in veh}}.items(), key=lambda kv: -kv[1])),
    }


def collect(model, files, imgsz, conf, device, tiled=False, tile=640, overlap=0.25):
    dets, t0 = [], time.time()
    for f in files:
        W, H = Image.open(f).size
        if not tiled:
            r = model.predict(f, imgsz=imgsz, conf=conf, device=device, verbose=False)[0]
            raw = [(int(b.cls), float(b.conf), *b.xyxy[0].tolist()) for b in r.boxes]
            names = r.names
        else:
            im = Image.open(f).convert("RGB")
            raw, names = [], None
            for x0, y0, x1, y1 in tiles(W, H, tile, overlap):
                crop = im.crop((x0, y0, x1, y1))
                r = model.predict(crop, imgsz=tile, conf=conf, device=device, verbose=False)[0]
                names = r.names
                for b in r.boxes:
                    bx1, by1, bx2, by2 = b.xyxy[0].tolist()
                    raw.append((int(b.cls), float(b.conf), bx1 + x0, by1 + y0, bx2 + x0, by2 + y0))
            keep = nms([list(r[2:]) for r in raw], [r[1] for r in raw], 0.5)
            raw = [raw[i] for i in keep]
        for cls, cf, bx1, by1, bx2, by2 in raw:
            w, h = bx2 - bx1, by2 - by1
            dets.append({"cls": cls, "name": names[cls], "conf": cf, "px": w * h,
                         "area_frac": (w * h) / (W * H), "rel_w": w / W})
    return dets, time.time() - t0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--img-dir", default="data/raw/screenshots")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", default="ml/runs/probe.json")
    a = ap.parse_args()

    from ultralytics import YOLO
    files = sorted(glob.glob(f"{a.img_dir}/*.png"),
                   key=lambda x: int("".join(filter(str.isdigit, os.path.basename(x)))))
    print(f"{len(files)} images")

    plan = [
        ("yolo11n.pt", 640, False), ("yolo11n.pt", 1280, False),
        ("yolo26n.pt", 640, False), ("yolo26n.pt", 1280, False),
        ("yolo26s.pt", 1280, False), ("yolo26m.pt", 1280, False),
        ("yolo26n.pt", 640, True),  ("yolo26m.pt", 640, True),
    ]
    out = {}
    for name, imgsz, tiled in plan:
        key = f"{name.replace('.pt','')}@{imgsz}{'+tiled' if tiled else ''}"
        try:
            m = YOLO(name)
            dets, secs = collect(m, files, imgsz, a.conf, a.device, tiled=tiled)
            out[key] = summarise(dets, files, key, secs)
            print(key, json.dumps(out[key], ensure_ascii=False), flush=True)
        except Exception as e:
            out[key] = {"error": f"{type(e).__name__}: {e}"}
            print(key, "FAILED", e, flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=2, ensure_ascii=False)
    print("DONE ->", a.out)
