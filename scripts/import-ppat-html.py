#!/usr/bin/env python3
"""Reconcile PPAT with publisher HTML Table 4."""
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
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def cells(row) -> list[str]:
    return [clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"], recursive=False)]


def rec_numbers(value: str) -> list[int]:
    value = value.strip()
    if not value or value.lower() == "none":
        return []
    out: list[int] = []
    for part in re.split(r",\s*", value):
        range_match = re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", part)
        if range_match:
            out.extend(range(int(range_match.group(1)), int(range_match.group(2)) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def recommendation_lineages() -> dict[int, str]:
    out = {}
    for path in (ROOT / "esge/recommendation/poem-2").glob("r*.json"):
        document = json.loads(path.read_text())
        out[int(document["number"])] = document["lineageId"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    soup = BeautifulSoup(args.html.read_text(), "html.parser")
    wrappers = soup.select("div.tableWrapper")
    if len(wrappers) < 4:
        raise SystemExit(f"Expected four POEM tables, found {len(wrappers)}")
    rows = [cells(row) for row in wrappers[3].find("table").find_all("tr")]
    lineages = recommendation_lineages()
    target_path = ROOT / "esge/cat/ppat.v1.0.0.json"
    document = json.loads(target_path.read_text())
    existing_items = document["items"]

    extracted: list[dict] = []
    domains: list[dict] = []
    current_domain: dict | None = None
    index = 1
    while index < len(rows):
        row = rows[index]
        if row and row[0] == "Overall PPAT":
            document["overallMaximumScore"] = int(row[-1])
            break
        if len(row) in {2, 3} and row[-1].isdigit() and not re.match(r"^[ivxlcdm\s]+$", row[0], re.I):
            current_domain = {
                "title": {"en": row[0]},
                "maximumScore": int(row[-1]),
                "itemLineageIds": [],
            }
            domains.append(current_domain)
            index += 1
            continue
        if len(row) != 8 or index + 1 >= len(rows) or len(rows[index + 1]) != 2:
            index += 1
            continue

        good_row = rows[index + 1]
        item_index = len(extracted)
        if item_index >= len(existing_items):
            raise SystemExit("Publisher table has more PPAT items than encoded JSON")
        existing = existing_items[item_index]
        component = re.sub(r"\s*(?:\[\s*5\s*\]|5)\s*$", "", row[1]).strip()
        is_optional = bool(re.search(r"(?:\[\s*5\s*\]|\s5)\s*$", row[1]))
        if clean(existing["label"]["en"]).lower() != component.lower():
            raise SystemExit(
                f"PPAT item {item_index + 1} label mismatch: {existing['label']['en']!r} vs {component!r}"
            )
        item = {
            "lineageId": existing["lineageId"],
            "label": {"en": component},
            "poorGuidance": {"en": row[3]},
            "guidance": {"en": good_row[1]},
            "applicability": {
                "live": "optional" if row[4] == "X" and is_optional else "mandatory" if row[4] == "X" else "not-applicable",
                "video": "optional" if row[5] == "X" and is_optional else "mandatory" if row[5] == "X" else "not-applicable",
            },
            "assessesRecommendations": [
                {"lineageId": lineages[number]} for number in rec_numbers(row[6])
            ],
        }
        extracted.append(item)
        if current_domain is None:
            raise SystemExit(f"PPAT item {item_index + 1} appears before a domain header")
        current_domain["itemLineageIds"].append(item["lineageId"])
        index += 2

    if len(extracted) != 29:
        raise SystemExit(f"Expected 29 PPAT items, extracted {len(extracted)}")
    if len(domains) != 8:
        raise SystemExit(f"Expected 8 PPAT domains, extracted {len(domains)}")

    document["scoringScale"] = {
        "kind": "ordinal",
        "levels": [
            {"value": 1, "label": {"en": "Very poor"}},
            {"value": 5, "label": {"en": "Very good"}},
        ],
    }
    document["items"] = extracted
    document["domains"] = domains
    document["scoringNotes"] = [
        {
            "en": "Possible total scores (denominators) per domain vary according to whether the procedure is assessed live or using video and the number of unfilled non-mandatory components."
        },
        {"en": "Non-mandatory component."},
    ]
    document["resourceUrls"] = [
        "https://academy.esge.com/en/pages/poem-curriculum-part-2-statement-video-links"
    ]
    document["_meta"]["encodedBy"] = "other:codex-publisher-dom-import"
    document["_meta"]["encodedAt"] = "2026-08-09"

    if args.write:
        target_path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "write": args.write,
                "items": len(extracted),
                "domains": len(domains),
                "overallMaximumScore": document.get("overallMaximumScore"),
                "poorAnchors": sum("poorGuidance" in item for item in extracted),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
