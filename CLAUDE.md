# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-21 11:14 PDT (Plan 4 merged)
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3, 3c all merged to `master` (relational layer + full observability stack). **Plan 4 (error handling & recoverability) is merged to `master`** (fast-forward to `7652713`; local — not yet pushed to `origin`). Generated projects now also ship the §19 resilience scaffold: an RFC 7807 (`application/problem+json`) global exception handler that carries the request correlation id and never leaks internal exception text (`middleware/errors.py`, covering unhandled `Exception`→500, `HTTPException`, and `RequestValidationError`→422 via `jsonable_encoder`); a `tenacity` `with_retry` decorator (`resilience/retry.py`); a `pybreaker` `build_breaker` circuit breaker whose state is mirrored to `/metrics` (`resilience/circuit_breaker.py`); graceful shutdown via a FastAPI `lifespan` that disposes the SQLAlchemy engine on `SIGTERM` (`main.py` + `db/engine.py:dispose_engine`); and first-class recoverability metrics on `/metrics` (`observability/recoverability.py`: `app_unhandled_exceptions_total`, `app_retry_attempts_total`/`recovered`/`exhausted`, `app_circuit_breaker_state`). DLQ is deferred to Plan 8 (needs the `workers` battery); `recovery_rate_pct`-as-an-SLO and MTTR/graceful-degradation-event metrics are deferred (need a directional SLO model + 3b provisioning regen / richer labels). See `docs/superpowers/plans/2026-05-21-error-handling-recoverability.md`.
- **Verification:** Both layers green locally for Plan 4. Layer A — `ruff`, `mypy`, 43 framework tests (incl. the new `test_render_includes_resilience_scaffold`), and the no-Docker `test_rendered_project_precommit_runs_clean` (the generated resilience code is lint/format/type-clean). Layer B (Docker installed: native `docker.io` 29.1.3 + `docker-compose-v2`) — the generated project's own suite **64 passed** on a testcontainers Postgres (44 from 3c + 20 new: 7 recoverability, 5 error-handling, 4 retry, 3 circuit-breaker, 1 graceful-shutdown), the coverage gate ≥70% holds with **total coverage 96%** (new modules ~97–100%; `db/engine.py` 80% — `dispose_engine`'s body is monkeypatched in tests by design). Plan 5 will also run these in authoritative CI.
- **Recent:** Plan 4 executed subagent-driven (Sonnet implementer + spec reviewer per task, Opus code-quality + final whole-branch review). Opus caught pre-merge, beyond the per-task fixes: a **`ruff format` miss** on the `/metrics` body line (93 chars; `ruff check` doesn't flag E501 but `ruff format` rewraps it → breaks the cleanliness gate — same class as the 3c `test_settings` miss); and a **Critical validation-handler bug** — passing raw `exc.errors()` to `JSONResponse` crashes (TypeError → 500, falsely incrementing the unhandled counter) when a pydantic custom `@field_validator` raises `ValueError` (its `errors()` entry holds a non-JSON-serializable `ValueError` in `ctx`); fixed with `jsonable_encoder(exc.errors())` + a regression test (revert-sanity-checked). Also: controller empirically corrected a plan assumption — pybreaker 1.4.1 raises `CircuitBreakerError` on the *tripping* call (not the original exception), so the breaker test uses `fail_max=3`.
- **Next:** Push `master` to `origin` when ready, then Plan 5 (CI/CD — wires the now-passing Docker-gated Layer-B tests into authoritative CI).

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
