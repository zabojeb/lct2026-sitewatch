"""Render aggregate bbox quantiles as a standalone SVG, without image data or ML libraries."""
# ruff: noqa: RUF001
# Russian presentation labels intentionally use Cyrillic characters.

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("docs/external-data-audit.json"))
    parser.add_argument(
        "--output", type=Path, default=Path("docs/figures/external-object-scale.svg")
    )
    args = parser.parse_args()
    report = json.loads(args.input.read_text())
    sources = [s for s in report["sources"] if s.get("bbox_area_fraction")]
    labels = {
        "xyzyxzzxy-construction-equipment": "Construction equipment",
        "kartaviychert-arh-df": "arh-df / CCTV",
        "miniexcav-construction-machines": "miniexcav / веб-фото",
        "dataclusterlabs-construction-vehicle-images": "DataCluster / мобильные фото",
    }
    height = 270 + 100 * len(sources)

    def x(value: float) -> float:
        return 365 + (math.log10(max(value, 1e-6)) + 6) / 6 * 685

    def percent(value: float) -> str:
        return f"{value * 100:.3g}%"

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1320" height="{height}" '
        f'viewBox="0 0 1320 {height}" role="img" aria-labelledby="title description">',
        '<title id="title">Масштаб объекта в открытых датасетах</title>',
        '<desc id="description">Доля площади кадра, занимаемая одной валидной рамкой. '
        "Круг — медиана, отрезок — десятый и девяностый перцентили; "
        "это разброс объектов, не доверительный интервал. Логарифмическая шкала.</desc>",
        f'<rect width="1320" height="{height}" fill="#f7f7f2"/>',
        '<g font-family="Arial, sans-serif" fill="#1d2724">',
        '<text x="48" y="53" font-size="15" letter-spacing="2">SITEWATCH / DATA AUDIT</text>',
        '<text x="48" y="103" font-size="36" font-weight="700">'
        "Одна задача. Разный масштаб объектов.</text>",
        '<text x="48" y="137" font-size="18" fill="#53605b">'
        "Площадь bbox / площадь кадра · логарифмическая шкала · "
        "только структурно валидная разметка</text>",
    ]
    for power in range(-6, 1):
        pos = x(10**power)
        parts.extend(
            [
                f'<line x1="{pos:.2f}" x2="{pos:.2f}" y1="176" y2="{height - 125}" '
                'stroke="#d9dfd8"/>',
                f'<text x="{pos:.2f}" y="{height - 98}" text-anchor="middle" '
                f'font-size="15" fill="#53605b">{percent(10**power)}</text>',
            ]
        )
    for index, source in enumerate(sources):
        y = 219 + index * 100
        values = source["bbox_area_fraction"]
        title = html.escape(labels.get(source["source"], source["source"]))
        count = source["valid_box_count"]
        p10, median, p90 = (values[q] for q in ("p10", "p50", "p90"))
        parts.extend(
            [
                f'<text x="48" y="{y - 5}" font-size="20" font-weight="700">{title}</text>',
                f'<text x="48" y="{y + 21}" font-size="15" fill="#53605b">'
                f"{count:,} bbox · {source['image_count']:,} кадров</text>",
                f'<line x1="{x(p10):.2f}" x2="{x(p90):.2f}" y1="{y}" y2="{y}" '
                'stroke="#6b9682" stroke-width="7" stroke-linecap="round"/>',
                f'<circle cx="{x(median):.2f}" cy="{y}" r="9" fill="#153f31" '
                'stroke="#f7f7f2" stroke-width="2"/>',
                f'<text x="1095" y="{y + 6}" font-size="25" font-weight="700">'
                f"{percent(median)}</text>",
                f'<text x="1095" y="{y + 29}" font-size="14" fill="#53605b">медиана</text>',
            ]
        )
    parts.extend(
        [
            f'<text x="48" y="{height - 52}" font-size="16" fill="#53605b">'
            "● Медиана     ━ P10–P90 (не доверительный интервал)     "
            "Источник: внешний acquisition-аудит, 2026-09-21</text>",
            f'<text x="48" y="{height - 26}" font-size="14" fill="#53605b">'
            "Классовый состав источников различается. Это описательное сравнение доменов, "
            "не доказательство улучшения mAP.</text>",
            "</g></svg>",
        ]
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
