#!/usr/bin/env python3
"""Verify every figure asset path, digest, dimensions, and release coverage."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIGURE_ROOT = REPO_ROOT / "esge" / "figure"


def image_metadata(data: bytes) -> tuple[str, int, int]:
    """Return media type and pixel dimensions without third-party packages."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "image/png", width, height

    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return "image/gif", width, height

    if data.startswith(b"\xff\xd8"):
        offset = 2
        start_of_frame = {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }
        while offset < len(data):
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker == 0x00 or marker == 0x01 or 0xD0 <= marker <= 0xD9:
                continue
            if offset + 2 > len(data):
                break
            segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
            if segment_length < 2 or offset + segment_length > len(data):
                break
            if marker in start_of_frame and segment_length >= 7:
                height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                return "image/jpeg", width, height
            offset += segment_length

    if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return "image/webp", width, height
        if chunk == b"VP8L" and data[20] == 0x2F:
            width = 1 + data[21] + ((data[22] & 0x3F) << 8)
            height = 1 + (data[22] >> 6) + (data[23] << 2) + ((data[24] & 0x0F) << 10)
            return "image/webp", width, height
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return "image/webp", width, height

    raise ValueError("unsupported or malformed image")


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

        asset_bytes = asset_path.read_bytes()
        actual_hash = hashlib.sha256(asset_bytes).hexdigest()
        if asset.get("sha256") != actual_hash:
            errors.append(
                f"{figure_path}: asset hash mismatch: expected {asset.get('sha256')}, got {actual_hash}"
            )
        try:
            media_type, width, height = image_metadata(asset_bytes)
        except ValueError as error:
            errors.append(f"{figure_path}: {error}: {relative_path}")
            continue
        if asset.get("mediaType") != media_type:
            errors.append(
                f"{figure_path}: asset media type mismatch: "
                f"expected {asset.get('mediaType')}, got {media_type}"
            )
        if (asset.get("width"), asset.get("height")) != (width, height):
            errors.append(
                f"{figure_path}: asset dimensions mismatch: "
                f"expected {asset.get('width')}x{asset.get('height')}, "
                f"got {width}x{height}"
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
