#!/usr/bin/env python3
"""extract-bibliography.py — parse a cached source PDF text and produce a
references.v1.0.0.json file with every numbered citation resolved to a DOI
via Crossref bibliographic search.

This is a one-time helper used during Phase 3 source-canonical re-encoding
(and by the autoupdate skill in future). Output schema mirrors the
`references` array embedded in `curriculum`, but as a separate file so the
wrapper stays compact.

Usage:
    python3 scripts/extract-bibliography.py <source.txt> <curriculum_lineageId> <release_tag>
    # e.g.
    python3 scripts/extract-bibliography.py .cache/sources/10-1055-a-2077-0497.txt \\
        cur-emr-colon-2023 r2026.07
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent.parent
REF_CACHE = ROOT / ".cache" / "crossref-search"
REF_CACHE.mkdir(parents=True, exist_ok=True)


# Locate "References" section then parse numbered entries [N].
REFERENCES_START_RE = re.compile(r"^References\s*$", re.MULTILINE)
ENTRY_RE = re.compile(r"(?ms)^\[(\d+)\]\s(.+?)(?=^\[\d+\]|\Z)")


def normalise_citation(raw: str) -> str:
    """Clean PDF artefacts in a bibliography entry: hyphenation, whitespace."""
    s = re.sub(r"\s+", " ", raw)
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)
    return s.strip().rstrip(".")


def extract_entries(text: str) -> list[tuple[int, str]]:
    m = REFERENCES_START_RE.search(text)
    if not m:
        raise SystemExit("[extract-bibliography] No 'References' section found in source text.")
    bib = text[m.end():]
    out: list[tuple[int, str]] = []
    for em in ENTRY_RE.finditer(bib):
        n = int(em.group(1))
        body = normalise_citation(em.group(2))
        out.append((n, body))
    return out


def crossref_search(citation: str, retries: int = 2) -> dict | None:
    """Free-text bibliographic search via Crossref. Returns top match or None."""
    cache_key = re.sub(r"[^a-z0-9]+", "-", citation.lower())[:120]
    cache_path = REF_CACHE / f"{cache_key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    for attempt in range(retries + 1):
        try:
            r = requests.get(
                "https://api.crossref.org/works",
                params={"query.bibliographic": citation, "rows": 3},
                timeout=20,
                headers={"User-Agent": "esge-curriculum-schema (mailto:noreply@evideris.com)"},
            )
            if not r.ok:
                if r.status_code in (429, 500, 502, 503):
                    time.sleep(2 ** attempt)
                    continue
                return None
            items = ((r.json().get("message") or {}).get("items") or [])
            if not items:
                cache_path.write_text("null")
                return None
            best = items[0]
            meta = {
                "doi":       best.get("DOI"),
                "title":     (best.get("title") or [""])[0],
                "year":      (best.get("issued", {}).get("date-parts") or [[None]])[0][0],
                "authors":   [a.get("family") for a in best.get("author", []) if a.get("family")],
                "container": (best.get("container-title") or [""])[0],
                "score":     best.get("score"),
            }
            cache_path.write_text(json.dumps(meta, indent=2))
            time.sleep(0.05)  # polite to Crossref
            return meta
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None


def first_author_surname(citation: str) -> str | None:
    m = re.match(r"\s*([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+[A-Z]", citation.strip())
    return m.group(1) if m else None


def year_of(citation: str) -> int | None:
    years = re.findall(r"\b(?:19|20|21)\d{2}\b", citation)
    return int(years[-1]) if years else None


def confidence(citation: str, match: dict) -> tuple[float, list[str]]:
    """Return (0..1 confidence, list of issues)."""
    issues = []
    score = 1.0
    surname = first_author_surname(citation)
    if surname:
        api_authors = [a.lower() for a in (match.get("authors") or [])]
        if api_authors and not any(a.startswith(surname.lower()) or surname.lower().startswith(a) for a in api_authors):
            score -= 0.5
            issues.append(f"surname '{surname}' not in match authors {api_authors[:3]}")
    cy = year_of(citation)
    my = match.get("year")
    if cy and my and abs(cy - my) > 1:
        score -= 0.4
        issues.append(f"year {cy} vs match year {my}")
    return max(0.0, score), issues


def resolve(citation: str) -> dict:
    """Search Crossref + score confidence. Returns enriched dict ready for output."""
    match = crossref_search(citation)
    if not match or not match.get("doi"):
        return {"resolved": False, "citation": citation, "reason": "no match in Crossref"}
    conf, issues = confidence(citation, match)
    return {
        "resolved": True,
        "confidence": conf,
        "issues": issues,
        "doi": match["doi"],
        "match_title": match.get("title"),
        "match_year":  match.get("year"),
        "match_authors": match.get("authors"),
        "citation": citation,
    }


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Extract + resolve bibliography from cached source PDF")
    p.add_argument("source_text", help="Path to cached source PDF text")
    p.add_argument("curriculum_lineage", help="Curriculum lineageId (e.g. cur-emr-colon-2023)")
    p.add_argument("release", help="Release tag (e.g. r2026.07)")
    p.add_argument("--out", default=None, help="Output JSON path (default derived from lineageId)")
    p.add_argument("--source-doi", default=None, help="Source DOI for the _meta envelope")
    args = p.parse_args(argv)

    text_path = Path(args.source_text).expanduser().resolve()
    if not text_path.exists():
        raise SystemExit(f"[extract-bibliography] Source text not found: {text_path}")
    text = text_path.read_text()

    entries = extract_entries(text)
    print(f"[extract-bibliography] Found {len(entries)} bibliography entries", file=sys.stderr)

    references = []
    low_conf = []
    unresolved = []
    for n, citation in entries:
        result = resolve(citation)
        rid = f"ref-{n}"
        if not result["resolved"]:
            unresolved.append({"id": rid, "citation": citation})
            references.append({"id": rid, "citation": citation, "doi": None, "unresolved": True})
            continue
        cit_with_doi = citation
        if result["doi"] and result["doi"].lower() not in citation.lower():
            cit_with_doi = f"{citation}. doi:{result['doi']}"
        ref = {"id": rid, "citation": cit_with_doi, "doi": result["doi"]}
        if result["confidence"] < 0.7:
            ref["lowConfidence"] = True
            ref["confidenceIssues"] = result["issues"]
            low_conf.append({"id": rid, "issues": result["issues"], "citation": citation[:100]})
        references.append(ref)
        if n % 25 == 0:
            print(f"  ... resolved up to [{n}]", file=sys.stderr)

    # Determine output path.
    slug = args.curriculum_lineage.replace("cur-", "").replace("-2023", "").replace("-2024", "").replace("-2025", "").replace("-2026", "")
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = ROOT / "esge" / "curriculum" / slug / "references.v1.0.0.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = {
        "$schema": "https://schema.evideris.com/schemas/references.schema.json",
        "$id": f"https://schema.evideris.com/esge/curriculum/{slug}/references.v1.0.0.json",
        "lineageId": f"refs-{args.curriculum_lineage}",
        "type": "references",
        "version": "1.0.0",
        "release": args.release,
        "language": ["en"],
        "forCurriculum": args.curriculum_lineage,
        "_meta": {
            "provenance": {
                "type": "verbatim",
                "source_doi": args.source_doi or "unknown",
            },
            "encodedBy": "claude:esge-curriculum-autoupdate@v0.1.0",
            "encodedAt": "2026-06-27"
        },
        "references": references
    }
    out_path.write_text(json.dumps(doc, indent=2) + "\n")

    print(f"\n[extract-bibliography] Wrote {len(references)} references to {out_path}", file=sys.stderr)
    print(f"  Resolved: {sum(1 for r in references if r.get('doi'))}/{len(references)}", file=sys.stderr)
    print(f"  Low confidence: {len(low_conf)}", file=sys.stderr)
    print(f"  Unresolved: {len(unresolved)}", file=sys.stderr)
    if unresolved[:5]:
        print(f"\n  First few unresolved:", file=sys.stderr)
        for u in unresolved[:5]:
            print(f"    {u['id']}: {u['citation'][:120]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
