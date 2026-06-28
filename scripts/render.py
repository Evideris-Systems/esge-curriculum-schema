#!/usr/bin/env python3
"""render.py — read both repos and emit a self-contained HTML page rendering
the curriculum end-to-end (or, with --cat-only, just one CAT).

Joins source-canonical (esge-curriculum-schema) with derived
(evideris-curriculum-derived) into one human-readable view.

Usage:
    python3 scripts/render.py                            # full Tate EMR 2023 → /tmp/curriculum.html
    python3 scripts/render.py --cat-only cat-gpat        # GPAT only → /tmp/cat-gpat.html
    python3 scripts/render.py --out report.html          # custom output path
    python3 scripts/render.py --open                     # auto-open in browser
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SOURCE_REPO  = Path(os.environ.get("ESGE_CURRICULUM_SCHEMA_REPO",
                                    str(Path.home() / "Documents/GitHubs/esge-curriculum-schema"))).expanduser()
DERIVED_REPO = Path(os.environ.get("EVIDERIS_CURRICULUM_DERIVED_REPO",
                                    str(Path.home() / "Documents/GitHubs/evideris-curriculum-derived"))).expanduser()


def load_all(repo: Path, sub: str) -> list[dict]:
    out = []
    for p in sorted((repo / sub).rglob("*.json")) if (repo / sub).exists() else []:
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            continue
    return out


def by_lineage(docs: list[dict]) -> dict[str, dict]:
    return {d.get("lineageId"): d for d in docs if d.get("lineageId")}


def loc(s, key="en"):
    """Pull English text from a locale-keyed object (or pass through plain strings)."""
    if isinstance(s, dict):
        return s.get(key, next(iter(s.values()), ""))
    return s or ""


def esc(s: str) -> str:
    return html.escape(str(s or ""))


# ============================================================================
# CSS — self-contained. Palette/typography from esge-certification-app-test
# design tokens (~/Documents/GitHubs/esge-certification-app-test/app/globals.css
# + tailwind.config.ts). When this page is later embedded INSIDE the cert app,
# pass --embed to drop the @import + outer chrome and inherit host styles.
# ============================================================================
CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Open+Sans:wdth,wght@75..100,400;75..100,600;75..100,700&family=Roboto:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  /* ESGE design tokens — mirror esge-certification-app-test */
  --color-primary: #004187;
  --color-primary-hover: #00305f;
  --color-accent: #009a91;
  --color-accent-hover: #007f78;
  --color-surface: #ffffff;
  --color-paper: #faf9f6;
  --color-surface-muted: #f2f1ef;
  --color-surface-mint: #eaf7f5;
  --color-mint: #a6dad0;
  --color-certificate-gold: #fde194;
  --color-on-surface: #171717;
  --color-on-surface-muted: #44546a;
  --color-on-surface-soft: #6b7280;
  --color-blue-grey: #44546a;
  --color-border: #e5e7eb;
  --color-border-strong: #d1d5db;
  --color-success: #22c55e;
  --color-success-surface: #dcfce7;
  --color-warning: #f59e0b;
  --color-warning-surface: #fef3c7;
  --color-error: #ef4444;
  --color-error-surface: #fee2e2;

  /* Legacy aliases used throughout the renderer */
  --ink: var(--color-on-surface);
  --paper: var(--color-paper);
  --paper-2: var(--color-surface-muted);
  --rule: var(--color-border);
  --accent: var(--color-accent);
  --primary: var(--color-primary);
  --shade: var(--color-on-surface-muted);
  --good: var(--color-success);
  --mid: var(--color-warning);
  --warn: var(--color-error);
}
* { box-sizing: border-box; }
body {
  font: 16px/1.55 "Roboto", system-ui, -apple-system, Helvetica, Arial, sans-serif;
  background: var(--paper);
  color: var(--ink);
  margin: 0;
  padding: 0;
}

/* ----- Sticky top nav (table of contents) ----- */
nav.toc {
  position: sticky; top: 0; z-index: 100;
  background: var(--color-primary); color: white;
  padding: .55rem 1rem;
  border-bottom: 3px solid var(--color-accent);
  display: flex; align-items: center; gap: 1rem;
  font-family: "Open Sans", "Arial Narrow", Arial, sans-serif;
  font-stretch: 87.5%;
  font-size: .82rem; letter-spacing: .03em;
  overflow-x: auto;
  -ms-overflow-style: none; scrollbar-width: none;
}
nav.toc::-webkit-scrollbar { display: none; }
nav.toc .brand { font-weight: 700; font-size: .95rem; margin-right: .8rem; white-space: nowrap; }
nav.toc a {
  color: white; text-decoration: none;
  padding: .25rem .6rem; border-radius: 3px;
  white-space: nowrap;
  transition: background .15s;
}
nav.toc a:hover { background: rgba(255,255,255,.12); }
nav.toc a.active { background: var(--color-accent); }
nav.toc .divider { color: rgba(255,255,255,.4); padding: 0 .2rem; }
nav.toc .source-link {
  margin-left: auto; padding: .25rem .65rem;
  background: rgba(255,255,255,.12); border-radius: 3px;
  font-size: .75rem;
}

.wrap { max-width: 980px; margin: 0 auto; padding: 2.5rem 1rem 6rem; }
header.cur {
  border-bottom: 2px solid var(--primary);
  padding-bottom: 1.5rem; margin-bottom: 2rem;
}
header.cur .eyebrow { font-size: .75rem; letter-spacing: .14em; text-transform: uppercase; color: var(--shade); font-family: "Open Sans", sans-serif; font-stretch: 87.5%; }
header.cur h1 {
  font-family: "Open Sans", "Arial Narrow", Arial, sans-serif;
  font-stretch: 87.5%; font-weight: 700;
  font-size: 2rem; line-height: 1.15;
  margin: .4rem 0 .6rem;
  color: var(--primary);
}
header.cur .auths { font-size: .9rem; color: var(--shade); }
header.cur .meta { font-size: .85rem; color: var(--shade); margin-top: .6rem; }
header.cur .meta a { color: var(--primary); text-decoration: underline; }
.tagline { font-size: .95rem; color: var(--shade); }

h2 {
  font-family: "Open Sans", "Arial Narrow", Arial, sans-serif;
  font-stretch: 87.5%; font-weight: 700;
  font-size: 1.4rem; line-height: 1.2;
  margin: 3rem 0 1.2rem;
  padding-bottom: .35rem;
  border-bottom: 1px solid var(--rule);
  color: var(--primary);
  scroll-margin-top: 4rem;
}
h3 {
  font-family: "Open Sans", "Arial Narrow", Arial, sans-serif;
  font-stretch: 87.5%; font-weight: 700;
  font-size: 1.05rem; line-height: 1.3;
  margin: 1.6rem 0 .5rem;
  color: var(--color-blue-grey);
  scroll-margin-top: 4rem;
}
h4 { font: 600 .8rem/1.3 "Roboto", sans-serif; margin: 1rem 0 .4rem; color: var(--shade); text-transform: uppercase; letter-spacing: .06em; }

.main-statements { background: var(--paper-2); padding: 1rem 1.4rem; border-left: 3px solid var(--accent); margin: 1rem 0 2rem; border-radius: 2px; }
.main-statements ol { margin: 0; padding-left: 1.2rem; }
.main-statements li { margin: .4rem 0; }

.rec { background: var(--paper-2); padding: 1.2rem 1.4rem; margin: 1rem 0; border-radius: 4px; border-left: 3px solid var(--rule); }
.rec.strong { border-left-color: var(--good); }
.rec.weak { border-left-color: var(--mid); }
.rec.best-practice { border-left-color: var(--accent); }
.rec .num-title { font-weight: 700; margin-bottom: .4rem; font-size: 1.05rem; }
.rec .num { color: var(--shade); margin-right: .5rem; }
.rec .statement { margin: .3rem 0 .8rem; }
.rec .grade { display: inline-flex; gap: .4rem; flex-wrap: wrap; margin: .2rem 0 .8rem; }
.chip { display: inline-block; padding: .15rem .55rem; font-size: .72rem; letter-spacing: .04em; text-transform: uppercase; border-radius: 99px; border: 1px solid var(--rule); background: white; color: var(--shade); }
.chip.strong { background: var(--good); color: white; border-color: var(--good); }
.chip.weak { background: var(--mid); color: white; border-color: var(--mid); }
.chip.best-practice { background: var(--accent); color: white; border-color: var(--accent); }
.chip.evidence-high   { background: #e8f5e9; color: var(--good); border-color: var(--good); }
.chip.evidence-moderate{ background: #fff8e1; color: var(--mid); border-color: var(--mid); }
.chip.evidence-low    { background: #fbe9e7; color: var(--warn); border-color: var(--warn); }
.chip.evidence-very-low{ background: #fbe9e7; color: var(--warn); border-color: var(--warn); }
.chip.evidence-no-evidence-available { background: #f0f0ee; color: var(--shade); }
.chip.loa { background: #e0f7fa; color: var(--ink); }
.chip.kind { background: #f3f1e8; color: var(--shade); }
.chip.applicability-mandatory { background: var(--good); color: white; border-color: var(--good); }
.chip.applicability-optional { background: #f3f1e8; color: var(--shade); }
.chip.applicability-not-applicable { background: #f0f0ee; color: var(--shade); text-decoration: line-through; }

.subitems { margin: .5rem 0; padding-left: 0; list-style: none; counter-reset: subi; }
.subitems li { padding: .35rem 0 .35rem 1.6rem; position: relative; }
.subitems li::before { counter-increment: subi; content: "(" attr(data-label) ")"; position: absolute; left: 0; color: var(--shade); font-size: .85rem; }
.subitems li .si-loa { font-size: .7rem; color: var(--shade); margin-left: .4rem; }
.commentary { background: white; padding: .8rem 1.1rem; margin: .8rem 0 0; font-size: .92rem; border-radius: 2px; color: var(--shade); font-style: italic; border-left: 2px solid var(--rule); }
.known-incomplete {
  background: var(--color-warning-surface);
  border-left: 3px solid var(--color-warning);
  padding: .65rem .9rem;
  margin: .7rem 0 0;
  font-size: .85rem;
  border-radius: 2px;
  color: var(--ink);
}
.known-incomplete .ki-reason { color: var(--color-on-surface-muted); display: block; margin-top: .25rem; }
.known-incomplete .ki-tracked { color: var(--color-on-surface-soft); font-size: .78rem; }
.refs-inline { font-size: .8rem; color: var(--shade); margin-left: .4rem; }

table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: .92rem; }
th, td { padding: .55rem .75rem; text-align: left; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { background: var(--paper-2); font-weight: 700; font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; color: var(--shade); }
.qi-table .num { color: var(--good); font-weight: 700; }

.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: .8rem; margin: 1rem 0; }
.card { background: var(--paper-2); padding: .9rem 1.1rem; border-radius: 3px; border-left: 3px solid var(--accent); }
.card .ktitle { font-weight: 700; margin-bottom: .3rem; }
.card .kdesc { font-size: .88rem; color: var(--shade); }

.cat-table { width: 100%; }
.cat-table th, .cat-table td { padding: .8rem; vertical-align: top; }
.cat-table .item { font-weight: 600; }
.cat-table .guidance { font-size: .88rem; color: var(--shade); }
.cat-table .appl { font-size: .75rem; }

.standards .std { margin: 1rem 0; }
.std .text { padding: .7rem 1rem; background: var(--paper-2); border-left: 3px solid var(--rule); }
.std .evidence { margin: .5rem 0 0 1.5rem; }
.std .evidence-item { padding: .3rem 0; font-size: .9rem; color: var(--shade); }
.std .evidence-item .et { background: var(--accent); color: white; padding: .05rem .4rem; border-radius: 2px; font-size: .7rem; margin-right: .4rem; text-transform: uppercase; letter-spacing: .04em; }

.disclaimer, .ack, .ci { font-size: .82rem; color: var(--shade); margin: 1rem 0; }
.disclaimer { padding: .8rem 1.1rem; background: var(--paper-2); border-left: 2px solid var(--rule); border-radius: 2px; }

.prov-badge { display: inline-block; padding: .1rem .45rem; font-size: .68rem; border-radius: 99px; margin-left: .4rem; vertical-align: middle; }
.prov-verbatim { background: var(--good); color: white; }
.prov-paraphrased { background: var(--accent); color: white; }
.prov-evideris-design { background: var(--mid); color: white; }
.prov-inferred-from-source { background: var(--shade); color: white; }
.prov-verbatim-from-primary-source, .prov-paraphrased-from-primary-source { background: var(--accent); color: white; }

footer.cur { margin-top: 4rem; padding-top: 1.2rem; border-top: 1px solid var(--rule); font-size: .8rem; color: var(--shade); }
footer.cur code { font-family: "JetBrains Mono", monospace; background: var(--paper-2); padding: .1rem .3rem; border-radius: 2px; }

@media print {
  body { background: white; }
  .rec, .card, .main-statements, .disclaimer { background: white; border-left-width: 2px; }
  h2 { page-break-before: always; }
  h2:first-of-type { page-break-before: auto; }
  .wrap { max-width: 100%; padding: 1rem; }
}
"""


# ============================================================================
# Renderers
# ============================================================================

def render_grade(grade: dict) -> str:
    if not grade: return ""
    parts = []
    s = grade.get("strength")
    e = grade.get("evidenceQuality")
    loa = grade.get("levelOfAgreement")
    if s:
        parts.append(f'<span class="chip {esc(s)}">{esc(s)}</span>')
    if e:
        parts.append(f'<span class="chip evidence-{esc(e)}">{esc(e)} evidence</span>')
    if loa is not None:
        parts.append(f'<span class="chip loa">LoA {esc(loa)}%</span>')
    return f'<div class="grade">{"".join(parts)}</div>'


def render_subitems(items: list[dict]) -> str:
    if not items: return ""
    rows = []
    for it in items:
        label = esc(it.get("label", ""))
        text = esc(loc(it.get("text", "")))
        loa = it.get("levelOfAgreement")
        loa_s = f'<span class="si-loa">LoA {loa}%</span>' if loa is not None else ""
        rows.append(f'<li data-label="{label}">{text}{loa_s}</li>')
    return f'<ul class="subitems">{"".join(rows)}</ul>'


def render_recommendation(rec: dict) -> str:
    strength = (rec.get("grade") or {}).get("strength", "")
    ki = (rec.get("_meta") or {}).get("knownIncomplete") or {}
    incomplete_html = ""
    if ki.get("field") == "subItems":
        incomplete_html = (
            '<div class="known-incomplete">'
            '<strong>🚧 Sub-items pending verbatim extraction.</strong> '
            f'<span class="ki-reason">{esc(ki.get("reason", ""))}</span>'
            + (f' <span class="ki-tracked">Tracked in {esc(ki.get("trackedIn"))}.</span>' if ki.get("trackedIn") else "")
            + '</div>'
        )
    return f"""
    <div class="rec {esc(strength)}">
      <div class="num-title"><span class="num">{esc(rec.get("number", "?"))}</span>{esc(loc(rec.get("title")))}</div>
      <div class="statement">{esc(loc(rec.get("statement")))}</div>
      {render_grade(rec.get("grade") or {})}
      {render_subitems(rec.get("subItems") or [])}
      {incomplete_html}
      {f'<div class="commentary">{esc(loc(rec.get("commentary")))}</div>' if rec.get("commentary") else ""}
    </div>
    """


def render_standards(standards: list[dict], evidence_criteria: list[dict]) -> str:
    ec_by_std = {}
    for ec in evidence_criteria:
        std = ec.get("forStandard")
        if std:
            ec_by_std.setdefault(std, []).append(ec)
    if not standards: return "<p>No standards.</p>"
    rows = []
    for s in standards:
        ecs = ec_by_std.get(s.get("lineageId"), [])
        ev_rows = []
        for ec in ecs:
            for c in ec.get("criteria", []):
                et = c.get("evidenceType", "")
                desc = esc(loc(c.get("description")))
                threshold = f" (threshold: <strong>{esc(c.get('threshold'))}</strong>)" if c.get("threshold") else ""
                ev_rows.append(f'<div class="evidence-item"><span class="et">{esc(et)}</span>{desc}{threshold}</div>')
        rows.append(f"""
        <div class="std">
          <h4>{esc(loc(s.get("title")))}</h4>
          <div class="text">{esc(loc(s.get("text")))}</div>
          {f'<div class="evidence">{"".join(ev_rows)}</div>' if ev_rows else ""}
        </div>
        """)
    return f'<div class="standards">{"".join(rows)}</div>'


def render_qis_table(qis: list[dict]) -> str:
    if not qis: return ""
    rows = []
    for q in qis:
        od = q.get("originData") or {}
        ci = od.get("confidenceInterval95") or {}
        ci_s = f' ({ci["low"]}%–{ci["high"]}%)' if ci.get("low") is not None else ""
        rows.append(f"""
        <tr>
          <td>{esc(loc(q.get("title")))}</td>
          <td>{esc(od.get("source", "—"))}</td>
          <td>{esc(od.get("value") if od.get("value") is not None else "—")}{esc(ci_s)}</td>
          <td>{esc(q.get("desiredStandard") if q.get("desiredStandard") is not None else "—")}{esc(" "+q.get("unit") if q.get("desiredStandard") is not None else "")}</td>
          <td>{esc(q.get("minimumStandard") if q.get("minimumStandard") is not None else "—")}{esc(" "+q.get("unit") if q.get("minimumStandard") is not None else "")}</td>
          <td>{esc(q.get("levelOfAgreement", "—"))}%</td>
        </tr>
        """)
    return f"""
    <table class="qi-table">
      <thead><tr><th>Indicator</th><th>Origin</th><th>Origin data</th><th>Desired</th><th>Minimum</th><th>LoA</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    """


def render_competencies(competencies: list[dict]) -> str:
    if not competencies: return "<p>No competencies in derived layer.</p>"
    rows = []
    for c in competencies:
        ms_rows = []
        for ms in c.get("milestones", []):
            cases = f' (≥{ms["expectedAtCases"]} cases)' if ms.get("expectedAtCases") else ""
            ms_rows.append(f'<li><strong>{esc(ms["level"])}{esc(cases)}:</strong> {esc(loc(ms["criteria"]))}</li>')
        sc = f"Suggested caseload: <strong>{c['suggestedCaseload']}</strong>" if c.get("suggestedCaseload") else ""
        rows.append(f"""
        <div class="card">
          <div class="ktitle">{esc(loc(c.get("title")))} <span class="chip kind">{esc(c.get("kind"))}</span></div>
          <div class="kdesc">{esc(loc(c.get("description")))}</div>
          {f'<ul style="margin:.6rem 0 0;padding-left:1.1rem;font-size:.88rem">{"".join(ms_rows)}</ul>' if ms_rows else ""}
          {f'<div style="margin-top:.5rem;font-size:.82rem;color:var(--shade)">{sc}</div>' if sc else ""}
        </div>
        """)
    return f'<div class="cards">{"".join(rows)}</div>'


def render_epa(epa: dict, competencies: list[dict]) -> str:
    if not epa: return ""
    comp_by_lid = {c.get("lineageId"): c for c in competencies}
    comp_titles = []
    for cref in epa.get("competencyRefs", []):
        c = comp_by_lid.get(cref)
        if c:
            comp_titles.append(f'<li>{esc(loc(c.get("title")))}</li>')
    tl_rows = []
    for tl in epa.get("trustLevels", []):
        tl_rows.append(f'<tr><td><strong>{esc(tl["value"])}</strong></td><td>{esc(loc(tl["label"]))}</td></tr>')
    req = epa.get("requiredExposure") or {}
    req_s = ", ".join(filter(None, [
        f"≥ {req['minProcedures']} procedures" if req.get("minProcedures") else "",
        f"≥ {req['minPeriodMonths']} months" if req.get("minPeriodMonths") else "",
        f"stratified by {esc(req['stratifiedBy'])}" if req.get("stratifiedBy") else "",
    ]))
    return f"""
    <div class="rec strong">
      <div class="num-title">{esc(loc(epa.get("title")))}</div>
      <div class="statement">{esc(loc(epa.get("description")))}</div>
      <h4>Bundles competencies</h4>
      <ul style="margin:.3rem 0 1rem;padding-left:1.2rem">{"".join(comp_titles)}</ul>
      <h4>Trust levels (ten Cate)</h4>
      <table>{"".join(tl_rows)}</table>
      {f'<h4>Required exposure</h4><div>{req_s}</div>' if req_s else ""}
    </div>
    """


def render_cat(cat: dict) -> str:
    if not cat: return ""
    levels = (cat.get("scoringScale") or {}).get("levels", [])
    lv_chips = "".join(f'<span class="chip">{esc(lv["value"])}: {esc(loc(lv["label"]))}</span>' for lv in levels)
    rows = []
    for it in cat.get("items", []):
        app = it.get("applicability") or {}
        app_chips = " ".join(f'<span class="chip applicability-{esc(v)}">{esc(k)}: {esc(v)}</span>' for k, v in app.items())
        rec_refs = []
        for r in it.get("assessesRecommendations", []):
            if isinstance(r, dict):
                rec_refs.append(f'{esc(r.get("lineageId"))} ({esc(r.get("subItem","?"))})')
            else:
                rec_refs.append(esc(r))
        rows.append(f"""
        <tr>
          <td class="item">{esc(loc(it.get("label")))}</td>
          <td class="guidance"><strong>Very good (5):</strong> {esc(loc(it.get("guidance", "")))}</td>
          <td class="appl">{app_chips}</td>
        </tr>
        """)
    return f"""
    <h3>Scoring scale</h3>
    <div style="margin:.5rem 0 1.2rem">{lv_chips}</div>
    <table class="cat-table">
      <thead><tr><th>Component</th><th>Anchor</th><th>Mandatory</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    """


def render_scoring_tools(tools: list[dict]) -> str:
    if not tools: return ""
    cards = []
    for t in tools:
        scale = (t.get("scale") or {})
        bands = scale.get("bands") or []
        band_html = "<br>".join(esc(loc(b["label"])) for b in bands) if bands else ""
        prov = (t.get("_meta") or {}).get("provenance") or {}
        prov_chip = f'<span class="prov-badge prov-{esc(prov.get("type",""))}">{esc(prov.get("type","").replace("-", " "))}</span>' if prov.get("type") else ""
        cards.append(f"""
        <div class="card">
          <div class="ktitle">{esc(loc(t.get("title")))} {prov_chip}</div>
          <div class="kdesc">{esc(loc(t.get("description")))}</div>
          {f'<div style="margin-top:.4rem;font-size:.85rem">{band_html}</div>' if band_html else ""}
        </div>
        """)
    return f'<div class="cards">{"".join(cards)}</div>'


def render_curriculum_page(cur: dict, recs: list[dict], standards: list[dict], qis: list[dict],
                            cat: dict | None, competencies: list[dict], epa: dict | None,
                            evidence_criteria: list[dict], scoring_tools_canonical: list[dict],
                            scoring_tools_derived: list[dict], refs_doc: dict | None) -> str:
    pub = cur.get("publication") or {}
    auths = ", ".join(a.get("name", "") for a in pub.get("authors", [])[:6])
    if len(pub.get("authors", [])) > 6:
        auths += f", and {len(pub['authors']) - 6} others"
    main_stmts = "".join(f'<li>{esc(loc(s["text"]))}</li>' for s in cur.get("mainStatements", []))

    # Group recs by section
    sections = {s.get("lineageId"): s for s in cur.get("sections", [])}
    recs_by_section = {}
    for r in recs:
        ws = r.get("withinSection") or "unsection"
        recs_by_section.setdefault(ws, []).append(r)

    section_blocks = []
    for s_lid, sec in sections.items():
        rec_list = sorted(recs_by_section.get(s_lid, []), key=lambda r: r.get("number") or 999)
        if not rec_list: continue
        rec_html = "".join(render_recommendation(r) for r in rec_list)
        section_blocks.append(f"""
        <h3>Section {esc(sec.get("number"))}: {esc(loc(sec.get("title")))}</h3>
        {rec_html}
        """)
    # Any recs not assigned to a section
    unsection_recs = sorted(recs_by_section.get("unsection", []), key=lambda r: r.get("number") or 999)
    if unsection_recs:
        section_blocks.append("".join(render_recommendation(r) for r in unsection_recs))

    cis = cur.get("competingInterests") or []
    ci_html = "<br>".join(f'<strong>{esc(c.get("author"))}:</strong> {esc(c.get("statement"))}' for c in cis)

    refs_link = ""
    if refs_doc:
        refs_count = len(refs_doc.get("references", []))
        refs_link = f'<p style="margin-top:1rem"><a href="#references">{refs_count} bibliography entries</a></p>'

    refs_html = ""
    if refs_doc:
        ref_rows = []
        for r in refs_doc.get("references", []):
            doi_link = f' <a href="https://doi.org/{esc(r["doi"])}" target="_blank">doi:{esc(r["doi"])}</a>' if r.get("doi") else ""
            ref_rows.append(f'<li id="{esc(r.get("id",""))}"><strong>[{esc(r.get("id","").replace("ref-",""))}]</strong> {esc(r.get("citation"))}{doi_link}</li>')
        refs_html = f"""
        <h2 id="references">References ({len(ref_rows)})</h2>
        <ol style="font-size:.85rem;line-height:1.5">{"".join(ref_rows[:200])}</ol>
        """

    nav_html = """
<nav class="toc" id="toc">
  <span class="brand">ESGE EMR Curriculum</span>
  <a href="#main-statements">Main statements</a>
  <a href="#recommendations">Recommendations</a>
  <a href="#standards">Standards</a>
  <a href="#qis">QIs</a>
  <a href="#cat">CAT</a>
  <a href="#scoring-tools">Scoring tools</a>
  <a href="#competencies">Competencies</a>
  <a href="#epa">EPA</a>
  <a href="#references">References</a>
  <a class="source-link" href="https://doi.org/""" + esc(pub.get("doi", "")) + """\" target="_blank">Source PDF →</a>
</nav>
"""

    scrollspy_js = """
<script>
// Lightweight scrollspy — highlight active nav link as user scrolls
(function() {
  var links = document.querySelectorAll('nav.toc a[href^="#"]');
  var sections = Array.from(links).map(function(a) {
    var id = a.getAttribute('href').slice(1);
    return { id: id, el: document.getElementById(id), link: a };
  }).filter(function(s) { return s.el; });

  function update() {
    var y = window.scrollY + 80;
    var current = sections[0];
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].el.offsetTop <= y) current = sections[i];
    }
    links.forEach(function(a) { a.classList.remove('active'); });
    if (current) current.link.classList.add('active');
  }
  window.addEventListener('scroll', update, { passive: true });
  update();
})();
</script>
"""

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(pub.get("title", loc(cur.get("scope"))))} — ESGE Curriculum</title>
<style>{CSS}</style>
</head>
<body>

{nav_html}

<div class="wrap">

<header class="cur" id="top">
  <div class="eyebrow">ESGE Position Statement · {esc(cur.get("lineageId"))} · release {esc(cur.get("release"))}</div>
  <h1>{esc(pub.get("title", loc(cur.get("scope"))))}</h1>
  <div class="auths">{esc(auths)}</div>
  <div class="meta">
    <em>{esc(pub.get("journal"))}</em> {esc(pub.get("year"))};{esc(pub.get("volume"))}({esc(pub.get("issue"))}): {esc(pub.get("pages"))}
    {f' · <a href="https://doi.org/{esc(pub["doi"])}" target="_blank">doi:{esc(pub["doi"])}</a>' if pub.get("doi") else ""}
    {f' · <a href="{esc(pub["openAccessUrl"])}" target="_blank">open-access PDF</a>' if pub.get("openAccessUrl") else ""}
    {refs_link}
  </div>
</header>

<p class="tagline">{esc(loc(cur.get("scope")))}</p>

<h2 id="main-statements">Main statements</h2>
<div class="main-statements"><ol>{main_stmts}</ol></div>

<h2 id="recommendations">Recommendations</h2>
{"".join(section_blocks)}

<h2 id="standards">Unit standards & accreditation evidence</h2>
<p class="tagline">Standards verbatim from ESGE source; evidence criteria are Evideris's design for Centre Accreditation.</p>
{render_standards(standards, evidence_criteria)}

<h2 id="qis">Lifelong quality indicators (Table 6)</h2>
{render_qis_table(qis)}

<h2 id="cat">Competency Assessment Tool ({esc(cat.get("catFamily","GPAT")) if cat else "GPAT"})</h2>
{render_cat(cat) if cat else "<p>No CAT artifact.</p>"}

<h2 id="scoring-tools">Scoring tools</h2>
<h4>Defined in source</h4>
{render_scoring_tools(scoring_tools_canonical)}
<h4>Referenced (defined in primary sources)</h4>
{render_scoring_tools(scoring_tools_derived)}

<h2 id="competencies">Competencies (Evideris-derived)</h2>
<p class="tagline">Atomic skills derived from source recommendations — the unit a trainee is scored on. <strong>This is Evideris's design</strong>, not published by ESGE.</p>
{render_competencies(competencies)}

<h2 id="epa">Entrustable Professional Activity (Evideris-derived)</h2>
<p class="tagline">Forward-design by David Tate as ESGE Curriculum committee member. Bundles competencies into a unit of work a supervisor can entrust.</p>
{render_epa(epa, competencies)}

<h2>Disclaimer</h2>
<div class="disclaimer">{esc(cur.get("disclaimer", ""))}</div>

<h2>Acknowledgments</h2>
<div class="ack">{esc(cur.get("acknowledgments", ""))}</div>

<h2>Competing interests</h2>
<div class="ci">{ci_html}</div>

{refs_html}

<footer class="cur">
  Rendered from <code>esge-curriculum-schema</code> + <code>evideris-curriculum-derived</code> via <code>scripts/render.py</code>.
  Source-canonical content CC BY 4.0 · Derived content CC BY-NC-SA 4.0 · Evideris Systems BV 2026.
  Branding tokens drawn from <code>esge-certification-app-test</code> design system for embedding consistency.
</footer>

</div>

{scrollspy_js}

</body></html>
"""


def render_cat_only(cat: dict) -> str:
    title = esc(loc(cat.get("title")))
    desc  = esc(loc(cat.get("description")))
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — CAT viewer</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="cur">
  <div class="eyebrow">Competency Assessment Tool · {esc(cat.get("catFamily",""))} · release {esc(cat.get("release",""))}</div>
  <h1>{title}</h1>
  <div class="meta">{desc}</div>
</header>
{render_cat(cat)}
<footer class="cur">Rendered from <code>esge-curriculum-schema</code>/cat/<code>{esc(cat.get("lineageId"))}</code></footer>
</div>
</body></html>
"""


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Render curriculum or CAT to HTML")
    p.add_argument("--cat-only", default=None, help="Render only the given CAT lineageId (e.g. cat-gpat)")
    p.add_argument("--out", default=None, help="Output HTML path (default: /tmp/curriculum.html or /tmp/<lineageId>.html)")
    p.add_argument("--open", action="store_true", help="Open in default browser when done")
    args = p.parse_args(argv)

    # Load source-canonical
    sc_recs = load_all(SOURCE_REPO, "esge/recommendation")
    sc_stds = load_all(SOURCE_REPO, "esge/standard")
    sc_qis  = load_all(SOURCE_REPO, "esge/qi")
    sc_cats = load_all(SOURCE_REPO, "esge/cat")
    sc_st   = load_all(SOURCE_REPO, "esge/scoring-tool")
    sc_curs = load_all(SOURCE_REPO, "esge/curriculum")
    refs    = [d for d in sc_curs if d.get("type") == "references"]
    curs    = [d for d in sc_curs if d.get("type") == "curriculum"]

    # Load derived
    d_comp = load_all(DERIVED_REPO, "derived/competency")
    d_epa  = load_all(DERIVED_REPO, "derived/epa")
    d_ec   = load_all(DERIVED_REPO, "derived/evidence-criterion")
    d_st   = load_all(DERIVED_REPO, "derived/scoring-tool")

    if args.cat_only:
        cat = next((c for c in sc_cats if c.get("lineageId") == args.cat_only), None)
        if not cat:
            raise SystemExit(f"CAT not found: {args.cat_only}")
        html_out = render_cat_only(cat)
        out_path = Path(args.out or f"/tmp/{args.cat_only}.html")
    else:
        if not curs:
            raise SystemExit("No curriculum found in source repo")
        cur = curs[0]  # currently only one
        cur_lid = cur.get("lineageId")
        refs_doc = next((r for r in refs if r.get("forCurriculum") == cur_lid), None)
        cat = sc_cats[0] if sc_cats else None
        epa = d_epa[0] if d_epa else None
        html_out = render_curriculum_page(
            cur, sc_recs, sc_stds, sc_qis, cat, d_comp, epa,
            d_ec, sc_st, d_st, refs_doc,
        )
        out_path = Path(args.out or "/tmp/curriculum.html")

    out_path.write_text(html_out)
    print(f"Wrote {out_path} ({len(html_out):,} chars)")
    if args.open:
        subprocess.run(["open", str(out_path)])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
