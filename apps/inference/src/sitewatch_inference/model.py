"""YOLO object proposals followed by the supplied ConvNeXt crop classifier."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .settings import Settings
from .taxonomy import map_class, validate_training_classes

# Ultralytics monkey-patches PIL.Image.open to attempt network package installs after an
# ordinary decode failure. Preserve Pillow's original decoder for untrusted uploads.
_image_open = Image.open
Image.MAX_IMAGE_PIXELS = 32_000_000


@dataclass(frozen=True)
class PredictionError(Exception):
    message: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_image(data: bytes, max_pixels: int) -> np.ndarray:
    try:
        with _image_open(io.BytesIO(data)) as source:
            if source.width * source.height > max_pixels:
                raise PredictionError("Image exceeds the pixel limit")
            source.load()
            image = ImageOps.exif_transpose(source)
            return np.asarray(image.convert("RGB"))
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise PredictionError("Unsupported or damaged image") from exc


def letterbox_crop(image: np.ndarray, size: int, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """Match the supplied inference.py exactly: RGB, aspect-preserving 114 pad, then normalize."""
    height, width = image.shape[:2]
    scale = size / max(height, width)
    new_width = max(1, round(width * scale))
    new_height = max(1, round(height * scale))
    resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    x = (size - new_width) // 2
    y = (size - new_height) // 2
    canvas[y : y + new_height, x : x + new_width] = resized
    return np.ascontiguousarray(((canvas.astype(np.float32) / 255 - mean) / std).transpose(2, 0, 1))


def normalized_box(box: list[float], width: int, height: int) -> dict[str, float] | None:
    x_min, y_min, x_max, y_max = box
    if not all(math.isfinite(value) for value in box):
        return None
    result = {
        "x_min": max(0.0, min(1.0, x_min / width)),
        "y_min": max(0.0, min(1.0, y_min / height)),
        "x_max": max(0.0, min(1.0, x_max / width)),
        "y_max": max(0.0, min(1.0, y_max / height)),
    }
    if result["x_min"] >= result["x_max"] or result["y_min"] >= result["y_max"]:
        return None
    return result


class InferenceEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.detector_path.is_file() or not settings.classifier_path.is_file():
            raise FileNotFoundError("Both detector and classifier weights must be mounted")
        self.detector_hash = sha256(settings.detector_path)
        self.classifier_hash = sha256(settings.classifier_path)
        if (
            self.detector_hash != settings.detector_sha256
            or self.classifier_hash != settings.classifier_sha256
        ):
            raise ValueError("Mounted model artifact hash differs from this reviewed release")
        import torch
        from torchvision.models import convnext_small
        from ultralytics import YOLO

        self.model_version = (
            f"yolo26x-{self.detector_hash[:12]}+convnext-{self.classifier_hash[:12]}"
        )
        self.device = self._device(settings.device)
        self.detector = YOLO(str(settings.detector_path))
        if self.detector.names != {0: "item"}:
            raise ValueError("Expected the reviewed class-agnostic YOLO detector with class 'item'")
        checkpoint = torch.load(settings.classifier_path, map_location="cpu", weights_only=True)
        if checkpoint.get("num_classes") != 22:
            raise ValueError("Expected 22 classifier classes")
        validate_training_classes(checkpoint["class_names"])
        preprocessing = checkpoint["preprocessing"]
        if (
            preprocessing.get("size") != 224
            or preprocessing.get("padding") != 114
            or preprocessing.get("resize") != "aspect-preserving letterbox"
        ):
            raise ValueError("Unsupported classifier preprocessing metadata")
        self.size = int(preprocessing["size"])
        self.mean = np.asarray(preprocessing["mean"], dtype=np.float32)
        self.std = np.asarray(preprocessing["std"], dtype=np.float32)
        if self.mean.shape != (3,) or self.std.shape != (3,) or np.any(self.std <= 0):
            raise ValueError("Invalid classifier normalization metadata")
        self.names: dict[str, str] = checkpoint["class_names"]
        self.classifier = convnext_small(weights=None)
        self.classifier.classifier[2] = torch.nn.Linear(
            self.classifier.classifier[2].in_features, checkpoint["num_classes"]
        )
        self.classifier.load_state_dict(checkpoint["model_state_dict"], strict=True)
        self.classifier.to(self.device).eval()

    @staticmethod
    def _device(configured: str) -> str:
        import torch

        if configured == "auto":
            return "cuda:0" if torch.cuda.is_available() else "cpu"
        if configured.startswith("cuda") and not torch.cuda.is_available():
            raise ValueError("CUDA requested but unavailable")
        if configured not in {"cpu", "cuda", "cuda:0"}:
            raise ValueError("INFERENCE_DEVICE must be auto, cpu or cuda:0")
        return configured

    def predict(self, image_bytes: bytes) -> dict[str, object]:
        import torch

        image = decode_image(image_bytes, self.settings.max_image_pixels)
        height, width = image.shape[:2]
        proposals = self.detector.predict(
            source=Image.fromarray(image),
            imgsz=640,
            conf=self.settings.detection_score,
            max_det=self.settings.max_detections,
            device=self.device,
            verbose=False,
        )[0].boxes
        prepared: list[np.ndarray] = []
        metadata: list[tuple[dict[str, float], float]] = []
        for coordinates, detector_score in zip(
            proposals.xyxy.cpu().tolist(), proposals.conf.cpu().tolist(), strict=True
        ):
            if not math.isfinite(detector_score):
                continue
            box = normalized_box(coordinates, width, height)
            if box is None:
                continue
            x_min = max(0, math.floor(coordinates[0]))
            y_min = max(0, math.floor(coordinates[1]))
            x_max = min(width, math.ceil(coordinates[2]))
            y_max = min(height, math.ceil(coordinates[3]))
            crop = image[y_min:y_max, x_min:x_max]
            if crop.size == 0:
                continue
            prepared.append(letterbox_crop(crop, self.size, self.mean, self.std))
            metadata.append((box, float(detector_score)))
        detections: list[dict[str, object]] = []
        # Small batches bound activation memory without dropping any detector proposals.
        for offset in range(0, len(prepared), 8):
            batch = torch.from_numpy(np.stack(prepared[offset : offset + 8])).to(self.device)
            with torch.inference_mode():
                probabilities = self.classifier(batch).softmax(dim=-1).cpu()
            for index, probabilities_for_crop in enumerate(probabilities):
                class_id = int(probabilities_for_crop.argmax())
                score = float(probabilities_for_crop[class_id])
                if not math.isfinite(score):
                    score = 0.0
                raw_class = self.names[str(class_id)]
                canonical_class, mapping_status = map_class(
                    raw_class, score, self.settings.classification_score
                )
                box, detector_score = metadata[offset + index]
                detections.append(
                    {
                        "raw_class_id": class_id,
                        "raw_class": raw_class,
                        "equipment_class": canonical_class,
                        "mapping_status": mapping_status,
                        "detector_score": detector_score,
                        "classifier_score": score,
                        "bounding_box": box,
                    }
                )
        return {
            "schema": "sitewatch.inference.v1",
            "model_version": self.model_version,
            "image_width": width,
            "image_height": height,
            "detections": detections,
            "note": (
                "Model evidence only; no schedule, coverage or deviation assessment was performed. "
                "Scores are uncalibrated."
            ),
        }
