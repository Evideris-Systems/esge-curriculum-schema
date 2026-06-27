#!/usr/bin/env python3
"""Extract every recommendation from the cached source PDF text and emit a draft
JSON file per rec under esge/recommendation/<curriculum-slug>/.

Strategy:
1. Walk the source text linearly. Topic headers (e.g. "3 ASSESSMENT OF…") mark
   a new rec's start.
2. For each rec, the body chunk spans [topic_header.start, next_topic_header.start).
3. Within the chunk, extract verbatim statement (between header and GRADE line),
   GRADE strength + evidence + LoA, sub-items (i)(ii)(iii)… with their LoA +
   inline references, commentary, figure/table refs.
4. Some recs (R5, R7, R34, R38) lack the "ESGE recommends" anchor — handle by
   topic header detection alone.
5. Sub-items often appear on the NEXT PDF page after the topic header. Handle
   by scanning the WHOLE chunk for sub-items, including past intermediate
   non-sub-item paragraphs.
6. Skip recs that already exist in the repo (don't overwrite verified ones).

Usage:
    python3 scripts/extract-recommendations.py \\
        .cache/sources/10-1055-a-2077-0497.txt cur-emr-colon-2023 r2026.07 \\
        --source-doi 10.1055/a-2077-0497 \\
        --modality-slug emr-colon \\
        --skip 1 2 3 10 17 38   # already hand-encoded
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Patterns
TOPIC_HEADER_RE = re.compile(r"(?m)^[ \t]*(\d{1,2})\s+([A-Z][A-Z /\-,()&]{4,}?)\s*$")
ESGE_RECOMMENDS_RE = re.compile(r"ESGE recommends.+?(?=^\d+\s+[A-Z]|\Z)", re.DOTALL | re.MULTILINE)
GRADE_LINE_RE = re.compile(
    r"(Strong|Weak|Best practice|Moderately strong)\s+recommendation,\s*"
    r"(low|moderate|high|very[\- ]low|no evidence available)\s+(?:quality\s+(?:of\s+)?)?evi[\s-]*?dence\.?",
    re.IGNORECASE | re.DOTALL,
)
LEVEL_OF_AGREEMENT_RE = re.compile(r"Level of agreement\s*(\d{1,3})\s*%\.?", re.IGNORECASE)
SUBITEM_RE = re.compile(r"\((i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx|xxi|xxii|xxiii|xxiv|xxv|xxvi|xxvii|xxviii|xxix|xxx)\)", re.IGNORECASE)
COMMENT_PARA_RE = re.compile(r"(?s)\bComment\s+([A-Z].*?)(?=\(i\)|\(I\)|^\d+\s+[A-Z]|\Z)", re.MULTILINE)
TABLE_REF_RE = re.compile(r"▶?\s*Table\s+(\d+)", re.IGNORECASE)
FIG_REF_RE   = re.compile(r"▶?\s*Fig\.?\s*(\d+)", re.IGNORECASE)
CITATION_RE  = re.compile(r"\[(\d+(?:[,\s]+\d+)*)\]")

# Affiliation noise — filter out from topic headers
AFFILIATION_KEYWORDS = ["DEPARTMENT", "UNIVERSITY", "HOSPITAL", "CLINIC", "GASTROENTEROLOGY", "ENDOSCOPY DEPARTMENT", "STUTTGART", "GERMANY", "ITALY", "BELGIUM", "STREET", "JAPAN"]


def clean_text(s: str) -> str:
    """Clean PDF artefacts."""
    s = re.sub(r"\s+", " ", s).strip()
    # Join hyphen-at-line-break for natural words. Cautious about compound words.
    s = re.sub(r"(\w)-\s+([a-z])", r"\1\2", s)  # only lowercase next letter to avoid joining compound proper nouns
    # Strip trailing journal/footer lines that appear within rec text.
    s = re.sub(r"\s*Tate David J et al.+?All rights reserved\.\s*", " ", s)
    s = re.sub(r"\s*Position Statement\s*=== PAGE \d+ ===\s*", " ", s)
    s = re.sub(r"\s*=== PAGE \d+ ===\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalise_strength(raw: str) -> str:
    raw = raw.strip().lower()
    return {"strong": "strong", "weak": "weak", "best practice": "best-practice",
            "moderately strong": "strong"}.get(raw, raw)


def normalise_evidence(raw: str) -> str:
    return raw.strip().lower().replace(" ", "-")


def find_topic_headers(text: str) -> list[dict]:
    """Detect numbered topic headers (1-N), filter out affiliations."""
    headers = []
    seen = set()
    for m in TOPIC_HEADER_RE.finditer(text):
        n = int(m.group(1))
        title = m.group(2).strip()
        if any(kw in title for kw in AFFILIATION_KEYWORDS):
            continue
        if n in seen:
            continue
        if n < 1 or n > 50:
            continue
        # Heuristic: real topic headers contain at least one ALL-CAPS word AND are short
        words = title.split()
        if len(words) > 12:
            continue
        headers.append({"number": n, "title": title, "start": m.start()})
        seen.add(n)
    return sorted(headers, key=lambda h: h["start"])


def extract_subitems(chunk: str) -> list[dict]:
    """Find (i)(ii)... sub-items in a chunk with their text + LoA + refs.
    Skips parenthesised roman numerals embedded in prose (e.g., "Figure D(i)").
    """
    out = []
    # Find all subitem markers
    matches = list(SUBITEM_RE.finditer(chunk))
    if not matches:
        return []
    # Filter: real sub-items appear at the start of a line / after newline / preceded by whitespace
    real = []
    for m in matches:
        prev = chunk[max(0, m.start()-3):m.start()]
        if prev.endswith("\n") or prev.endswith(" .") or prev.endswith(". ") or prev.endswith(") ") or m.start() == 0 or prev[-1] in "\n .":
            real.append(m)
    if not real:
        real = matches
    # Detect roman-numeral sequence: (i)(ii)(iii)... contiguous, no jumps
    labels = [m.group(1).lower() for m in real]
    # Keep only contiguous sequence starting at (i)
    expected_seq = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix", "xx", "xxi", "xxii", "xxiii", "xxiv", "xxv", "xxvi", "xxvii", "xxviii"]
    valid_indices = []
    seq_idx = 0
    for i, lab in enumerate(labels):
        if seq_idx < len(expected_seq) and lab == expected_seq[seq_idx]:
            valid_indices.append(i)
            seq_idx += 1
    if not valid_indices:
        return []
    real = [real[i] for i in valid_indices]
    labels = [labels[i] for i in valid_indices]

    for i, m in enumerate(real):
        label = labels[i]
        body_start = m.end()
        body_end = real[i + 1].start() if i + 1 < len(real) else len(chunk)
        body = chunk[body_start:body_end].strip()
        # Extract LoA from body
        loa = None
        loa_m = LEVEL_OF_AGREEMENT_RE.search(body)
        if loa_m:
            loa = int(loa_m.group(1))
            body = body[:loa_m.start()].strip()
        # Strip trailing Comment paragraph
        body = re.split(r"\bComment\b", body, maxsplit=1)[0].strip()
        # Extract refs [N]
        refs = []
        for rm in CITATION_RE.finditer(body):
            for n in re.split(r"[,\s]+", rm.group(1)):
                if n.strip().isdigit():
                    refs.append(f"ref-{n.strip()}")
        # Strip ref tags from body
        body = CITATION_RE.sub("", body).strip()
        body = clean_text(body)
        # Strip trailing isolated punctuation orphaned by citation removal
        body = re.sub(r"\s+\.$", ".", body)
        body = re.sub(r"\s+,", ",", body)
        body = re.sub(r"\s+\.", ".", body)
        if not body:
            continue
        item = {"label": label, "text": {"en": body}}
        if loa is not None:
            item["levelOfAgreement"] = loa
        if refs:
            item["references"] = sorted(set(refs), key=lambda x: int(x.split("-")[1]))
        out.append(item)
    return out


def extract_commentary(chunk: str) -> str | None:
    m = COMMENT_PARA_RE.search(chunk)
    if not m:
        return None
    body = m.group(1)
    body = re.split(r"\(i\)|\(I\)", body, maxsplit=1)[0]
    body = CITATION_RE.sub("", body).strip()
    body = clean_text(body)
    return body if body else None


def extract_refs(chunk: str) -> list[str]:
    refs = []
    for rm in CITATION_RE.finditer(chunk):
        for n in re.split(r"[,\s]+", rm.group(1)):
            if n.strip().isdigit():
                refs.append(f"ref-{n.strip()}")
    return sorted(set(refs), key=lambda x: int(x.split("-")[1]))


def extract_rec(text: str, header: dict, next_header: dict | None) -> dict:
    """Extract one rec given its topic header + optional next-topic-header."""
    start = header["start"]
    end = next_header["start"] if next_header else len(text)
    chunk = text[start:end]

    # Title: clean topic header (turn ALL CAPS to Title Case-friendly)
    title = header["title"].strip()
    title_clean = " ".join(w.capitalize() if w.isupper() else w for w in title.split())

    # Statement: find ESGE recommends text or fallback to first sentence after header
    esge_m = re.search(r"(?s)ESGE recommends.+?(?=^\d+\s+[A-Z]|\bBest practice recommendation|\bStrong recommendation|\bWeak recommendation|\bModerately strong recommendation|\bLevel of agreement)", chunk, re.MULTILINE)
    statement = None
    if esge_m:
        statement = clean_text(esge_m.group(0))
    else:
        # Fallback: first sentence after the topic header
        body = chunk[len(header["title"]):]
        first_sentence_m = re.search(r"[A-Z][^.]+\.", body)
        if first_sentence_m:
            statement = clean_text(first_sentence_m.group(0))

    # GRADE
    grade_m = GRADE_LINE_RE.search(chunk)
    grade = None
    if grade_m:
        grade = {
            "strength": normalise_strength(grade_m.group(1)),
            "evidenceQuality": normalise_evidence(grade_m.group(2)),
        }
        # Top-level LoA
        tail = chunk[grade_m.end():]
        first_subitem_m = SUBITEM_RE.search(tail)
        loa_m = LEVEL_OF_AGREEMENT_RE.search(tail)
        if loa_m and (not first_subitem_m or loa_m.start() < first_subitem_m.start()):
            grade["levelOfAgreement"] = int(loa_m.group(1))

    # Sub-items
    sub_items = extract_subitems(chunk)

    # Commentary
    commentary = extract_commentary(chunk)

    # Figure / Table refs in statement+commentary only
    text_region = (statement or "") + " " + (commentary or "")
    fig_refs = [f"fig-{m.group(1)}" for m in FIG_REF_RE.finditer(text_region)]
    tab_refs = [f"table-{m.group(1)}" for m in TABLE_REF_RE.finditer(text_region)]

    # Top-level references in the chunk
    refs = extract_refs(chunk)

    return {
        "number": header["number"],
        "topic": title,
        "title": title_clean,
        "statement": statement,
        "grade": grade,
        "subItems": sub_items,
        "commentary": commentary,
        "figureRefs": sorted(set(fig_refs)),
        "tableRefs": sorted(set(tab_refs)),
        "references": refs,
    }


def render_rec_json(rec: dict, curriculum_lineage: str, modality_slug: str, release: str, source_doi: str, section_map: dict) -> dict:
    n = rec["number"]
    # Build a lineageId slug from the title
    slug_words = re.findall(r"[a-z]{3,}", rec["title"].lower())[:4]
    slug = "-".join(slug_words) if slug_words else f"r{n}"
    lineageId = f"rec-emr-cln-r{n}-{slug}"
    base_id = f"https://schema.evideris.com/esge/recommendation/{modality_slug}/r{n}.v1.0.0.json"
    section = section_map.get(n, "sec-emr-during-emr")  # best-guess default

    doc = {
        "$schema": "https://schema.evideris.com/schemas/recommendation.schema.json",
        "$id": base_id,
        "lineageId": lineageId,
        "type": "recommendation",
        "version": "1.0.0",
        "release": release,
        "supersedes": None,
        "supersededBy": None,
        "language": ["en"],
        "withinCurriculum": curriculum_lineage,
        "withinSection": section,
        "number": n,
        "title": {"en": rec["title"]},
        "statement": {"en": rec["statement"] or rec["title"]},
    }
    if rec["grade"]:
        doc["grade"] = rec["grade"]
    if rec["subItems"]:
        doc["subItems"] = rec["subItems"]
    if rec["commentary"]:
        doc["commentary"] = {"en": rec["commentary"]}
    if rec["figureRefs"]:
        doc["figureRefs"] = rec["figureRefs"]
    if rec["tableRefs"]:
        doc["tableRefs"] = rec["tableRefs"]
    doc["references"] = rec["references"]
    doc["_meta"] = {
        "provenance": {"type": "verbatim", "source_doi": source_doi},
        "encodedBy": "claude:extract-recommendations@v0.1.0",
        "encodedAt": "2026-06-27",
    }
    return doc


# Section assignment per Tate EMR 2023 topic-number → section-lineageId
# (Based on the source paper's sections 1-8 structure.)
SECTION_BY_NUMBER = {
    1:  "sec-emr-preadoption",
    2:  "sec-emr-preadoption",
    3:  "sec-emr-before-emr",
    4:  "sec-emr-before-emr",
    5:  "sec-emr-knowledge",
    6:  "sec-emr-knowledge",
    7:  "sec-emr-knowledge",
    8:  "sec-emr-knowledge",
    9:  "sec-emr-before-emr",
    10: "sec-emr-before-emr",
    11: "sec-emr-before-emr",
    12: "sec-emr-before-emr",
    13: "sec-emr-before-emr",
    14: "sec-emr-before-emr",
    15: "sec-emr-before-emr",
    16: "sec-emr-during-emr",
    17: "sec-emr-during-emr",
    18: "sec-emr-during-emr",
    19: "sec-emr-during-emr",
    20: "sec-emr-during-emr",
    21: "sec-emr-during-emr",
    22: "sec-emr-during-emr",
    23: "sec-emr-during-emr",
    24: "sec-emr-during-emr",
    25: "sec-emr-during-emr",
    26: "sec-emr-during-emr",
    27: "sec-emr-during-emr",
    28: "sec-emr-during-emr",
    29: "sec-emr-during-emr",
    30: "sec-emr-during-emr",
    31: "sec-emr-after-emr",
    32: "sec-emr-after-emr",
    33: "sec-emr-after-emr",
    34: "sec-emr-after-emr",
    35: "sec-emr-surveillance",
    36: "sec-emr-surveillance",
    37: "sec-emr-training",
    38: "sec-emr-lifelong-qi",
}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Extract recommendations from cached source PDF")
    p.add_argument("source_text", help="Path to cached source text")
    p.add_argument("curriculum_lineage", help="e.g. cur-emr-colon-2023")
    p.add_argument("release", help="e.g. r2026.07")
    p.add_argument("--source-doi", required=True)
    p.add_argument("--modality-slug", required=True)
    p.add_argument("--skip", type=int, nargs="*", default=[], help="Topic numbers to skip (already encoded)")
    p.add_argument("--out-root", default=None, help="Output dir (default: <repo>/esge/recommendation/<modality-slug>/)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    text_path = Path(args.source_text).expanduser().resolve()
    if not text_path.exists():
        raise SystemExit(f"Source text not found: {text_path}")
    text = text_path.read_text()

    headers = find_topic_headers(text)
    print(f"Detected {len(headers)} topic headers", file=sys.stderr)

    out_root = Path(args.out_root) if args.out_root else ROOT / "esge" / "recommendation" / args.modality_slug
    out_root.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    failed = []
    for i, h in enumerate(headers):
        n = h["number"]
        if n in args.skip:
            skipped += 1
            continue
        next_h = headers[i + 1] if i + 1 < len(headers) else None
        try:
            rec = extract_rec(text, h, next_h)
            if not rec["statement"]:
                failed.append(f"r{n} (no statement extracted): {h['title']}")
                continue
            doc = render_rec_json(rec, args.curriculum_lineage, args.modality_slug, args.release, args.source_doi, SECTION_BY_NUMBER)
            out_path = out_root / f"r{n}.v1.0.0.json"
            if args.dry_run:
                print(f"[dry-run] would write {out_path}", file=sys.stderr)
            else:
                out_path.write_text(json.dumps(doc, indent=2) + "\n")
                written += 1
            si = len(rec["subItems"])
            print(f"  r{n:2d}: {h['title'][:60]:60s} sub-items={si} loa={rec['grade'].get('levelOfAgreement') if rec['grade'] else '?'}", file=sys.stderr)
        except Exception as e:
            failed.append(f"r{n}: {e}")

    print(f"\nWrote {written} files; skipped {skipped} (already encoded); {len(failed)} failures", file=sys.stderr)
    for f in failed[:10]:
        print(f"  FAIL {f}", file=sys.stderr)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
