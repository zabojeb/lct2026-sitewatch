#!/usr/bin/env python3
"""Build the browser demo from the two Kaggle construction datasets.

The script never runs a detector: every box is read from the supplied YOLO
labels. Image matching and short-term tracking are computed locally.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


CLASSES = [
    "Автобетоносмеситель", "Бетононасос", "Бульдозер", "Буровая установка",
    "Экскаватор", "Грузовик", "Работник", "Каска", "Каток", "Башенный кран",
    "Манипулятор", "Мини-бульдозер", "Автокран", "Мусоровоз", "Подъёмник",
    "Самосвал", "Трактор", "Вилочный погрузчик",
]

CLASS_SLUGS = [
    "mixer", "pump", "bulldozer", "drill", "excavator", "truck", "person",
    "helmet", "roller", "tower-crane", "manipulator", "mini-bulldozer",
    "mobile-crane", "garbage-truck", "lift", "dump-truck", "tractor", "forklift",
]

PROGRESS_CLASSES = [
    ("Самосвал", "dump-truck"),
    ("Бульдозер", "bulldozer"),
    ("Автобетоносмеситель", "mixer"),
    ("Мини-погрузчик", "mini-loader"),
    ("Башенный кран", "tower-crane"),
    ("Автокран", "mobile-crane"),
    ("Грузовик", "truck"),
    ("Работник", "person"),
]

# Timestamps are printed in the source frames. These checkpoints keep one
# fixed D3 viewpoint and deliberately span visible construction progress.
PROGRESS_SESSION = {
    700: "2020-12-02T09:09:59", 720: "2020-12-02T09:11:52",
    740: "2020-12-02T09:13:23", 760: "2020-12-02T09:14:53",
    780: "2021-01-06T11:00:55", 800: "2021-01-06T11:03:04",
    820: "2021-01-06T11:05:14", 840: "2021-02-12T09:00:06",
    860: "2021-02-12T09:01:54", 880: "2021-02-12T09:03:17",
    900: "2021-02-12T09:04:51",
}

STAGE_PROFILES = {
    "Разработка котлована": {"required": {"excavator": 1}, "optional": {"dump-truck", "bulldozer", "tractor"}},
    "Буронабивные сваи": {"required": {"drill": 1}, "optional": {"excavator", "manipulator", "mobile-crane", "truck"}},
    "Монолитные конструкции": {"required_any": {"tower-crane", "mobile-crane", "manipulator"}, "optional": {"mixer", "pump", "truck"}},
    "Бетонирование": {"required_any": {"mixer", "pump"}, "optional": {"mobile-crane", "truck"}},
}

SEQUENCE_RE = re.compile(r"(?P<camera>\d+)_\d+_(?P<stamp>\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})_jpeg")


@dataclass
class Box:
    class_id: int
    x: float
    y: float
    w: float
    h: float

    @property
    def xyxy(self):
        return self.x - self.w / 2, self.y - self.h / 2, self.x + self.w / 2, self.y + self.h / 2

    @property
    def foot(self):
        return self.x, self.y + self.h / 2


def read_boxes(image_path: Path) -> list[Box]:
    label = image_path.parents[1] / "labels" / f"{image_path.stem}.txt"
    if not label.exists():
        label = image_path.with_suffix(".txt")
    boxes = []
    for line in label.read_text().splitlines() if label.exists() else []:
        parts = line.split()
        if len(parts) >= 5:
            boxes.append(Box(int(parts[0]), *map(float, parts[1:5])))
    return boxes


def progress_image(root: Path, number: int) -> Path:
    matches = list(root.glob(f"*/*/IMG{number}.jpg"))
    if not matches:
        raise FileNotFoundError(f"IMG{number}.jpg")
    return matches[0]


def build_progress_session(root: Path, out: Path):
    frames, previous = [], {}
    for number, iso in PROGRESS_SESSION.items():
        source = progress_image(root, number)
        target_name = f"timeline-{number:04d}.webp"
        save_web_image(source, out / "assets" / "timeline" / target_name, width=1440)
        raw = read_boxes(source)
        by_class = defaultdict(list)
        for box in raw:
            by_class[box.class_id].append(box)
        boxes = []
        for class_id, class_boxes in by_class.items():
            class_boxes.sort(key=lambda b: b.x)
            for rank, box in enumerate(class_boxes, 1):
                name, slug = PROGRESS_CLASSES[class_id]
                track_id = f"D3-{slug[:3].upper()}-{rank:02d}"
                key = (class_id, rank)
                movement = math.dist(previous[key].foot, box.foot) / max(.01, math.hypot(box.w, box.h)) if key in previous else 0.0
                previous[key] = box
                boxes.append({
                    "classId": class_id, "className": name, "classSlug": slug,
                    "bbox": [round(v, 6) for v in (box.x, box.y, box.w, box.h)],
                    "trackId": track_id, "motion": round(movement, 5),
                    "visualChange": 0.0, "evidenceSec": 0, "stillSec": 0,
                    "stationary": False,
                    "mapPoint": [round(box.foot[0] * 100, 2), round(box.foot[1] * 100, 2)],
                })
        counts = Counter(box["classSlug"] for box in boxes if box["classSlug"] != "person")
        stamp = datetime.fromisoformat(iso)
        frames.append({
            "timestamp": iso, "time": stamp.strftime("%H:%M:%S"),
            "dateLabel": stamp.strftime("%d.%m.%Y"), "cameraId": "Камера D3",
            "image": f"assets/timeline/{target_name}", "split": "исходная разметка",
            "sourceFrame": number, "boxes": boxes, "counts": dict(counts),
        })
    return frames


def timestamp_and_camera(path: Path):
    match = SEQUENCE_RE.match(path.name)
    if not match:
        return None
    return match.group("camera"), datetime.strptime(match.group("stamp"), "%Y-%m-%d-%H-%M-%S")


def iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a.xyxy
    bx1, by1, bx2, by2 = b.xyxy
    iw, ih = max(0, min(ax2, bx2) - max(ax1, bx1)), max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    return inter / max(1e-9, a.w * a.h + b.w * b.h - inter)


def track_sequence(items):
    next_id, active, result = 1, {}, {}
    previous_gray = None
    for stamp, path in items:
        current_gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        boxes = read_boxes(path)
        assigned, used = {}, set()
        candidates = []
        for bi, box in enumerate(boxes):
            for tid, track in active.items():
                if track["box"].class_id != box.class_id:
                    continue
                overlap = iou(track["box"], box)
                distance = math.dist(track["box"].foot, box.foot)
                score = overlap - distance * 0.35
                if overlap >= 0.08 or distance <= 0.035:
                    candidates.append((score, bi, tid, distance))
        for _, bi, tid, distance in sorted(candidates, reverse=True):
            if bi in assigned or tid in used:
                continue
            assigned[bi], used = tid, used | {tid}
            track = active[tid]
            elapsed = max(1.0, (stamp - track["last"]).total_seconds())
            normalized_motion = distance / max(0.01, math.hypot(boxes[bi].w, boxes[bi].h)) / elapsed
            track["motion"].append((stamp, normalized_motion))
            if previous_gray is not None and current_gray is not None:
                h, w = current_gray.shape[:2]
                x1, y1, x2, y2 = boxes[bi].xyxy
                sx1, sy1 = max(0, int(x1 * w)), max(0, int(y1 * h))
                sx2, sy2 = min(w, int(x2 * w)), min(h, int(y2 * h))
                if sx2 > sx1 + 4 and sy2 > sy1 + 4:
                    now_crop = cv2.resize(current_gray[sy1:sy2, sx1:sx2], (48, 48))
                    old_crop = cv2.resize(previous_gray[sy1:sy2, sx1:sx2], (48, 48))
                    visual_change = float(np.mean(cv2.absdiff(now_crop, old_crop)) / 255.0)
                    track["appearance"].append((stamp, visual_change))
            track.update(box=boxes[bi], last=stamp)
        for bi, box in enumerate(boxes):
            if bi not in assigned:
                assigned[bi] = next_id
                active[next_id] = {
                    "box": box, "last": stamp, "first": stamp,
                    "motion": deque(maxlen=180), "appearance": deque(maxlen=180),
                }
                next_id += 1
        active = {tid: track for tid, track in active.items() if (stamp - track["last"]).total_seconds() <= 4}
        frame_boxes = []
        for bi, box in enumerate(boxes):
            tid = assigned[bi]
            track = active[tid]
            speeds = [value for _, value in track["motion"]]
            changes = [value for _, value in track["appearance"]]
            speed = float(np.median(speeds[-30:])) if speeds else 0.0
            visual_change = float(np.median(changes[-30:])) if changes else 0.0
            evidence_sec = int((stamp - track["first"]).total_seconds())
            quiet_samples = 0
            for (_, movement), (_, appearance) in zip(reversed(track["motion"]), reversed(track["appearance"])):
                if movement < 0.012 and appearance < 0.022:
                    quiet_samples += 1
                else:
                    break
            still_sec = min(evidence_sec, quiet_samples)
            stationary = evidence_sec >= 60 and still_sec >= 60
            frame_boxes.append({
                "classId": box.class_id, "className": CLASSES[box.class_id], "classSlug": CLASS_SLUGS[box.class_id],
                "bbox": [round(v, 6) for v in (box.x, box.y, box.w, box.h)], "trackId": f"{items[0][1].name[:3]}-{tid:02d}",
                "motion": round(speed, 5), "visualChange": round(visual_change, 5),
                "evidenceSec": evidence_sec, "stillSec": still_sec, "stationary": stationary,
            })
        result[str(path)] = frame_boxes
        previous_gray = current_gray
    return result


def sift_match(path_a: Path, path_b: Path, homography=True, include_matrix=False):
    a = cv2.imread(str(path_a), cv2.IMREAD_GRAYSCALE)
    b = cv2.imread(str(path_b), cv2.IMREAD_GRAYSCALE)
    scale = 960 / max(a.shape[1], b.shape[1])
    a = cv2.resize(a, None, fx=scale, fy=scale)
    b = cv2.resize(b, None, fx=scale, fy=scale)
    detector = cv2.SIFT_create(nfeatures=1800, contrastThreshold=0.03)
    ka, da = detector.detectAndCompute(a, None)
    kb, db = detector.detectAndCompute(b, None)
    if da is None or db is None:
        return {"keypoints": [len(ka), len(kb)], "matches": 0, "inliers": 0, "inlierRatio": 0, "rmse": None}
    pairs = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [m for m, n in pairs if m.distance < 0.72 * n.distance]
    inliers, rmse, matrix_out = 0, None, None
    if len(good) >= 8:
        pa = np.float32([ka[m.queryIdx].pt for m in good])
        pb = np.float32([kb[m.trainIdx].pt for m in good])
        if homography:
            matrix, mask = cv2.findHomography(pa, pb, cv2.RANSAC, 4.0)
            if matrix is not None and mask is not None:
                matrix_out = matrix
                projected = cv2.perspectiveTransform(pa.reshape(-1, 1, 2), matrix).reshape(-1, 2)
                selected = mask.ravel().astype(bool)
                inliers = int(selected.sum())
                rmse = float(np.sqrt(np.mean(np.square(projected[selected] - pb[selected])))) if inliers else None
        else:
            _, mask = cv2.findFundamentalMat(pa, pb, cv2.FM_RANSAC, 2.0, 0.995)
            inliers = int(mask.sum()) if mask is not None else 0
    result = {
        "keypoints": [len(ka), len(kb)], "matches": len(good), "inliers": inliers,
        "inlierRatio": round(inliers / max(1, len(good)), 3), "rmse": round(rmse, 2) if rmse is not None else None,
    }
    if include_matrix:
        result["matrix"] = matrix_out.tolist() if matrix_out is not None else None
    return result


def transform_point(point, matrix):
    if matrix is None:
        return None
    source = np.float32([[point]])
    mapped = cv2.perspectiveTransform(source, np.asarray(matrix, dtype=np.float64))[0, 0]
    return [round(float(mapped[0]), 2), round(float(mapped[1]), 2)]


def save_web_image(source: Path, target: Path, width=1280):
    image = cv2.imread(str(source))
    scale = min(1.0, width / image.shape[1])
    image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), image, [cv2.IMWRITE_WEBP_QUALITY, 82])


def stage_scores(counts):
    scores = []
    observed = {slug for slug, count in counts.items() if count > 0}
    for name, profile in STAGE_PROFILES.items():
        required = profile.get("required", {})
        required_any = profile.get("required_any", set())
        optional = profile.get("optional", set())
        req_score = sum(min(counts.get(k, 0) / amount, 1) for k, amount in required.items()) / max(1, len(required))
        any_score = 1 if required_any and observed & required_any else 0
        expected = set(required) | required_any | optional
        union = observed | expected
        jaccard = len(observed & expected) / max(1, len(union))
        score = 0.20 * jaccard + 0.35 * req_score + 0.45 * any_score
        scores.append({"name": name, "score": round(score, 3)})
    return sorted(scores, key=lambda x: x["score"], reverse=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-root", type=Path, required=True)
    parser.add_argument("--progress-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    all_video_images = list(args.video_root.glob("*/images/*.jpg"))
    sequences = defaultdict(list)
    for path in all_video_images:
        parsed = timestamp_and_camera(path)
        if parsed:
            camera, stamp = parsed
            if camera in {"801", "901"}:
                sequences[camera].append((stamp, path))
    for values in sequences.values():
        values.sort()

    tracks = {camera: track_sequence(items) for camera, items in sequences.items()}
    picks = {"801": [0, 60, 120, 180, 240, -1], "901": [0, 20, 40, -1]}
    frames = []
    for camera in ("801", "901"):
        items = sequences[camera]
        for index in picks[camera]:
            stamp, source = items[index]
            target_name = f"cam-{camera}-{stamp.strftime('%H%M%S')}.webp"
            save_web_image(source, args.out / "assets" / "real" / target_name)
            boxes = tracks[camera][str(source)]
            counts = Counter(box["classSlug"] for box in boxes if box["classSlug"] not in {"person", "helmet"})
            frames.append({
                "timestamp": stamp.isoformat(), "time": stamp.strftime("%H:%M:%S"), "cameraId": f"Камера {camera[0]}",
                "image": f"assets/real/{target_name}", "split": source.parents[1].name, "boxes": boxes, "counts": dict(counts),
            })
    frames.sort(key=lambda x: x["timestamp"])

    latest_counts = Counter()
    for camera in ("801", "901"):
        _, path = sequences[camera][-1]
        counts = Counter(CLASS_SLUGS[b.class_id] for b in read_boxes(path) if CLASS_SLUGS[b.class_id] not in {"person", "helmet"})
        for key, value in counts.items():
            latest_counts[key] = max(latest_counts[key], value)

    calibration = []
    for camera in ("801", "901"):
        first, last = sequences[camera][0][1], sequences[camera][-1][1]
        calibration.append({"cameraId": f"Камера {camera[0]}", **sift_match(first, last), "spanSec": int((sequences[camera][-1][0] - sequences[camera][0][0]).total_seconds())})
    cross_geometry = sift_match(sequences["801"][-1][1], sequences["901"][0][1], homography=False)
    # Matrix maps camera 9 into camera 8's reference image. The matcher works
    # on 960 px wide images, so the resulting coordinates are a real local
    # image-plane frame, not invented geographic coordinates.
    cross_map = sift_match(sequences["901"][0][1], sequences["801"][-1][1], homography=True, include_matrix=True)
    map_matrix = cross_map.get("matrix")
    for frame in frames:
        for box in frame["boxes"]:
            x, y, _, height = box["bbox"]
            foot = [x * 960, (y + height / 2) * 540]
            mapped = foot if frame["cameraId"] == "Камера 8" else transform_point(foot, map_matrix)
            box["mapPoint"] = [round(mapped[0] / 9.6, 2), round(mapped[1] / 5.4, 2)] if mapped is not None else None

    progress_numbers = [1, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
    progress = []
    for number in progress_numbers:
        matches = list(args.progress_root.glob(f"*/*/IMG{number}.jpg"))
        if not matches:
            continue
        source = matches[0]
        target_name = f"progress-{number:04d}.webp"
        save_web_image(source, args.out / "assets" / "progress" / target_name, width=1120)
        boxes = read_boxes(source)
        progress.append({
            "index": number, "image": f"assets/progress/{target_name}", "boxCount": len(boxes),
            "cranes": sum(b.class_id == 4 for b in boxes), "workers": sum(b.class_id == 7 for b in boxes),
        })

    test_images = list((args.video_root / "test" / "images").glob("*.jpg"))
    test_sample = None
    if test_images:
        source = test_images[0]
        save_web_image(source, args.out / "assets" / "real" / "test-sample.webp")
        test_sample = {"image": "assets/real/test-sample.webp", "boxes": [
            {"classId": b.class_id, "className": CLASSES[b.class_id], "classSlug": CLASS_SLUGS[b.class_id], "bbox": [b.x, b.y, b.w, b.h]}
            for b in read_boxes(source)
        ]}

    progress_frames = build_progress_session(args.progress_root, args.out)
    latest_counts = Counter(progress_frames[-1]["counts"])
    payload = {
        "source": {
            "videoDataset": "nickpudovkin/const-video-v2i-yolo26", "progressDataset": "nickpudovkin/dataset-object-identication-training-construction",
            "videoFrames": len(all_video_images), "progressFrames": len(list(args.progress_root.glob("*/*/*.jpg"))), "classes": CLASSES,
        },
        "session": {
            "start": progress_frames[0]["timestamp"], "end": progress_frames[-1]["timestamp"],
            "durationDays": (datetime.fromisoformat(progress_frames[-1]["timestamp"]) - datetime.fromisoformat(progress_frames[0]["timestamp"])).days,
            "frames": progress_frames,
        },
        "calibration": calibration,
        "crossCamera": {"epipolar": cross_geometry, "mapHomography": cross_map},
        "observedCounts": dict(latest_counts), "stageScores": stage_scores(latest_counts),
        "progress": progress, "testSample": test_sample,
    }
    data_dir = args.out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "real-session.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({"frames": len(progress_frames), "durationDays": payload["session"]["durationDays"], "calibration": calibration, "crossCamera": payload["crossCamera"], "stageScores": payload["stageScores"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
