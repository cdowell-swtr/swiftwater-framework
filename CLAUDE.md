# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-21 18:30 PDT (Plan 5b plan written + revised; executing on branch `plan-5b-deploy-seam`)
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3, 3c, 4 all merged to `master`. **Plan 5a (generated-project CI pipeline) is now merged to `master`** (fast-forward to `e91e858`) **and `master` is pushed to `origin`** (in sync). Generated projects now ship: a GitHub Actions `ci.yml` (integrity-seam → lint → test [unit/functional/e2e, 85% gate] → build → OpenAPI contract diff → pip-audit + full-history gitleaks → review-agent seam); coverage suite contexts (unit/functional/e2e); `scripts/coverage.sh` (multi-context gate); `task ci` (local pre-flight) + `task push` (triggers GHA); pip-audit + `.github/dependabot.yml` (weekly uv + github-actions PRs); actionlint + shellcheck as pre-commit hooks and in `task lint`; and an e2e test tier (`tests/e2e/`, `e2e_client` fixture). See `docs/superpowers/plans/2026-05-21-cicd-pipeline.md`.
- **Verification:** Layer A — `ruff`, `mypy`, **47 framework tests** (incl. `test_render_includes_ci_pipeline`, `test_render_dependency_security`, `test_render_workflow_and_shell_linters`, `test_render_coverage_script_and_tasks`, `push:` in Taskfile assertion), and the no-Docker acceptance tests (`test_rendered_project_precommit_runs_clean` — includes actionlint+shellcheck over the rendered `ci.yml` + scripts — and `test_rendered_project_exports_openapi`) all pass. Layer B (Docker) — all 3 Docker-gated acceptance tests pass: generated suite passes its own tests, the 70% unit+functional gate passes, and the 85% combined gate passes — **generated project at 97% total coverage**.
- **Next:** **Plan 5b (deploy seam) is being executed** subagent-driven on branch `plan-5b-deploy-seam` (plan: `docs/superpowers/plans/2026-05-21-deploy-seam.md`) — smoke/sniff/k6/target-aware-e2e validation tiers, staging/prod compose, an **opinionated deploy-strategy skeleton** (config-validated, migration-aware rollback; builder fills only `__target_*` hooks for their target), `deploy-staging.yml`/`deploy-prod.yml`, and a migration-reversibility guard that blocks irreversible migrations. A complete compose-over-SSH+Traefik/ACME reference strategy is queued as Plan 5c. Then Plan 6 (integrity + upskill).

## Keeping state current (required before every commit)

Before every commit, update the **Current State** pointer above — including **Last updated** as a datetime with timezone (e.g. `2026-05-21 09:19 PDT`, since we commit several times a day) — and the meta-plan's status table when a plan's status changes, then `git add CLAUDE.md`. This keeps the repo's state accurate as we move across machines and environments. A `PreToolUse` hook in `.claude/settings.json` enforces this — it blocks `git commit` until `CLAUDE.md` is staged. Run `/hooks` to review or disable it.

## How we build here
- Work proceeds plan-by-plan per the meta-plan, using the superpowers subagent-driven flow: a feature branch → an implementer per task (TDD) → controller verification → a final review → merge to `master`.
- TDD is required: write the failing test first, confirm red, implement the minimum, confirm green.

## Quality gate (must be green before commit / merge)
```bash
uv run pytest -q          # all tests
uv run ruff check .       # lint
uv run mypy src           # type-check (framework source only)
```
`uv` is the package manager — run all tooling via `uv run`. If `uv` is not found, make sure its install directory is on PATH (restart the session after a fresh install).

## Critical conventions
- **`src/framework_cli/template/` is template *payload*, not framework source.** Those `.jinja` / `.py` / config files are rendered into generated projects — do not refactor or lint them as framework code. The framework's own `mypy` excludes that directory. The template is validated by rendering it and exercising the generated project: `tests/test_copier_runner.py` (files render / interpolate) and `tests/acceptance/test_rendered_project.py` (the generated project's own tests, coverage gate, and pre-commit pass).
- Brace-named paths like `src/framework_cli/template/src/{{package_name}}/` are intentional Copier path templating — leave them.
- The CLI (`src/framework_cli/`) is a thin shell over Copier; keep logic in focused modules (`naming.py`, `copier_runner.py`, `cli.py`).
- Changing the template means re-running the render + acceptance tests. A freshly generated project must make a clean first `pre-commit` pass — enforced by `test_rendered_project_precommit_runs_clean`.

## Known follow-ups
- `.copier-answers.yml` records a machine-specific `_src_path`; the `framework upskill` / `copier update` flow (Plan 6) needs a portable, versioned template source.
