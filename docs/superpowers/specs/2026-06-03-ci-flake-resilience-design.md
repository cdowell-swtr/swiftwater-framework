# Plan 15 — CI external-flake resilience

**Date:** 2026-06-03
**Status:** Design — approved, pending spec review
**Plan:** 15 (meta-plan `docs/superpowers/plans/2026-05-20-meta-plan.md`, row 15)
**Depends on:** 8f (db-paradigm batteries / the custom Postgres image). Plan 13 + 14 follow-ups.

## Problem

Two recurring external-registry flakes keep generated-project CI (and the framework's own render-matrix / `release.yml`) **intermittently red**, despite the work being correct:

1. **Timescale packagecloud apt.** The custom Postgres image (`infra/docker/postgres.Dockerfile`, built whenever a postgres-extension battery is present) installs `timescaledb-2-postgresql-17` from `packagecloud.io` at build time. That apt step intermittently returns a non-zero code (a packagecloud-side bad response, not a plain network timeout). The v0.1.4 mitigation (`apt-get -o Acquire::Retries` + `wget --tries` in the Dockerfile, a 3× build/start retry in the generated `conftest.py`) **reduces but does not eliminate** it — a longer packagecloud window outlasts the retries. It blocked `release.yml` for v0.1.1, v0.1.3, and v0.1.4 until a re-run. It hits **both** the framework render-matrix (~19 combos each build the image) and **every real builder's generated-project CI** (their `task ci`/testcontainers builds the same image).

2. **oasdiff base-spec 404 (folded-in Plan 14 edge).** The generated `ci.yml` `contract` job's oasdiff breaking-change step fetches the base branch's `openapi.json` over HTTP with `fail-on: ERR`. After Plan 14, it's gated on the spec being git-tracked on the PR head — so the **first PR that commits `openapi.json`** runs oasdiff, but the base branch lacks the file → 404 → job fails (once per project). The graphql sibling guards this with a `|| skip`; openapi does not.

## Goal

Make generated-project CI (and the framework render-matrix) **reliably green without re-runs**, eliminating the build-time packagecloud dependency for timescaledb and the oasdiff first-commit 404 — for real builders, not just the framework's own CI.

## Approach (chosen)

### Part A — drop the packagecloud apt by COPYing timescaledb from a prebuilt image

> **Spike outcome (2026-06-03, supersedes the base-swap design below).** The spike found `FROM timescale/timescaledb-ha` is **blocked**: `-ha` is Ubuntu 22.04 / glibc 2.35, but the AGE `age.so` (`apache/age:release_PG17_1.6.0`) needs glibc 2.38 → it won't load on `-ha` → the `timescaledb+age` combo can't start. So instead of swapping the base, **COPY timescaledb from `-ha` onto the unchanged `postgres:17` base** (the same multi-stage pattern already used for AGE) — glibc-safe in this direction (a 2.35-built `.so` runs on trixie's 2.41), and validated end-to-end (all three extensions create on the all-batteries combo). See `docs/superpowers/eval-scorecards/ci-flake-resilience-spike-2026-06-03.md`.

**The implemented approach:** in `infra/docker/postgres.Dockerfile.jinja`, keep `FROM postgres:17` and replace **only** the flaky timescaledb packagecloud apt block with a multi-stage `COPY --from=timescale/timescaledb-ha:pg17.10-ts2.27.1` of timescaledb's `.so` + extension files. pgvector (PGDG apt — reliable, never the flaky part) and AGE (COPY) are unchanged; non-timescaledb combos are untouched. The pinned `-ha` tag (`pg17.10-ts2.27.1`, not floating `pg17`) can't drift.

**Original base-swap design (superseded — kept for context):** `timescaledb` → `FROM timescale/timescaledb-ha:pg17-<pinned>`; otherwise `FROM postgres:17`. Dropped because of the AGE glibc incompatibility above.

**Pinned, not floating:** the `-ha` base uses a specific tag/digest (e.g. `pg17.x-ts2.x`), never a floating `pg17` — the root cause of this whole saga was `postgres:17` floating to Debian trixie ahead of packagecloud. A pinned `-ha` tag cannot drift.

**Spike-first (the plan's opening task), because the `-ha` base is combo-sensitive.** Before committing, empirically verify across `timescaledb`, `timescaledb+pgvector`, `timescaledb+age`, and all-three:
1. the image builds;
2. testcontainers `PostgresContainer` starts it — entrypoint, `POSTGRES_*` env, and the compose `command: postgres -c shared_preload_libraries=timescaledb,age` all behave on the `-ha` base;
3. the **AGE** multi-stage `COPY` still loads (same pg17 ABI);
4. **pgvector** — confirm whether `-ha` bundles it (drop the PGDG apt on the `-ha` branch) or the PGDG apt must stay (and whether PGDG sources are available on `-ha`).

The spike's findings nail down the exact `-ha`-branch Dockerfile + the pinned tag.

**Fallback:** if the spike shows `-ha` is incompatible (testcontainers/entrypoint/AGE breakage that can't be cheaply resolved), fall back to the lower-risk alternative — have the framework's `render-matrix.yml` build the custom image **once** and reuse it across the ~19 matrix combos (GHCR push/pull or GHA cache), cutting the framework's flake exposure ~19×. (This is framework-CI-only — it would NOT help real builders — so it's a fallback, not the preferred design.) The fallback decision + rationale gets recorded if taken.

### Part B — oasdiff base-spec gate

In `ci.yml.jinja`'s `contract` job, extend the existing `id: spec` step to probe whether the base branch has `openapi.json`, and gate oasdiff on it:

```bash
# inside the id: spec step, after determining openapi_tracked:
if curl -sfI "https://raw.githubusercontent.com/${{ github.repository }}/${{ github.base_ref }}/openapi.json" >/dev/null 2>&1; then
  echo "base_has_openapi=true" >> "$GITHUB_OUTPUT"
else
  echo "base_has_openapi=false" >> "$GITHUB_OUTPUT"
fi
```

then extend the oasdiff `if:` to `… && steps.spec.outputs.openapi_tracked == 'true' && steps.spec.outputs.base_has_openapi == 'true'`. (`github.base_ref` is only set on `pull_request`, which is already in the gate.) Net: the first spec-committing PR generates + tracks the spec and **skips** oasdiff with a notice (no base to diff); subsequent PRs (base now has the spec) get the full breaking-change diff.

## Validation

- **Dogfood (Part A integration proof):** the all-batteries config includes `timescaledb`, so its image now builds from `-ha` (no packagecloud). Re-run → green proves the flake source is gone for builders. A **render-matrix-on-master** run that goes green **without a flaky-combo re-run** is the framework-side proof.
- **Framework's own timescaledb coverage:** `test_copier_runner.py`'s preload test + the db-paradigm acceptance test (builds the image + testcontainers) stay green on the new base.
- **Part B:** a content test asserts the `base_has_openapi` gate wiring; the behavioral proof is the reasoned skip-on-first-PR (a full dogfood "commit-the-spec" scenario is out of scope — the gate logic is small and clear).

## Components / files

| File | Change |
|---|---|
| `src/framework_cli/template/infra/docker/{{ 'postgres.Dockerfile' … }}.jinja` | Conditional `-ha` base for timescaledb (drop packagecloud apt); pinned tag. Per the spike. |
| `src/framework_cli/template/.github/workflows/ci.yml.jinja` (`contract` job) | Part B: `base_has_openapi` probe + extend the oasdiff gate. |
| `tests/test_copier_runner.py` | Content tests: timescaledb render → `-ha` base + no packagecloud block; oasdiff `base_has_openapi` gate wiring. |
| `.github/workflows/render-matrix.yml` | Only if the fallback is taken (build-once/reuse). |

## Tasks (subagent-driven)

- **T1 — spike** (investigative, controller-driven): build the `-ha`-based image across the relevant combos; verify testcontainers/AGE/compose/pgvector; pick + pin the `-ha` tag; produce the exact `-ha`-branch Dockerfile + a go/no-go (vs the build-once-reuse fallback).
- **T2** — implement the conditional `-ha` base per the spike + `test_copier_runner.py` content test + re-run the timescaledb framework/acceptance tests.
- **T3** — Part B oasdiff `base_has_openapi` gate + content test.
- **T4** (controller) — re-run the dogfood + a render-matrix-on-master run → both green = acceptance.
- **T5** (controller) — branch-end review → merge → cut `v0.1.6` (ships the base swap to builders) → state updates (Plan 15 → done; next is Plan 16).

## Testing boundary

The Dockerfile + ci.yml changes are validated by content tests (rendered output) + the real build/run proofs (the spike, the timescaledb acceptance test, the dogfood). The spike is discovery (no TDD); its findings drive T2's TDD.

## Out of scope (YAGNI)

- The Docker Hub `FROM`/ryuk-pull timeout flake beyond what the existing conftest build/start retry already covers (the `-ha` base is bigger → still pulled, but the conftest retry wraps it; not separately re-engineered here).
- A dogfood "commit-the-spec" scenario for Part B's behavioral validation.
- Frontend-obs / env-parity / docs (Plans 16–19).

## Risks / edges

- **`-ha` incompatibility** with testcontainers/compose/AGE — mitigated by the spike-first gate + the documented build-once-reuse fallback.
- **Bigger image pull** (`-ha` is ~1GB vs `postgres:17` ~400MB) → potentially more Docker-Hub-timeout-prone; the conftest build/start retry (v0.1.4) covers transient pull failures.
- **pgvector on `-ha`** — the spike determines whether the PGDG apt is dropped (bundled) or kept (PGDG source availability); getting this wrong breaks the `timescaledb+pgvector` combo, so it's an explicit spike checklist item.
