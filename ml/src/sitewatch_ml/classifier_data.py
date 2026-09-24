"""Build an independent equipment-crop classification dataset from admitted YOLO labels."""

from __future__ import annotations

import hashlib
import random
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from sitewatch_ml.io import write_json
from sitewatch_ml.models import BoundingBox, CropAugmentation, EquipmentClass


def prepare_classifier_crops(
    detector_dataset: Path,
    output_dir: Path,
    augmentation: CropAugmentation,
    seed: int,
) -> Path:
    """Crop only labeled objects; augment only train crops; preserve scene split boundaries."""
    if not (detector_dataset / "dataset.yaml").is_file():
        raise ValueError("detector dataset must pass the preparation gate first")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".classifier-crops-", dir=output_dir.parent))
    records: list[dict[str, str | int | float]] = []
    classes_by_split: dict[str, set[str]] = {split: set() for split in ("train", "val", "test")}
    try:
        for split in ("train", "val", "test"):
            images = detector_dataset / "images" / split
            labels = detector_dataset / "labels" / split
            if not images.is_dir() or not labels.is_dir():
                raise ValueError(f"missing prepared split: {split}")
            for image_path in sorted(images.iterdir()):
                if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    continue
                label_path = labels / f"{image_path.stem}.txt"
                if not label_path.is_file():
                    raise ValueError(f"missing label: {label_path}")
                with Image.open(image_path) as opened:
                    image = ImageOps.exif_transpose(opened).convert("RGB")
                for index, line in enumerate(label_path.read_text(encoding="utf-8").splitlines()):
                    if not line.strip():
                        continue
                    class_id, box = _parse_label(line)
                    label = list(EquipmentClass)[class_id].value
                    classes_by_split[split].add(label)
                    crop = _crop(image, box, augmentation.context_fraction)
                    digest = hashlib.sha256(
                        f"{split}:{image_path.name}:{index}:{line}".encode()
                    ).hexdigest()[:16]
                    destination = staging / split / label
                    destination.mkdir(parents=True, exist_ok=True)
                    original_name = f"{digest}.jpg"
                    crop.save(destination / original_name, quality=93)
                    records.append(
                        {
                            "split": split,
                            "class": label,
                            "source_image": image_path.name,
                            "source_label_line": index + 1,
                            "crop": str(Path(split) / label / original_name),
                            "augmentation": "none",
                        }
                    )
                    if split != "train":
                        continue
                    for variant in range(augmentation.variants_per_train_crop):
                        variant_seed = int.from_bytes(
                            hashlib.sha256(f"{seed}:{digest}:{variant}".encode()).digest()[:8],
                            byteorder="big",
                        )
                        transformed = _augment_crop(crop, augmentation, random.Random(variant_seed))
                        variant_name = f"{digest}-aug-{variant}.jpg"
                        transformed.save(destination / variant_name, quality=93)
                        records.append(
                            {
                                "split": split,
                                "class": label,
                                "source_image": image_path.name,
                                "source_label_line": index + 1,
                                "crop": str(Path(split) / label / variant_name),
                                "augmentation": "machine_crop",
                            }
                        )
        if not any(record["split"] == "train" for record in records):
            raise ValueError("classifier training split contains no labeled crops")
        for split in ("val", "test"):
            if not any(record["split"] == split for record in records):
                raise ValueError(f"classifier {split} split contains no labeled crops")
        if len(classes_by_split["train"]) < 2:
            raise ValueError("classifier requires at least two labeled equipment classes")
        if any(classes_by_split[split] != classes_by_split["train"] for split in ("val", "test")):
            raise ValueError("classifier train/val/test must cover the same equipment classes")
        write_json(staging / "crop-manifest.json", records)
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
    return output_dir


def _parse_label(line: str) -> tuple[int, BoundingBox]:
    parts = line.split()
    if len(parts) != 5:
        raise ValueError(f"expected five YOLO label fields, got: {line!r}")
    try:
        class_id = int(parts[0])
        values = [float(value) for value in parts[1:]]
    except ValueError as error:
        raise ValueError(f"invalid YOLO label: {line!r}") from error
    if not 0 <= class_id < len(EquipmentClass):
        raise ValueError(f"class id outside SiteWatch taxonomy: {class_id}")
    return class_id, BoundingBox(
        center_x=values[0], center_y=values[1], width=values[2], height=values[3]
    )


def _crop(image: Image.Image, box: BoundingBox, context: float) -> Image.Image:
    left = max(0, box.center_x - box.width * (0.5 + context))
    top = max(0, box.center_y - box.height * (0.5 + context))
    right = min(1, box.center_x + box.width * (0.5 + context))
    bottom = min(1, box.center_y + box.height * (0.5 + context))
    pixels = (
        round(left * image.width),
        round(top * image.height),
        round(right * image.width),
        round(bottom * image.height),
    )
    if pixels[2] - pixels[0] < 4 or pixels[3] - pixels[1] < 4:
        raise ValueError("labeled crop is too small for classification")
    return image.crop(pixels)


def _augment_crop(
    image: Image.Image, augmentation: CropAugmentation, generator: random.Random
) -> Image.Image:
    result = ImageEnhance.Brightness(image).enhance(
        generator.uniform(augmentation.brightness_min, augmentation.brightness_max)
    )
    result = ImageEnhance.Contrast(result).enhance(
        generator.uniform(augmentation.contrast_min, augmentation.contrast_max)
    )
    if generator.random() < augmentation.horizontal_flip_probability:
        result = ImageOps.mirror(result)
    if generator.random() < augmentation.blur_probability:
        result = result.filter(ImageFilter.GaussianBlur(radius=0.6))
    return result
