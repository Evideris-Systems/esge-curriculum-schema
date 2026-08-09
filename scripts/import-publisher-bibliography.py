#!/usr/bin/env python3
"""Import clean numbered bibliographies from Thieme publisher HTML."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover
    raise SystemExit("beautifulsoup4 is required") from exc


ROOT = Path(__file__).resolve().parent.parent
UTILITY_LABELS = (
    " Crossref",
    " Thieme Connect",
    " PubMed",
    " Search in Google Scholar",
    " Download RIS citation",
)
DOI_CORRECTIONS = {
    # The publisher page links this O-POEM paper to an unrelated Wiley DOI.
    # PubMed 28859393 and the journal record give 10.1093/dote/dox070.
    ("poem-2", 110): "10.1093/dote/dox070",
}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ").replace("\u200a", " ")).strip()


def doi_from_li(li) -> str | None:
    for anchor in li.select("a[href]"):
        href = unquote(anchor.get("href", ""))
        if href.startswith("https://doi.org/"):
            return href.removeprefix("https://doi.org/").strip().lower()
        marker = "/products/all/doi/"
        if marker in href:
            return href.split(marker, 1)[1].strip().lower()
    return None


def extract(path: Path) -> dict[int, dict]:
    soup = BeautifulSoup(path.read_text(), "html.parser")
    found: dict[int, dict] = {}
    for anchor in soup.find_all("a", attrs={"name": re.compile(r"^JR\d+-\d+$")}):
        match = re.search(r"-(\d+)$", anchor.get("name", ""))
        if not match:
            continue
        number = int(match.group(1))
        if number in found:
            continue
        li = anchor.find_parent("li")
        if li is None:
            continue
        citation = clean(li.get_text(" ", strip=True))
        citation = re.sub(rf"^{number}\s+", "", citation)
        cut_positions = [citation.find(label) for label in UTILITY_LABELS if label in citation]
        if cut_positions:
            citation = citation[: min(cut_positions)].strip()
        doi = doi_from_li(li)
        entry = {"id": f"ref-{number}", "citation": citation}
        if doi:
            entry["doi"] = doi
        found[number] = entry
    if not found:
        raise ValueError(f"No numbered publisher references found in {path}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emr", type=Path, required=True)
    parser.add_argument("--esd", type=Path, required=True)
    parser.add_argument("--poem", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    paths = {"emr-colon": args.emr, "esd": args.esd, "poem-2": args.poem}
    counts = {}
    for slug, html_path in paths.items():
        target = ROOT / "esge/curriculum" / slug / "references.v1.0.0.json"
        document = json.loads(target.read_text())
        publisher_references = extract(html_path)
        existing = {int(entry["id"].split("-")[1]): entry for entry in document["references"]}
        if max(publisher_references) != max(existing):
            raise ValueError(
                f"{slug}: publisher maximum reference {max(publisher_references)} differs from encoded {max(existing)}"
            )
        # A few EMR website/book/video references are deliberately absent from
        # the publisher HTML bibliography DOM. Preserve those reviewed entries;
        # use clean publisher entries everywhere the DOM provides one.
        references = []
        for number in range(1, max(existing) + 1):
            # Keep manual DOI resolution and review annotations, while replacing
            # the formatted citation with the clean publisher-DOM version.
            entry = dict(existing[number])
            entry.update(publisher_references.get(number, {}))
            if (slug, number) in DOI_CORRECTIONS:
                entry["doi"] = DOI_CORRECTIONS[(slug, number)]
            references.append(entry)
        counts[slug] = len(references)
        document["references"] = references
        document["_meta"]["encodedBy"] = "other:codex-publisher-dom-import"
        document["_meta"]["encodedAt"] = "2026-08-09"
        if args.write:
            target.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"write": args.write, "counts": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
