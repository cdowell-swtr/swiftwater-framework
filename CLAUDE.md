# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-23 18:10 PDT (7d Task 2: flags detection rule — `flags()` added to evals.py, 5 new tests green [red→green confirmed], ruff+mypy clean.)
- **Where we are:** Plans 1–6b, 7a, 7b all merged to `master` (7b FF `41376e7`). **Plan 7c (cross-agent interactions + the review aggregator) is now merged to `master`** (fast-forward to `2fb6694`). 7c adds the findings-collection + aggregation layer on top of 7b's agent matrix: `framework review <agent> --findings-out <path>` writes a lossless `{agent, conclusion, findings}` JSON at *every* terminal path (no-key skip / not-triggered / infra-error→neutral / normal) — `write_findings` in `src/framework_cli/review/aggregate.py`, `--findings-out` defaults unset so 7a/7b behavior is unchanged. A pure `aggregate(results) -> AggregateResult` (overall pass/fail + `severity_counts` + **deterministic** `relationships` [same file flagged by ≥2 agents + `_RELATED_PAIRS`: lineage↔privacy, lineage↔compliance, performance↔data-integrity — sorted so the sticky comment never churns] + rendered `markdown` carrying `SUMMARY_MARKER`) plus `load_results` (skips malformed/missing). `src/framework_cli/review/comment.py` posts a single **sticky** PR comment via `gh` (find-or-create on the marker, **`--paginate`d** list so it's never duplicated, `except Exception: pass` so posting never fails CI). `framework review-aggregate <dir>` posts on a PR / prints on a push. Generated `ci.yml`: the `review` matrix job gains `--findings-out` + an `if: always()` `upload-artifact` (`review-findings-<agent>`); a new `review-aggregate` job (`needs: review`, `if: always()`, `pull-requests: write`) downloads `review-findings-*` (`merge-multiple: true`) and runs the aggregator. **Deferred (unchanged):** the 3 battery agents → Plan 8; eval harness → 7d. See `docs/superpowers/plans/2026-05-23-review-aggregator.md`.
- **Verification (7c):** `ruff` clean, `mypy` clean, `uv lock --check` clean (no new runtime deps), **full suite 209 passed / 0 failed** (incl. the Docker-gated acceptance suite — 18 acceptance tests *ran*, exercising actionlint on the rendered `ci.yml` including the new `review-aggregate` job). Built subagent-driven across 4 TDD tasks; each task got a spec + code-quality review. Two real defects were caught by the code-quality reviewer and fixed: (1) `_RELATED_PAIRS` is a `set[frozenset]` so iterating it was hash-seed-dependent → non-deterministic markdown → sticky-comment churn (fixed: `sorted_pairs`, verified across 5 seeds); (2) the PR-comment list wasn't paginated → a sticky comment past page 1 would be *duplicated* (fixed: `--paginate`). Final whole-branch review **ran the tooling** (incl. a wheel build confirming `aggregate.py`/`comment.py` + all 12 prompts ship) and returned "Ready to merge: Yes". No real Anthropic call in tests (mocked); real review quality is Plan 7d.
- **Next (▶ RESUME HERE):** **Plan 7d — the eval harness.** Golden fixtures + threshold detection for *real* review quality (spec §20): mocked-client tests prove the plumbing, but no test yet exercises a real Anthropic call or asserts an agent catches a planted defect. 7d builds that. Then 5c-2 (multi-host rolling strategy — needs an e2e-harness design pass); 8 (batteries — also wires the 3 deferred battery review agents api-design/accessibility/usability); 9 (dogfooding CI + release automation). Start 7d with `superpowers:brainstorming` → `writing-plans` → subagent-driven.

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
