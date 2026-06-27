.PHONY: check schema-check source-trace verify-citations completeness validate self all

# Default: full check pipeline (used by CI).
check: schema-check validate source-trace verify-citations completeness
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

# Convenience targets.
self: schema-check
all: check
