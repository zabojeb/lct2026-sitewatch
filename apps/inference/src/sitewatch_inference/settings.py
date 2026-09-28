"""Serving configuration for the two reviewed YOLO modes and shared classifier."""

import os
from dataclasses import dataclass
from pathlib import Path

DETECTOR_SHA256 = {
    "640": "4f35c1c790721ac54491445375e53f6cdf48e4289ef46af92c0c6260c79b03df",
    "960": "898f8b7d942e60e5e9f345a6babe7a63986c7bdc6948d3a0e02877180131f179",
}
CLASSIFIER_SHA256 = "1aa87eac3f31514380d804ac29e4d72b39f654c548937b70cb9f4c17fb15f73a"
REJECT_SHA256 = "923c5a14318dfeac612f261ff63a7e1f0624deda1093c94b3a56ef2576a80386"


@dataclass(frozen=True)
class Settings:
    detector_640_path: Path
    detector_960_path: Path
    classifier_path: Path
    reject_threshold_path: Path
    internal_token: str
    device: str = "auto"
    detection_score: float = 0.25
    max_upload_bytes: int = 12 * 1024 * 1024
    max_image_pixels: int = 32_000_000
    max_detections: int = 300
    classifier_batch: int = 16
    threads: int = 4

    @classmethod
    def from_environment(cls) -> "Settings":
        token = os.environ.get("SITEWATCH_INTERNAL_TOKEN", "")
        if len(token.encode()) < 32:
            raise ValueError("SITEWATCH_INTERNAL_TOKEN must contain at least 32 bytes")
        settings = cls(
            detector_640_path=Path(os.environ.get("DETECTOR_WEIGHTS_640", "/models/yolo_640.pt")),
            detector_960_path=Path(os.environ.get("DETECTOR_WEIGHTS_960", "/models/yolo_960.pt")),
            classifier_path=Path(
                os.environ.get("CLASSIFIER_WEIGHTS", "/models/convnext_small_latest.pth")
            ),
            reject_threshold_path=Path(
                os.environ.get("REJECT_THRESHOLD_FILE", "/models/reject_threshold.json")
            ),
            internal_token=token,
            device=os.environ.get("INFERENCE_DEVICE", "auto"),
            detection_score=float(os.environ.get("DETECTION_SCORE", "0.25")),
            threads=int(os.environ.get("INFERENCE_THREADS", "4")),
        )
        if not 0 < settings.detection_score <= 1 or settings.threads < 1:
            raise ValueError("Invalid detector confidence or thread count")
        return settings
