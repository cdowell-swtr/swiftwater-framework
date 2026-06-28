# swiftwater-framework — Working Agreement

This repo is an opinionated Python scaffold framework: a `framework` CLI that renders a bundled Copier template into new projects which ship with TDD, quality gates, observability, and environment parity built in.

**Source of truth:**
- Current state / what's next: `PLAN.md` (+ `ACTION_LOG.md` for history) — read first.
- Design spec: `docs/superpowers/specs/2026-05-20-framework-design.md`
- Build roadmap (FROZEN historical record through v0.2.4): `docs/superpowers/plans/2026-05-20-meta-plan.md`

@AGENTS.md

## Operating environment
- **Env parity (this box, Ubuntu 26.04/WSL2, systemd):** does NOT ship the acceptance toolchain by default — only `uv`/`claude` (in `~/.local/bin`) are preinstalled. Bring it to parity (verified 2026-06-17) via apt: `docker.io` (29.x) + `docker-compose-v2` + `docker-buildx`, `nodejs` 22 + `npm`, `mkcert` + `libnss3-tools`, `shellcheck`; plus `go-task` 3.51.1 from `taskfile.dev/install.sh` → `/usr/local/bin`. No host `k6` needed (`load.sh` runs the `grafana/k6` image). After `usermod -aG docker`, the docker group needs a **fresh login** (`wsl --shutdown` + restart the session) to take effect. dind works under `--privileged` + `--storage-driver=vfs`; acceptance tier is host-UID clean. **Preflight with `task doctor`** (framework FWK35; expect 10/10). Second machine (laptop) for reviewer eval/audit: `docs/maintenance/laptop-dev-parity.md`.
- **Running the docker/acceptance tier here:** `/tmp` is a small (~4 GB) RAM tmpfs — set `TMPDIR=/var/tmp` (~1 TB) for image builds/renders. Under the Claude Code sandbox, docker/compose/acceptance commands need the sandbox disabled (the docker socket + Docker Hub/ghcr.io are not in the allowlist); a transient `ghcr.io`/Docker Hub pull timeout is a flake → retry, not a failure ([[render-matrix-dockerhub-flake-triage]]).
- **`$DEV_ROOT` is the projects-root convention.** An exported env var (in shell rc) points at the parent of all sibling checkouts — `/home/chris/Claude Code/Projects` on this box. **Write every *load-bearing* path through it** — runbook commands, scratch scripts, fixture/`cd` paths, sibling-repo references you'll actually execute — as `"$DEV_ROOT/swiftwater-framework/main"`, `"$DEV_ROOT/meridian/main"`, etc. This survives a later relocation of the projects dir and dodges the space-in-`Claude Code` quoting hazard. **Do NOT** rewrite *historical/prose* path references (frozen `ACTION_LOG.md` entries, completed plans, PI-registry rows) — those record what was literally true at a point in time and stay as-is.
- **Model facts:** Opus 4.8 = `claude-opus-4-8` (agentic); Sonnet 4.6 = `claude-sonnet-4-6` (bundle default); Haiku 4.5 = `claude-haiku-4-5-20251001`.
- **Reviewer system = source of truth for review state:** commit history, agent prompts under `src/framework_cli/review/agents/`, calibrated `tests/eval/fixtures/thresholds.yaml`, dated scorecards under `docs/superpowers/eval-scorecards/`. The human-facing per-agent reference is `documentation/reference/review-agents.md` — **generated** from `review/registry.py` + `review/reference_doc.py` (`_BLURBS`) by `scripts/gen_reviewer_reference.py`, kept current by `tests/test_reviewer_reference.py`; edit the registry/blurbs and regenerate, never the page by hand (FWK3).

## Keeping state current (required before every commit)

Before every commit, update `PLAN.md` (tick the task; move finished items to `Done`) and append an `ACTION_LOG.md` entry for every completion and every deviation, per `pi-convention.md`. A `PreToolUse` hook in `.claude/settings.json` enforces this — it blocks `git commit` until `PLAN.md` or `ACTION_LOG.md` is staged. Run `/hooks` to review or disable it.

## How we build here
- Work proceeds plan-by-plan per the meta-plan, using the superpowers subagent-driven flow: a feature branch → an implementer per task (TDD) → controller verification → a final review → merge to `main`.
- **Review-model policy** (long-standing; see [[subagent-review-model-pattern]]): implementers → Sonnet (Haiku for trivial); spec-compliance review → Sonnet; **code-quality review → Opus**; final/branch-end whole-branch review → Opus. Pass `model` explicitly per role and restate this in every plan's Execution section — don't let the writing-plans/subagent-driven skills' generic "least powerful model" guidance collapse the reviewers.
- TDD is required: write the failing test first, confirm red, implement the minimum, confirm green.

## Quality gate (must be green before commit / merge)
```bash
uv run ruff check .           # lint
uv run ruff format --check .  # formatting — CI's `gate` job runs this; `ruff check` alone misses it
uv run mypy src               # type-check (framework source only)
task test:fast                # FAST tier — non-docker suite, -n auto; mirrors the CI `gate`
task test:full                # FULL tier — + docker acceptance, bounded -n; run at branch-end
```
**Test tiers (FWK96).** The suite is split fast (per-commit) vs full (per-merge/branch-end):
`task test:fast` is the non-docker suite under `-n auto` and is byte-for-byte the CI `gate`'s
pytest invocation; `task test:full` adds the two docker/dind acceptance files. The docker
acceptance tests are intentionally **not** a required CI check (heavy + dind-flaky on GHA) —
they run only at branch-end via the full tier. That is a *documented* exception, not a silent
gap: `tests/test_test_tiers.py` enforces that every fast-tier `--ignore` is recorded with a
reason, and that the local fast tier and the CI gate never drift. See
`docs/maintenance/test-tiers.md`. (`uv run pytest -q` / `task test` still runs everything serially.)

`uv` is the package manager — run all tooling via `uv run`. If `uv` is not found, make sure its install directory is on PATH (restart the session after a fresh install).

## Critical conventions
- **`src/framework_cli/template/` is template *payload*, not framework source.** Those `.jinja` / `.py` / config files are rendered into generated projects — do not refactor or lint them as framework code. The framework's own `mypy` excludes that directory. The template is validated by rendering it and exercising the generated project: `tests/test_copier_runner.py` (files render / interpolate) and `tests/acceptance/test_rendered_project.py` (the generated project's own tests, coverage gate, and pre-commit pass).
- Brace-named paths like `src/framework_cli/template/src/{{package_name}}/` are intentional Copier path templating — leave them.
- The CLI (`src/framework_cli/`) is a thin shell over Copier; keep logic in focused modules (`naming.py`, `copier_runner.py`, `cli.py`).
- Changing the template means re-running the render + acceptance tests. A freshly generated project must make a clean first `pre-commit` pass — enforced by `test_rendered_project_precommit_runs_clean`.
- **Workflow actions are pinned to Node-24-capable versions** (GHA forces Node 24 on 2026-06-16). `tests/test_workflow_node24.py::APPROVED_ACTIONS` is the source of truth across the framework's own + the template's workflows; see `docs/maintenance/github-actions-node-runtime.md`.

## Known follow-ups
- Resolved follow-ups and items promoted to plans are no longer mirrored here — their record of record is `PLAN.md` (open work) plus the FROZEN meta-plan status table and the FF SHAs in git. Open work is tracked as `PLAN.md` `Next` items (the repo's `FWK`-prefixed task IDs); there are no standalone open follow-ups at present. *(History: this section previously accumulated ~10 resolved/promoted entries kept verbatim "for reference" — pruned 2026-06-04 once they were all recorded in the meta-plan + git.)*

<!-- MEMORY-convention: v1 -->
## Committed project memory
Project memory is autoloaded from `MEMORY.md` (imported below). Resolve `[[slug]]`
to `_memory/<slug>.md`. Commit a memory only when it is BOTH useful to anyone
working this repo AND safe to publish; otherwise keep it in the native store.
When in doubt, native. Full rule + never-commit list in
`memory-convention.md`.

@MEMORY.md
