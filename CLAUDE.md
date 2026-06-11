# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record — every completed slice, FF SHA, and what's next — is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`). Keep this section short; update the meta-plan status table when a plan's status changes.

- **Last updated:** 2026-06-11 15:05 PDT — **Plan 21 Phase-3 fixture-coverage batch** (branch `plan21-phase3-fixtures`, PR #7; rebased on `v0.2.1` master `f0e8459`; test-data only). 7 eval fixtures authored + `--repeat 3`-verified on the free subagent backend (scorecard `…/2026-06-11-plan21-phase3-fixtures/`): 2nd good fixtures for **security/data-integrity/performance/env-parity** + **api-design `good/graphql-additive-field`**; **contracts `bad/weakened-consumer-assertion`**; observability redesigned → **`bad/suppressed-delete-error`** (active-suppression flags `high` 3/3 — a plain delete-without-log only reached *medium*; see [[observability-bad-fixture-needs-active-suppression]]). **NO `thresholds.yaml` change** (good fixtures threshold-neutral). env-parity recall 0.78 + api-design 0.83 = **pre-existing agent-prompt wobbles**, NOT this batch (our additions are good fixtures, fp 0.00). **Prior: `v0.2.1` cut + merged (PR #8, `f0e8459`)** — dropped the template `dependabot.yml` **github-actions** ecosystem (action versions are framework-owned + integrity-LOCKED, so every bump PR was born red; kept `uv`); surfaced by the first real render (**Meridian**). **`v0.2.0` PUBLISHED** (GraphQL introspection-in-prod fix; PR #5 `03d8cf7` + tag → Release; publish-tidy PR #6 → `dfd8777`). **Remaining for v0.2.1:** tag `v0.2.1` → `release.yml` → Release (if not already done), then propagate the regenerated `dependabot.yml` into **Meridian** as the manual stand-in for `framework upgrade` ([[release-cut-procedure]]). **Plans 1–22 merged to `master`** (`v0.1.9`; docs site live). **Plan 21 ✅ DONE** (PR #3, `8a9357d`): retuned to one shared severity+scope rubric. **Open next: `compliance` + `observability-infra` = REQUIRES-REWORK** (Phase-1 fixes adversarially refuted; thresholds kept strict, NOT masked) — plus two prompt-robustness follow-ups the Phase-3 sweep surfaced (env-parity non-JSON parse-reliability on `compose-var-not-declared`; api-design `severity`-field omission, still PASS). Detail = scorecards `docs/superpowers/eval-scorecards/2026-06-1{0,1}-plan21-*/` + Phase-3 backlog `…/2026-06-10-plan21-audit/PHASE3-CHECKLIST.md`. **Reviewer fixture authoring:** render→edit→`git diff` against the rendered demo ([[render-edit-gitdiff-eval-fixtures]]). **Next plans: 23** (agent self-improvement) + **24** (`framework upgrade`).
- **Where we are:** Plans 1–22 merged to `master`; **`v0.2.1`** (Dependabot github-actions ecosystem dropped) atop **`v0.2.0`** (GraphQL introspection-in-prod fix) atop `v0.1.9`; Plan-21 Phase-3 fixture-coverage batch in PR #7; docs site live at https://cdowell-swtr.github.io/swiftwater-framework/. **Remaining: Plan 23** (agent self-improvement tooling) + **Plan 24** (`framework upgrade` + rollback) — both future/not-started.
- **Env parity (this box, Ubuntu/WSL2):** native Linux **Node 22** + **docker buildx** + **shellcheck** (`~/.local/bin`); dind works under `--privileged` + `--storage-driver=vfs` ([[dind-e2e-harness-gotchas]]). `/tmp` is RAM tmpfs (16 GB), `/` ext4 936 GB. The Docker acceptance tier is host-UID clean (Plan 9). **Second machine (laptop) for reviewer eval/audit work (uv + claude + repo only — no docker/node/shellcheck): `docs/maintenance/laptop-dev-parity.md`** (headless-PATH fix: symlink uv/claude into `/usr/local/bin` + `~/.profile`, not `~/.bashrc`). _On the laptop in sandbox mode, uv/framework/render run sandboxed (cache+/var/tmp allowlisted); only crontab/PID-introspection need sandbox-off ([[prefer-sandboxed-execution]]). Subscription quota is shared across ~4–5 projects ([[subscription-quota-shared-across-projects]])._
- **Model facts:** Opus 4.8 = `claude-opus-4-8` (agentic tier); Sonnet 4.6 = `claude-sonnet-4-6` (bundle default); Haiku 4.5 = `claude-haiku-4-5-20251001`. **Operational gotchas (memory-backed):** `[[gate-cadence-framework-slices]]`, `[[commit-gate-hook-timing]]`, `[[subagent-implementers-stop-before-commit]]`, `[[release-readiness-needs-render-not-local-gate]]`, `[[dind-e2e-harness-gotchas]]`, `[[reviewers-tune-quota-throttling]]`, `[[reviewers-tune-pytest-tmp-accumulation]]`, `[[audit-prepare-snapshot-stderr-breaks-cli-runner-output]]`.
- **Reviewer system = source of truth for review state:** commit history, agent prompts under `src/framework_cli/review/agents/`, calibrated `tests/eval/fixtures/thresholds.yaml`, dated scorecards under `docs/superpowers/eval-scorecards/`.

## Keeping state current (required before every commit)

Before every commit, update the **Current State** pointer above — including **Last updated** as a datetime with timezone (e.g. `2026-05-21 09:19 PDT`, since we commit several times a day) — and the meta-plan's status table when a plan's status changes, then `git add CLAUDE.md`. This keeps the repo's state accurate as we move across machines and environments. A `PreToolUse` hook in `.claude/settings.json` enforces this — it blocks `git commit` until `CLAUDE.md` is staged. Run `/hooks` to review or disable it.

## How we build here
- Work proceeds plan-by-plan per the meta-plan, using the superpowers subagent-driven flow: a feature branch → an implementer per task (TDD) → controller verification → a final review → merge to `master`.
- **Review-model policy** (long-standing; see [[subagent-review-model-pattern]]): implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet; **code-quality review → Opus**; final/branch-end whole-branch review → Opus. Pass `model` explicitly per role and restate this in every plan's Execution section — don't let the writing-plans/subagent-driven skills' generic "least powerful model" guidance collapse the reviewers.
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
- **Workflow actions are pinned to Node-24-capable versions** (GHA forces Node 24 on 2026-06-16). `tests/test_workflow_node24.py::APPROVED_ACTIONS` is the source of truth across the framework's own + the template's workflows; see `docs/maintenance/github-actions-node-runtime.md`.

## Known follow-ups
- Resolved follow-ups and items promoted to plans are no longer mirrored here — their record of record is the **meta-plan status table** (`docs/superpowers/plans/2026-05-20-meta-plan.md`) plus the FF SHAs in git. Open work is tracked as meta-plan rows (Plans 16–19) and named priority rows; there are no standalone open follow-ups at present. *(History: this section previously accumulated ~10 resolved/promoted entries kept verbatim "for reference" — pruned 2026-06-04 once they were all recorded in the meta-plan + git.)*
