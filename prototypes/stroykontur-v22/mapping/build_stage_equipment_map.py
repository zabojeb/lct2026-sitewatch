#!/usr/bin/env python3
"""Parse the source Excel schedule and build auditable stage/equipment tables."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re

from stage_equipment_mapper import (
    EQUIPMENT_CLASSES,
    OFFICIAL_SOURCES,
    map_stage,
    profile_records,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_XLSX = ROOT / "Сводный перечень строительных работ_ЛТЦ.xlsx"


def fix_code(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.day in (10, 12):
            return f"{value.day}.{value.month}"
        return value.strftime("%Y-%m-%d")
    text = str(value).strip().rstrip(".")
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        month, day = int(match.group(2)), int(match.group(3))
        if day in (10, 12):
            return f"{day}.{month}"
    return text


def parse_excel(path: Path) -> list[dict]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - environment guidance
        raise SystemExit("Install openpyxl or run with the repository .venv: .venv/bin/python") from exc

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    values = list(sheet.iter_rows(values_only=True))
    object_names = list(values[2][2:])
    rows: list[dict] = []
    l1 = ""
    l2 = ""
    for row_number, values_row in enumerate(values[3:], start=4):
        code_value = values_row[0] if len(values_row) > 0 else None
        name_value = values_row[1] if len(values_row) > 1 else None
        if not name_value or not str(name_value).strip():
            continue
        name = str(name_value).strip()
        code = fix_code(code_value)
        parts = [p for p in code.split(".") if p]
        if code in {"10", "12"}:
            l1, l2 = name, ""
            level = 1
        elif len(parts) == 2 and parts[0] in {"10", "12"}:
            l2 = name
            level = 2
        elif code:
            level = 3
        else:
            level = 4

        objects = []
        for offset, object_name in enumerate(object_names, start=2):
            value = values_row[offset] if len(values_row) > offset else None
            if object_name and value not in (None, "", 0, False):
                objects.append(str(object_name).strip())
        rows.append(
            {
                "row": row_number,
                "code": code,
                "name": name,
                "level_guess": level,
                "l1": l1,
                "l2": l2 or None,
                "n_obj": len(objects),
                "objs": objects,
                "all_obj": bool(object_names) and len(objects) == len([x for x in object_names if x]),
            }
        )
    return rows


def build_rows(parsed: list[dict]) -> list[dict]:
    output = []
    for row in parsed:
        mapped = map_stage(row["name"], l1=row.get("l1") or "", l2=row.get("l2") or "")
        output.append({**row, **mapped})
    return output


def join(values) -> str:
    return ", ".join(values)


def join_any(groups) -> str:
    return " | ".join(" ИЛИ ".join(group) for group in groups)


def write_outputs(rows: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    parsed_path = output_dir / "works_parsed.json"
    parsed_fields = ("row", "code", "name", "level_guess", "l1", "l2", "n_obj", "objs", "all_obj")
    parsed_path.write_text(
        json.dumps([{k: row[k] for k in parsed_fields} for row in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    payload = {
        "schema_version": 2,
        "classes": EQUIPMENT_CLASSES,
        "n": len(rows),
        "n_camera_control": sum(bool(r["camera_control"]) for r in rows),
        "n_needs_review": sum(r["match_status"] == "needs_review" for r in rows),
        "methodology": (
            "Название этапа нормализуется и сопоставляется с технологическим профилем. "
            "Контекст l1/l2 применяется только для снятия неоднозначности. required проверяется "
            "в пределах observation_window_minutes; required_any означает наличие хотя бы одного "
            "класса; optional разрешён, но его отсутствие не вызывает предупреждение. Неизвестный "
            "этап получает needs_review, а не фиктивный набор техники."
        ),
        "official_sources": OFFICIAL_SOURCES,
        "profiles": profile_records(),
        "rows": rows,
    }
    (output_dir / "stage_equipment_map.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    columns = [
        "row", "code", "l1", "l2", "name", "profile_id", "profile_name",
        "match_status", "confidence", "required", "required_any", "optional",
        "camera_control", "observation_window_minutes", "gesn_tables", "source_refs",
        "rule_id", "reason", "note",
    ]
    with (output_dir / "stage_equipment_map.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record["required"] = join(row["required"])
            record["required_any"] = join_any(row["required_any"])
            record["optional"] = join(row["optional"])
            record["camera_control"] = "yes" if row["camera_control"] else "no"
            record["gesn_tables"] = join(row["gesn_tables"])
            record["source_refs"] = join(row["source_refs"])
            writer.writerow(record)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="source schedule")
    parser.add_argument("--output-dir", type=Path, default=ROOT, help="directory for JSON/CSV outputs")
    parser.add_argument("--stage", help="classify one new stage instead of rebuilding the table")
    parser.add_argument("--l1", default="", help="level-1 context for --stage")
    parser.add_argument("--l2", default="", help="level-2 context for --stage")
    args = parser.parse_args()

    if args.stage:
        print(json.dumps(map_stage(args.stage, l1=args.l1, l2=args.l2), ensure_ascii=False, indent=2))
        return

    parsed = parse_excel(args.xlsx)
    rows = build_rows(parsed)
    write_outputs(rows, args.output_dir)
    from collections import Counter
    print("rows", len(rows))
    print("camera_control", sum(r["camera_control"] for r in rows))
    print("needs_review", sum(r["match_status"] == "needs_review" for r in rows))
    print("profiles")
    for profile_id, count in Counter(r["profile_id"] for r in rows).most_common():
        print(f"  {count:3} {profile_id}")


if __name__ == "__main__":
    main()
