---
name: dogfood-e2e-harness-and-task-ci-coverage-gap
description: "The Plan 13 dogfood e2e harness, and the crucial gap that the render-matrix's `task ci` does NOT cover (only the real ci.yml on GHA does)."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 8ee32788-65d6-4cce-ba1d-2d370eb00620
---

**Plan 13 shipped `scripts/dogfood_e2e.py` (+ pure `framework_cli/dogfood.py`):** an operator-run harness that renders generated projects, pushes them to `cdowell-swtr/swiftwater-dogfood` (public, reset between configs), and asserts the SHIPPED generated `ci.yml` runs green on **real GitHub Actions** for `baseline` + `all-batteries` × push/PR. Run: `uv run python scripts/dogfood_e2e.py` (default free; `--with-review-key` for the paid review path). Runbook: `docs/dogfood-e2e.md`. Pins `DOGFOOD_COMMIT` (the installed-framework tag for integrity step-0); renders the template from the LOCAL working tree (so template fixes are validated without a release).

**The key insight — what `task ci` (the Plan 10 render-matrix path) does NOT exercise, so generated-`ci.yml`-only bugs slip past it:** the render-matrix runs each generated project's *local* `task ci`, which uses plain `uv run` (no `--frozen`), does NOT run `ruff format --check`, does NOT run actionlint/shellcheck over `ci.yml`'s embedded scripts the same way, and never runs the `ci.yml` jobs themselves (integrity step-0, gitleaks, the review matrix+aggregator, Pact `contracts`, Playwright `frontend`, oasdiff/graphql). So the dogfood found **6 real generated-project CI defects** the 700-test framework suite + render-matrix missed (gitleaks missing `GITHUB_TOKEN`; conftest not ruff-format-clean; ci.yml shellcheck SC2034; non-deterministic openapi/graphql export via stdout pollution; flaky timescaledb image build; workers DLQ test). Also: a fresh `framework new` project is NOT push-ready (no committed `uv.lock`/`openapi.json`/`schema.graphql`).

**Harness fidelity requirements (or the live run lies):** `render()` must mirror `framework new` exactly — `render_project` → `write_manifest` (the `.framework/integrity.lock`) → `record_portable_source`; and `prepare_project()` must replicate the builder's pre-push setup (`uv sync` → uv.lock + `export-openapi.sh`/`export-graphql-schema.sh`). **Review Check Runs** are named `review-<agent>` and attach to the PR **merge** commit (`GITHUB_SHA`), NOT the PR head — query `merge_commit_sha` for surface-2. See [[release-readiness-needs-render-not-local-gate]] (same class: local gate ≠ what ships).
