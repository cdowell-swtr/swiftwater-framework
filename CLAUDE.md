# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-22 16:15 PDT (Plan 6a-2 Task 3: checker hybrid branch; on branch `plan-6a2-hybrid-sections`)
- **Where we are:** Plans 1, 2, 2b, 3a, 3b-1, 3b-2, 3b-3, 3c, 4, 5a, 5b, 5c-1 all merged to `master`. **Plan 6a (framework integrity) is now merged to `master`** (fast-forward to `b33b2e8`). 6a adds the `framework integrity` self-check, with the engine living entirely in the installed CLI (`src/framework_cli/integrity/`: `hashing`, `manifest`, `classes`, `generate`, `checker`, `restore`) so a builder can't disable it: `framework new` writes a self-checksummed `.framework/integrity.lock` recording every **locked** framework-infra file's SHA-256 (tracked tier) plus the gitignored `.env` (existence tier); `framework integrity [--ci] [--allow-drift <file>]` re-verifies (fatal on altered/missing locked files or a tampered manifest; `--ci` skips the existence tier) and `framework restore <file>` re-renders the canonical file from the bundled template; a guarded `task integrity` precondition runs it during `task dev`/`test`/`ci`. **Deferred to follow-ups:** hybrid managed-section files (6a-2; manifest schema already carries `cls`), CI step-0 activation + cross-version restore (6b). See `docs/superpowers/plans/2026-05-22-framework-integrity.md`.
- **Verification (6a):** `ruff` clean, `mypy` clean, **full suite 105 passed / 0 failed** (incl. the Docker-gated acceptance suite). Built subagent-driven across 10 TDD tasks (each through spec + code-quality review); final whole-branch review returned "Ready to merge: Yes". New tests: `tests/integrity/{test_hashing,test_manifest,test_classes,test_generate,test_checker,test_restore}.py`, `test_new_writes_a_verifiable_manifest` + `integrity`/`restore` CLI tests in `tests/test_cli.py`, `test_taskfile_wires_integrity` in `tests/test_copier_runner.py`, and the end-to-end `test_rendered_project_integrity_verifies_tamper_and_restore` acceptance test.
- **Next:** **Execute Plan 6a-2** — plan at `docs/superpowers/plans/2026-05-22-hybrid-managed-sections.md` (6 TDD tasks: `sections.py` extractor; markers in `.env.example`+`Taskfile`; hybrid branches in checker/generate/restore reusing the `sha256` field; `HYBRID_TRACKED` registry; end-to-end acceptance). `pyproject.toml` explicitly excluded (loud-failure content, dep array can't be cleanly locked). Then still open: **6b** (portable/versioned template source + `upskill`/`check` + CI step-0 activation — needs a template-source design pass) and **5c-2** (multi-host rolling reference strategy — needs an e2e-harness design pass).

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
