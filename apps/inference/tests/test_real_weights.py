"""Optional local smoke test, not an accuracy or generalization benchmark."""

import importlib.util
from pathlib import Path

import pytest

from sitewatch_inference.model import InferenceEngine
from sitewatch_inference.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = REPO_ROOT / "models" / "sitewatch-v2"


@pytest.mark.skipif(
    not (MODEL_DIR / "yolo_640.pt").is_file()
    or not (MODEL_DIR / "yolo_960.pt").is_file()
    or not (MODEL_DIR / "convnext_small_latest.pth").is_file()
    or not (MODEL_DIR / "reject_threshold.json").is_file()
    or importlib.util.find_spec("torch") is None
    or importlib.util.find_spec("ultralytics") is None,
    reason="private model weights or serving dependencies are not present in this checkout",
)
def test_both_pinned_modes_return_distinct_provenance_on_demo_frame() -> None:
    settings = Settings(
        MODEL_DIR / "yolo_640.pt",
        MODEL_DIR / "yolo_960.pt",
        MODEL_DIR / "convnext_small_latest.pth",
        MODEL_DIR / "reject_threshold.json",
        "t" * 32,
    )
    engine = InferenceEngine(settings)
    image_path = REPO_ROOT / "apps/web/static/demo-scenes/media/scene-4-01.webp"
    image = image_path.read_bytes()
    medium = engine.predict(image, "640")
    maximum = engine.predict(image, "960")
    for mode, result in [("640", medium), ("960", maximum)]:
        assert result["schema"] == "sitewatch.inference.v1"
        assert result["recognition_mode"] == mode
        assert result["detections"]
        assert all(detection["raw_class"] != "object" for detection in result["detections"])
    assert medium["model_version"] != maximum["model_version"]
