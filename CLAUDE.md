# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-22 20:08 PDT (Plan 7a merged + pushed; Plan 7b — full agent set + triggering matrix — design spec written + approved, plan next)
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3, 3c, 4, 5a, 5b, 5c-1, 6a, 6a-2, 6b all merged to `master`. **Plan 7a (review agent runner) is now merged to `master`** (fast-forward to `23d95ce`). 7a ships `framework review <agent>` — a CLI subcommand (framework-owned, like `framework integrity`) that reviews the PR diff with an Anthropic-backed agent and posts a GitHub Check Run. Under `src/framework_cli/review/`: `findings` (structured `Finding` contract + tolerant JSON parse), `registry` (`AgentSpec` + the `review-security` prompt in `agents/security.md`), `runner` (Anthropic Messages API, diff as a cached prompt prefix, **injected** client for tests; lazy `anthropic` import), `checks` (findings → Check Run conclusion gated by the agent's block-threshold + inline annotations + non-fatal `gh`-API posting), `diff` (PR diff from the CI env). The `review` command: no `ANTHROPIC_API_KEY` → neutral skip (exit 0); blocking finding → exit 1; any infra error → neutral (exit 0) — **infra failure never blocks CI**. `anthropic` is a CLI dep. The generated `ci.yml` review job installs the framework at the recorded `_commit` (the 6b pattern) and runs `framework review security` (opt-in by the secret; "blocks merge" = the builder's branch protection, documented in-job). **Deferred:** the other 14 agents + triggering matrix (7b), cross-agent interactions + aggregator (7c), the eval harness / real-quality assertions (7d). See `docs/superpowers/plans/2026-05-22-review-agent-runner.md`.
- **Verification (7a):** `ruff` clean, `mypy` clean, **full suite 159 passed / 0 failed** (incl. the Docker-gated acceptance suite). Built subagent-driven across 7 TDD tasks; the final whole-branch review caught a **critical** defect — `anthropic` was in `uv.lock` but not declared in `pyproject.toml` (lock inconsistent; generated CI couldn't install the SDK) — fixed (`23d95ce`) + re-verified (`uv lock --check` clean). New `tests/review/` (findings/registry/checks/runner/diff) + `review` CLI cases + the `ci.yml` render assertion. No real Anthropic call in tests (mocked); real review quality is Plan 7d's eval harness.
- **Next:** **Write the Plan 7b implementation plan** (`superpowers:writing-plans`) from the approved design `docs/superpowers/specs/2026-05-22-review-agent-set-design.md` — the 10 remaining "always" agents + `review-dependency` (file-trigger); `AgentSpec` gains `block_threshold: Severity|None` (None=advisory), `on_push`, `trigger_globs`; `active_agents(event)` + a `framework review-agents` command → dynamic CI matrix (`review-plan`→`review` jobs); `diff.changed_files` + the file-trigger self-skip; the advisory `to_check_run` tweak. 3 battery agents deferred to Plan 8. Then: **7c** (interactions + aggregator), **7d** (eval harness); **5c-2** (multi-host strategy — e2e-harness design pass); **8** (batteries); **9** (dogfooding CI + release automation).

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
