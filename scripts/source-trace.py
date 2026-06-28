#!/usr/bin/env python3
"""source-trace.py — every text-bearing field in source-canonical artifacts must
either grep-match the source PDF text, OR carry an explicit _meta.fieldProvenance
override declaring a `source_span` that itself grep-matches.

Source PDF text is cached at .cache/sources/<doi-slug>.txt keyed by DOI. The
cache is populated by the autoupdate skill's acquire stage.

Exits 0 if every checked field is source-traceable; non-zero otherwise.

Usage:
    python3 scripts/source-trace.py            # all artifacts under esge/
    python3 scripts/source-trace.py path.json  # one artifact
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "sources"

# Text-bearing fields per artifact type — paths use dot/bracket JSONPath-like syntax.
TEXT_PATHS = {
    "curriculum":     ["scope.en", "publication.title", "mainStatements[*].text.en", "sections[*].title.en", "disclaimer", "acknowledgments", "competingInterests[*].statement", "references[*].citation"],
    "recommendation": ["title.en", "statement.en", "subItems[*].text.en", "commentary.en"],
    "competency":     ["title.en", "description.en", "milestones[*].criteria.en"],
    "epa":            ["title.en", "description.en", "trustLevels[*].label.en"],
    "standard":       ["title.en", "text.en"],
    "scoringTool":    ["title.en", "description.en", "scale.bands[*].label.en", "inputs[*].label.en", "inputs[*].values[*].label.en"],
    "kpi":            ["title.en", "metric.en"],
    "qi":             ["title.en", "metric.en"],
    "cat":            ["title.en", "description.en", "items[*].label.en", "items[*].guidance.en"],
}


# --- PDF artefact normalisation ---

def normalise(s: str) -> str:
    """Strip PDF artefacts so a multi-line PDF span matches a clean schema string."""
    s = re.sub(r"\s+", " ", s)
    # Strip inline citation tags like [28] or [28, 33] or [59–61] — extractors
    # typically remove these from rec text, so source haystack must do likewise.
    # Handles ranges with en-dash (U+2013), em-dash (U+2014), or hyphen.
    s = re.sub(r"\s*\[\d+(?:[,\s\-–—]+\d+)*\]\s*", " ", s)
    # Join hyphenated line breaks: "pedun- culated" -> "pedunculated".
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)
    # Same for slash-line-break: "size/ type" -> "size/type".
    s = re.sub(r"(\w)/\s+(\w)", r"\1/\2", s)
    # Tighten orphaned punctuation introduced by citation/whitespace stripping.
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    # Strip ▶ glyph and similar.
    s = s.replace("▶", "").replace("–", "-").replace("—", "-")
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def grep_match(field_text: str, source_text: str) -> bool:
    """Substring match after normalisation. Tolerates minor whitespace/glyph
    differences. PDF hyphenation is genuinely ambiguous (line-break artifacts
    vs real compound-word hyphens), so we try in order:
      1. Standard normalisation (joins hyphen-at-line-break).
      2. Fallback: strip ALL hyphens from both sides — catches cases where
         the source PDF has 'through-\\nthe-scope' (joined to 'throughthe-scope')
         and the JSON has 'through-the-scope' (no change).
      3. 5-gram 70% threshold for paraphrased fragments."""
    if not field_text or not field_text.strip():
        return True
    needle = normalise(field_text)
    haystack = normalise(source_text)
    if needle in haystack:
        return True
    # Fallback: strip all hyphens (handles compound-word vs line-break ambiguity).
    needle_nh = needle.replace("-", "")
    haystack_nh = haystack.replace("-", "")
    if needle_nh in haystack_nh:
        return True
    # 5-gram fallback for paraphrased fragments.
    tokens = needle.split()
    if len(tokens) < 8:
        return False
    grams = [" ".join(tokens[i:i+5]) for i in range(0, len(tokens) - 4)]
    hits = sum(1 for g in grams if g in haystack)
    return hits / len(grams) >= 0.70


# --- JSONPath walker ---

def walk_path(obj, path: str):
    """Yield every value matching a JSONPath-like pattern.
    Supports dot-traversal and [*] (all list items)."""
    parts = re.findall(r"[^.\[\]]+|\[\*\]", path)
    def recurse(node, idx):
        if idx == len(parts):
            yield node
            return
        token = parts[idx]
        if token == "[*]":
            if isinstance(node, list):
                for item in node:
                    yield from recurse(item, idx + 1)
        elif isinstance(node, dict) and token in node:
            yield from recurse(node[token], idx + 1)
    yield from recurse(obj, 0)


# --- Field provenance lookup ---

def get_field_provenance(meta: dict, path: str) -> dict | None:
    """Return _meta.fieldProvenance.<path> if present."""
    if not meta:
        return None
    fp = meta.get("fieldProvenance") or {}
    return fp.get(path)


# --- DOI -> cached source text ---

def doi_to_cache_path(doi: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", doi.lower()).strip("-")
    return CACHE_DIR / f"{slug}.txt"


def find_source_doi(artifact: dict) -> str | None:
    """Pull DOI from the artifact's _meta.provenance or from a curriculum's publication.doi."""
    meta = artifact.get("_meta") or {}
    prov = meta.get("provenance") or {}
    if "source_doi" in prov:
        return prov["source_doi"]
    if "primary_source_doi" in prov:
        return prov["primary_source_doi"]
    pub = (artifact.get("publication") or {})
    if "doi" in pub:
        return pub["doi"]
    return None


# --- Per-file check ---

def trace_file(path: Path) -> list[str]:
    try:
        artifact = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"{path}: invalid JSON: {e}"]

    type_ = artifact.get("type")
    if type_ not in TEXT_PATHS:
        return []  # unknown type, skip
    meta = artifact.get("_meta") or {}
    prov = meta.get("provenance") or {}
    prov_type = prov.get("type")

    # Skip non-source-canonical provenance for now (those are handled by completeness.py).
    if prov_type and prov_type not in ("verbatim", "paraphrased"):
        return []

    doi = find_source_doi(artifact)
    if not doi:
        return [f"{path}: no DOI on artifact (need _meta.provenance.source_doi)"]
    cache_path = doi_to_cache_path(doi)
    if not cache_path.exists():
        return [f"{path}: source PDF text not cached at {cache_path}. Run acquire stage first."]
    source_text = cache_path.read_text()

    errors: list[str] = []
    for field_path in TEXT_PATHS[type_]:
        for value in walk_path(artifact, field_path):
            if not isinstance(value, str):
                continue
            # Check for field-level provenance override.
            override = get_field_provenance(meta, field_path)
            if override:
                span = override.get("source_span")
                if span and grep_match(span, source_text):
                    continue
                errors.append(f"{path}: {field_path}: fieldProvenance.source_span does not grep-match source")
                continue
            # Otherwise the value itself must grep-match source.
            if not grep_match(value, source_text):
                snippet = value[:80].replace("\n", " ")
                errors.append(f"{path}: {field_path}: not found in source PDF — '{snippet}...'")
    return errors


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="source-trace: every field must be source-traceable")
    p.add_argument("targets", nargs="*", help="JSON files to check (default: all under esge/)")
    args = p.parse_args(argv)

    if args.targets:
        targets = [Path(t).resolve() for t in args.targets]
    else:
        targets = sorted(list((ROOT / "esge").rglob("*.json")))
    if not targets:
        print("source-trace: nothing to check")
        return 0

    all_errors: list[str] = []
    pass_count = 0
    for path in targets:
        errs = trace_file(path)
        if errs:
            all_errors.extend(errs)
        else:
            pass_count += 1
    print(f"source-trace: {pass_count}/{len(targets)} files passed")
    if all_errors:
        for e in all_errors[:50]:
            print(f"  FAIL {e}")
        if len(all_errors) > 50:
            print(f"  ... and {len(all_errors) - 50} more")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
