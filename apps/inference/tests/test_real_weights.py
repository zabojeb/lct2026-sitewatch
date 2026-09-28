"""Optional local smoke test, not an accuracy or generalization benchmark."""

import importlib.util
from pathlib import Path

import pytest

from sitewatch_inference.model import InferenceEngine
from sitewatch_inference.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_DIR = REPO_ROOT / "models" / "sitewatch-v1"


@pytest.mark.skipif(
    not (MODEL_DIR / "detector.pt").is_file()
    or not (MODEL_DIR / "classifier.pth").is_file()
    or importlib.util.find_spec("torch") is None
    or importlib.util.find_spec("ultralytics") is None,
    reason="private model weights or serving dependencies are not present in this checkout",
)
def test_pinned_weights_detect_one_known_demo_object() -> None:
    settings = Settings(MODEL_DIR / "detector.pt", MODEL_DIR / "classifier.pth", "t" * 32)
    engine = InferenceEngine(settings)
    image = (REPO_ROOT / "apps" / "web" / "static" / "images" / "excavation-768.webp").read_bytes()
    result = engine.predict(image)
    assert result["schema"] == "sitewatch.inference.v1"
    assert any(
        detection["raw_class"] == "excavator" and detection["equipment_class"] == "excavator"
        for detection in result["detections"]
    )
