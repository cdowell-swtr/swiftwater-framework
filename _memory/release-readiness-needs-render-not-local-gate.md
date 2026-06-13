---
name: release-readiness-needs-render-not-local-gate
description: "Before a framework release/tag, the local gate is insufficient — render combos + run generated mypy/ruff-format, which catches template-payload + dep-drift the local gate structurally misses."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 61c129b2-5eb7-4302-935f-554fa0cc0686
---

The local framework gate (`uv run pytest -q --ignore=tests/acceptance` + `ruff check .` + `mypy src`) is NOT sufficient to know a release will pass. Cutting the inaugural `v0.1.0` tag triggered `release.yml`'s broad render-matrix, which caught **4 real defects the local gate structurally cannot**:

1. **`ruff check` ≠ `ruff format --check`.** `ruff check` passes long lines / minor format drift that `ruff format --check` fails. (Re-confirms [[ruff-format-check-after-inline-edits]].)
2. **Framework `mypy src` EXCLUDES `src/framework_cli/template/`.** Template-payload type errors (e.g. `result.rowcount` on SQLAlchemy's `Result[Any]`) only surface when a project is rendered and runs ITS OWN mypy. (Re-confirms [[template-payload-tdd-loop]].)
3. **Generated projects resolve deps FRESH (no shipped lockfile) → version drift.** A new upstream release (e.g. strawberry 0.316.0 typing the bare `GraphQLRouter` context as `None`) breaks generated-project mypy even though the template code is unchanged and a prior CI run passed on an older resolved version.
4. **Battery-gated import vs dep mismatch.** An always-present file importing a battery-only package (worker tracing importing `opentelemetry.instrumentation.celery`) fails mypy in combos lacking that battery.

**Why:** the local gate runs against the framework's own venv + only framework source; the matrix/acceptance tier renders projects and runs their own toolchain against fresh dep resolutions. Different inputs, different failures.

**How to apply:** before cutting a release tag (or trusting "it's green"), render representative battery combos — at minimum **baseline (all-off), all-batteries (all-on), and the singles touched by recent slices** — and run each generated project's `uv sync && uv run mypy src && uv run ruff check . && uv run ruff format --check .` locally (no Docker needed for the lint/type tier). Also run `ruff format --check .` on the framework itself, not just `ruff check`. The "import present but dep absent" class shows up specifically in combos where the gating battery is OFF — test those, not just the all-on case.
