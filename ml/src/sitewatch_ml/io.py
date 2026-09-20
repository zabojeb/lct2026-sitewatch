from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dataset_fingerprint(records: Iterable[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    for relative_path, content_hash in sorted(records):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_json(path: Path, payload: BaseModel | dict[str, Any] | list[Any]) -> None:
    value: Any = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, records: Iterable[BaseModel]) -> None:
    body = "".join(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n" for record in records
    )
    _atomic_write(path, body)


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def read_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    records: list[T] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if line.strip():
                try:
                    records.append(model.model_validate_json(line))
                except ValueError as error:
                    raise ValueError(f"invalid JSONL at {path}:{line_number}") from error
    return records


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
