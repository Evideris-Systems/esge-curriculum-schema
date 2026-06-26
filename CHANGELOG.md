# Changelog

All notable changes to the ESGE Curriculum Schema. Follows per-artifact SemVer + repo-level CalVer release tags.

## Unreleased — r2026.07 (in progress)

### Added
- Initial repo skeleton: directory tree, LICENSE (CC BY 4.0), README.
- JSON Schema 2020-12 validator files for all nine artifact types: `release`, `curriculum`, `recommendation`, `competency`, `epa`, `standard`, `scoringTool`, `kpi`, `qi`, `cat`.
- Common envelope shared by all artifacts (`schemas/_common.schema.json`): versioned URL, `lineageId`, `type` discriminator, per-artifact SemVer, repo CalVer release tag, supersedes/supersededBy chain, language array.
- Tate et al. *Curriculum for training in endoscopic mucosal resection in the colon: ESGE Position Statement* (Endoscopy 2023; 55: 645–679, DOI 10.1055/a-2077-0497) seeding in progress as the first canonical curriculum.

### Notes
- Schema shape and design rationale are captured in the parent Evideris repo: `docs/plans/2026-06-15-evideris-endoscopy-design.md` §4 and `docs/plans/2026-06-17-esge-curriculum-schema-v0.md`.

### Tate EMR 2023 — first seed (Batch 1)
First substantive batch encoding Tate et al., *Curriculum for training in endoscopic mucosal resection in the colon: ESGE Position Statement*, Endoscopy 2023; 55: 645–679 (DOI 10.1055/a-2077-0497):

- **Curriculum wrapper** (`cur-emr-colon-2023`) with publication metadata (19 authors), Delphi methodology, all 11 main statements, 7 sections, disclaimer, acknowledgments, competing interests, partial bibliography.
- **6 of 38 recommendations** (representative across sections): R1 prerequisite competencies, R2 unit standards, R3 SMI assessment, R10 patient consent, R17 cold-snare placement/capture/closure, R38 essential QIs.
- **11 competencies** — typed across procedural / theoretical / communication / adverse-event management.
- **1 EPA** — independent piecemeal EMR (bundles 8 competencies; ten-Cate trust levels 1–5; 30-procedures-over-6-months gate, SMSA-stratified).
- **3 unit standards** (Rec 2 sub-items) with `evidenceRequired` for Centre Accreditation evidence-pack generation.
- **3 scoring tools** — NICE, JNET, Sydney DMI (SMSA was already seeded in the smoke-test batch).
- **1 KPI** — 30-cases-minimum training target (Main Statement 10).
- **5 QIs** (Table 6 subset) — procedures/year, success rate, intraprocedural bleeding, intraprocedural perforation, adenoma recurrence — each with `desiredStandard` / `minimumStandard` / `originData` (`iACE` study or `delphi`).
- **1 CAT** — GPAT with 6 of ~20 Table 4 items (items cross-ref recommendation sub-items via `assessesRecommendations`, with per-technique `applicability`: hot-snare vs cold-snare).
- **Release manifest** `r2026.07.json` updated to include all the above.

Every file validates against its schema via `scripts/validate.py`. Remaining ~30 recommendations and ~70 competencies, additional GPAT items, and the remaining 13 QIs will be added in subsequent batches.
