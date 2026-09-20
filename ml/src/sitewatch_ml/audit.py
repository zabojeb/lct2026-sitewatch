from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from sitewatch_ml.io import dataset_fingerprint, sha256_file, write_json
from sitewatch_ml.models import (
    Annotation,
    BoundingBox,
    DatasetQualityReport,
    EquipmentClass,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def audit_dataset(
    image_dir: Path,
    annotation_dir: Path,
    report_path: Path,
    *,
    near_duplicate_distance: int = 4,
) -> DatasetQualityReport:
    image_paths = sorted(
        path
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    hashes: dict[Path, str] = {}
    perceptual_hashes: dict[Path, int] = {}
    image_modes: Counter[str] = Counter()
    widths: list[int] = []
    heights: list[int] = []
    invalid_images: list[str] = []
    invalid_annotations: list[str] = []
    class_counts: Counter[EquipmentClass] = Counter()
    labeled_images = 0
    annotation_count = 0

    for image_path in image_paths:
        relative_path = image_path.relative_to(image_dir).as_posix()
        try:
            with Image.open(image_path) as image:
                image.load()
                widths.append(image.width)
                heights.append(image.height)
                image_modes[image.mode] += 1
                perceptual_hashes[image_path] = difference_hash(image)
            hashes[image_path] = sha256_file(image_path)
        except (UnidentifiedImageError, OSError):
            invalid_images.append(relative_path)
            continue

        label_path = annotation_dir / f"{image_path.stem}.txt"
        if not label_path.exists():
            continue
        labeled_images += 1
        try:
            annotations = parse_yolo_annotations(label_path)
            annotation_count += len(annotations)
            class_counts.update(annotation.equipment_class for annotation in annotations)
        except ValueError as error:
            invalid_annotations.append(f"{label_path.name}: {error}")

    exact_groups = _exact_duplicate_groups(image_dir, hashes)
    near_groups = _near_duplicate_groups(image_dir, perceptual_hashes, near_duplicate_distance)
    blockers: list[str] = []
    if not image_paths:
        blockers.append("dataset contains no supported images")
    if invalid_images:
        blockers.append(f"{len(invalid_images)} images cannot be decoded")
    if invalid_annotations:
        blockers.append(f"{len(invalid_annotations)} annotation files are invalid")
    if labeled_images != len(image_paths):
        blockers.append(f"annotation coverage is {labeled_images}/{len(image_paths)} images")
    if annotation_count == 0:
        blockers.append("dataset contains no bounding-box annotations")

    report = DatasetQualityReport(
        dataset_fingerprint=dataset_fingerprint(
            (path.relative_to(image_dir).as_posix(), digest) for path, digest in hashes.items()
        ),
        image_count=len(image_paths),
        readable_image_count=len(hashes),
        labeled_image_count=labeled_images,
        annotation_count=annotation_count,
        invalid_image_count=len(invalid_images),
        invalid_annotation_count=len(invalid_annotations),
        exact_duplicate_groups=exact_groups,
        near_duplicate_groups=near_groups,
        class_counts={equipment: class_counts[equipment] for equipment in EquipmentClass},
        image_modes=dict(sorted(image_modes.items())),
        width_range=(min(widths), max(widths)) if widths else None,
        height_range=(min(heights), max(heights)) if heights else None,
        training_ready=not blockers,
        blockers=blockers,
    )
    write_json(report_path, report)
    return report


def parse_yolo_annotations(path: Path) -> list[Annotation]:
    annotations: list[Annotation] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"line {line_number}: expected five fields")
        try:
            class_id = int(fields[0])
            box = BoundingBox(
                center_x=float(fields[1]),
                center_y=float(fields[2]),
                width=float(fields[3]),
                height=float(fields[4]),
            )
            equipment = list(EquipmentClass)[class_id]
            annotations.append(
                Annotation(class_id=class_id, equipment_class=equipment, bounding_box=box)
            )
        except (ValueError, IndexError, ValidationError) as error:
            raise ValueError(f"line {line_number}: invalid annotation") from error
    return annotations


def difference_hash(image: Image.Image, hash_size: int = 8) -> int:
    grayscale = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = grayscale.tobytes()
    value = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for column in range(hash_size):
            value = (value << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return value


def _exact_duplicate_groups(image_dir: Path, hashes: dict[Path, str]) -> list[list[str]]:
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for path, digest in hashes.items():
        groups[digest].append(path.relative_to(image_dir).as_posix())
    return sorted(sorted(group) for group in groups.values() if len(group) > 1)


def _near_duplicate_groups(
    image_dir: Path, perceptual_hashes: dict[Path, int], max_distance: int
) -> list[list[str]]:
    paths = sorted(perceptual_hashes)
    parent = list(range(len(paths)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(paths)):
        for right in range(left + 1, len(paths)):
            distance = (
                perceptual_hashes[paths[left]] ^ perceptual_hashes[paths[right]]
            ).bit_count()
            if distance <= max_distance:
                union(left, right)

    groups: defaultdict[int, list[str]] = defaultdict(list)
    for index, path in enumerate(paths):
        groups[find(index)].append(path.relative_to(image_dir).as_posix())
    return sorted(sorted(group) for group in groups.values() if len(group) > 1)
