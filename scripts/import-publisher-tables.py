#!/usr/bin/env python3
"""Import ESD and POEM tables from the publisher HTML DOM."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover
    raise SystemExit("beautifulsoup4 is required") from exc


ROOT = Path(__file__).resolve().parent.parent


def clean(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\u200a", " ").replace("CO 2", "CO2")
    value = re.sub(r"\[\s+(\d+)\s+\]", r"[\1]", value)
    return re.sub(r"\s+", " ", value).strip()


def row_cells(row) -> list[str]:
    values = []
    for cell in row.find_all(["th", "td"], recursive=False):
        # Superscripts in these tables are footnote markers, not cell content.
        clone = BeautifulSoup(str(cell), "html.parser")
        for marker in clone.find_all("sup"):
            marker.decompose()
        values.append(clean(clone.get_text(" ", strip=True)))
    return values


def table_document(
    slug: str,
    lineage: str,
    doi: str,
    number: int,
    wrapper,
    columns: list[str],
    header_rows: int,
    column_source_span: str | None = None,
) -> dict:
    table = wrapper.find("table")
    caption_node = table.find("caption")
    title_node = caption_node.find(["h2", "h3", "h4"]) if caption_node else None
    caption = clean(caption_node.get_text(" ", strip=True)) if caption_node else f"Table {number}"
    caption = re.sub(rf"^Table\s*{number}\s*", "", caption, flags=re.I)
    rows = []
    for row in table.find_all("tr")[header_rows:]:
        physical_cells = row.find_all(["th", "td"], recursive=False)
        values = row_cells(row)
        if not values:
            continue
        row_spans = [int(cell.get("rowspan", 1)) for cell in physical_cells]
        col_spans = [int(cell.get("colspan", 1)) for cell in physical_cells]
        rows.append(
            {
                "cells": [{"en": value} for value in values],
                "isGroupHeader": len(values) <= 2 and sum(col_spans) >= len(columns),
                "rowSpans": row_spans,
                "colSpans": col_spans,
            }
        )
    document = {
        "$schema": "https://schema.evideris.com/schemas/table.schema.json",
        "$id": f"https://schema.evideris.com/esge/table/{slug}/table-{number}.v1.0.0.json",
        "lineageId": f"table-{slug}-{number}",
        "type": "table",
        "version": "1.0.0",
        "release": "r2026.07",
        "supersedes": None,
        "supersededBy": None,
        "language": ["en"],
        "withinCurriculum": lineage,
        "number": str(number),
        "title": {"en": f"Table {number} {caption}"},
        "columns": [{"header": {"en": column}} for column in columns],
        "rows": rows,
        "_meta": {
            "provenance": {"type": "verbatim", "source_doi": doi},
            "encodedBy": "other:codex-publisher-dom-import",
            "encodedAt": "2026-08-09",
        },
    }
    if column_source_span:
        document["_meta"]["fieldProvenance"] = {
            "columns[*].header.en": {
                "type": "paraphrased",
                "source_doi": doi,
                "source_span": column_source_span,
            }
        }
    return document


def write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esd", type=Path, required=True)
    parser.add_argument("--poem", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    esd = BeautifulSoup(args.esd.read_text(), "html.parser")
    esd_wrappers = esd.select("div.tableWrapper")
    if len(esd_wrappers) != 1:
        raise SystemExit(f"ESD: expected 1 source table, found {len(esd_wrappers)}")
    documents = [
        (
            ROOT / "esge/table/esd/table-1.v1.0.0.json",
            table_document(
                "esd",
                "cur-esd-2019",
                "10.1055/a-0996-0912",
                1,
                esd_wrappers[0],
                ["List of recommendations for training in endoscopic submucosal dissection (ESD)."],
                0,
            ),
        )
    ]

    poem = BeautifulSoup(args.poem.read_text(), "html.parser")
    poem_wrappers = poem.select("div.tableWrapper")
    if len(poem_wrappers) != 4:
        raise SystemExit(f"POEM: expected 4 source tables, found {len(poem_wrappers)}")
    specs = [
        (
            1,
            ["Recommendation number", "Recommendation", "Quality of evidence; Strength of recommendation"],
            1,
            None,
        ),
        (2, ["POEM steps", "Electrosurgical settings"], 1, None),
        (
            3,
            [
                "Medication",
                "Low thrombotic risk — withdrawal",
                "Low thrombotic risk — resumption",
                "High thrombotic risk — withdrawal",
                "High thrombotic risk — resumption",
            ],
            2,
            "Medication Low thrombotic risk High thrombotic risk Withdrawal Resumption Withdrawal Resumption",
        ),
        (
            4,
            [
                "Component",
                "Component",
                "Possible responses and scoring",
                "Possible responses and scoring",
                "L",
                "V",
                "Recommendation number",
                "Maximum score",
            ],
            1,
            "Component Possible responses and scoring",
        ),
    ]
    for number, columns, header_rows, column_source_span in specs:
        documents.append(
            (
                ROOT / f"esge/table/poem-2/table-{number}.v1.0.0.json",
                table_document(
                    "poem-2",
                    "cur-poem-2-2025",
                    "10.1055/a-2569-7634",
                    number,
                    poem_wrappers[number - 1],
                    columns,
                    header_rows,
                    column_source_span,
                ),
            )
        )

    if args.write:
        for path, document in documents:
            write(path, document)
    print(
        json.dumps(
            {
                "write": args.write,
                "tables": [
                    {"path": str(path.relative_to(ROOT)), "rows": len(document["rows"])}
                    for path, document in documents
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
