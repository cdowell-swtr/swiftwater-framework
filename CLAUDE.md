# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-22 19:45 PDT (Plan 7a Task 7: activate ci.yml review job — `framework review security` wired, ANTHROPIC_API_KEY opt-in; 57 render tests pass)
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3, 3c, 4, 5a, 5b, 5c-1, 6a, 6a-2 all merged to `master`. **Plan 6b (portable template source + upskill/version) is now merged to `master`** (fast-forward to `84d3ada`). 6b makes the template source git-tag-versioned and portable: a repo-root `copier.yml` (`_subdirectory: src/framework_cli/template` + `_exclude`) makes `git+<repo>@<tag>` a valid Copier source (questions stay in the subdir `copier.yml`; bundled `framework new` render unchanged); `framework new` rewrites `.copier-answers.yml` to a portable `_src_path` (`gh:cdowell-swtr/swiftwater-framework`) + `_commit` (`vX.Y.Z`) via `src/framework_cli/source.py`; `framework check` compares the installed version to the latest remote tag (`git ls-remote --tags`); `framework upskill <project>` runs Copier `run_update` (3-way merge from the recorded tag; requires a git-tracked project) + `task test`; the generated `ci.yml` step-0 integrity job is **activated** (installs the framework at the recorded `_commit`, runs `framework integrity --ci`). Distribution is git tags only; `RELEASING.md` documents the tag==version==bundled-template invariant. **Deferred:** PyPI; `upskill --with <battery>` (Plan 8); release-automation workflow (Plan 9); cutting the first real tags (operational). See `docs/superpowers/plans/2026-05-22-template-source-and-upskill.md`.
- **Verification (6b):** `ruff` clean, `mypy` clean, **full suite 135 passed / 0 failed** (incl. the Docker-gated acceptance suite). Built subagent-driven across 6 TDD tasks (each spec + code-quality reviewed) after a controller spike that resolved the Copier `_subdirectory`/`_exclude` mechanic up-front; final whole-branch review verified the new→check→upskill→CI story live and returned "Ready to merge: Yes". New tests: `tests/test_source.py`, `tests/test_upskill.py` (hermetic local two-tag-repo update test), plus `check`/`new`-records/CI-activation cases in `test_cli.py`/`test_copier_runner.py`.
- **Next:** **Execute Plan 7a** — plan at `docs/superpowers/plans/2026-05-22-review-agent-runner.md` (7 TDD tasks: `src/framework_cli/review/` — findings contract, agent registry + `review-security` prompt, runner (Anthropic, prompt-cached diff, mock-injected client), Check Run mapping, diff resolution; the `framework review` command; the generated `ci.yml` review-job activation). `anthropic` becomes a CLI dep (lazy import). Plan 7 = **7a** (runner) + **7b** (14 more agents + triggering matrix) + **7c** (interactions + aggregator) + **7d** (eval harness). Also still open: **5c-2** (multi-host rolling strategy — needs an e2e-harness design pass), Plan 8 (batteries), Plan 9 (dogfooding CI).

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
