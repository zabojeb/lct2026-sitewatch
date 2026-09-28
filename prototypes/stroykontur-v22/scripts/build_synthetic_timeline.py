#!/usr/bin/env python3
"""Compose generated transparent equipment onto real dataset frames.

The output is a reproducible demonstration timeline.  Every inserted object's
bbox is calculated from the exact alpha-composite placement and stored with the
frame, so the UI can treat it as an ideal detector result.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageEnhance


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DATA_PATH = DIST / "data/real-session.json"
OUT_DIR = DIST / "assets/synthetic-timeline"
EQUIPMENT_DIR = DIST / "assets/equipment"

NAMES = {
    "excavator": "Экскаватор",
    "dump-truck": "Самосвал",
    "drill": "Буровая установка",
    "tower-crane": "Башенный кран",
    "mobile-crane": "Автокран",
    "mixer": "Автобетоносмеситель",
}


def load_cutout(name: str) -> Image.Image:
    image = Image.open(EQUIPMENT_DIR / f"{name}.png").convert("RGBA")
    alpha_box = image.getchannel("A").getbbox()
    return image.crop(alpha_box)


def place(
    canvas: Image.Image,
    cutout: Image.Image,
    slug: str,
    center_x: float,
    bottom_y: float,
    width_ratio: float,
    brightness: float = 0.82,
) -> dict:
    target_w = max(16, round(canvas.width * width_ratio))
    target_h = round(cutout.height * target_w / cutout.width)
    resized = cutout.resize((target_w, target_h), Image.Resampling.LANCZOS)
    rgb = ImageEnhance.Brightness(resized.convert("RGB")).enhance(brightness)
    resized = Image.merge("RGBA", (*rgb.split(), resized.getchannel("A")))
    left = round(canvas.width * center_x - target_w / 2)
    top = round(canvas.height * bottom_y - target_h)
    canvas.alpha_composite(resized, (left, top))
    return {
        "className": NAMES[slug],
        "classSlug": slug,
        "confidence": 0.97,
        "synthetic": True,
        "bbox": [
            round((left + target_w / 2) / canvas.width, 6),
            round((top + target_h / 2) / canvas.height, 6),
            round(target_w / canvas.width, 6),
            round(target_h / canvas.height, 6),
        ],
    }


def build_frame(spec: dict, assets: dict[str, Image.Image]) -> dict:
    canvas = Image.open(DIST / spec["background"]).convert("RGBA")
    boxes = []
    for item in spec["objects"]:
        boxes.append(place(canvas, assets[item["asset"]], item["slug"], item["x"], item["bottom"], item["width"], item.get("brightness", 0.82)))
    output = OUT_DIR / f"{spec['id']}.jpg"
    canvas.convert("RGB").save(output, quality=88, optimize=True, progressive=True)
    counts = Counter(box["classSlug"] for box in boxes)
    return {
        "id": spec["id"],
        "timestamp": spec["timestamp"],
        "camera": spec["camera"],
        "image": str(output.relative_to(DIST)),
        "counts": dict(counts),
        "boxes": boxes,
        "source": "Синтетическая вставка PNG на реальный кадр датасета",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = {
        "excavator": load_cutout("excavator"),
        "dump-truck": load_cutout("dump-truck"),
        "drill": load_cutout("drill-rig"),
    }
    specs = [
        {
            "id": "timeline-excavation-01", "timestamp": "2020-09-28T09:00:00", "camera": "Камера 4",
            "background": "assets/incidents/extra-401-000.jpg",
            "objects": [
                {"asset": "excavator", "slug": "excavator", "x": .47, "bottom": .54, "width": .16},
                {"asset": "excavator", "slug": "excavator", "x": .69, "bottom": .49, "width": .10},
                {"asset": "dump-truck", "slug": "dump-truck", "x": .58, "bottom": .65, "width": .13},
            ],
        },
        {
            "id": "timeline-excavation-02", "timestamp": "2020-10-08T11:20:00", "camera": "Камера 4",
            "background": "assets/incidents/extra-401-025.jpg",
            "objects": [
                {"asset": "excavator", "slug": "excavator", "x": .49, "bottom": .55, "width": .15},
                {"asset": "dump-truck", "slug": "dump-truck", "x": .61, "bottom": .68, "width": .14},
                {"asset": "dump-truck", "slug": "dump-truck", "x": .73, "bottom": .50, "width": .08},
            ],
        },
        {
            "id": "timeline-excavation-03", "timestamp": "2020-10-25T10:10:00", "camera": "Камера 4",
            "background": "assets/incidents/extra-401-049.jpg",
            "objects": [
                {"asset": "excavator", "slug": "excavator", "x": .44, "bottom": .56, "width": .15},
                {"asset": "excavator", "slug": "excavator", "x": .68, "bottom": .49, "width": .09},
                {"asset": "dump-truck", "slug": "dump-truck", "x": .60, "bottom": .68, "width": .13},
            ],
        },
        {
            "id": "timeline-piles-01", "timestamp": "2020-10-25T15:00:00", "camera": "Камера 5",
            "background": "assets/incidents/required-501-000.jpg",
            "objects": [
                {"asset": "drill", "slug": "drill", "x": .25, "bottom": .51, "width": .095},
                {"asset": "excavator", "slug": "excavator", "x": .63, "bottom": .48, "width": .085},
            ],
        },
        {
            "id": "timeline-piles-02", "timestamp": "2020-11-08T12:30:00", "camera": "Камера 5",
            "background": "assets/incidents/required-501-030.jpg",
            "objects": [
                {"asset": "drill", "slug": "drill", "x": .26, "bottom": .52, "width": .10},
                {"asset": "excavator", "slug": "excavator", "x": .65, "bottom": .48, "width": .08},
            ],
        },
        {
            "id": "timeline-piles-03", "timestamp": "2020-11-28T09:40:00", "camera": "Камера 5",
            "background": "assets/incidents/required-501-059.jpg",
            "objects": [
                {"asset": "drill", "slug": "drill", "x": .28, "bottom": .53, "width": .105},
                {"asset": "excavator", "slug": "excavator", "x": .65, "bottom": .49, "width": .08},
            ],
        },
    ]
    frames = [build_frame(spec, assets) for spec in specs]
    monolith = [
        ("timeline-monolith-01", "2020-11-28T14:00:00", "assets/progress/progress-0001.webp", 3),
        ("timeline-monolith-02", "2020-12-20T11:00:00", "assets/progress/progress-0200.webp", 2),
        ("timeline-monolith-03", "2021-01-10T10:00:00", "assets/progress/progress-0500.webp", 2),
        ("timeline-monolith-04", "2021-01-30T09:00:00", "assets/progress/progress-0800.webp", 3),
        ("timeline-monolith-05", "2021-02-12T09:00:00", "assets/progress/progress-1000.webp", 3),
    ]
    for frame_id, timestamp, image, cranes in monolith:
        frames.append({
            "id": frame_id,
            "timestamp": timestamp,
            "camera": "Камера хода строительства",
            "image": image,
            "counts": {"tower-crane": cranes, "mixer": 1},
            "boxes": [],
            "source": "Долгосрочная серия датасета",
        })
    payload = json.loads(DATA_PATH.read_text())
    payload["stageTimeline"] = frames
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Created {len(specs)} synthetic frames and {len(frames)} timeline observations")


if __name__ == "__main__":
    main()
