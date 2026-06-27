#!/usr/bin/env python3
"""completeness.py — heuristic stub detector + provenance-required enforcement.

Catches the kind of silent stubs that schema-structural validation misses:
  - Citations shorter than 60 chars or missing year/journal markers
  - Description / commentary / text fields containing 'TODO', '...', '[placeholder]'
  - Vague-phrasing citations: 'context references', 'placeholder reference', etc.
  - Missing _meta.provenance
  - Source-canonical repo: any provenance type other than verbatim/paraphrased

This is a HEURISTIC check; complements source-trace (which is strict grep) and
verify-citations (which is strict resolver).

Usage:
    python3 scripts/completeness.py            # all artifacts under esge/
    python3 scripts/completeness.py path.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


# --- Stub heuristics ---

VAGUE_CITATION_PATTERNS = [
    r"context references?",
    r"placeholder",
    r"to be added",
    r"\bTBD\b",
    r"published reference",
    r"consensus reference, ESGE",
    r"reference for [a-z ]+",
]
VAGUE_TEXT_PATTERNS = [
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\.\.\.$",          # ends with literal ellipsis
    r"\[placeholder\]",
    r"\[stub\]",
]


def is_stub_citation(citation: str) -> str | None:
    """Returns a reason if the citation looks stubbed, else None."""
    if not citation or not citation.strip():
        return "empty citation"
    if len(citation.strip()) < 60:
        return f"citation too short ({len(citation.strip())} chars) — likely stub"
    # No year?
    if not re.search(r"\b(19|20|21)\d{2}\b", citation):
        return "citation missing year"
    # Vague language?
    for pat in VAGUE_CITATION_PATTERNS:
        if re.search(pat, citation, re.IGNORECASE):
            return f"vague phrasing matches /{pat}/"
    return None


def is_stub_text(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    for pat in VAGUE_TEXT_PATTERNS:
        if re.search(pat, text):
            return f"contains stub marker /{pat}/"
    return None


# --- Per-artifact check ---

ALLOWED_SOURCE_PROVENANCE = {"verbatim", "paraphrased"}
ALLOWED_DERIVED_PROVENANCE = {"verbatim-from-primary-source", "paraphrased-from-primary-source", "evideris-design", "inferred-from-source"}


def check_file(path: Path, repo_mode: str) -> list[str]:
    """repo_mode is 'source-canonical' (this repo) or 'derived' (the sibling)."""
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"{path}: invalid JSON: {e}"]

    errs: list[str] = []
    meta = data.get("_meta")
    if meta is None:
        errs.append(f"{path}: missing _meta block")
        return errs  # cascade — can't check provenance if envelope is broken

    prov = meta.get("provenance")
    if not prov or "type" not in prov:
        errs.append(f"{path}: missing _meta.provenance.type")
        return errs

    ptype = prov["type"]
    if repo_mode == "source-canonical":
        if ptype not in ALLOWED_SOURCE_PROVENANCE:
            errs.append(f"{path}: provenance.type='{ptype}' not allowed in source-canonical repo (must be one of {sorted(ALLOWED_SOURCE_PROVENANCE)})")
        if "source_doi" not in prov:
            errs.append(f"{path}: source-canonical artifact missing provenance.source_doi")
    elif repo_mode == "derived":
        if ptype not in ALLOWED_DERIVED_PROVENANCE:
            errs.append(f"{path}: provenance.type='{ptype}' not allowed in derived repo")
        if "reason" not in prov:
            errs.append(f"{path}: derived artifact missing provenance.reason")

    # Stub-text scan: walk every string in the document.
    def walk(node, path_str=""):
        if isinstance(node, str):
            reason = is_stub_text(node)
            if reason:
                errs.append(f"{path}: {path_str}: {reason}")
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path_str}.{k}" if path_str else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path_str}[{i}]")
    walk(data)

    # Citation stub scan.
    refs = data.get("references") or []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        cit = ref.get("citation", "")
        reason = is_stub_citation(cit)
        if reason:
            rid = ref.get("id", "?")
            errs.append(f"{path}: references[{rid}]: {reason}")

    return errs


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="completeness: heuristic stub + provenance enforcement")
    p.add_argument("targets", nargs="*", help="JSON files to check (default: all under esge/)")
    p.add_argument("--mode", default="source-canonical", choices=["source-canonical", "derived"],
                   help="Which repo's rules to apply (default: source-canonical)")
    args = p.parse_args(argv)

    if args.targets:
        targets = [Path(t).resolve() for t in args.targets]
    else:
        targets = sorted(list((ROOT / "esge").rglob("*.json")))
    if not targets:
        print("completeness: nothing to check")
        return 0

    all_errors: list[str] = []
    pass_count = 0
    for path in targets:
        errs = check_file(path, args.mode)
        if errs:
            all_errors.extend(errs)
        else:
            pass_count += 1
    print(f"completeness ({args.mode}): {pass_count}/{len(targets)} files passed")
    if all_errors:
        for e in all_errors[:50]:
            print(f"  FAIL {e}")
        if len(all_errors) > 50:
            print(f"  ... and {len(all_errors) - 50} more")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
