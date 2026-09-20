from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from sitewatch_ml.labeling import import_label_studio_export


def test_imports_label_studio_rectangle_as_yolo(tmp_path: Path) -> None:
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    Image.new("RGB", (100, 80), "black").save(images / "frame.png")
    export = tmp_path / "export.json"
    export.write_text(
        json.dumps(
            [
                {
                    "data": {"image": "/data/local-files/?d=frame.png"},
                    "meta": {"relative_path": "frame.png"},
                    "annotations": [
                        {
                            "id": 1,
                            "result": [
                                {
                                    "type": "rectanglelabels",
                                    "value": {
                                        "x": 10,
                                        "y": 20,
                                        "width": 30,
                                        "height": 40,
                                        "rectanglelabels": ["excavator"],
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    report = import_label_studio_export(export, images, labels, tmp_path / "report.json")

    assert report.annotation_count == 1
    assert report.missing_images == []
    assert (labels / "frame.txt").read_text(encoding="utf-8") == (
        "1 0.25000000 0.40000000 0.30000000 0.40000000\n"
    )


def test_rejects_unknown_class_without_replacing_existing_labels(tmp_path: Path) -> None:
    images = tmp_path / "images"
    labels = tmp_path / "labels"
    images.mkdir()
    labels.mkdir()
    Image.new("RGB", (100, 80), "black").save(images / "frame.png")
    (labels / "existing.txt").write_text("keep", encoding="utf-8")
    export = tmp_path / "export.json"
    export.write_text(
        json.dumps(
            [
                {
                    "meta": {"relative_path": "frame.png"},
                    "annotations": [
                        {
                            "result": [
                                {
                                    "type": "rectanglelabels",
                                    "value": {
                                        "x": 10,
                                        "y": 10,
                                        "width": 20,
                                        "height": 20,
                                        "rectanglelabels": ["spaceship"],
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid rectangle"):
        import_label_studio_export(export, images, labels, tmp_path / "report.json")

    assert (labels / "existing.txt").read_text(encoding="utf-8") == "keep"
