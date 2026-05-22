# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-22 17:30 PDT (Plan 6a Task 5: manifest at `framework new` — `write_manifest` called in `new` command after render; `test_new_writes_a_verifiable_manifest` added to test_cli.py)
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3, 3c, 4, 5a, 5b all merged to `master`. **Plan 5c-1 (migration backward-compatibility) is now merged to `master`** (fast-forward to `39dc0a7`) **and `master` is pushed to `origin`** (in sync). 5c-1 adds to generated projects: the `APP_RUN_MIGRATIONS` entrypoint gate (default `true`, preserving migrate-on-start behavior while letting zero-downtime deployments skip it via `APP_RUN_MIGRATIONS=false`); a contract-direction migration guard (`scripts/check_migrations.py` expanded) that blocks destructive `upgrade()` ops (`drop_column`/`drop_table`/`drop_constraint`/`drop_index`/`rename_table`, and a column rename via `alter_column(new_column_name=...)`) unless the migration is tagged `# deploy: contract` (a standalone post-rollout release); and the expand/contract discipline documented in the generated `CLAUDE.md` convention, `infra/deploy/README.md`, and `DEPLOY.md`. See `docs/superpowers/plans/2026-05-22-migration-backward-compat.md`.
- **Verification (5c-1):** Layer A — `ruff` clean, `mypy` clean, **59 framework tests** all pass (incl. `test_render_entrypoint_gates_migrations`, the extended `test_render_migration_guard`, and `test_render_migration_docs`), plus `test_rendered_project_blocks_contract_migration` + `test_rendered_project_precommit_runs_clean` + `test_rendered_project_exports_openapi` all pass. Layer B (Docker) — `test_rendered_project_passes_its_own_tests` + `test_rendered_project_dev_stack_serves_seeded_items` both pass (default-`true` gate preserves migrate-on-start behavior; generated suite passes).
- **Next:** Execute **Plan 6a** (framework integrity) — plan at `docs/superpowers/plans/2026-05-22-framework-integrity.md` (10 TDD tasks: integrity engine under `src/framework_cli/integrity/`, `.framework/integrity.lock` written at `framework new`, `framework integrity`/`restore`, local Taskfile precondition; hybrid sections + CI activation deferred to 6b). Also still open: **Plan 5c-2** (multi-host rolling reference strategy, after an e2e-harness design pass) and **Plan 6b** (portable/versioned template source + upskill/check + hybrid sections — needs a template-source design pass).

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
