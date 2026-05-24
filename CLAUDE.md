# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`) — update its status table when a plan's status changes.

- **Last updated:** 2026-05-24 (8b Task 5: upskill regenerates the manifest — `upskill_project` now imports `write_manifest`/`installed_framework_version` at module level and re-records `.framework/integrity.lock` after `run_update` when the lock already exists; guard ensures minimal-template upskill tests are unaffected; 45 passed, ruff + mypy clean.)
- **Where we are:** Plans 1–6b + **Plan 7 (7a–7d) all merged to `master`** (7d FF `a92b85e`): the full Layer-3 review-agent system — the `framework review` runner, the 12-agent set + dynamic CI matrix, the aggregator + single sticky PR comment (`framework review-aggregate`), and the hermetic eval harness (`framework eval` + golden fixtures for all 12 agents + `agent-evals.yml`). Detail in `docs/superpowers/plans/2026-05-23-{review-aggregator,eval-harness}.md`. ⚠ **7d is not yet e2e-tested** (no real Anthropic key in this env; thresholds provisional) — see **Known follow-ups**; Plan 9 validates it.
- **Plan 8a-1 (additive battery mechanism) — merged to `master` (FF `ea9a192`).** The first slice of Plan 8 (batteries). A CLI-side `src/framework_cli/batteries.py` registry (`BatterySpec` + `resolve()` dependency-closure); **`framework new --with <battery>`** + **`framework upskill --with <battery>`** (validated + dep-resolved, non-interactive); **router autodiscovery** in the always-on base app (`template/.../routes/__init__.py: include_routers(app)` replaces explicit `include_router` calls) so route-adding batteries are pure file-adds; **conditional rendering** driven by a `batteries` Copier answer (declared `type: yaml`) via templated paths (`{% if "<b>" in batteries %}`); the **websockets** vehicle battery (a `routes/websockets.py` WS route + a `connection_manager` package + a `tests/functional/test_websockets.py`). The active battery set is **framework-owned** in `.copier-answers.yml` (`source.record_batteries` + `read_batteries`) — Copier does **not** re-emit the subdir-declared answer through the portable `_subdirectory` source on `run_update`, so `upskill_project` passes the effective set to the update AND re-records it (the headline-risk fix). Managed-section injection (for deps/services) is specified in the spec but not yet exercised (websockets needs none); the 3 battery review agents (api-design/accessibility/usability) stay deferred to 8d/8g (auto-evaluated by 7d once registered). See `docs/superpowers/plans/2026-05-24-battery-mechanism.md`.
- **Verification (8a-1):** `ruff` clean, `mypy` clean, `uv lock --check` clean (no new runtime deps), **full suite 250 passed / 0 failed** (incl. the Docker acceptance suite + a new **with-websockets** variant that renders the battery and runs its WS functional test green, asserting `routes/websockets.py` hits 100% coverage to prove the test actually ran). Built subagent-driven across 6 TDD tasks, each spec + code-quality reviewed. Three real defects caught by review and fixed: (1) the WS test landed at the tests root (outside the project's `testpaths`) → moved to `tests/functional/`; (2) the acceptance assertion was unsound (passed even with the WS test deleted, since autodiscovery imports the route anyway) → now keys on the route reaching 100% coverage; (3) **the final whole-branch review caught the headline upskill defect** — the recorded `batteries` answer was silently wiped after a real `run_update` through the portable `_subdirectory` source → fixed by framework-owned recording, proven by two real (non-mocked) round-trip tests (preserve + add).
- **Next (▶ RESUME HERE):** continue Plan 8: **8a-2** (battery removal `--downskill`/`--without` + the usage-detection safety net — now unblocked since a battery [websockets] exists to test removal against; note the [[key-label-convention]]-style lesson: any answer that must survive upskill is framework-owned in `.copier-answers.yml`, so removal updates the recorded set via `record_batteries`); then **8b** webhooks, **8c** workers (+ the Plan 4 DLQ), **8d** graphql (+`review-api-design`), **8f** database paradigm batteries + wizard, **8g** react (+`review-accessibility`/`review-usability`), **8h** consumers. (8e websockets is effectively delivered as the 8a-1 vehicle.) Also outstanding: **Plan 5c-2**, **9** (dogfooding CI + `SECRETS.md` + e2e-validate 7d), **10** (docs pack). The API-key/secret naming convention is in auto-memory ([[key-label-convention]]). Start the next slice with `superpowers:brainstorming` (or `writing-plans` directly for 8a-2 since its design is already in the meta-plan) → subagent-driven.

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
- **⚠ Plan 7d is NOT e2e-tested.** The eval harness suite is fully green but **hermetic** — no real Anthropic call has ever exercised it (no `ANTHROPIC_API_KEY` was available). The agents have never actually been scored against the golden fixtures, so the `0.67`/`0.34` thresholds are **provisional** and an agent's real recall/precision is unknown. **Resolution:** set the `ANTHROPIC_FRAMEWORK_CI_EVAL` repo secret and let the first scheduled `agent-evals.yml` run produce a real scorecard (then tune `tests/eval/fixtures/thresholds.yaml`). **Plan 9 (dogfooding) must explicitly verify this** — a real eval run is the e2e gate 7d couldn't perform itself.
- *(resolved in Plan 6b)* `.copier-answers.yml` now records a portable `_src_path` (`gh:cdowell-swtr/swiftwater-framework`) + `_commit` (`vX.Y.Z`); the repo-root `copier.yml` makes `git+<repo>@<tag>` a Copier source, so `framework upskill` / `copier update` work across machines.
