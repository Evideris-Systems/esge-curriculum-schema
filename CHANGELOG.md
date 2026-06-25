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
