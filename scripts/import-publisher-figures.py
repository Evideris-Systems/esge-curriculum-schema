#!/usr/bin/env python3
"""Extract the eight reviewed curriculum figures from authoritative PDFs."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import fitz


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class FigureSpec:
    curriculum: str
    number: int
    pdf_key: str
    page: int
    crop: tuple[float, float, float, float]


# Pages are zero-indexed. Crops are PDF points measured against the published
# PDF pages, excluding the printed caption because captions are structured JSON.
FIGURES = (
    FigureSpec("emr-colon", 1, "emr", 5, (42.52, 62.36, 538.60, 340.60)),
    FigureSpec("emr-colon", 2, "emr", 15, (42.52, 110.18, 538.36, 551.78)),
    FigureSpec("emr-colon", 3, "emr", 25, (308.30, 73.00, 538.60, 462.00)),
    FigureSpec("esd", 1, "esd", 9, (42.52, 62.36, 538.60, 367.40)),
    FigureSpec("poem-2", 1, "poem", 6, (42.5, 62.36, 282.5, 323.0)),
    FigureSpec("poem-2", 2, "poem", 12, (42.52, 62.36, 538.36, 168.44)),
    FigureSpec("poem-2", 3, "poem", 15, (56.69, 528.61, 552.53, 676.21)),
    FigureSpec("poem-2", 4, "poem", 17, (56.69, 62.36, 552.53, 336.68)),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emr-pdf", required=True, type=Path)
    parser.add_argument("--esd-pdf", required=True, type=Path)
    parser.add_argument("--poem-pdf", required=True, type=Path)
    parser.add_argument("--scale", type=float, default=2.5)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parse_args()
    pdfs = {"emr": args.emr_pdf, "esd": args.esd_pdf, "poem": args.poem_pdf}
    documents = {key: fitz.open(path) for key, path in pdfs.items()}
    try:
        for spec in FIGURES:
            document = documents[spec.pdf_key]
            if spec.page >= document.page_count:
                raise ValueError(f"{pdfs[spec.pdf_key]} has no page {spec.page + 1}")
            page = document[spec.page]
            crop = fitz.Rect(*spec.crop)
            if not page.rect.contains(crop):
                raise ValueError(f"figure crop is outside page {spec.page + 1}: {crop}")

            asset_relative = Path(
                f"esge/figure/{spec.curriculum}/assets/fig-{spec.number}.png"
            )
            asset_path = REPO_ROOT / asset_relative
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(args.scale, args.scale), clip=crop, alpha=False
            )
            pixmap.save(asset_path)

            figure_path = (
                REPO_ROOT
                / f"esge/figure/{spec.curriculum}/fig-{spec.number}.v1.0.0.json"
            )
            figure = json.loads(figure_path.read_text())
            figure["asset"] = {
                "path": asset_relative.as_posix(),
                "mediaType": "image/png",
                "sha256": sha256(asset_path),
                "width": pixmap.width,
                "height": pixmap.height,
            }
            figure_path.write_text(json.dumps(figure, indent=2, ensure_ascii=False) + "\n")
            print(
                f"{figure['lineageId']}: {asset_relative} "
                f"({pixmap.width}x{pixmap.height}, {figure['asset']['sha256']})"
            )
    finally:
        for document in documents.values():
            document.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
