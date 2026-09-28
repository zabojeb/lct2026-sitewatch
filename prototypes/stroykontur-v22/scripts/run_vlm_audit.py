#!/usr/bin/env python3
"""Run a small local VLM on the real demo frames and cache structured results.

The detector remains the source of object classes and bounding boxes.  The VLM
only classifies the visual construction context; it does not create alerts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import torch
from PIL import Image, ImageDraw, ImageFont
from transformers import AutoModelForImageTextToText, AutoProcessor


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "dist/data/real-session.json"
ARTIFACT_DIR = ROOT / "artifacts/vlm"
MODEL_ID = "HuggingFaceTB/SmolVLM-256M-Instruct"
LABELS = {
    "WORK_FRONT": "Основной фронт работ",
    "ACCESS_ROAD": "Технологический проезд",
    "STORAGE_AREA": "Зона складирования",
    "CRANE_SECTOR": "Рабочий сектор кранов",
    "UNCLEAR": "Контекст не определён",
}


def annotate(frame: dict) -> Image.Image:
    image = Image.open(ROOT / "dist" / frame["image"]).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(12, image.width // 90))
    for index, box in enumerate(frame.get("boxes", []), start=1):
        if box.get("classSlug") in {"person", "helmet"}:
            continue
        x, y, w, h = box["bbox"]
        left, top = (x - w / 2) * image.width, (y - h / 2) * image.height
        right, bottom = (x + w / 2) * image.width, (y + h / 2) * image.height
        label = f"{index}: {box.get('classSlug', 'object')}"
        draw.rectangle((left, top, right, bottom), outline=(185, 239, 119), width=3)
        text_box = draw.textbbox((left, top), label, font=font)
        draw.rectangle(text_box, fill=(7, 12, 9))
        draw.text((left, top), label, fill=(255, 255, 255), font=font)
    return image


def classify(raw: str) -> str:
    normalized = raw.upper().replace(" ", "_")
    for label in LABELS:
        if label in normalized:
            return label
    if "WORK" in normalized or "EXCAV" in normalized:
        return "WORK_FRONT"
    if "ROAD" in normalized or "ACCESS" in normalized:
        return "ACCESS_ROAD"
    if "STOR" in normalized:
        return "STORAGE_AREA"
    if "CRANE" in normalized:
        return "CRANE_SECTOR"
    return "UNCLEAR"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Process only N frames (0 = all)")
    args = parser.parse_args()

    payload = json.loads(DATA_PATH.read_text())
    frames = payload.get("incidentEvidence", [])
    if args.limit:
        frames = frames[: args.limit]

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float16 if device == "mps" else torch.float32
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, dtype=dtype).to(device)
    model.eval()

    prompt = (
        "The image is a construction-site camera frame. Green boxes and English labels come from an object detector. "
        "Classify the dominant site area containing the boxed machinery. Answer with exactly one token from: "
        "WORK_FRONT, ACCESS_ROAD, STORAGE_AREA, CRANE_SECTOR, UNCLEAR."
    )
    results: dict[str, dict] = {}
    for position, frame in enumerate(frames, start=1):
        image = annotate(frame)
        artifact = ARTIFACT_DIR / f"{frame['id']}.jpg"
        image.save(artifact, quality=88, optimize=True)
        messages = [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": prompt}]}]
        text = processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = processor(text=text, images=[image], return_tensors="pt").to(device)
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=6, do_sample=False)
        answer = processor.batch_decode(generated[:, inputs["input_ids"].shape[1] :], skip_special_tokens=True)[0].strip()
        label = classify(answer)
        results[frame["id"]] = {
            "model": MODEL_ID,
            "promptVersion": 1,
            "scene_code": label,
            "scene": LABELS[label],
            "summary_ru": f"Ответ модели: {answer or 'пустой ответ'}",
            "raw_output": answer,
        }
        print(f"[{position}/{len(frames)}] {frame['id']}: {answer!r} -> {label}", flush=True)

    payload["vlmObservations"] = results
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(results)} observations to {DATA_PATH}")


if __name__ == "__main__":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    main()
