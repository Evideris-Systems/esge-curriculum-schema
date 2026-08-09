#!/usr/bin/env python3
"""Synchronize a source-canonical release with every artifact in ``esge/``."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TYPE_TO_GROUP = {
    "curriculum": "curricula",
    "recommendation": "recommendations",
    "standard": "standards",
    "scoringTool": "scoringTools",
    "kpi": "kpis",
    "qi": "qis",
    "cat": "cats",
    "references": "references",
    "figure": "figures",
    "table": "tables",
}
GROUP_ORDER = list(TYPE_TO_GROUP.values())


def natural_key(value: str) -> list[str | int]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect() -> dict[str, list[dict]]:
    groups = {group: [] for group in GROUP_ORDER}
    for path in sorted((ROOT / "esge").rglob("*.json"), key=lambda p: natural_key(str(p))):
        document = json.loads(path.read_text())
        group = TYPE_TO_GROUP.get(document.get("type"))
        if group is None:
            raise ValueError(f"No release group for artifact type {document.get('type')!r}: {path}")
        groups[group].append(
            {
                "lineageId": document["lineageId"],
                "version": document["version"],
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
            }
        )
    return groups


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    document = json.loads(manifest_path.read_text())
    groups = collect()

    output: dict = {}
    inserted = False
    for key, value in document.items():
        if key in GROUP_ORDER:
            if not inserted:
                output.update(groups)
                inserted = True
            continue
        if key in {"majorBumps", "minorBumps", "patchBumps", "_meta"} and not inserted:
            output.update(groups)
            inserted = True
        output[key] = value
    if not inserted:
        output.update(groups)

    rendered = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        manifest_path.write_text(rendered)
    print(
        json.dumps(
            {"write": args.write, "groups": {key: len(value) for key, value in groups.items()}},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
