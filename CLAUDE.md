# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record — every completed slice, FF SHA, and what's next — is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`). Keep this section short; update the meta-plan status table when a plan's status changes.

- **Last updated:** 2026-06-11 11:10 PDT — **Plan 21 (reviewer prompt + threshold re-tuning) ✅ MERGED to `master`** (PR #3, merge commit `8a9357d`; all 18 PR checks green); **Plan 22 (docs pack, 22a+22b) already on `master`** (docs site live). Plan 21: Phase 1 audit (vetted 23-change changelist, 7 adversarially refuted) -> Phase 2 (15 agents retuned to one shared severity+scope rubric, each eval-PASS + Opus review-gate PASS — over-flaggers driven to fp 0; contracts recall 0.50->1.00, data-lineage 0.17->1.00, observability-db keystone redesign 0->1.00) -> Phase 3 (`--repeat 3` whole-set re-sweep -> `eval-analyze` threshold re-derivation; architecture/env-parity wobbles were PROMPT bugs — severity-field omission + fabricated overlay injection — firmed to 1.00/0.00). **compliance + observability-infra = REQUIRES-REWORK** (their Phase-1 fixes were adversarially refuted, never retuned; thresholds kept STRICT so they fail accurately, NOT masked — the `agent-evals` CI job is opt-in/skip-neutral so they don't gate merge). Branch-end Opus review = GO. Detail of record: the **meta-plan status table** + scorecards under `docs/superpowers/eval-scorecards/2026-06-1{0,1}-plan21-*/` + the shared rubric `docs/superpowers/specs/plan21-rubric-final.md`; Phase-3 follow-ups (2nd good fixtures, the 2 rework agents, doc normalizations) tracked in `…/2026-06-10-plan21-audit/PHASE3-CHECKLIST.md`.
- **Where we are:** Plans 1–22 merged to `master`; `v0.1.9` shipped; docs site live at https://cdowell-swtr.github.io/swiftwater-framework/. **Remaining: Plan 23** (agent self-improvement tooling) + **Plan 24** (`framework upgrade` + rollback) — both future/not-started.
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
