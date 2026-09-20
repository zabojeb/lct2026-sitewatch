from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import yaml

from sitewatch_ml.io import read_json
from sitewatch_ml.models import DatasetQualityReport, EquipmentClass, SplitManifest


class TrainingNotReadyError(RuntimeError):
    """Raised when the dataset does not satisfy the training contract."""


def prepare_yolo_dataset(
    image_dir: Path,
    annotation_dir: Path,
    quality_report_path: Path,
    split_manifest_path: Path,
    output_dir: Path,
) -> Path:
    report = DatasetQualityReport.model_validate(read_json(quality_report_path))
    if not report.training_ready:
        raise TrainingNotReadyError("; ".join(report.blockers))
    manifest = SplitManifest.model_validate(read_json(split_manifest_path))
    if manifest.dataset_fingerprint != report.dataset_fingerprint:
        raise TrainingNotReadyError("quality report and split manifest describe different datasets")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".yolo-dataset-", dir=output_dir.parent))
    try:
        for entry in manifest.entries:
            source_image = image_dir / entry.relative_path
            source_label = annotation_dir / f"{source_image.stem}.txt"
            if not source_label.is_file():
                raise TrainingNotReadyError(f"missing annotation: {source_label}")
            target_split = "val" if entry.split == "validation" else entry.split
            target_image = staging / "images" / target_split / source_image.name
            target_label = staging / "labels" / target_split / source_label.name
            _link_or_copy(source_image, target_image)
            _link_or_copy(source_label, target_label)

        dataset_yaml = staging / "dataset.yaml"
        dataset_yaml.write_text(
            yaml.safe_dump(
                {
                    "path": str(output_dir.resolve()),
                    "train": "images/train",
                    "val": "images/val",
                    "test": "images/test",
                    "names": {index: item.value for index, item in enumerate(EquipmentClass)},
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        previous = output_dir.with_name(f".{output_dir.name}.previous")
        if previous.exists():
            shutil.rmtree(previous)
        if output_dir.exists():
            output_dir.replace(previous)
        staging.replace(output_dir)
        if previous.exists():
            shutil.rmtree(previous)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return output_dir / "dataset.yaml"


def _link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)
