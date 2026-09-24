from pathlib import Path

import pytest
from PIL import Image

from sitewatch_ml.classifier_data import prepare_classifier_crops
from sitewatch_ml.config import PROJECT_ROOT, load_classifier_experiment_config
from sitewatch_ml.experiments import _macro_f1
from sitewatch_ml.io import read_json
from sitewatch_ml.models import CropAugmentation


def _detector_fixture(root: Path, invalid: bool = False) -> Path:
    root.mkdir()
    (root / "dataset.yaml").write_text("names: {0: dump_truck}\n", encoding="utf-8")
    for split in ("train", "val", "test"):
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        image_dir.mkdir(parents=True)
        label_dir.mkdir(parents=True)
        Image.new("RGB", (100, 100), (100, 120, 140)).save(image_dir / "frame.jpg")
        (label_dir / "frame.txt").write_text(
            "0 0.3 0.3 0.3 0.3\n1 0.7 0.7 0.3 0.3\n" if not invalid else "0 1.5 0.5 0.4 0.4\n",
            encoding="utf-8",
        )
    return root


def test_classifier_crops_only_augment_train_and_are_deterministic(tmp_path: Path) -> None:
    detector = _detector_fixture(tmp_path / "detector")
    config = CropAugmentation(variants_per_train_crop=2)
    first = prepare_classifier_crops(detector, tmp_path / "classifier", config, seed=42)
    records = read_json(first / "crop-manifest.json")
    assert len(records) == 10
    assert [record["augmentation"] for record in records if record["split"] == "val"] == [
        "none",
        "none",
    ]
    generated = sorted((first / "train" / "dump_truck").glob("*.jpg"))
    before = [path.read_bytes() for path in generated]
    second = prepare_classifier_crops(detector, tmp_path / "classifier", config, seed=42)
    assert before == [
        path.read_bytes() for path in sorted((second / "train" / "dump_truck").glob("*.jpg"))
    ]


def test_classifier_crops_reject_invalid_boxes_without_touching_existing_output(
    tmp_path: Path,
) -> None:
    detector = _detector_fixture(tmp_path / "detector", invalid=True)
    output = tmp_path / "classifier"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("kept", encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_classifier_crops(detector, output, CropAugmentation(), seed=1)
    assert sentinel.read_text(encoding="utf-8") == "kept"


def test_macro_f1_rejects_missing_classes() -> None:
    assert _macro_f1([[8, 2], [1, 9]]) == pytest.approx((16 / 19 + 18 / 21) / 2)
    assert _macro_f1([[2, 0], [0, 0]]) is None


def test_classifier_experiment_config_is_separate_from_detector_config() -> None:
    config = load_classifier_experiment_config(
        PROJECT_ROOT / "config" / "experiments" / "classifier-baseline.yaml"
    )
    assert config.base_model.endswith("-cls.pt")
    assert config.augmentation.variants_per_train_crop == 2
    assert config.macro_f1_gate_min > 0
