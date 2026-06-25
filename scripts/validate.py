#!/usr/bin/env python3
"""Validate every JSON instance file in the repo against its artifact schema.

Usage:
    python3 scripts/validate.py            # validate everything under esge/ + releases/
    python3 scripts/validate.py file.json  # validate one file
    python3 scripts/validate.py --self     # syntax-check all schemas

Picks the schema by the file's `type` field. Walks `_common.schema.json` $refs
via the `referencing` library so cross-file refs resolve cleanly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"

TYPE_TO_SCHEMA = {
    "release":        "release.schema.json",
    "curriculum":     "curriculum.schema.json",
    "recommendation": "recommendation.schema.json",
    "competency":     "competency.schema.json",
    "epa":            "epa.schema.json",
    "standard":       "standard.schema.json",
    "scoringTool":    "scoring-tool.schema.json",
    "kpi":            "kpi.schema.json",
    "qi":             "qi.schema.json",
    "cat":            "cat.schema.json",
}


def load_registry() -> Registry:
    """Load every schema file so cross-file $refs resolve."""
    registry = Registry()
    for schema_file in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        with schema_file.open() as f:
            schema = json.load(f)
        resource = Resource(contents=schema, specification=DRAFT202012)
        # Register under both the absolute $id and the relative filename so refs work both ways.
        registry = registry.with_resource(uri=schema["$id"], resource=resource)
        registry = registry.with_resource(uri=schema_file.name, resource=resource)
    return registry


def validator_for(schema_file: str, registry: Registry) -> Draft202012Validator:
    with (SCHEMAS_DIR / schema_file).open() as f:
        schema = json.load(f)
    return Draft202012Validator(schema, registry=registry)


def validate_instance(path: Path, registry: Registry) -> list[str]:
    with path.open() as f:
        instance = json.load(f)
    instance_type = instance.get("type")
    if instance_type not in TYPE_TO_SCHEMA:
        return [f"{path}: unknown type {instance_type!r}"]
    validator = validator_for(TYPE_TO_SCHEMA[instance_type], registry)
    errors = []
    for err in validator.iter_errors(instance):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {loc}: {err.message}")
    return errors


def validate_schemas_themselves() -> list[str]:
    """Check every schema file is a valid Draft 2020-12 meta-schema."""
    errors = []
    for sf in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        with sf.open() as f:
            try:
                schema = json.load(f)
            except json.JSONDecodeError as e:
                errors.append(f"{sf.name}: JSON parse error: {e}")
                continue
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as e:
            errors.append(f"{sf.name}: schema invalid: {e}")
    return errors


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--self":
        errors = validate_schemas_themselves()
        if errors:
            for e in errors:
                print("FAIL", e)
            return 1
        print(f"OK: all {len(list(SCHEMAS_DIR.glob('*.schema.json')))} schemas pass meta-schema check.")
        return 0

    registry = load_registry()
    targets: list[Path]
    if argv:
        targets = [Path(p) for p in argv]
    else:
        targets = sorted(list((ROOT / "esge").rglob("*.json")) + list((ROOT / "releases").rglob("*.json")))
    if not targets:
        print("No JSON instance files yet — nothing to validate.")
        return 0

    all_errors: list[str] = []
    for path in targets:
        errs = validate_instance(path, registry)
        if errs:
            all_errors.extend(errs)
        else:
            print(f"OK {path.relative_to(ROOT)}")
    if all_errors:
        print()
        for e in all_errors:
            print("FAIL", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
