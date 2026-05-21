# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-21 10:01 PDT
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3 merged to `master` (3b observability stack complete). **Plan 3c (database lifecycle) merged to `master`** (fast-forward; pushed to `origin`). Generated projects now ship a relational layer: PostgreSQL + SQLAlchemy + Alembic, a `db/` package (`Base`/engine/`get_session`/`Item`/repository/idempotent seed), an initial migration, a DB-backed `GET /items` (Pydantic `response_model`), and a container entrypoint that runs `alembic upgrade head` + seed before serving. Compose gains `postgres` (dev/lite, persistent `pgdata` volume) and ephemeral `postgres-test` (test profile, tmpfs). Tests run against a **real Postgres via testcontainers and HARD-FAIL (not skip) without Docker** — a deliberate forcing function; no SQLite anywhere. See `docs/superpowers/plans/2026-05-21-database-lifecycle.md`.
- **Verification:** Both layers green locally. Layer A — `ruff`, `mypy`, 35 render tests, and the no-Docker `test_rendered_project_precommit_runs_clean` (generated `db/` + route code is lint/format/type-clean everywhere). **Layer B is now validated against real Postgres: Docker is installed in the dev env** (native `docker.io` 29.1.3 + `docker-compose-v2` under systemd), so the full Docker-gated `tests/acceptance/test_rendered_project.py` suite passes — the generated project's suite on a testcontainers Postgres (**44 passed**), the coverage gate ≥70% with the DB tests counted, the live `docker compose` stack serving seeded `/items` (entrypoint `alembic upgrade head` + seed), and the dev-stack observability live tests (health/prometheus/loki/tempo, confirming `postgres` in the dev profile didn't break the full bringup). Plan 5 will also run these in authoritative CI.
- **Recent:** Plan 3c executed subagent-driven (Sonnet implementer/spec, Opus quality/final). Key calls: real Postgres + testcontainers with fail-without-Docker forcing function (no SQLite fallback); `/items` upgraded to a Pydantic `response_model`; `test_rendered_project_precommit_runs_clean` runs with `SKIP=coverage-threshold` to stay a no-Docker cleanliness check (the coverage pre-commit hook runs the DB suite, which needs Docker). Opus caught pre-merge: the missing `/items` response contract, a false "localhost default" in the `db:migrate` desc, a ruff-**format** (not just lint) miss in `test_settings`, and the coverage-hook-needs-Docker consequence.
- **Next:** Plan 4 (error handling & recoverability) or Plan 5 (CI/CD — wires the now-passing Docker-gated Layer-B tests into authoritative CI).

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
