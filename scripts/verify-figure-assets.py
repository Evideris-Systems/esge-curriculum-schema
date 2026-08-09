#!/usr/bin/env python3
"""Verify every figure asset path, digest, dimensions, and release coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz


REPO_ROOT = Path(__file__).resolve().parent.parent
FIGURE_ROOT = REPO_ROOT / "esge" / "figure"


def main() -> int:
    errors: list[str] = []
    referenced: set[Path] = set()
    for figure_path in sorted(FIGURE_ROOT.glob("*/*.json")):
        figure = json.loads(figure_path.read_text())
        asset = figure.get("asset")
        if not isinstance(asset, dict):
            errors.append(f"{figure_path}: missing asset")
            continue
        relative_path = asset.get("path")
        if not isinstance(relative_path, str):
            errors.append(f"{figure_path}: asset path is missing")
            continue
        candidate = Path(relative_path)
        asset_path = (REPO_ROOT / candidate).resolve()
        if candidate.is_absolute() or ".." in candidate.parts or REPO_ROOT not in asset_path.parents:
            errors.append(f"{figure_path}: unsafe asset path {relative_path}")
            continue
        if asset_path.is_symlink() or not asset_path.is_file():
            errors.append(f"{figure_path}: asset is missing or symlinked: {relative_path}")
            continue
        referenced.add(asset_path)

        actual_hash = hashlib.sha256(asset_path.read_bytes()).hexdigest()
        if asset.get("sha256") != actual_hash:
            errors.append(
                f"{figure_path}: asset hash mismatch: expected {asset.get('sha256')}, got {actual_hash}"
            )
        pixmap = fitz.Pixmap(asset_path)
        if (asset.get("width"), asset.get("height")) != (pixmap.width, pixmap.height):
            errors.append(
                f"{figure_path}: asset dimensions mismatch: "
                f"expected {asset.get('width')}x{asset.get('height')}, "
                f"got {pixmap.width}x{pixmap.height}"
            )

    stored = {path.resolve() for path in FIGURE_ROOT.glob("*/assets/*") if path.is_file()}
    for orphan in sorted(stored - referenced):
        errors.append(f"unreferenced figure asset: {orphan.relative_to(REPO_ROOT)}")

    for error in errors:
        print(f"FAIL {error}")
    if errors:
        return 1
    print(f"OK figure assets: {len(referenced)} verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
