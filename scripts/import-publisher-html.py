#!/usr/bin/env python3
"""Repair curriculum recommendation artifacts from Thieme publisher HTML.

The publisher DOM preserves recommendation boxes, chapter headings, ordered
lists, and rationale boundaries.  This importer deliberately uses those DOM
relationships instead of linear PDF text, which can interleave two columns.

The command is intentionally write-gated.  Without ``--write`` it reports the
source coverage it would import and leaves the repository unchanged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from bs4 import BeautifulSoup, Tag
except ImportError as exc:  # pragma: no cover - authoring-only dependency
    raise SystemExit(
        "beautifulsoup4 is required for publisher HTML import: "
        "python3 -m pip install beautifulsoup4"
    ) from exc


ROOT = Path(__file__).resolve().parent.parent
ENCODED_AT = "2026-08-09"
ENCODED_BY = "other:codex-publisher-dom-import"


@dataclass(frozen=True)
class CurriculumConfig:
    slug: str
    doi: str
    curriculum_lineage: str
    section_for_number: dict[int, str]


CONFIGS = {
    "emr-colon": CurriculumConfig(
        slug="emr-colon",
        doi="10.1055/a-2077-0497",
        curriculum_lineage="cur-emr-colon-2023",
        section_for_number={
            **{n: "sec-emr-preadoption" for n in range(1, 3)},
            **{n: "sec-emr-knowledge" for n in range(3, 9)},
            **{n: "sec-emr-before-emr" for n in range(9, 16)},
            **{n: "sec-emr-during-emr" for n in range(16, 32)},
            **{n: "sec-emr-after-emr" for n in range(32, 35)},
            **{n: "sec-emr-surveillance" for n in range(35, 37)},
            37: "sec-emr-training",
            38: "sec-emr-lifelong-qi",
        },
    ),
    "esd": CurriculumConfig(
        slug="esd",
        doi="10.1055/a-0996-0912",
        curriculum_lineage="cur-esd-2019",
        section_for_number={
            **{n: "sec-esd-skills-competence" for n in range(1, 4)},
            **{n: "sec-esd-training" for n in range(4, 11)},
            **{n: "sec-esd-knowledge-competence" for n in range(11, 18)},
        },
    ),
    "poem-2": CurriculumConfig(
        slug="poem-2",
        doi="10.1055/a-2569-7634",
        curriculum_lineage="cur-poem-2-2025",
        section_for_number={
            **{n: "sec-poem-2-preparation" for n in range(1, 9)},
            **{n: "sec-poem-2-cleaning-inspection" for n in range(9, 13)},
            **{n: "sec-poem-2-mucosal-incision" for n in range(13, 19)},
            **{n: "sec-poem-2-submucosal-tunneling" for n in range(19, 26)},
            **{n: "sec-poem-2-myotomy" for n in range(26, 35)},
            **{n: "sec-poem-2-mucosal-closure" for n in range(35, 37)},
            **{n: "sec-poem-2-adverse-events" for n in range(37, 44)},
            44: "sec-poem-2-technical-adaptations",
            **{n: "sec-poem-2-postoperative-care" for n in range(45, 49)},
        },
    ),
}


UNICODE_SPACES = "\u00a0\u2002\u2003\u2009\u200a\u202f"
ROMAN_RE = re.compile(r"^\(\s*([ivxlcdm]+)\s*\)\s*(.*)$", re.I)
LOA_RE = re.compile(r"^Level of agreement\s+(\d+)\s*%\.?$", re.I)
REFERENCE_HREF_RE = re.compile(r"^#JR\d+-(\d+)$")


def clean_text(node: Tag | str) -> str:
    source = node if isinstance(node, str) else node.get_text(" ", strip=True)
    for char in UNICODE_SPACES:
        source = source.replace(char, " ")
    source = re.sub(r"\s+", " ", source)
    source = re.sub(r"\[\s+", "[", source)
    source = re.sub(r"\s+\]", "]", source)
    source = re.sub(r"\(\s+", "(", source)
    source = re.sub(r"\s+\)", ")", source)
    source = re.sub(r"\s+([.,;:%])", r"\1", source)
    source = re.sub(r"([<>≤≥])\s+(\d)", r"\1\2", source)
    source = re.sub(r"\b(CO|O|H)\s+([234])\b", r"\1\2", source)
    source = source.replace("Table ", "Table ").replace("Fig. ", "Fig. ")
    return source.strip()


def refs_in(nodes: Iterable[Tag]) -> list[str]:
    numbers: set[int] = set()
    for node in nodes:
        for anchor in node.select("a[href]"):
            match = REFERENCE_HREF_RE.match(anchor.get("href", ""))
            if match:
                numbers.add(int(match.group(1)))
    return [f"ref-{number}" for number in sorted(numbers)]


def direct_segment(box: Tag, next_box: Tag | None) -> list[Tag]:
    nodes: list[Tag] = []
    sibling = box.next_sibling
    while sibling is not None and sibling is not next_box:
        if isinstance(sibling, Tag):
            nodes.append(sibling)
        sibling = sibling.next_sibling
    return nodes


def relevant_nodes_before_heading(nodes: list[Tag]) -> list[Tag]:
    out: list[Tag] = []
    for node in nodes:
        if node.name in {"h2", "h3", "h4"}:
            break
        out.append(node)
    return out


def grade_from_box(box: Tag) -> tuple[dict | None, int | None]:
    paragraphs = [clean_text(p) for p in box.select(".boxContent > p")]
    grade: dict | None = None
    loa: int | None = None
    for text in paragraphs[1:]:
        match = LOA_RE.match(text)
        if match:
            loa = int(match.group(1))
            continue
        lower = text.lower()
        if "good practice statement" in lower or "best practice recommendation" in lower:
            strength = "best-practice"
        elif "moderately strong recommendation" in lower:
            strength = "moderately-strong"
        elif "strong recommendation" in lower:
            strength = "strong"
        elif "weak recommendation" in lower:
            strength = "weak"
        else:
            continue

        if "very low quality" in lower:
            evidence = "very-low"
        elif "moderate quality" in lower:
            evidence = "moderate"
        elif "low quality" in lower:
            evidence = "low"
        elif "high quality" in lower:
            evidence = "high"
        else:
            evidence = "no-evidence-available"
        grade = {"strength": strength, "evidenceQuality": evidence}
    return grade, loa


def statement_from_box(box: Tag) -> str:
    paragraphs = box.select(".boxContent > p")
    if not paragraphs:
        raise ValueError("recommendation box has no statement paragraph")
    return clean_text(paragraphs[0])


def roman_value(value: str) -> int:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    previous = 0
    for character in reversed(value.lower()):
        current = values[character]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total


def append_sentence(parts: list[str], text: str) -> None:
    text = text.strip()
    if not text:
        return
    if parts and parts[-1].endswith(":"):
        parts.append(text[0].lower() + text[1:] if text else text)
    else:
        parts.append(text)


def emr_subitems(nodes: list[Tag], number: int) -> list[dict]:
    if number == 38:
        return []
    cap = 4 if number == 37 else None
    expected = 1
    current: dict | None = None
    current_parts: list[str] = []
    current_nodes: list[Tag] = []
    items: list[dict] = []
    started = False

    def finish() -> None:
        nonlocal current, current_parts, current_nodes
        if current is None:
            return
        current["text"] = {"en": " ".join(current_parts).strip()}
        item_refs = refs_in(current_nodes)
        if item_refs:
            current["references"] = item_refs
        items.append(current)
        current = None
        current_parts = []
        current_nodes = []

    for node in relevant_nodes_before_heading(nodes):
        if cap is not None and len(items) >= cap and current is None:
            break
        if node.name in {"ul", "ol"}:
            if current is not None:
                bullets = [clean_text(li) for li in node.find_all("li", recursive=False)]
                if bullets:
                    append_sentence(current_parts, "; ".join(bullets))
                    current_nodes.append(node)
            continue
        if node.name != "p":
            continue
        text = clean_text(node)
        if not text:
            continue
        if text.lower().startswith("comment "):
            finish()
            break
        label_match = ROMAN_RE.match(text)
        if label_match:
            label = label_match.group(1).lower()
            value = roman_value(label)
            if not started:
                if value != 1:
                    continue
                started = True
            if value != expected:
                finish()
                break
            finish()
            current = {"label": label}
            current_parts = [label_match.group(2).strip()]
            current_nodes = [node]
            expected += 1
            continue
        loa_match = LOA_RE.match(text)
        if loa_match and current is not None:
            current["levelOfAgreement"] = int(loa_match.group(1))
            current_nodes.append(node)
            finish()
            if cap is not None and len(items) >= cap:
                break
            continue
        if current is not None:
            append_sentence(current_parts, text)
            current_nodes.append(node)

    finish()
    return items[:cap] if cap is not None else items


def ordered_list_items(nodes: list[Tag]) -> list[dict]:
    for node in relevant_nodes_before_heading(nodes):
        if node.name != "ol":
            continue
        items = []
        for index, list_item in enumerate(node.find_all("li", recursive=False), start=1):
            item = {"label": str(index), "text": {"en": clean_text(list_item)}}
            references = refs_in([list_item])
            if references:
                item["references"] = references
            items.append(item)
        return items
    return []


def recommendation_boxes(soup: BeautifulSoup, slug: str) -> list[Tag]:
    boxes = soup.select("div.articleBox.backinfo")
    if boxes and "scope" in clean_text(boxes[0].select_one(".boxLabel") or "").lower():
        boxes = boxes[1:]
    expected = 38 if slug == "emr-colon" else 17 if slug == "esd" else 48
    if len(boxes) != expected:
        raise ValueError(f"{slug}: expected {expected} recommendation boxes, found {len(boxes)}")
    return boxes


def has_narrative_or_heading(nodes: list[Tag]) -> bool:
    return any(
        node.name in {"p", "ul", "ol", "h2", "h3", "h4"} and clean_text(node)
        for node in nodes
    )


def recommendation_groups(boxes: list[Tag]) -> list[tuple[list[int], list[Tag]]]:
    groups: list[tuple[list[int], list[Tag]]] = []
    pending: list[int] = []
    for index, box in enumerate(boxes):
        number = index + 1
        pending.append(number)
        next_box = boxes[index + 1] if index + 1 < len(boxes) else None
        segment = direct_segment(box, next_box)
        if has_narrative_or_heading(segment) or next_box is None:
            groups.append((pending, relevant_nodes_before_heading(segment)))
            pending = []
    if pending:
        groups.append((pending, []))
    return groups


def commentary_from_nodes(nodes: list[Tag]) -> str | None:
    paragraphs: list[str] = []
    for node in nodes:
        if node.name == "p":
            text = clean_text(node)
            if text and not LOA_RE.match(text):
                paragraphs.append(text)
    return "\n\n".join(paragraphs) if paragraphs else None


def load_existing(slug: str) -> dict[int, tuple[Path, dict]]:
    out: dict[int, tuple[Path, dict]] = {}
    for path in (ROOT / "esge/recommendation" / slug).glob("r*.v*.json"):
        document = json.loads(path.read_text())
        out[int(document["number"])] = (path, document)
    return out


def new_emr_r34(config: CurriculumConfig) -> tuple[Path, dict]:
    path = ROOT / "esge/recommendation/emr-colon/r34.v1.0.0.json"
    document = {
        "$schema": "https://schema.evideris.com/schemas/recommendation.schema.json",
        "$id": "https://schema.evideris.com/esge/recommendation/emr-colon/r34.v1.0.0.json",
        "lineageId": "rec-emr-cln-r34-situations-requiring-admission-hospital",
        "type": "recommendation",
        "version": "1.0.0",
        "release": "r2026.07",
        "supersedes": None,
        "supersededBy": None,
        "language": ["en"],
        "withinCurriculum": config.curriculum_lineage,
        "withinSection": config.section_for_number[34],
        "number": 34,
        "title": {"en": "Situations requiring admission to hospital"},
        "statement": {"en": "Pending publisher DOM import."},
        "references": [],
        "_meta": {
            "provenance": {"type": "verbatim", "source_doi": config.doi},
            "encodedBy": ENCODED_BY,
            "encodedAt": ENCODED_AT,
        },
    }
    return path, document


def repaired_base(document: dict, config: CurriculumConfig, number: int) -> dict:
    out = copy.deepcopy(document)
    out["withinCurriculum"] = config.curriculum_lineage
    out["withinSection"] = config.section_for_number[number]
    out["number"] = number
    out.pop("commentary", None)
    out.pop("commentaryForRecommendations", None)
    out.pop("subItems", None)
    out.pop("figureRefs", None)
    out.pop("tableRefs", None)
    out["references"] = []
    out["_meta"] = {
        "provenance": {"type": "verbatim", "source_doi": config.doi},
        "encodedBy": ENCODED_BY,
        "encodedAt": ENCODED_AT,
    }
    return out


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fidelity_fixture(slug: str, config: CurriculumConfig, repaired: dict[int, tuple[Path, dict]]) -> dict:
    recommendations = []
    for number in sorted(repaired):
        document = repaired[number][1]
        entry = {
            "number": number,
            "lineageId": document["lineageId"],
            "withinSection": document["withinSection"],
            "statementSha256": text_sha256(document["statement"]["en"]),
            "grade": document.get("grade"),
            "levelOfAgreement": document.get("levelOfAgreement"),
            "subItems": [
                {
                    "label": item["label"],
                    "textSha256": text_sha256(item["text"]["en"]),
                    "levelOfAgreement": item.get("levelOfAgreement"),
                }
                for item in document.get("subItems", [])
            ],
        }
        if document.get("commentary"):
            entry["commentary"] = {
                "forRecommendations": document.get("commentaryForRecommendations", [number]),
                "textSha256": text_sha256(document["commentary"]["en"]),
            }
        recommendations.append(entry)
    return {
        "schemaVersion": 1,
        "slug": slug,
        "sourceDoi": config.doi,
        "sourceUrl": f"https://www.thieme-connect.de/products/ejournals/html/{config.doi}",
        "extractionMethod": "publisher-html-dom",
        "reviewedAt": ENCODED_AT,
        "recommendations": recommendations,
    }


def import_curriculum(slug: str, html_path: Path, write: bool) -> dict:
    config = CONFIGS[slug]
    soup = BeautifulSoup(html_path.read_text(), "html.parser")
    boxes = recommendation_boxes(soup, slug)
    existing = load_existing(slug)
    if slug == "emr-colon" and 34 not in existing:
        existing[34] = new_emr_r34(config)

    repaired: dict[int, tuple[Path, dict]] = {}
    segments: dict[int, list[Tag]] = {}
    for index, box in enumerate(boxes):
        number = index + 1
        next_box = boxes[index + 1] if index + 1 < len(boxes) else None
        segments[number] = direct_segment(box, next_box)
        path, old = existing[number]
        document = repaired_base(old, config, number)
        statement = statement_from_box(box)
        grade, loa = grade_from_box(box)

        if slug == "emr-colon":
            label = clean_text(box.select_one(".boxLabel"))
            title = re.sub(r"^\d+\s+", "", label)
            title = title.replace("resction", "resection").replace("Determing", "Determining")
            statement = statement.replace("MR ESGE", "ESGE").replace("EGSE", "ESGE")
            document["title"] = {"en": title}
            document["statement"] = {"en": statement}
            if grade:
                if loa is not None:
                    grade["levelOfAgreement"] = loa
                document["grade"] = grade
            else:
                document.pop("grade", None)
            subitems = emr_subitems(segments[number], number)
            if subitems:
                document["subItems"] = subitems
            document["references"] = sorted(
                {ref for item in subitems for ref in item.get("references", [])},
                key=lambda ref: int(ref.split("-")[1]),
            )
        else:
            if slug == "poem-2" and number == 30:
                statement = statement.replace("postPOEM", "post-POEM")
            document["title"] = {"en": statement}
            document["statement"] = {"en": statement}
            if grade:
                document["grade"] = grade
            else:
                document.pop("grade", None)
            if loa is not None:
                document["levelOfAgreement"] = loa
            else:
                document.pop("levelOfAgreement", None)
        repaired[number] = (path, document)

    if slug in {"esd", "poem-2"}:
        for numbers, nodes in recommendation_groups(boxes):
            commentary = commentary_from_nodes(nodes)
            if commentary:
                final_number = numbers[-1]
                document = repaired[final_number][1]
                document["commentary"] = {"en": commentary}
                document["commentaryForRecommendations"] = numbers
                document["references"] = refs_in(nodes)

        if slug == "poem-2":
            r21_items = ordered_list_items(segments[21])
            if len(r21_items) != 4:
                raise ValueError(f"poem-2 R21: expected 4 ordered-list points, got {len(r21_items)}")
            repaired[21][1]["subItems"] = r21_items
            group_41_43 = next(nodes for numbers, nodes in recommendation_groups(boxes) if 42 in numbers)
            r42_items = ordered_list_items(group_41_43)
            if len(r42_items) != 5:
                raise ValueError(f"poem-2 R42: expected 5 ordered-list points, got {len(r42_items)}")
            repaired[42][1]["subItems"] = r42_items
            repaired[37][1].pop("subItems", None)
            for number in (21, 42):
                document = repaired[number][1]
                document["references"] = sorted(
                    {
                        *document.get("references", []),
                        *{
                            ref
                            for item in document.get("subItems", [])
                            for ref in item.get("references", [])
                        },
                    },
                    key=lambda ref: int(ref.split("-")[1]),
                )

    if slug == "emr-colon":
        curriculum_path = ROOT / "esge/curriculum/emr-colon/v1.0.0.json"
        curriculum = json.loads(curriculum_path.read_text())
        curriculum["recommendations"] = [repaired[number][1]["lineageId"] for number in range(1, 39)]
        if write:
            write_json(curriculum_path, curriculum)

    if slug == "poem-2":
        curriculum_path = ROOT / "esge/curriculum/poem-2/v1.0.0.json"
        curriculum = json.loads(curriculum_path.read_text())
        for author in curriculum.get("publication", {}).get("authors", []):
            if author.get("name") == "Roy Soetikno":
                author["name"] = "Roy M. Soetikno"
        if write:
            write_json(curriculum_path, curriculum)

    if write:
        for number in sorted(repaired):
            path, document = repaired[number]
            write_json(path, document)
        write_json(
            ROOT / "audits" / f"{slug}.source-fidelity.json",
            fidelity_fixture(slug, config, repaired),
        )

    return {
        "slug": slug,
        "recommendations": len(repaired),
        "subItems": sum(len(document.get("subItems", [])) for _, document in repaired.values()),
        "commentaryBlocks": sum("commentary" in document for _, document in repaired.values()),
        "sections": len({document["withinSection"] for _, document in repaired.values()}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emr", type=Path, required=True, help="EMR publisher HTML")
    parser.add_argument("--esd", type=Path, required=True, help="ESD publisher HTML")
    parser.add_argument("--poem", type=Path, required=True, help="POEM Part II publisher HTML")
    parser.add_argument("--write", action="store_true", help="write repaired artifacts")
    args = parser.parse_args()

    paths = {"emr-colon": args.emr, "esd": args.esd, "poem-2": args.poem}
    for slug, path in paths.items():
        if not path.is_file():
            raise SystemExit(f"{slug}: source HTML not found at {path}")
    summaries = [import_curriculum(slug, path, args.write) for slug, path in paths.items()]
    print(json.dumps({"write": args.write, "curricula": summaries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
