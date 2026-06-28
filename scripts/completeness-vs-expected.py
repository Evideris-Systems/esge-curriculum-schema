#!/usr/bin/env python3
"""completeness-vs-expected.py — the FOURTH gate.

For each curriculum that has an expected.yaml manifest, verify that the
encoded JSON matches the human's declared coverage. Catches:
  1. Silent extraction skip (rec has 0 sub-items when manifest says 6)
  2. Unverified rec (no manifest entry — forces human audit before merge)
  3. Drift (count mismatch — must update manifest or fix encoding)

The manifest IS the source-fidelity audit. It records the human's promise
about what the source paper contains. Updating it without re-reading the
source defeats the gate.

Usage:
  python3 scripts/completeness-vs-expected.py            # check all curricula
  python3 scripts/completeness-vs-expected.py emr-colon  # specific curriculum
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Minimal YAML reader — just enough to parse our expected.yaml shape.
def parse_expected(path: Path) -> dict:
    text = path.read_text()
    out: dict = {"recommendations": {}}
    cur_section = None
    for raw in text.splitlines():
        line = raw.split("#")[0].rstrip()
        if not line.strip():
            continue
        # Section headings
        m = re.match(r"^(recommendations|qis|gpatItems|mainStatements|sections|references):\s*$", line)
        if m:
            cur_section = m.group(1)
            if cur_section not in out:
                out[cur_section] = {}
            continue
        # Top-level key: value
        m = re.match(r"^(\w+):\s*(.+)$", line)
        if m and not line.startswith(" "):
            k, v = m.group(1), m.group(2).strip()
            if v.isdigit():
                out[k] = int(v)
            else:
                out[k] = v
            cur_section = None
            continue
        # Indented under recommendations: "  N: { subItems: X, ... }"
        m = re.match(r"^\s+(\d+):\s*\{(.+)\}$", line)
        if m and cur_section == "recommendations":
            n = int(m.group(1))
            body = m.group(2)
            entry: dict = {}
            for fld in re.finditer(r'(\w+):\s*("[^"]*"|[\w\-]+)', body):
                k, v = fld.group(1), fld.group(2).strip('"')
                if v.isdigit():
                    entry[k] = int(v)
                elif v in ("true", "false"):
                    entry[k] = v == "true"
                else:
                    entry[k] = v
            out["recommendations"][n] = entry
    return out


def check_curriculum(slug: str, expected: dict) -> list[str]:
    errs: list[str] = []
    rec_dir = ROOT / "esge/recommendation" / slug
    if not rec_dir.exists():
        return [f"no recommendation dir for curriculum slug {slug!r}"]

    # Map encoded recs by number
    encoded: dict[int, dict] = {}
    for p in rec_dir.glob("*.v*.json"):
        d = json.loads(p.read_text())
        n = d.get("number")
        if n is not None:
            encoded[int(n)] = d

    # Cross-check
    expected_recs = expected.get("recommendations", {})
    for n, decl in expected_recs.items():
        if n not in encoded:
            errs.append(f"R{n}: declared in expected.yaml but no encoded JSON file")
            continue
        d = encoded[n]
        actual = len(d.get("subItems") or [])
        decl_sub = decl.get("subItems")
        known_incomplete = bool((d.get("_meta") or {}).get("knownIncomplete"))

        if decl_sub == "known-incomplete":
            # Manifest says incomplete — the rec MUST have the knownIncomplete flag set
            if not known_incomplete:
                errs.append(f"R{n}: expected.yaml says known-incomplete but artifact missing _meta.knownIncomplete flag")
        elif isinstance(decl_sub, int):
            if actual != decl_sub:
                # Allow knownIncomplete partial coverage with explicit note
                if known_incomplete:
                    continue
                errs.append(f"R{n}: expected {decl_sub} sub-items, got {actual} (declare _meta.knownIncomplete or fix encoding or update expected.yaml)")
            # NEW Rule (Fix C): if declared 0 sub-items, manifest must give a reason
            if decl_sub == 0 and not decl.get("reason"):
                errs.append(f"R{n}: expected.yaml declares 0 sub-items but no reason — add reason: \"...\" so 0 is auditable")
            # NEW Rule (Fix B): if rec statement promises a list ('described below'/etc),
            # it cannot legitimately have 0 sub-items UNLESS the manifest has an explicit
            # reason explaining why (the reason IS the audit trail).
            stmt = ((d.get("statement") or {}).get("en") or "").lower()
            PROMISES_LIST = ["following list", "following techniques", "following criteria",
                             "described below", "detailed below", "listed below",
                             "given in the following", "given below", "criteria below",
                             "techniques below", "the list below"]
            promises = any(p in stmt for p in PROMISES_LIST)
            if promises and decl_sub == 0 and not known_incomplete and not decl.get("reason"):
                errs.append(f"R{n}: statement promises a list ('{next(p for p in PROMISES_LIST if p in stmt)}') but expected.yaml says 0 sub-items. Either source-extract the items, set knownIncomplete, or add a reason: explaining why 0 is correct")
        else:
            errs.append(f"R{n}: expected.yaml subItems value {decl_sub!r} not understood (need int or 'known-incomplete')")

    # Any rec encoded but not declared in manifest?
    for n in encoded:
        if n not in expected_recs:
            errs.append(f"R{n}: encoded but NOT declared in expected.yaml — add a manifest entry first")

    # Cross-check QI count
    if "qis" in expected:
        qi_dir = ROOT / "esge/qi" / slug
        qi_count = len(list(qi_dir.glob("*.v*.json"))) if qi_dir.exists() else 0
        if qi_count != expected["qis"]:
            errs.append(f"QIs: expected {expected['qis']}, got {qi_count}")

    # Cross-check main-statement count via curriculum wrapper
    cur_dir = ROOT / "esge/curriculum" / slug
    if cur_dir.exists() and "mainStatements" in expected:
        cur_file = next((p for p in cur_dir.glob("v*.json") if "references" not in p.name), None)
        if cur_file:
            d = json.loads(cur_file.read_text())
            n_main = len(d.get("mainStatements") or [])
            if n_main != expected["mainStatements"]:
                errs.append(f"mainStatements: expected {expected['mainStatements']}, got {n_main}")

    return errs


def main(argv: list[str]) -> int:
    target_slug = argv[0] if argv else None
    cur_dirs = (
        [ROOT / "esge/curriculum" / target_slug]
        if target_slug
        else [p for p in (ROOT / "esge/curriculum").iterdir() if p.is_dir()]
    )
    rc = 0
    total = 0
    for cur_dir in cur_dirs:
        slug = cur_dir.name
        expected_file = cur_dir / "expected.yaml"
        if not expected_file.exists():
            print(f"  [{slug}] no expected.yaml — SKIPPED (write one before merging this curriculum!)")
            rc = 1
            continue
        expected = parse_expected(expected_file)
        errs = check_curriculum(slug, expected)
        total += 1
        if errs:
            print(f"  [{slug}] FAIL — {len(errs)} issue(s):")
            for e in errs:
                print(f"    - {e}")
            rc = 1
        else:
            print(f"  [{slug}] OK — coverage matches expected.yaml")
    print(f"\ncompleteness-vs-expected: {total} curricula checked.")
    if rc:
        print("FAIL — fix encoding or update expected.yaml.")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
