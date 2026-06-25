# ESGE Curriculum Schema

A versioned, machine-readable JSON Schema 2020-12 representation of the **European Society of Gastrointestinal Endoscopy (ESGE)** curricula and Competency Assessment Tools (CATs).

> **Status:** v0 — schema shape locked, validator files in place, first curriculum (Tate EMR 2023) being seeded. Open for review and adoption.
> **Licence:** [CC BY 4.0](./LICENSE) — fork it, build on it, integrate it. Just attribute.

## What this is

A canonical schema for expressing what ESGE publishes:

- **Curriculum** publications (their Delphi-derived position statements)
- **Recommendations** (GRADE-classified numbered statements)
- **Competencies** (atomic skills, surviving across curriculum revisions)
- **EPAs** (Entrustable Professional Activities — bundles of competencies with trust levels)
- **Standards** (institutional/unit-level requirements feeding centre accreditation)
- **Scoring tools** (SMSA, NICE, JNET, Sydney DMI, …)
- **KPIs** (training-target metrics)
- **QIs** (lifelong quality indicators)
- **CATs** (Competency Assessment Tools — DOPS, GPAT, …)

Plus a **release manifest** that snapshots which versions of which artifacts ship together each month.

## Why it exists

Trainee e-portfolios, centre accreditation evidence packs, and cross-border training recognition all need to point at *the same* canonical version of the curriculum. Right now they don't: every system rolls its own data model and they don't interoperate.

This repo is the shared schema layer. If your trainee e-portfolio cites
`https://schema.evideris.com/esge/competency/emr-cln/snare-capture.v1.0.0.json`,
any other ESGE-aligned system can resolve and interpret that pin.

## Layout

```
schemas/        # JSON Schema 2020-12 validator files (one per artifact type)
releases/       # Monthly release manifests (r2026.07.json, ...)
esge/           # The actual content — versioned JSON instances
  curriculum/
  recommendation/
  competency/
  epa/
  standard/
  scoring-tool/
  kpi/
  qi/
  cat/
```

## Versioning

- **Per-artifact SemVer** (`v1.0.0`) — each curriculum, recommendation, etc. has its own.
- **Release CalVer** (`r2026.07`) — monthly manifest snapshot pointing at all artifacts shipped together.
- Trainee logs cite the **per-artifact SemVer**, never the CalVer.
- Breaking-change rules and the autoupdate workflow live in the parent design doc (see [evideris](https://github.com/Evideris-Systems/evideris) `docs/plans/2026-06-15-evideris-endoscopy-design.md` §4.4).

## Hosting

Versioned URLs are served at `https://schema.evideris.com/...` (DNS / nginx setup pending). Until then, raw GitHub URLs work:
`https://raw.githubusercontent.com/Evideris-Systems/esge-curriculum-schema/main/esge/<type>/<path>`.

## Contributing

Issues and PRs welcome from the community. Curriculum content edits should be PR'd against the relevant JSON file with the per-artifact SemVer bump appropriate to the change (see breaking-change rules). The autoupdate skill (separate repo) handles bulk ingest from new ESGE publications.

## Citing

> Evideris Systems BV. ESGE Curriculum Schema. https://github.com/Evideris-Systems/esge-curriculum-schema. CC BY 4.0.

Once a stable v1.0.0 ships, a Zenodo DOI will be issued.
