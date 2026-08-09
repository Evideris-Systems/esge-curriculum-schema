#!/usr/bin/env python3
"""Apply source Table 6 / ESD threshold semantics to QI artifacts."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EMR_ORDER = [
    "practitioner-outcome-awareness",
    "procedures-per-year",
    "patient-consent-documentation",
    "lnpcp-attempt-rate",
    "success-rate",
    "intraprocedural-bleeding",
    "intraprocedural-perforation",
    "complete-perforation-closure",
    "clinically-significant-post-emr-bleeding",
    "delayed-perforation",
    "unplanned-hospitalization",
    "surgery-for-incomplete-emr",
    "patients-returning-surveillance",
    "adenoma-recurrence",
    "adenoma-recurrence-with-margin-ablation",
    "adenoma-recurrence-treatable-endoscopically",
    "surgery-for-unresectable-recurrence",
    "patient-satisfaction-recorded",
]


def write(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    for source_order, stem in enumerate(EMR_ORDER, start=1):
        path = ROOT / "esge/qi/emr-colon" / f"{stem}.v1.0.0.json"
        document = json.loads(path.read_text())
        document["sourceOrder"] = source_order
        if stem == "procedures-per-year":
            document["desiredStandard"] = 70
            document["minimumStandard"] = None
        write(path, document)

    esd = {
        "en-bloc-resection-rate": (1, ">"),
        "perforation-rate": (2, "<"),
        "surgery-for-complications-rate": (3, "<"),
    }
    for stem, (source_order, comparator) in esd.items():
        path = ROOT / "esge/qi/esd" / f"{stem}.v1.0.0.json"
        document = json.loads(path.read_text())
        document["sourceOrder"] = source_order
        document["desiredComparator"] = comparator
        write(path, document)
    print("quality indicators repaired: 18 EMR + 3 ESD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
