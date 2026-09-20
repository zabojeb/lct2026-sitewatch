from __future__ import annotations

import io
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from sitewatch_ml.ingest import ingest_archive
from sitewatch_ml.io import read_jsonl
from sitewatch_ml.models import AssetRecord


def test_ingests_images_from_nested_archive_and_deduplicates(tmp_path: Path) -> None:
    red = _png_bytes((255, 0, 0))
    blue = _png_bytes((0, 0, 255))
    nested_buffer = io.BytesIO()
    with ZipFile(nested_buffer, "w") as nested:
        nested.writestr("site/red.png", red)
        nested.writestr("site/red-copy.png", red)
        nested.writestr("site/blue.png", blue)

    archive_path = tmp_path / "source.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("dataset.zip", nested_buffer.getvalue())
        archive.writestr("notes.txt", "ignored")

    output = tmp_path / "raw"
    manifest = tmp_path / "manifest.jsonl"
    records = ingest_archive(archive_path, output, manifest)

    assert len(records) == 2
    assert len(list(output.glob("*.png"))) == 2
    assert read_jsonl(manifest, AssetRecord) == records
    assert all(record.source_member.startswith("dataset.zip!") for record in records)


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(stream, format="PNG")
    return stream.getvalue()
