#!/usr/bin/env python3
"""verify-citations.py — every references[].citation must resolve to a real DOI
or PMID via Crossref / OpenAlex / NCBI ID converter, with author surnames + year
matching the citation string.

Caches resolved metadata at .cache/citations/<doi-or-pmid>.json so we don't hit
external APIs on every CI run.

Usage:
    python3 scripts/verify-citations.py            # all artifacts under esge/
    python3 scripts/verify-citations.py path.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "citations"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


DOI_RE  = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20|21)\d{2}\b")
PMID_HINT_RE = re.compile(r"\bpmid[:\s]+(\d+)\b", re.IGNORECASE)


def extract_doi(citation: str) -> str | None:
    m = DOI_RE.search(citation)
    return m.group(1) if m else None


def extract_year(citation: str) -> int | None:
    years = YEAR_RE.findall(citation)
    return int(years[-1] + "00") if years and False else (int(years[-1] + "00") if False else (int(YEAR_RE.findall(citation)[0]) if YEAR_RE.search(citation) else None))


def first_author_surname(citation: str) -> str | None:
    """Heuristic: 'Burgess NG, Hourigan LF...' -> 'Burgess'."""
    m = re.match(r"\s*([A-Z][a-z]+(?:-[A-Z][a-z]+)?)\s+[A-Z]", citation.strip())
    return m.group(1) if m else None


def resolve_doi(doi: str) -> dict | None:
    """Resolve via Crossref. Cached."""
    cache_key = hashlib.sha256(doi.encode()).hexdigest()[:16] + "_" + re.sub(r"[^a-z0-9-]+", "-", doi.lower())[:80]
    cache_path = CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    try:
        r = requests.get(
            f"https://api.crossref.org/works/{doi}",
            timeout=15,
            headers={"User-Agent": "esge-curriculum-schema verify-citations (mailto:noreply@evideris.com)"},
        )
        if not r.ok:
            return None
        msg = r.json().get("message") or {}
        meta = {
            "doi": msg.get("DOI"),
            "title": (msg.get("title") or [""])[0],
            "year": (msg.get("issued", {}).get("date-parts") or [[None]])[0][0],
            "authors": [a.get("family") for a in msg.get("author", []) if a.get("family")],
            "container": (msg.get("container-title") or [""])[0],
        }
        cache_path.write_text(json.dumps(meta, indent=2))
        # Be polite to Crossref.
        time.sleep(0.05)
        return meta
    except requests.RequestException:
        return None


def verify_citation(ref_id: str, citation: str) -> list[str]:
    errs: list[str] = []
    doi = extract_doi(citation)
    pmid_m = PMID_HINT_RE.search(citation)
    if not doi and not pmid_m:
        return [f"{ref_id}: no DOI or PMID in citation string — citation must include one"]
    if not doi:
        return [f"{ref_id}: only PMID detected; PMID-only lookup not implemented yet — please add the DOI"]
    meta = resolve_doi(doi)
    if not meta:
        return [f"{ref_id}: DOI {doi} did not resolve via Crossref"]

    # Cross-check author + year.
    surname = first_author_surname(citation)
    yrs = YEAR_RE.findall(citation)
    citation_year = int(yrs[-1]) if yrs else None
    api_authors = [a.lower() for a in (meta.get("authors") or [])]
    if surname and api_authors and surname.lower() not in api_authors:
        # Allow surname-prefix matches (e.g. "Rivero" vs "Rivero-Sánchez").
        if not any(a.startswith(surname.lower()) or surname.lower().startswith(a) for a in api_authors):
            errs.append(f"{ref_id}: first-author surname '{surname}' not in Crossref author list {api_authors[:3]}")
    if citation_year and meta.get("year") and abs(citation_year - meta["year"]) > 1:
        errs.append(f"{ref_id}: citation year {citation_year} does not match Crossref year {meta['year']}")
    return errs


def verify_file(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"{path}: invalid JSON: {e}"]
    refs = data.get("references") or []
    errs: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        rid = ref.get("id", "?")
        citation = ref.get("citation", "")
        errs.extend(f"{path}: {e}" for e in verify_citation(rid, citation))
    return errs


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="verify-citations: every reference must be resolvable")
    p.add_argument("targets", nargs="*", help="JSON files to check (default: all under esge/ that have references[])")
    args = p.parse_args(argv)

    if args.targets:
        targets = [Path(t).resolve() for t in args.targets]
    else:
        targets = sorted(list((ROOT / "esge").rglob("*.json")))

    all_errors: list[str] = []
    files_checked = 0
    for path in targets:
        if not path.exists():
            continue
        # Skip files without references[]
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if not data.get("references"):
            continue
        files_checked += 1
        all_errors.extend(verify_file(path))

    print(f"verify-citations: checked {files_checked} files with references")
    if all_errors:
        for e in all_errors[:50]:
            print(f"  FAIL {e}")
        if len(all_errors) > 50:
            print(f"  ... and {len(all_errors) - 50} more")
        return 1
    print("  all references resolved cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
