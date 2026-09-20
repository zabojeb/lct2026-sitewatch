from __future__ import annotations

from pathlib import Path

from PIL import Image

from sitewatch_ml.models import SplitConfig
from sitewatch_ml.split import create_split_manifest


def test_split_is_deterministic_and_keeps_duplicates_together(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    first = Image.new("RGB", (32, 32), "red")
    first.save(images / "a.png")
    first.save(images / "b.png")
    Image.new("RGB", (32, 32), "blue").save(images / "c.png")
    Image.new("RGB", (32, 32), "green").save(images / "d.png")
    config = SplitConfig(train=0.5, validation=0.25, test=0.25)

    first_manifest = create_split_manifest(images, tmp_path / "first.json", config, 42)
    second_manifest = create_split_manifest(images, tmp_path / "second.json", config, 42)

    first_assignments = {entry.relative_path: entry.split for entry in first_manifest.entries}
    second_assignments = {entry.relative_path: entry.split for entry in second_manifest.entries}
    assert first_assignments == second_assignments
    assert first_assignments["a.png"] == first_assignments["b.png"]


def test_split_ratios_must_sum_to_one() -> None:
    try:
        SplitConfig(train=0.8, validation=0.3, test=0.1)
    except ValueError as error:
        assert "split ratios must sum to 1" in str(error)
    else:
        raise AssertionError("invalid ratios were accepted")


def test_split_does_not_depend_on_absolute_dataset_path(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    for name, color in (("a.png", "red"), ("b.png", "blue"), ("c.png", "green")):
        Image.new("RGB", (32, 32), color).save(left / name)
        Image.new("RGB", (32, 32), color).save(right / name)
    config = SplitConfig(train=0.5, validation=0.25, test=0.25)

    left_manifest = create_split_manifest(left, tmp_path / "left.json", config, 42)
    right_manifest = create_split_manifest(right, tmp_path / "right.json", config, 42)

    assert left_manifest == right_manifest
