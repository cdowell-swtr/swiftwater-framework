# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-21
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, and **3b-3 (observability traces) merged to `master`** — this **completes the 3b observability stack**. Generated projects now have metrics (Prometheus/Grafana/Alertmanager), logs (Loki/Promtail), and traces (OpenTelemetry → OTEL Collector → Tempo, gated on in dev) with forward log→trace correlation (`trace_id` in logs → Loki derived field → Tempo). See `docs/superpowers/plans/2026-05-20-observability-traces.md`. Framework gate green (`ruff`, `mypy`, 22 render tests + acceptance suite; 4 Docker-gated live tests skip without Docker). **Local `master` is ahead of `origin`** — 3b-3's commits await `git push origin master`.
- **Recent:** Plan 3b-3 executed subagent-driven (Sonnet implementer/spec, Opus quality/final). Opus caught two CRITICALs pre-merge: the structlog `JSONRenderer` space-after-colon vs the Loki derived-field regex (fixed with `\s*` + a real-line test), and a dead `tracesToLogsV2` trace→logs back-link (removed — the OTel `service.name` ≠ the Loki `service` label).
- **Next:** Plan 3c (database lifecycle) or Plan 4 (error handling & recoverability) — the 3b observability stack is complete.

## Keeping state current (required before every commit)

Before every commit, update the **Current State** pointer above (and the meta-plan's status table when a plan's status changes), then `git add CLAUDE.md`. This keeps the repo's state accurate as we move across machines and environments. A `PreToolUse` hook in `.claude/settings.json` enforces this — it blocks `git commit` until `CLAUDE.md` is staged. Run `/hooks` to review or disable it.

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
