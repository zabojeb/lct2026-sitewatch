from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from sitewatch_ml.audit import audit_dataset, parse_yolo_annotations


def test_audit_blocks_unlabeled_dataset(tmp_path: Path) -> None:
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    Image.new("RGB", (80, 60), "red").save(images / "frame.png")

    report = audit_dataset(images, labels, tmp_path / "report.json")

    assert report.image_count == 1
    assert report.labeled_image_count == 0
    assert report.training_ready is False
    assert "dataset contains no bounding-box annotations" in report.blockers


def test_audit_accepts_valid_yolo_annotation(tmp_path: Path) -> None:
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    Image.new("RGB", (80, 60), "red").save(images / "frame.png")
    (labels / "frame.txt").write_text("1 0.5 0.5 0.25 0.5\n", encoding="utf-8")

    report = audit_dataset(images, labels, tmp_path / "report.json")

    assert report.training_ready is True
    assert report.annotation_count == 1
    assert report.class_counts["excavator"] == 1


def test_annotation_outside_image_is_rejected(tmp_path: Path) -> None:
    label = tmp_path / "bad.txt"
    label.write_text("0 0.05 0.5 0.2 0.2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid annotation"):
        parse_yolo_annotations(label)
