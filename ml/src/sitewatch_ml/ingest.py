from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from PIL import Image, UnidentifiedImageError

from sitewatch_ml.io import sha256_bytes, write_jsonl
from sitewatch_ml.models import AssetRecord

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
MAX_IMAGE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 100_000


class UnsafeArchiveError(ValueError):
    """Raised when an input archive violates extraction safety limits."""


def ingest_archive(archive_path: Path, output_dir: Path, manifest_path: Path) -> list[AssetRecord]:
    if not archive_path.is_file():
        raise FileNotFoundError(f"source archive does not exist: {archive_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    records_by_hash: dict[str, AssetRecord] = {}
    with ZipFile(archive_path) as archive:
        _validate_member_count(archive)
        for source_member, payload, suffix in _iter_images(archive):
            if len(payload) > MAX_IMAGE_BYTES:
                raise UnsafeArchiveError(f"image exceeds {MAX_IMAGE_BYTES} bytes: {source_member}")
            digest = sha256_bytes(payload)
            if digest in records_by_hash:
                continue

            try:
                with Image.open(io.BytesIO(payload)) as image:
                    image.verify()
                with Image.open(io.BytesIO(payload)) as image:
                    width, height = image.size
                    color_mode = image.mode
            except (UnidentifiedImageError, OSError) as error:
                raise ValueError(f"invalid image in archive: {source_member}") from error

            target = output_dir / f"{digest[:20]}{suffix.lower()}"
            if target.exists() and sha256_bytes(target.read_bytes()) != digest:
                raise FileExistsError(f"hash-named target contains different bytes: {target}")
            target.write_bytes(payload)
            records_by_hash[digest] = AssetRecord(
                asset_id=digest[:32],
                relative_path=target.relative_to(output_dir).as_posix(),
                source_member=source_member,
                sha256=digest,
                size_bytes=len(payload),
                width_px=width,
                height_px=height,
                color_mode=color_mode,
            )

    records = sorted(records_by_hash.values(), key=lambda record: record.relative_path)
    if not records:
        raise ValueError(f"no supported images found in {archive_path}")
    write_jsonl(manifest_path, records)
    return records


def _iter_images(archive: ZipFile, prefix: str = "") -> Iterator[tuple[str, bytes, str]]:
    for member in archive.infolist():
        if member.is_dir():
            continue
        safe_name = _safe_member_name(member)
        source_name = f"{prefix}{safe_name}"
        suffix = PurePosixPath(safe_name).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            yield source_name, archive.read(member), suffix
        elif suffix == ".zip":
            try:
                with ZipFile(io.BytesIO(archive.read(member))) as nested:
                    _validate_member_count(nested)
                    yield from _iter_images(nested, prefix=f"{source_name}!")
            except BadZipFile as error:
                raise ValueError(f"invalid nested archive: {source_name}") from error


def _safe_member_name(member: ZipInfo) -> str:
    path = PurePosixPath(member.filename.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise UnsafeArchiveError(f"unsafe archive member: {member.filename}")
    return path.as_posix()


def _validate_member_count(archive: ZipFile) -> None:
    if len(archive.infolist()) > MAX_ARCHIVE_MEMBERS:
        raise UnsafeArchiveError(f"archive has more than {MAX_ARCHIVE_MEMBERS} members")
