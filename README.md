# ESGE Curriculum Schema

A versioned, machine-readable JSON Schema 2020-12 representation of European
Society of Gastrointestinal Endoscopy (ESGE) curricula, source-defined
assessment tools and related publication artifacts.

> **Status:** `r2026.07` is a review release containing EMR, ESD and POEM Part
> II. It is not approved as production certification policy.

## Rights and licence

The [CC BY 4.0 licence](./LICENSE) covers Evideris-authored schema definitions,
validation code and release metadata. Encoded ESGE/Thieme publication content
retains the rights of its original authors and publishers. This repository does
not by itself grant permission to relicense or redistribute that third-party
content; confirm the applicable authority before external or production use.

Every artifact records its own source and provenance. Release manifests record
which exact versions are assembled together, but do not replace the rights
status of their members.

## What this is

The source-canonical layer expresses what the underlying publications define:

- curriculum wrappers and bibliography records;
- GRADE-classified recommendations and main statements;
- institutional standards, KPIs and quality indicators;
- source-defined scoring and competency assessment tools such as SMSA, GPAT and
  PPAT;
- publication figures and tables retained for traceability and rights review.

Evideris-authored competencies, EPAs, evidence criteria and
recommendation-to-competency mappings live in the separate
[`evideris-curriculum-derived`](https://github.com/Evideris-Systems/evideris-curriculum-derived)
repository. They are deliberately not represented as source-canonical ESGE
publication content.

## Why it exists

Trainee e-portfolios, centre accreditation evidence packs and cross-border
training recognition need stable identifiers for the same published material.
The repository supplies versioned artifacts and a release manifest so consumers
can pin an exact, reviewable snapshot rather than silently choosing the latest
file.

For example, a consumer can pin
`esge/recommendation/emr-colon/r1.v1.0.0.json` together with its release path and
SHA-256.

## Layout

```text
schemas/        # JSON Schema 2020-12 validators
releases/       # Calendar-versioned release manifests
esge/           # Versioned source-canonical instances
  curriculum/   # Publication wrappers and bibliography records
  recommendation/
  standard/
  scoring-tool/
  kpi/
  qi/
  cat/
  figure/
  table/
scripts/        # Validation, source-trace and release-hash tooling
```

## Versioning and release integrity

- Each artifact has its own semantic version, such as `v1.0.0`.
- A release uses calendar versioning, such as `r2026.07`, and selects exact
  artifact versions.
- Every release member records a repository-relative `path` and raw-file
  `sha256`; `make check` rejects missing, moved or modified members.
- Downstream records should cite the artifact lineage and semantic version and
  retain the release/bundle digest used at the time.

After changing release membership or a released artifact, refresh the manifest
and run the full checks:

```bash
python3 scripts/update-release-hashes.py --write --root esge releases/r2026.07.json
make check
```

## Hosting

`schema.evideris.com` is the identifier namespace and planned publication
endpoint. It is not a runtime dependency for the certification application.
Until publication is configured, consumers should use a pinned Git commit or
bundle rather than a mutable raw-GitHub URL.

## Contributing

Issues and pull requests are welcome. Content changes require source evidence,
an appropriate artifact version change, refreshed release hashes and a passing
`make check`. Adding content to the repository does not settle its publication
or redistribution rights.

## Citing

> Evideris Systems BV. ESGE Curriculum Schema (schema, validation tooling and
> release metadata). https://github.com/Evideris-Systems/esge-curriculum-schema.
> CC BY 4.0. Encoded publication content retains its original rights.

Once a stable schema release ships, a Zenodo DOI can be issued for the
Evideris-authored schema and tooling.
