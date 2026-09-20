from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest
from PIL import Image

from sitewatch_ml.external_data import (
    annotation_candidates,
    audit_archive,
    duplicate_report,
    validate_members,
    voc_boxes,
    yolo_boxes,
)


@pytest.mark.parametrize("name", ["../escape.jpg", "/root.jpg", "C:\\secret.jpg"])
def test_rejects_unsafe_archive_paths(name: str) -> None:
    with pytest.raises(ValueError, match="unsafe"):
        validate_members([ZipInfo(name)])


def test_rejects_duplicate_archive_members() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        validate_members([ZipInfo("a.jpg"), ZipInfo("a.jpg")])


@pytest.mark.parametrize(
    "line",
    [
        "-1 .5 .5 .2 .2",
        "2 .5 .5 .2 .2",
        "0 nan .5 .2 .2",
        "0 .1 .5 .5 .2",
        "0 .5 .5 0 .2",
        "0 .5 .5 .2",
    ],
)
def test_rejects_invalid_yolo_boxes(line: str) -> None:
    with pytest.raises(ValueError):
        yolo_boxes(line, ["excavator"])


def test_preserves_source_taxonomy_and_empty_annotation() -> None:
    assert yolo_boxes("0 .5 .5 .2 .4", ["tractor"])[0]["class"] == "tractor"
    assert yolo_boxes("\n", ["tractor"]) == []


def test_rejects_xml_entities() -> None:
    with pytest.raises(ValueError, match="entities"):
        voc_boxes('<!DOCTYPE a [<!ENTITY x "test">]><annotation/>', 30, 30)


def test_voc_dimensions_and_boundaries() -> None:
    xml = """<annotation><size><width>30</width><height>20</height></size>
    <object><name>tractor</name><bndbox><xmin>0</xmin><ymin>0</ymin>
    <xmax>30</xmax><ymax>20</ymax></bndbox></object></annotation>"""
    assert voc_boxes(xml, 30, 20)[0]["area_fraction"] == 1
    with pytest.raises(ValueError, match="width"):
        voc_boxes(xml, 31, 20)


def test_candidate_lookup_preserves_ambiguity() -> None:
    assert annotation_candidates("train/images/a.jpg", {"train/labels/a.txt"}) == [
        "train/labels/a.txt"
    ]
    assert annotation_candidates("Images/a.jpg", {"a/a.xml", "b/a.xml"}) == ["a/a.xml", "b/a.xml"]


def test_archive_audit_does_not_treat_missing_labels_as_background(tmp_path: Path) -> None:
    image = io.BytesIO()
    Image.new("RGB", (30, 20), "orange").save(image, format="PNG")
    archive_path = tmp_path / "source.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("classes.txt", "excavator\n")
        archive.writestr("images/a.png", image.getvalue())
        archive.writestr("images/b.png", image.getvalue())
        archive.writestr("labels/a.txt", "0 .5 .5 .4 .4\n")
    source = {
        "id": "example",
        "version": "1",
        "url": "https://example.com/data",
        "admission": "pending",
        "declared_license": "unknown",
        "class_names": [],
    }
    summary, records = audit_archive(archive_path, source)
    assert summary["image_count"] == 2
    assert summary["decoded_image_count"] == 2
    assert summary["annotation_status"] == {"valid_nonempty": 1, "missing": 1}
    assert summary["per_class_boxes"] == {"excavator": 1}
    assert summary["training_ready"] is False
    assert duplicate_report(records, "sha256")["redundant_image_count"] == 1
    assert not (tmp_path / "images").exists()


def test_cross_source_and_native_split_duplicates() -> None:
    records = [
        {"source": "one", "member": "a", "sha256": "same", "native_split": "train"},
        {"source": "two", "member": "b", "sha256": "same", "native_split": "test"},
    ]
    result = duplicate_report(records, "sha256")
    assert result["cross_source_group_count"] == 1
    assert result["cross_native_split_group_count"] == 1
