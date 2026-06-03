# Plan 15 T4 — dogfood acceptance (2026-06-03)

**Verdict: GREEN.** The live dogfood proved the COPY-from-`-ha` timescaledb path (Part A)
and the oasdiff `base_has_openapi` gate (Part B) on real GitHub Actions, with **no
packagecloud flake**. This is the builder-side acceptance proof for Plan 15.

## What ran

`uv run python scripts/dogfood_e2e.py` (working-tree template, `_commit` pinned to `v0.1.5`
for the integrity step-0). Both configs, each on `push` (→ main) and `pull_request` (→ benign
no-op PR); both surfaces asserted (every workflow job `success`; `review-*` Check Runs neutral
without a key). Repo torn down on green.

| Config | batteries | push run | PR run | result |
| --- | --- | --- | --- | --- |
| baseline | 0 | [26900792587](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26900792587) | [26900931542](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26900931542) | ✅ green |
| all-batteries | 11 (incl. timescaledb + pgvector + age) | [26901086113](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26901086113) | [26901426539](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26901426539) | ✅ green |

## Why this proves Part A

The all-batteries config builds the custom Postgres image (`infra/docker/postgres.Dockerfile`)
in the `test` job's testcontainers path. That image now `COPY --from=timescale/timescaledb-ha:pg17.10-ts2.27.1`
the timescaledb extension instead of the old `packagecloud.io` apt — and the run went green
**first try, no re-run**, so the flaky build-time packagecloud dependency is gone for real
builders. All three extensions (timescaledb, pgvector, age) load on the unchanged `postgres:17`
base (glibc-safe COPY; validated end-to-end in the T1 spike + this CI build).

## Part B (oasdiff gate)

Behavioral validation is out of scope per the spec (a "commit-the-spec" dogfood scenario was
not added — the gate logic is small and content-tested). The dogfood PRs don't commit
`openapi.json`, so oasdiff stays gated off (`openapi_tracked == 'false'`) as before; the new
`base_has_openapi` probe is the additional guard for the first-spec-committing PR.

## Render-matrix-on-master (framework-side proof)

Folded into T5: the FF merge to `master` triggers `render-matrix.yml` (and the `v0.1.6`
`release.yml` re-runs the matrix). A green matrix **without a flaky-combo re-run** is the
framework-side confirmation — recorded at T5 to avoid a redundant pre-merge branch-dispatch run
of the ~19-combo matrix.

## Op notes

- `scripts/dogfood_e2e.py` must run via **`uv run python`** (bare `python3` lacks `copier`);
  the docstring's "run from the repo root" is now "run via `uv run` from the repo root."
