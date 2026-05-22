# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-22 09:30 PDT (Plan 5c design brainstormed + spec written: `docs/superpowers/specs/2026-05-22-deploy-reference-strategy-design.md`; awaiting spec review)
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3, 3c, 4, 5a all merged to `master`. **Plan 5b (deploy seam) is now merged to `master`** (fast-forward to `0ba8f91`) **and `master` is pushed to `origin`** (in sync). Generated projects now also ship: four validation tiers (smoke/Phase 1 → sniff/Phase 2 → E2E with `E2E_TARGET`/Phase 3 → k6 load/Phase 4 at SLO thresholds); `deploy-staging.yml` (build+push to GHCR, deploy via strategy, 4-phase validation, automatic rollback) and `deploy-prod.yml` (manual approval gate via the `production` Environment, image promotion, smoke+sniff, rollback); staging/prod Compose topologies (`infra/compose/staging.yml`, `infra/compose/prod.yml`); an opinionated deploy-strategy skeleton (`infra/deploy/strategy.sh` with config validation, migration-aware rollback, and `__target_*` hook seams for any target); a migration-reversibility guard (`scripts/check_migrations.py`, in pre-commit + CI) that blocks empty/pass/raise `downgrade()`; and `DEPLOY.md` documenting the full orchestration flow and what builders need to implement. See `docs/superpowers/plans/2026-05-21-deploy-seam.md`.
- **Verification:** Layer A — `ruff`, `mypy`, **57 framework tests** (incl. `test_render_deploy_docs`, `test_render_deploy_strategy_seam`, `test_render_staging_prod_compose`, `test_render_deploy_staging_workflow`, `test_render_deploy_prod_workflow`, `test_render_migration_guard`), and the no-Docker acceptance tests (`test_rendered_project_precommit_runs_clean` — now actionlints `deploy-staging.yml`+`deploy-prod.yml`, shellchecks `strategy.sh`/`notify.sh`/`load.sh`, and runs `migrations-reversible` over `0001_initial.py` — and `test_rendered_project_exports_openapi`) all pass. Layer B (Docker) — all Docker-gated acceptance tests pass: generated suite **66 passed**, the 85% combined gate holds (97% total coverage), and the new `test_rendered_project_smoke_and_sniff_against_lite` (smoke + sniff + remote-E2E against live lite stack) passes.
- **Next:** Plan 6 (integrity + upskill — file classes, `.framework/integrity.lock`, `framework integrity`/`restore`/`check`/`upskill`). Plan 5c (turnkey reference strategy — compose-over-SSH + Traefik/ACME blue-green filling the `__target_*` hooks) is queued as a deploy follow-up.

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
