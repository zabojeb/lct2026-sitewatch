from __future__ import annotations

import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from sitewatch_ml.audit import IMAGE_SUFFIXES
from sitewatch_ml.io import read_json, write_json
from sitewatch_ml.models import BoundingBox, EquipmentClass, LabelImportReport


def create_label_studio_tasks(image_dir: Path, output_path: Path) -> list[dict[str, object]]:
    image_paths = sorted(
        path
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    tasks: list[dict[str, object]] = []
    for image_path in image_paths:
        relative_path = image_path.relative_to(image_dir).as_posix()
        tasks.append(
            {
                "data": {"image": f"/data/local-files/?d={relative_path}"},
                "meta": {"relative_path": relative_path, "source": "organizer"},
            }
        )
    write_json(output_path, tasks)
    return tasks


def import_label_studio_export(
    export_path: Path,
    image_dir: Path,
    output_dir: Path,
    report_path: Path,
    canonical_export_path: Path | None = None,
) -> LabelImportReport:
    """Convert a Label Studio JSON export to an atomically replaced YOLO label set."""
    payload = read_json(export_path)
    if not isinstance(payload, list):
        raise ValueError("Label Studio export must be a JSON array")

    image_paths = {
        path.relative_to(image_dir).as_posix(): path
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    }
    seen: set[str] = set()
    class_counts = {equipment: 0 for equipment in EquipmentClass}
    annotation_count = 0
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".label-import-", dir=output_dir.parent))
    try:
        for task_index, task in enumerate(payload):
            if not isinstance(task, dict):
                raise ValueError(f"task {task_index}: expected an object")
            relative_path = _task_relative_path(task, task_index)
            if relative_path in seen:
                raise ValueError(f"task {task_index}: duplicate image {relative_path}")
            if relative_path not in image_paths:
                raise ValueError(f"task {task_index}: unknown image {relative_path}")
            seen.add(relative_path)

            annotation = _select_annotation(task, task_index)
            lines: list[str] = []
            for result_index, result in enumerate(annotation.get("result", [])):
                parsed = _parse_rectangle(result, task_index, result_index)
                if parsed is None:
                    continue
                equipment, box = parsed
                class_id = list(EquipmentClass).index(equipment)
                lines.append(
                    f"{class_id} {box.center_x:.8f} {box.center_y:.8f} "
                    f"{box.width:.8f} {box.height:.8f}"
                )
                class_counts[equipment] += 1
                annotation_count += 1

            label_path = staging / f"{image_paths[relative_path].stem}.txt"
            label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

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

    report = LabelImportReport(
        task_count=len(payload),
        image_count=len(image_paths),
        imported_image_count=len(seen),
        annotation_count=annotation_count,
        missing_images=sorted(set(image_paths) - seen),
        class_counts=class_counts,
    )
    if canonical_export_path is not None:
        write_json(canonical_export_path, payload)
    write_json(report_path, report)
    return report


def _task_relative_path(task: dict[str, Any], task_index: int) -> str:
    meta = task.get("meta")
    candidate = meta.get("relative_path") if isinstance(meta, dict) else None
    if not isinstance(candidate, str):
        data = task.get("data")
        image_url = data.get("image") if isinstance(data, dict) else None
        if not isinstance(image_url, str):
            raise ValueError(f"task {task_index}: image path is missing")
        values = parse_qs(urlparse(image_url).query).get("d", [])
        candidate = values[0] if len(values) == 1 else None
    if not candidate:
        raise ValueError(f"task {task_index}: image path is missing")
    normalized = PurePosixPath(candidate)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"task {task_index}: unsafe image path")
    return normalized.as_posix()


def _select_annotation(task: dict[str, Any], task_index: int) -> dict[str, Any]:
    annotations = task.get("annotations")
    if not isinstance(annotations, list):
        raise ValueError(f"task {task_index}: annotations list is missing")
    completed = [
        item
        for item in annotations
        if isinstance(item, dict) and not bool(item.get("was_cancelled", False))
    ]
    if not completed:
        raise ValueError(f"task {task_index}: no completed annotation")
    ground_truth = [item for item in completed if bool(item.get("ground_truth", False))]
    candidates = ground_truth or completed
    return max(candidates, key=lambda item: str(item.get("updated_at", item.get("id", ""))))


def _parse_rectangle(
    result: object,
    task_index: int,
    result_index: int,
) -> tuple[EquipmentClass, BoundingBox] | None:
    if not isinstance(result, dict):
        raise ValueError(f"task {task_index}, result {result_index}: expected an object")
    if result.get("type") != "rectanglelabels":
        return None
    value = result.get("value")
    if not isinstance(value, dict):
        raise ValueError(f"task {task_index}, result {result_index}: value is missing")
    labels = value.get("rectanglelabels")
    if not isinstance(labels, list) or len(labels) != 1 or not isinstance(labels[0], str):
        raise ValueError(f"task {task_index}, result {result_index}: expected one class")
    if float(value.get("rotation", 0.0)) != 0.0:
        raise ValueError(f"task {task_index}, result {result_index}: rotated boxes are unsupported")
    try:
        equipment = EquipmentClass(labels[0])
        left = float(value["x"]) / 100.0
        top = float(value["y"]) / 100.0
        width = float(value["width"]) / 100.0
        height = float(value["height"]) / 100.0
        box = BoundingBox(
            center_x=left + width / 2,
            center_y=top + height / 2,
            width=width,
            height=height,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise ValueError(f"task {task_index}, result {result_index}: invalid rectangle") from error
    return equipment, box
