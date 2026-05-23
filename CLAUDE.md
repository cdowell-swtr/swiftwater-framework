# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-22 23:04 PDT (Plan 7b merged + pushed; Plan 7c — interactions + aggregator — design spec written + approved, plan next)
- **Where we are:** Plans 1–6b, 7a all merged to `master`. **Plan 7b (full review agent set + triggering matrix) is now merged to `master`** (fast-forward to `41376e7`). 7b completes the §7 "always" set on the 7a runner: `AgentSpec` gained `block_threshold: Severity|None` (None=advisory, never blocks), `on_push`, `trigger_globs`; **11 new agents** ship as `src/framework_cli/review/agents/<name>.md` prompts + registry entries — the 10 "always" (`data-integrity`/`application-logic` block on *any* finding [`info`], the rest `high`, `documentation` advisory) + `review-dependency` (file-trigger, advisory). `active_agents(event)` + a `framework review-agents` command drive a **dynamic parallel CI matrix** (generated `ci.yml`: `review-plan` lists the agents → `review` matrix fans out via `fromJSON`); push-to-main runs only the `on_push` subset (security/data-integrity/data-lineage/observability). `review-dependency` **self-skips** (neutral, no LLM call) when no dependency file changed (`diff.changed_files`+`matches_globs`); the `review` command re-raises `typer.Exit` past its broad `except` so the skip isn't swallowed. **Deferred:** the 3 battery agents (api-design/accessibility/usability) → Plan 8; interactions + aggregator → 7c; eval harness → 7d. See `docs/superpowers/plans/2026-05-22-review-agent-set.md`.
- **Verification (7b):** `ruff` clean, `mypy` clean, **full suite 184 passed / 0 failed** (incl. the Docker-gated acceptance suite). Built subagent-driven across 6 TDD tasks; the final whole-branch review **ran the tooling** (`uv lock --check` clean, actionlint on the rendered `ci.yml`, and a wheel build confirming all 12 prompts ship) and returned "Ready to merge: Yes". A mid-run `/tmp` exhaustion (the full Docker suite filling tmpfs) blocked Task 1's commit once — cleared with `rm -rf /tmp/pytest-of-chris/*` + `docker system prune`. No real Anthropic call in tests (mocked); real review quality is Plan 7d.
- **Next:** **Write the Plan 7c implementation plan** (`superpowers:writing-plans`) from the approved design `docs/superpowers/specs/2026-05-22-review-aggregator-design.md` — `framework review --findings-out` (write per-agent findings JSON at every exit path) + per-agent artifacts; `review/aggregate.py` (pure `aggregate(results)` → pass/fail + severity counts + deterministic relationships: same-file + `_RELATED_PAIRS`) + `framework review-aggregate <dir>` (sticky PR comment via `gh`); the generated `ci.yml` artifact-upload (`if: always()`) + `review-aggregate` job. Then: **7d** (eval harness — golden fixtures + threshold detection, §20); **5c-2** (multi-host strategy — e2e-harness design pass); **8** (batteries — also wires the 3 deferred battery review agents); **9** (dogfooding CI + release automation).

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
- *(resolved in Plan 6b)* `.copier-answers.yml` now records a portable `_src_path` (`gh:cdowell-swtr/swiftwater-framework`) + `_commit` (`vX.Y.Z`); the repo-root `copier.yml` makes `git+<repo>@<tag>` a Copier source, so `framework upskill` / `copier update` work across machines.
