"""Read-only acquisition audit. Never extract archives or admit data into training."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import stat
import sys
import warnings
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile, ZipInfo

from PIL import Image, ImageStat

from sitewatch_ml.audit import difference_hash
from sitewatch_ml.io import read_json, sha256_file, write_json

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
MAX_MEMBER_BYTES = 100 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 25 * 1024**3


def audit_signature(source: dict[str, Any]) -> str:
    source_json = json.dumps(source, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(Path(__file__).read_bytes() + source_json).hexdigest()


def validate_members(members: list[ZipInfo]) -> None:
    if len(members) > 100_000 or sum(m.file_size for m in members) > MAX_ARCHIVE_BYTES:
        raise ValueError("archive exceeds audit limits")
    seen: set[str] = set()
    for member in members:
        name = member.filename.replace("\\", "/")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or re.match(r"^[A-Za-z]:", name):
            raise ValueError("unsafe archive path")
        if stat.S_ISLNK(member.external_attr >> 16):
            raise ValueError("archive symlinks are not supported")
        if name in seen:
            raise ValueError("duplicate archive member name")
        seen.add(name)
        if member.file_size > MAX_MEMBER_BYTES:
            raise ValueError("archive member exceeds audit limit")


def read_text(archive: ZipFile, name: str) -> str:
    if archive.getinfo(name).file_size > MAX_TEXT_BYTES:
        raise ValueError("annotation/configuration exceeds text limit")
    return archive.read(name).decode("utf-8-sig")


def yolo_boxes(text: str, class_names: list[str]) -> list[dict[str, Any]]:
    boxes: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError("YOLO detection annotation must have five fields")
        class_id = int(fields[0])
        if not 0 <= class_id < len(class_names):
            raise ValueError("unknown source class ID")
        x, y, width, height = map(float, fields[1:])
        if not all(math.isfinite(v) for v in (x, y, width, height)):
            raise ValueError("non-finite bounding box")
        if not 0 < width <= 1 or not 0 < height <= 1:
            raise ValueError("invalid bounding box size")
        if min(x - width / 2, y - height / 2) < -1e-6:
            raise ValueError("bounding box crosses image boundary")
        if max(x + width / 2, y + height / 2) > 1 + 1e-6:
            raise ValueError("bounding box crosses image boundary")
        boxes.append({"class": class_names[class_id], "area_fraction": width * height})
    return boxes


def voc_boxes(text: str, width: int, height: int) -> list[dict[str, Any]]:
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("XML document types/entities are not allowed")
    root = ElementTree.fromstring(text)
    if root.tag != "annotation":
        raise ValueError("not a Pascal VOC annotation")
    if int(root.findtext("size/width", "0")) != width:
        raise ValueError("VOC width does not match image")
    if int(root.findtext("size/height", "0")) != height:
        raise ValueError("VOC height does not match image")
    result: list[dict[str, Any]] = []
    for obj in root.findall("object"):
        name = obj.findtext("name", "").strip()
        coords = [
            float(obj.findtext(f"bndbox/{key}", "nan")) for key in ("xmin", "ymin", "xmax", "ymax")
        ]
        x0, y0, x1, y1 = coords
        if not name or not all(math.isfinite(x) for x in coords):
            raise ValueError("invalid VOC class/coordinates")
        # Tolerate both common zero-based and one-based VOC boundary conventions.
        # This is a structural audit, not a coordinate conversion for training.
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError("VOC bounding box crosses image boundary")
        result.append({"class": name, "area_fraction": (x1 - x0) * (y1 - y0) / width / height})
    return result


def annotation_candidates(image: str, names: set[str]) -> list[str]:
    path = PurePosixPath(image)
    candidates: set[str] = set()
    for extension in (".txt", ".xml"):
        local = path.with_suffix(extension).as_posix()
        if local in names:
            candidates.add(local)
        parts = list(path.parts)
        for index, part in enumerate(parts):
            if part.lower() == "images":
                changed = parts.copy()
                changed[index] = "labels"
                counterpart = PurePosixPath(*changed).with_suffix(extension).as_posix()
                if counterpart in names:
                    candidates.add(counterpart)
    if candidates:
        return sorted(candidates)
    # VOC exports may separate annotation and image roots. Never select arbitrarily
    # when the source reuses a basename for different images or annotations.
    return sorted(
        n
        for n in names
        if PurePosixPath(n).stem == path.stem
        and PurePosixPath(n).suffix.lower() in {".txt", ".xml"}
    )


def inspect_image(payload: bytes) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            grayscale = image.convert("L")
            grayscale.thumbnail((128, 128))
            return {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "exif_orientation": image.getexif().get(274, 1),
                "dhash64": f"{difference_hash(image):016x}",
                "brightness_0_255": round(ImageStat.Stat(grayscale).mean[0], 3),
            }


def quantiles(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    result: dict[str, float] = {}
    for label, fraction in (("min", 0), ("p10", 0.1), ("p50", 0.5), ("p90", 0.9), ("max", 1)):
        position = (len(ordered) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        result[label] = round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 6)
    return result


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in records if r["image_status"] == "decoded"]
    boxes = [b for r in valid for b in r.get("boxes", [])]
    return {
        "image_count": len(records),
        "decoded_image_count": len(valid),
        "invalid_image_count": len(records) - len(valid),
        "annotation_status": dict(Counter(r["annotation_status"] for r in records)),
        "valid_box_count": len(boxes),
        "per_class_boxes": dict(sorted(Counter(b["class"] for b in boxes).items())),
        "per_class_images": dict(
            sorted(
                Counter(
                    name for r in valid for name in {b["class"] for b in r.get("boxes", [])}
                ).items()
            )
        ),
        "native_splits": dict(Counter(r.get("native_split", "unspecified") for r in records)),
        "width_px": quantiles([r["width"] for r in valid]),
        "height_px": quantiles([r["height"] for r in valid]),
        "brightness_0_255": quantiles([r["brightness_0_255"] for r in valid]),
        "bbox_area_fraction": quantiles([b["area_fraction"] for b in boxes]),
        "exif_orientation_counts": dict(Counter(str(r["exif_orientation"]) for r in valid)),
        "rotated_or_mirrored_exif_count": sum(r["exif_orientation"] in range(2, 9) for r in valid),
        "invalid_exif_orientation_count": sum(
            r["exif_orientation"] not in range(1, 9) for r in valid
        ),
        "training_ready": False,
        "semantic_label_completeness": "not_reviewed",
        "interpretation": (
            "Structural validity is not semantic correctness. Missing labels are NOT background "
            "images. Brightness is not a weather/season classifier."
        ),
    }


def audit_archive(
    path: Path, source: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    class_names = list(source.get("class_names", []))
    with ZipFile(path) as archive:
        members = archive.infolist()
        validate_members(members)
        names = {m.filename for m in members if not m.is_dir()}
        class_files = sorted(n for n in names if PurePosixPath(n).name == "classes.txt")
        if not class_names and len(class_files) == 1:
            class_names = [
                line.strip()
                for line in read_text(archive, class_files[0]).splitlines()
                if line.strip()
            ]
        images = sorted(n for n in names if PurePosixPath(n).suffix.lower() in IMAGE_EXTENSIONS)
        image_stems = Counter(PurePosixPath(n).stem for n in images)
        annotation_names = {n for n in names if PurePosixPath(n).suffix.lower() in {".txt", ".xml"}}
        matched_annotations: set[str] = set()
        for index, name in enumerate(images):
            record: dict[str, Any] = {
                "source": source["id"],
                "member": name,
                "image_status": "invalid",
                "annotation_status": "not_checked",
                "native_split": next(
                    (
                        p
                        for p in PurePosixPath(name).parts
                        if p in {"train", "val", "valid", "validation", "test"}
                    ),
                    "unspecified",
                ),
            }
            try:
                record.update(inspect_image(archive.read(name)))
                record["image_status"] = "decoded"
            except (
                OSError,
                ValueError,
                SyntaxError,
                Image.DecompressionBombError,
                Image.DecompressionBombWarning,
            ) as error:
                record["image_error"] = type(error).__name__
                records.append(record)
                continue
            candidates = annotation_candidates(name, annotation_names)
            if not candidates:
                record["annotation_status"] = "missing"
            elif len(candidates) > 1 or image_stems[PurePosixPath(name).stem] > 1:
                record["annotation_status"] = "ambiguous"
                record["annotation_candidates"] = candidates
            else:
                label = candidates[0]
                matched_annotations.add(label)
                record["annotation_member"] = label
                try:
                    text = read_text(archive, label)
                    boxes = (
                        voc_boxes(text, record["width"], record["height"])
                        if (label.lower().endswith(".xml"))
                        else yolo_boxes(text, class_names)
                    )
                    record["boxes"] = boxes
                    record["annotation_status"] = "valid_nonempty" if boxes else "valid_empty"
                except (ValueError, ElementTree.ParseError) as error:
                    record["annotation_status"] = "invalid"
                    record["annotation_error"] = str(error)
            records.append(record)
            if (index + 1) % 500 == 0:
                sys.stderr.write(f"{source['id']}: {index + 1}/{len(images)} images audited\n")
        summary = summarize(records)
        summary.update(
            {
                "source": source["id"],
                "version": source.get("version"),
                "source_url": source["url"],
                "archive_sha256": sha256_file(path),
                "archive_bytes": path.stat().st_size,
                "uncompressed_bytes": sum(m.file_size for m in members),
                "class_names": class_names,
                "file_extensions": dict(Counter(PurePosixPath(n).suffix.lower() for n in names)),
                "unmatched_text_or_xml_count": len(annotation_names - matched_annotations),
                "admission": source["admission"],
                "declared_license": source["declared_license"],
                "audit_signature": audit_signature(source),
            }
        )
    return summary, records


def duplicate_report(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get(key):
            groups[record[key]].append(record)
    duplicate_groups = [g for g in groups.values() if len(g) > 1]
    return {
        "key": key,
        "group_count": len(duplicate_groups),
        "redundant_image_count": sum(len(g) - 1 for g in duplicate_groups),
        "cross_source_group_count": sum(
            len({r["source"] for r in g}) > 1 for g in duplicate_groups
        ),
        "cross_native_split_group_count": sum(
            len(
                {
                    r.get("native_split", "unspecified")
                    for r in g
                    if r.get("native_split", "unspecified") != "unspecified"
                }
            )
            > 1
            for g in duplicate_groups
        ),
        "groups": [
            [
                {
                    "source": r["source"],
                    "member": r["member"],
                    "native_split": r.get("native_split", "unspecified"),
                }
                for r in g
            ]
            for g in duplicate_groups
        ],
        "interpretation": (
            "Byte-identical files."
            if key == "sha256"
            else "Equal 64-bit dHash candidates only, NOT verified duplicates. "
            "Not an exhaustive near-duplicate or video-sequence analysis."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("ml/config/external-sources.json"))
    parser.add_argument("--root", type=Path, default=Path("data/ml/external"))
    parser.add_argument("--source", action="append", help="Limit to named sources")
    parser.add_argument(
        "--reuse", action="store_true", help="Reuse checksum-verified audit records"
    )
    parser.add_argument(
        "--organizer", type=Path, help="Include organizer images in duplicate checks"
    )
    parser.add_argument(
        "--summary-output", type=Path, help="Write aggregate-only versionable report"
    )
    args = parser.parse_args()
    registry = read_json(args.registry)
    sources = [s for s in registry["sources"] if not args.source or s["id"] in args.source]
    summaries: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for source in sources:
        directory = args.root / source["id"]
        archive_path = directory / "source.zip"
        report_path = directory / "audit.json"
        records_path = directory / "image-records.json"
        if not archive_path.exists():
            summaries.append(
                {
                    "source": source["id"],
                    "status": "not_downloaded",
                    "admission": source["admission"],
                }
            )
            continue
        cached = read_json(report_path) if args.reuse and report_path.exists() else None
        if (
            cached
            and records_path.exists()
            and cached.get("audit_signature") == audit_signature(source)
            and cached["archive_sha256"] == sha256_file(archive_path)
        ):
            summary, source_records = cached, read_json(records_path)
        else:
            summary, source_records = audit_archive(archive_path, source)
            write_json(report_path, summary)
            write_json(records_path, source_records)
        summaries.append(summary)
        records.extend(source_records)
        sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    if args.organizer:
        organizer_records: list[dict[str, Any]] = []
        for path in sorted(args.organizer.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                organizer_records.append(
                    {
                        "source": "organizer",
                        "member": path.relative_to(args.organizer).as_posix(),
                        "image_status": "decoded",
                        "annotation_status": "not_checked",
                        **inspect_image(path.read_bytes()),
                    }
                )
        summaries.append({"source": "organizer", **summarize(organizer_records)})
        records.extend(organizer_records)
    output: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": summaries,
        "byte_duplicates": duplicate_report(records, "sha256"),
        "perceptual_candidates": duplicate_report(records, "dhash64"),
    }
    write_json(args.root / "acquisition-audit.json", output)
    if args.summary_output:
        aggregate = {**output}
        for key in ("byte_duplicates", "perceptual_candidates"):
            aggregate[key] = {k: v for k, v in output[key].items() if k != "groups"}
        write_json(args.summary_output, aggregate)


if __name__ == "__main__":
    main()
