# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-22 14:41 PDT (Plan 6b — portable template source + upskill/check — implementation plan written + committed; Copier `_subdirectory`/`_exclude` spike resolved; ready to execute)
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3, 3c, 4, 5a, 5b, 5c-1, 6a all merged to `master`. **Plan 6a-2 (hybrid managed-section integrity) is now merged to `master`** (fast-forward to `c63ab1d`). 6a-2 adds the `hybrid` file class to the 6a integrity engine: `CLAUDE.md`, `.env.example`, and `Taskfile.yml` each carry a framework-owned region delimited by `FRAMEWORK:BEGIN/END` markers — the section *between* the markers is checksummed (tamper-evident) while content outside is the builder's. New `src/framework_cli/integrity/sections.py` extracts/hashes the region; `build_manifest`/`check`/`restore` gained hybrid branches (reusing the `sha256` field — no schema change; `restore` splices only the marker span, preserving builder content, and errors rather than clobbering damaged markers); `HYBRID_TRACKED` registers the three files. **`pyproject.toml` is deliberately excluded** (its dependency arrays must stay builder-editable; breakage there is loud, not silent). Deferred: CI step-0 activation + cross-version restore (6b). See `docs/superpowers/plans/2026-05-22-hybrid-managed-sections.md`.
- **Verification (6a-2):** `ruff` clean, `mypy` clean, **full suite 123 passed / 0 failed** (incl. the Docker-gated acceptance suite, notably `test_rendered_project_precommit_runs_clean` — the marker additions don't break the generated project's first pre-commit). Built subagent-driven across 6 TDD tasks (each through spec + code-quality review); final whole-branch review verified end-to-end (edit-outside-clean / edit-inside-fatal / restore-preserves-builder-content / damaged-markers-error) and returned "Ready to merge: Yes". New test file `tests/integrity/test_sections.py`; hybrid cases added to `test_checker`/`test_generate`/`test_classes`/`test_restore`; `test_hybrid_files_render_with_markers` in `test_copier_runner.py`; `test_rendered_project_hybrid_section_integrity` acceptance test.
- **Next:** **Execute Plan 6b** — plan at `docs/superpowers/plans/2026-05-22-template-source-and-upskill.md` (6 TDD tasks: repo-root `copier.yml` with `_subdirectory`+`_exclude`; `framework new` records a portable `_src_path`+`_commit` via `source.py`; `framework check` (latest remote tag); `framework upskill` (`copier update`+`task test`, git-tracked precondition) tested with a local two-tag repo; CI step-0 activation; `RELEASING.md`). The Copier spike is resolved (findings in the plan header). Then still open: **5c-2** (multi-host rolling reference strategy — needs an e2e-harness design pass).

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
