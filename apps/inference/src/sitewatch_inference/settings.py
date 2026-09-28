"""Serving configuration. Model bytes are mounted, never included in the Git repository."""

import os
from dataclasses import dataclass
from pathlib import Path

DETECTOR_SHA256 = "1740e491176042786976a8e291ac2b81623eec16b895d7ccd187d4fbb48b97b7"
CLASSIFIER_SHA256 = "c3fb36540f7368d164cecd53f243024bd4344c899b5062ea717ab8060162ba07"


@dataclass(frozen=True)
class Settings:
    detector_path: Path
    classifier_path: Path
    internal_token: str
    device: str = "auto"
    detection_score: float = 0.25
    classification_score: float = 0.5
    max_upload_bytes: int = 12 * 1024 * 1024
    max_image_pixels: int = 32_000_000
    max_detections: int = 100
    detector_sha256: str = DETECTOR_SHA256
    classifier_sha256: str = CLASSIFIER_SHA256

    @classmethod
    def from_environment(cls) -> "Settings":
        token = os.environ.get("SITEWATCH_INTERNAL_TOKEN", "")
        if len(token.encode()) < 32:
            raise ValueError("SITEWATCH_INTERNAL_TOKEN must contain at least 32 bytes")
        settings = cls(
            detector_path=Path(os.environ.get("DETECTOR_WEIGHTS", "/models/detector.pt")),
            classifier_path=Path(os.environ.get("CLASSIFIER_WEIGHTS", "/models/classifier.pth")),
            internal_token=token,
            device=os.environ.get("INFERENCE_DEVICE", "auto"),
            detection_score=float(os.environ.get("DETECTION_SCORE", "0.25")),
            classification_score=float(os.environ.get("CLASSIFICATION_SCORE", "0.5")),
        )
        if not 0 < settings.detection_score <= 1 or not 0 < settings.classification_score <= 1:
            raise ValueError("Model score thresholds must be within (0, 1]")
        return settings
