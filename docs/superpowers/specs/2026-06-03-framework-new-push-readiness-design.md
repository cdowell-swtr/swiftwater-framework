# Plan 14 — `framework new` push-readiness

**Date:** 2026-06-03
**Status:** Design — approved, pending spec review
**Plan:** 14 (meta-plan `docs/superpowers/plans/2026-05-20-meta-plan.md`, row 14)
**Depends on:** 5a (the generated CI pipeline), 6b (`framework new` portable source). Surfaced by Plan 13's dogfood.

## Problem

A freshly `framework new`'d project is **not green-on-first-push**. The shipped `.github/workflows/ci.yml` requires three committed artifacts that `framework new` does not generate:

- **`uv.lock`** — 5 jobs run `uv sync --frozen` (`lint`, `security`, `test`, `contract`, `contracts`) and the multi-stage `Dockerfile` `COPY`s it. `--frozen` fails outright with no lockfile.
- **`openapi.json`** — the `contract` job regenerates it and fails if it is missing or stale (`git status --porcelain`).
- **`schema.graphql`** (graphql battery) — same staleness check.

So a builder must run `uv sync` + `task openapi:export` (+ graphql export) and commit before their first push, or CI is red. The Plan 10 render-matrix never caught this because its `task ci` path uses plain `uv run` (no `--frozen`), does not run `ruff format --check`, and never executes the shipped `ci.yml`. Plan 13's dogfood found it: its `prepare_project` replicates the manual builder setup precisely to get a green run.

`framework new` is currently a **pure render** — `render_project` → `write_manifest` → `record_portable_source`, no network/install/git. The cost asymmetry that shapes the fix: generating `uv.lock` is cheap (`uv lock` = dependency resolve, no install, no venv); generating `openapi.json`/`schema.graphql` is expensive (needs a full `uv sync` install + importing the app).

## Goal

A vanilla `framework new` project's `ci.yml` runs **green on its first push to GitHub Actions** with **zero manual artifact setup**, without turning `framework new` into a heavy, install-dependent operation.

## Approach (chosen)

Two mechanisms, split by the cheap/expensive cost line:

### Part A — `framework new` generates `uv.lock` (cheap, resolve-only)

After the existing render steps, `new` runs `uv lock` in the rendered project to produce `uv.lock`. `uv lock` *resolves* dependencies (network) but does NOT install or create a venv — fast, no dep tree on disk.

- **Failure handling: warn-and-continue.** If `uv lock` fails (offline, `uv` not on PATH, resolution error), emit a warning (`couldn't pre-generate uv.lock — run 'uv sync' before your first push`) and leave the project lock-less. The scaffold still succeeds — a transient network issue must never break `framework new`. Worst case = today's behavior; best case = a committed-ready lock. Strict improvement.
- **Order / integrity:** render → `write_manifest` → `record_portable_source` → `uv lock`. `uv.lock` is a builder artifact, NOT a locked manifest file (verified in Plan 13: integrity passes with `uv.lock` present), and it is generated *after* the manifest, so there is no integrity interaction.
- **Fixes:** the 5 `--frozen` jobs + the Dockerfile `COPY uv.lock`. Also unblocks the acceptance test `test_rendered_react_battery_passes` (which hit `/uv.lock not found` in the image build).

### Part B — the generated `ci.yml` `contract` job self-seeds the spec

Rework the `contract` job's openapi (and graphql) steps so the spec is **enforced only when committed**:

- Always regenerate the spec (`bash scripts/export-openapi.sh`, and the graphql export when present).
- If the spec file is **git-tracked** → enforce currency (fail on drift, today's behavior) **and** run the PR-only breaking-change checks (oasdiff for openapi; `graphql-core.find_breaking_changes` for the SDL) against the base.
- If the spec file is **untracked/absent** → emit a `::notice::` ("generated for this run; commit it to track the API contract + enable breaking-change diffs") and **skip** the staleness + breaking-change gates.

Detect tracked-ness with `git ls-files --error-unmatch <file>`. The oasdiff step (which fetches the base branch's `openapi.json` from `raw.githubusercontent.com`) is gated on tracked-ness so a never-committed-spec project never 404s on the base.

Net: first push (no committed spec) → `contract` green; the moment a builder commits `openapi.json`/`schema.graphql`, full staleness + breaking-change enforcement kicks in. This makes committing the API spec **opt-in** — a deliberate, minor relaxation of the "spec is always tracked" intent, chosen over the alternatives (a heavy `uv sync`+export at `new`, or a fragile template-shipped `openapi.json.jinja` that must be hand-synced to the routes/models). The generated `CLAUDE.md` contract/convention section nudges the builder to commit it.

## Part C — validation (closes the dogfood loop)

Plan 13's dogfood harness works *around* this gap via `prepare_project` (manual `uv sync` + export). Plan 14 removes the gap, so the dogfood becomes Plan 14's acceptance test:

- Simplify the dogfood: `scripts/dogfood_e2e.py::render()` mirrors the new `framework new` (add `uv lock`); drop `prepare_project`'s manual openapi/graphql export (the `contract` job now self-seeds). Bump `DOGFOOD_COMMIT` to the release that ships Plan 14.
- Re-run the dogfood → it must go **green with no manual artifact prep**, proving `framework new` projects are genuinely push-ready (not green only because the harness pre-generated everything).
- Confirm `test_rendered_react_battery_passes` (the `/uv.lock not found` image build) now passes, and the render-matrix `framework new` combos ship a lock.

## Components / files

| File | Change |
|---|---|
| `src/framework_cli/lockfile.py` (new) | `write_lockfile(dest: Path) -> bool` — runs `uv lock` in `dest`; returns True on success, False + warns on failure. Pure, unit-testable in isolation. |
| `src/framework_cli/cli.py` (`new`) | Call `write_lockfile(dest)` after `record_portable_source`; keep `new` a thin shell. |
| `src/framework_cli/template/.github/workflows/ci.yml.jinja` | Rework the `contract` job openapi + graphql steps to the tracked-vs-untracked self-seed logic. |
| `scripts/dogfood_e2e.py` | Simplify `render()`/`prepare_project` per the new push-readiness; bump `DOGFOOD_COMMIT`. |
| Generated `CLAUDE.md` (contract/convention section) | One-line nudge to commit `openapi.json` (+ `schema.graphql`) to track the API contract. |
| `tests/test_lockfile.py` (new) + `tests/test_copier_runner.py` | Unit tests for `write_lockfile`; content assertions on the rendered `contract` job. |

## Testing boundary (TDD where it bites)

- **`write_lockfile` helper** — full TDD: success path (creates `uv.lock`; real or faked `uv lock`); the **warn-and-continue** path (a failing fake `uv` → returns False, warns, raises nothing). Hermetic.
- **`framework new` integration** — `new` (with `uv` available) leaves a `uv.lock` in the project; a forced `uv lock` failure does not abort the scaffold (the render + manifest + portable source still complete).
- **contract-job self-seed** — content test: the rendered `ci.yml` `contract` job contains the tracked-vs-untracked branches + the `git ls-files --error-unmatch` guard. The *behavioral* proof is the live dogfood (Part C).
- **Integration proof** — the simplified dogfood re-run goes green with no manual prep.

## Out of scope (YAGNI)

- The heavy "generate openapi/schema at `new` via `uv sync`+export" option (rejected — turns `new` into a full install).
- Template-shipped `openapi.json.jinja` (rejected — fragile hand-sync to routes/models).
- The durable timescaledb image-build fix (separate plan — **Plan 15**).
- `framework new` git-init/commit (still the builder's; `new` only generates the artifacts on disk).

## Risks / edges

- **`uv lock` network dependency at `new`** — mitigated by warn-and-continue (scaffold never fails on it).
- **oasdiff base fetch** — must be gated on tracked-ness, else a never-committed-spec project 404s fetching the base `openapi.json`; the design gates it.
- **Self-seed weakens the always-tracked-spec guarantee** — accepted + documented; the nudge in `CLAUDE.md` + the enforce-once-committed behavior recover it as soon as the builder opts in.
