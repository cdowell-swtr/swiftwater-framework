# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record — every completed slice, FF SHA, and what's next — is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`). Keep this section short; update the meta-plan status table when a plan's status changes.

- **Last updated:** 2026-06-10 — **Plan 20 COMPLETE — 20a + 20b both merged to `master`, CI all-green** (ci+render-matrix+review+agent-evals success on `e6f6535`). The reviewer is now ONE in-process engine with a swappable `messages.create`-shaped backend (`--backend api` paid ↔ `--backend subagent` free `claude -p`); the prepare→split→Workflow-JS→finalize orchestration + JS/slash/template payload are fully retired; both commit-gate hooks (framework + template) rewired to `framework gate` (skip-neutral degrade); cost-safe resolution R1–R4 (no spend without explicit intent). Paid-vs-free parity smoke confirmed **dev = prod by construction** (Plan 20's thesis); the live smoke caught + fixed a real `SubagentBackend` ARG_MAX bug (system→`--system-prompt-file`, prompt→stdin). Full suite 824 + CI all-green. **Next: Plan 21** (reviewer prompt + threshold re-tuning + fixture quality — now unblocked), then Plan 22 (docs pack). Non-blocking follow-ups inherited by Plan 21: gate-on-exhaustion strict skip-neutral, re-derive the stale audit baselines (the 2.35 MB-delta case), the test-only `_review_run`/`_eval_run` `backend=None` fallback. Detailed record = meta-plan + [[reviewer-dev-prod-parity-gap]] (now RESOLVED). _(History of the 20b per-task execution is in git + the meta-plan; this pointer was collapsed on merge.)_
- **Where we are:** Plans 1–17 + NODE24-MIGRATION + **Plan 20 (reviewer path parity — 20a + 20b)** + all follow-ups merged to `master`; `v0.1.9` shipped. **Remaining = Plan 21 (prompt+threshold re-tuning + fixture quality — ← next, now unblocked by Plan 20), Plan 22 (docs pack — last).** Plan 18 (paid anchor) run & superseded; the old Plan 19 (docs) renumbered → 22 so it follows the reviewer work.
- **Env parity (this box):** native Linux **Node 22** + **docker buildx** + **shellcheck** (`~/.local/bin`) installed; dind works under `--privileged` + `--storage-driver=vfs` ([[dind-e2e-harness-gotchas]]). `/tmp` is RAM tmpfs (16 GB) while `/` ext4 has 936 GB — optional `sudo systemctl mask tmp.mount` + `wsl --shutdown` makes `/tmp` disk-backed. The Docker acceptance tier is host-UID clean (Plan 9).
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
