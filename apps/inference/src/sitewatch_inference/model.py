"""The supplied YOLO 640/960 detectors with one shared 23-class ConvNeXt classifier."""

from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .settings import CLASSIFIER_SHA256, DETECTOR_SHA256, REJECT_SHA256, Settings
from .taxonomy import map_class, validate_training_classes

# Ultralytics replaces Image.open with a version that can attempt network installs on bad uploads.
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
                raise PredictionError("Слишком большое разрешение кадра: не больше 32 Мп.")
            source.load()
            image = ImageOps.exif_transpose(source)
            return np.asarray(image.convert("RGB"))
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise PredictionError("Файл повреждён или формат не поддерживается.") from exc


def letterbox_crop(
    image: np.ndarray, size: int, mean: np.ndarray, std: np.ndarray, padding: int = 114
) -> np.ndarray:
    """Match the released predict.py crop preprocessing."""
    height, width = image.shape[:2]
    scale = size / max(height, width)
    new_width = max(1, round(width * scale))
    new_height = max(1, round(height * scale))
    resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), padding, dtype=np.uint8)
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
        detector_paths = {"640": settings.detector_640_path, "960": settings.detector_960_path}
        artifacts = {
            **{mode: (path, DETECTOR_SHA256[mode]) for mode, path in detector_paths.items()},
            "classifier": (settings.classifier_path, CLASSIFIER_SHA256),
            "reject": (settings.reject_threshold_path, REJECT_SHA256),
        }
        for name, (path, expected_hash) in artifacts.items():
            if not path.is_file():
                raise FileNotFoundError(f"Missing model artifact: {name}")
            if sha256(path) != expected_hash:
                raise ValueError(f"Model artifact hash mismatch: {name}")

        import torch
        from torchvision.models import convnext_small
        from ultralytics import YOLO

        torch.set_num_threads(settings.threads)
        cv2.setNumThreads(1)
        self.device = self._device(settings.device)
        self.detectors = {mode: YOLO(str(path)) for mode, path in detector_paths.items()}
        for mode, detector in self.detectors.items():
            if detector.names != {0: "equipment"}:
                raise ValueError(f"YOLO {mode} is not the reviewed class-agnostic detector")

        checkpoint = torch.load(settings.classifier_path, map_location="cpu", weights_only=True)
        if (
            checkpoint.get("architecture") != "convnext_small"
            or checkpoint.get("num_classes") != 23
        ):
            raise ValueError("Expected the reviewed 23-class ConvNeXt-small classifier")
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
        threshold = json.loads(settings.reject_threshold_path.read_text())["threshold"]
        if not isinstance(threshold, (int, float)) or not 0 < threshold < 1:
            raise ValueError("Invalid unknown rejection threshold")
        self.unknown_threshold = float(threshold)
        self.classifier = convnext_small(weights=None)
        self.classifier.classifier[2] = torch.nn.Linear(
            self.classifier.classifier[2].in_features, checkpoint["num_classes"]
        )
        self.classifier.load_state_dict(checkpoint["model_state_dict"], strict=True)
        self.classifier.float().to(self.device).eval()
        self.model_versions = {
            mode: f"yolo-{mode}-{DETECTOR_SHA256[mode][:12]}+convnext-{CLASSIFIER_SHA256[:12]}"
            for mode in detector_paths
        }
        self.model_version = "YOLO 640 / 960 + ConvNeXt 23"

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

    def predict(self, image_bytes: bytes, recognition_mode: str = "640") -> dict[str, object]:
        import torch
        from ultralytics.models.yolo.detect import DetectionPredictor

        if recognition_mode not in self.detectors:
            raise PredictionError("Режим распознавания должен быть 640 или 960.")
        image = decode_image(image_bytes, self.settings.max_image_pixels)
        height, width = image.shape[:2]
        proposals = (
            self.detectors[recognition_mode]
            .predict(
                cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
                predictor=DetectionPredictor,
                imgsz=int(recognition_mode),
                conf=self.settings.detection_score,
                iou=0.7,
                max_det=self.settings.max_detections,
                half=False,
                augment=False,
                rect=False,
                batch=1,
                device=self.device,
                verbose=False,
            )[0]
            .boxes
        )
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
        for offset in range(0, len(prepared), self.settings.classifier_batch):
            batch = torch.from_numpy(
                np.stack(prepared[offset : offset + self.settings.classifier_batch])
            ).to(self.device)
            with torch.inference_mode():
                probabilities = self.classifier(batch).float().softmax(dim=-1).cpu()
            for index, crop_probabilities in enumerate(probabilities):
                known_id = int(crop_probabilities[:22].argmax())
                unknown_probability = float(crop_probabilities[22])
                class_id = 22 if unknown_probability > self.unknown_threshold else known_id
                score = float(crop_probabilities[class_id])
                raw_class = self.names[str(class_id)]
                canonical_class, mapping_status = map_class(raw_class, score)
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
            "recognition_mode": recognition_mode,
            "model_version": self.model_versions[recognition_mode],
            "image_width": width,
            "image_height": height,
            "detections": detections,
            "note": (
                "Model evidence only; no schedule, coverage or deviation assessment was performed. "
                "Classifier uses the reviewed unknown rejection threshold. Scores are uncalibrated."
            ),
        }
