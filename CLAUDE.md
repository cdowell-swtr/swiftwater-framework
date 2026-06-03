# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap / status: `docs/superpowers/plans/2026-05-20-meta-plan.md` — read this to see what's done and what's next.

## Current State

> Quick pointer, kept current so any environment starts with the real state. The detailed record of record — every completed slice, FF SHA, and what's next — is the meta-plan (`docs/superpowers/plans/2026-05-20-meta-plan.md`). Keep this section short; update the meta-plan status table when a plan's status changes.

- **Last updated:** 2026-06-04 04:10 PDT — **`NODE24-MIGRATION` ✅ DONE & SHIPPED — merged FF `7618ce4`; `v0.1.7` GitHub Release published green** (release.yml full pipeline + `uv build`; assets = wheel + sdist + default.gitignore). Bumped every GitHub Actions `uses:` off the deprecated Node 20 runtime onto Node-24 versions across the framework's 5 workflows + the generated template's 3, guarded by a new allowlist test (`tests/test_workflow_node24.py::APPROVED_ACTIONS`, raw-source scan of both surfaces) + maintenance doc (`docs/maintenance/github-actions-node-runtime.md`). Final set: **checkout@v5, setup-uv@v7, setup-node@v6, upload-artifact@v6, download-artifact@v7, action-gh-release@v3**; `arduino/setup-task` held as a tracked `node20-forced` exception (no Node-24 release exists); oasdiff/gitleaks Docker-exempt. **Branch-end Opus review caught a real defect** — `setup-uv@v6` is still node20 (node24 only at v7); fixed all 20 refs → `@v7` + allowlist floor → 7 (lesson: verify action Node runtime against `action.yml`, not a web-search summary). Subagent-driven (5 tasks); local gate **729 pass** clean; framework `render-matrix`+`review` green on the bumped actions (live proof) + render-matrix actionlints the generated `ci.yml`. The 3 template workflows are integrity-tracked → expected one-time baseline-hash shift (self-consistent; no golden-hash test). GHA forces Node 24 on 2026-06-16. **Plan:** `docs/superpowers/plans/2026-06-04-node24-actions-migration.md`. `v0.1.7` cut (commit `c275a7c`, tag `v0.1.7`). **Next: Plan 16** (frontend-obs surface + `review-observability-fe`). *(Housekeeping 2026-06-04: pruned the bloated Known-follow-ups section — ~10 resolved/promoted entries, now recorded only in the meta-plan + git; saved two memories: `[[release-cut-procedure]]`, `[[verify-action-node-runtime-from-actionyml]]`.)* — *(prior: Plan 15 CI external-flake resilience ✅ SHIPPED `v0.1.6` FF `fcfc67b` — COPY timescaledb from pinned `-ha` onto `postgres:17` drops the packagecloud flake; oasdiff `base_has_openapi` gate; render-matrix green vs prior packagecloud failure + dogfood green.)*
- **Where we are:** Plans 1–15 + `NODE24-MIGRATION` + all post-Plan-11 follow-ups + the `v0.1.0`–`v0.1.7` GitHub Releases all merged to `master`. **Remaining = Plans 16–19:** **16** frontend-obs surface + `review-observability-fe` **← next**; **17** environment-parity reviewer (needs 16); **18** optional paid real-key eval anchor (Slice E3); **19** MkDocs + Material docs pack.
- **Env parity (this box):** native Linux **Node 22** + **docker buildx** + **shellcheck** (`~/.local/bin`) installed; dind works under `--privileged` + `--storage-driver=vfs` ([[dind-e2e-harness-gotchas]]). `/tmp` is RAM tmpfs (16 GB) while `/` ext4 has 936 GB — optional `sudo systemctl mask tmp.mount` + `wsl --shutdown` makes `/tmp` disk-backed. The Docker acceptance tier is host-UID clean (Plan 9).
- **Model facts:** Opus 4.8 = `claude-opus-4-8` (agentic tier); Sonnet 4.6 = `claude-sonnet-4-6` (bundle default); Haiku 4.5 = `claude-haiku-4-5-20251001`. **Operational gotchas (memory-backed):** `[[gate-cadence-framework-slices]]`, `[[commit-gate-hook-timing]]`, `[[subagent-implementers-stop-before-commit]]`, `[[release-readiness-needs-render-not-local-gate]]`, `[[dind-e2e-harness-gotchas]]`, `[[reviewers-tune-quota-throttling]]`, `[[reviewers-tune-pytest-tmp-accumulation]]`, `[[audit-prepare-snapshot-stderr-breaks-cli-runner-output]]`.
- **Reviewer system = source of truth for review state:** commit history, agent prompts under `src/framework_cli/review/agents/`, calibrated `tests/eval/fixtures/thresholds.yaml`, dated scorecards under `docs/superpowers/eval-scorecards/`.

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
- **Workflow actions are pinned to Node-24-capable versions** (GHA forces Node 24 on 2026-06-16). `tests/test_workflow_node24.py::APPROVED_ACTIONS` is the source of truth across the framework's own + the template's workflows; see `docs/maintenance/github-actions-node-runtime.md`.

## Known follow-ups
- Resolved follow-ups and items promoted to plans are no longer mirrored here — their record of record is the **meta-plan status table** (`docs/superpowers/plans/2026-05-20-meta-plan.md`) plus the FF SHAs in git. Open work is tracked as meta-plan rows (Plans 16–19) and named priority rows; there are no standalone open follow-ups at present. *(History: this section previously accumulated ~10 resolved/promoted entries kept verbatim "for reference" — pruned 2026-06-04 once they were all recorded in the meta-plan + git.)*
