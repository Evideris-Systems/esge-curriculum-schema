.PHONY: check schema-check source-trace verify-citations completeness completeness-vs-expected validate self all

# Default: full check pipeline (used by CI).
check: schema-check validate source-trace verify-citations completeness completeness-vs-expected
	@echo "✓ All correctness checks passed."

# Pre-flight: meta-schema check on the schemas themselves.
schema-check:
	@python3 scripts/validate.py --self

# Strict JSON Schema 2020-12 validation of every instance file.
validate:
	@python3 scripts/validate.py

# Every text field must grep-match the cached source PDF (or carry source_span override).
source-trace:
	@python3 scripts/source-trace.py

# Every references[].citation must resolve via Crossref / OpenAlex / NCBI.
verify-citations:
	@python3 scripts/verify-citations.py

# Heuristic stub detector + provenance-required enforcement.
completeness:
	@python3 scripts/completeness.py

# NEW (Part 1 of "make this not happen again" fix): every curriculum must
# have an expected.yaml manifest declaring per-rec sub-item counts. This
# gate FAILS if a rec has fewer sub-items than declared without an
# explicit _meta.knownIncomplete flag. Catches silent extraction bugs.
completeness-vs-expected:
	@python3 scripts/completeness-vs-expected.py

# Convenience targets.
self: schema-check
all: check
