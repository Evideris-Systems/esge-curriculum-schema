#!/usr/bin/env python3
"""Restore reviewed bibliography metadata while retaining clean citations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent.parent
REFERENCE_PATHS = [
    Path("esge/curriculum/emr-colon/references.v1.0.0.json"),
    Path("esge/curriculum/esd/references.v1.0.0.json"),
    Path("esge/curriculum/poem-2/references.v1.0.0.json"),
]
PUBLISHER_FIELDS = {"id", "citation"}


def from_git(ref: str, path: Path) -> dict:
    raw = subprocess.check_output(
        ["git", "show", f"{ref}:{path.as_posix()}"], cwd=ROOT
    )
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-ref", default="HEAD")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    counts: dict[str, int] = {}
    for relative_path in REFERENCE_PATHS:
        path = ROOT / relative_path
        current = json.loads(path.read_text())
        reviewed = from_git(args.git_ref, relative_path)
        old_by_id = {entry["id"]: entry for entry in reviewed["references"]}
        restored = 0
        for entry in current["references"]:
            old = old_by_id[entry["id"]]
            for key, value in old.items():
                if key in PUBLISHER_FIELDS or key in entry:
                    continue
                entry[key] = value
                restored += 1
        counts[relative_path.as_posix()] = restored
        if args.write:
            path.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps({"write": args.write, "restoredFields": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
