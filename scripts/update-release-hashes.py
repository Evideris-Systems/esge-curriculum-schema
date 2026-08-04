#!/usr/bin/env python3
"""Add or verify immutable artifact paths and SHA-256 hashes in release manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterator


REPO_ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def artifact_references(document: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    for group, value in document.items():
        if not isinstance(value, list) or not value:
            continue
        if all(
            isinstance(item, dict)
            and isinstance(item.get("lineageId"), str)
            and isinstance(item.get("version"), str)
            for item in value
        ):
            for item in value:
                yield group, item


def artifact_index(artifact_root: Path) -> dict[tuple[str, str], Path]:
    index: dict[tuple[str, str], Path] = {}
    for path in sorted(artifact_root.rglob("*.json")):
        document = load_json(path)
        lineage_id = document.get("lineageId")
        version = document.get("version")
        if not isinstance(lineage_id, str) or not isinstance(version, str):
            continue
        key = (lineage_id, version)
        if key in index:
            raise ValueError(f"duplicate artifact {lineage_id}@{version}: {index[key]} and {path}")
        index[key] = path
    return index


def safe_manifest_path(relative_path: str, artifact_root: Path) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe artifact path: {relative_path}")
    resolved = (REPO_ROOT / path).resolve()
    root = artifact_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"artifact path escapes {artifact_root}: {relative_path}")
    return resolved


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process_manifest(manifest_path: Path, artifact_root: Path, write: bool) -> list[str]:
    document = load_json(manifest_path)
    index = artifact_index(artifact_root)
    errors: list[str] = []

    for group, reference in artifact_references(document):
        lineage_id = reference["lineageId"]
        version = reference["version"]
        key = (lineage_id, version)
        relative_path = reference.get("path")
        if write and not isinstance(relative_path, str):
            indexed_path = index.get(key)
            if indexed_path is None:
                errors.append(f"{group}: missing artifact {lineage_id}@{version}")
                continue
            relative_path = indexed_path.relative_to(REPO_ROOT).as_posix()
            reference["path"] = relative_path
        if not isinstance(relative_path, str):
            errors.append(f"{group}: {lineage_id}@{version} has no path")
            continue

        try:
            artifact_path = safe_manifest_path(relative_path, artifact_root)
        except ValueError as error:
            errors.append(f"{group}: {lineage_id}@{version}: {error}")
            continue
        if not artifact_path.is_file():
            errors.append(f"{group}: {lineage_id}@{version} path is missing: {relative_path}")
            continue

        artifact = load_json(artifact_path)
        if artifact.get("lineageId") != lineage_id or artifact.get("version") != version:
            errors.append(
                f"{group}: {relative_path} identity does not match {lineage_id}@{version}"
            )
            continue

        actual_hash = sha256(artifact_path)
        if write:
            reference["sha256"] = actual_hash
        elif reference.get("sha256") != actual_hash:
            errors.append(
                f"{group}: {relative_path} hash mismatch: expected {reference.get('sha256')}, got {actual_hash}"
            )

    if write and not errors:
        manifest_path.write_text(json.dumps(document, indent=2) + "\n")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--root", required=True, type=Path, help="Artifact root, e.g. esge")
    parser.add_argument("--write", action="store_true", help="Populate paths and hashes")
    args = parser.parse_args()

    artifact_root = (REPO_ROOT / args.root).resolve()
    errors: list[str] = []
    for manifest in args.manifests:
        manifest_path = manifest if manifest.is_absolute() else REPO_ROOT / manifest
        manifest_errors = process_manifest(manifest_path, artifact_root, args.write)
        errors.extend(f"{manifest}: {error}" for error in manifest_errors)
        if not manifest_errors:
            action = "updated" if args.write else "verified"
            print(f"OK {action} {manifest}")

    for error in errors:
        print(f"FAIL {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
