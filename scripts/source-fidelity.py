#!/usr/bin/env python3
"""Parent-aware deterministic checks against publisher-DOM audit fixtures."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_recommendations(slug: str) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for path in (ROOT / "esge/recommendation" / slug).glob("r*.v*.json"):
        document = json.loads(path.read_text())
        number = int(document["number"])
        if number in out:
            raise ValueError(f"{slug}: duplicate recommendation number R{number}")
        out[number] = document
    return out


def check_fixture(path: Path) -> list[str]:
    fixture = json.loads(path.read_text())
    slug = fixture["slug"]
    errors: list[str] = []
    actual = load_recommendations(slug)
    expected = {int(entry["number"]): entry for entry in fixture["recommendations"]}
    if set(actual) != set(expected):
        errors.append(
            f"recommendation numbers differ: expected {sorted(expected)}, got {sorted(actual)}"
        )

    for number in sorted(set(actual) & set(expected)):
        document = actual[number]
        entry = expected[number]
        prefix = f"R{number}"
        for field in ("lineageId", "withinSection"):
            if document.get(field) != entry.get(field):
                errors.append(
                    f"{prefix} {field}: expected {entry.get(field)!r}, got {document.get(field)!r}"
                )
        if sha256(document["statement"]["en"]) != entry["statementSha256"]:
            errors.append(f"{prefix} statement text differs from publisher-DOM fixture")
        if document.get("grade") != entry.get("grade"):
            errors.append(f"{prefix} grade differs from publisher-DOM fixture")
        if document.get("levelOfAgreement") != entry.get("levelOfAgreement"):
            errors.append(f"{prefix} top-level agreement differs from publisher-DOM fixture")

        actual_items = document.get("subItems", [])
        expected_items = entry.get("subItems", [])
        if len(actual_items) != len(expected_items):
            errors.append(
                f"{prefix} sub-item count: expected {len(expected_items)}, got {len(actual_items)}"
            )
        for index, (item, expected_item) in enumerate(zip(actual_items, expected_items), start=1):
            if item.get("label") != expected_item.get("label"):
                errors.append(
                    f"{prefix} sub-item {index} label: expected {expected_item.get('label')!r}, got {item.get('label')!r}"
                )
            if sha256(item["text"]["en"]) != expected_item["textSha256"]:
                errors.append(f"{prefix} sub-item {index} text differs from publisher-DOM fixture")
            if item.get("levelOfAgreement") != expected_item.get("levelOfAgreement"):
                errors.append(f"{prefix} sub-item {index} agreement differs from publisher-DOM fixture")

        expected_commentary = entry.get("commentary")
        actual_commentary = document.get("commentary")
        if expected_commentary is None and actual_commentary is not None:
            errors.append(f"{prefix} has commentary absent from publisher-DOM fixture")
        elif expected_commentary is not None:
            if not actual_commentary:
                errors.append(f"{prefix} is missing publisher-DOM commentary")
            else:
                if sha256(actual_commentary["en"]) != expected_commentary["textSha256"]:
                    errors.append(f"{prefix} commentary text differs from publisher-DOM fixture")
                if document.get("commentaryForRecommendations") != expected_commentary[
                    "forRecommendations"
                ]:
                    errors.append(f"{prefix} shared-commentary parent group differs from fixture")

    curriculum_files = list((ROOT / "esge/curriculum" / slug).glob("v*.json"))
    if len(curriculum_files) != 1:
        errors.append(f"expected one curriculum wrapper, found {len(curriculum_files)}")
    else:
        curriculum = json.loads(curriculum_files[0].read_text())
        expected_lineages = [expected[number]["lineageId"] for number in sorted(expected)]
        if curriculum.get("recommendations") != expected_lineages:
            errors.append("curriculum recommendation lineage order differs from fixture")

    references_files = list((ROOT / "esge/curriculum" / slug).glob("references*.json"))
    bibliography_ids: set[str] = set()
    if len(references_files) == 1:
        bibliography = json.loads(references_files[0].read_text())
        bibliography_ids = {entry["id"] for entry in bibliography.get("references", [])}
    for number, document in actual.items():
        cited = set(document.get("references", []))
        for item in document.get("subItems", []):
            cited.update(item.get("references", []))
        unresolved = sorted(cited - bibliography_ids)
        if unresolved:
            errors.append(f"R{number} has unresolved bibliography ids: {', '.join(unresolved)}")
    return [f"{slug}: {error}" for error in errors]


def main() -> int:
    fixtures = sorted((ROOT / "audits").glob("*.source-fidelity.json"))
    if not fixtures:
        print("source-fidelity: no publisher-DOM fixtures found")
        return 1
    errors: list[str] = []
    for fixture in fixtures:
        errors.extend(check_fixture(fixture))
    if errors:
        print(f"source-fidelity: FAIL ({len(errors)} issues)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"source-fidelity: OK ({len(fixtures)} curricula)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
