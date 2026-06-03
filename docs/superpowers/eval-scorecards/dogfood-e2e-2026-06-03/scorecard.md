# Dogfood E2E scorecard — 2026-06-03

**Result: GREEN** ✅ — the generated `.github/workflows/ci.yml` runs green end-to-end on
**real GitHub Actions** for both the baseline and the maximal all-batteries configuration,
across both the `on: push` and `on: pull_request` triggers.

- **Framework tag dogfooded:** `v0.1.2`
- **Harness:** `scripts/dogfood_e2e.py` (default mode — no review key; review checks neutral)
- **Dogfood repo:** `cdowell-swtr/swiftwater-dogfood` (public, reset between configs)

| Config | review key | push run | PR run | result |
| --- | --- | --- | --- | --- |
| baseline | no (review→neutral) | [run](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26866052080) | [run](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26866145296) | ✅ green |
| all-batteries | no (review→neutral) | [run](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26866246481) | [run](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26866410580) | ✅ green |

`all-batteries` = `age, consumers, graphql, mongodb, pgvector, react, redis, timescaledb,
webhooks, websockets, workers`.

## What this proves (the gap Plan 10's render-matrix left open)

The render-matrix runs each generated project's local `task ci`. This dogfood runs the
shipped `ci.yml` on real GHA, exercising the runtime-only components nothing else did:

- **integrity step-0** — installs the framework CLI at the recorded `_commit` (`v0.1.2`) and
  runs `framework integrity --ci` (green).
- **gitleaks** full-history secret scan (with `GITHUB_TOKEN`).
- **contract** — OpenAPI export + staleness; on PR, oasdiff breaking-change; for graphql, the
  SDL staleness + `graphql-core` breaking-change.
- **review-plan → review matrix → review-aggregate** — the dynamic matrix expands, each agent
  posts a `review-<agent>` Check Run (neutral with no key — verified on the PR **merge** commit),
  and the aggregator runs. (14 agents baseline, 18 all-batteries.)
- **contracts** — Pact provider verification (first ever green run on GHA).
- **frontend** — Vite build + Playwright/axe e2e (first ever green run on GHA).
- the job-graph `needs` wiring and both the `on: push` and `on: pull_request` trigger paths.

## Real generated-project defects this dogfood found + fixed

The dogfood earned its keep before it ever went green — it surfaced **six** real defects that
the framework's own 700-test suite and the render-matrix never caught (because the render-matrix
runs `task ci`, not the shipped `ci.yml`):

1. **workers DLQ functional test stale vs DLQ-PII redact-by-default** — `record_failure()` missing
   the required `redacted=` kwarg; `dlq_traceback` redacts the message. (Merged as `v0.1.2`.)
2. **gitleaks `GITHUB_TOKEN` missing** — gitleaks-action v2 now requires it to scan PRs; every
   generated project's PR `security` job was broken.
3. **all-batteries `tests/conftest.py` not ruff-format-clean** — the `shared_preload_libraries=
   timescaledb,age` one-liner exceeded the line limit; `task ci` runs `ruff check` but not
   `ruff format --check` (only `ci.yml` does).
4. **react `ci.yml` frontend job shellcheck SC2034** — `for i in $(seq …)` unused loop var.
5. **non-deterministic `openapi.json`/`schema.graphql` for graphql projects** — `export-openapi.sh`
   captured a `graphql_ide_configured` structlog line (with a timestamp) into the committed spec
   via the stdout redirect → the staleness check always failed.
6. **custom Postgres image build flaky on packagecloud** — the timescaledb apt install
   intermittently failed; hardened with `apt-get -o Acquire::Retries` + `wget --tries`.

Plus a noted **follow-up**: a fresh `framework new` project is **not push-ready** out of the box
(no committed `uv.lock`/`openapi.json`/`schema.graphql`, which the Dockerfile + 5 `ci.yml` jobs
require). The harness replicates the documented builder pre-push setup (`prepare_project`: `uv
sync` + the export scripts); whether `framework new` should auto-generate these is a future slice.

And two **harness-fidelity** gaps fixed (so the harness faithfully mirrors a real builder):
missing `write_manifest` (the integrity lock); and the review Check Runs are named `review-<agent>`
and attach to the PR **merge** commit (`GITHUB_SHA`), not the head.

## How to reproduce

`uv run python scripts/dogfood_e2e.py` (see `docs/dogfood-e2e.md`). Default is free; add
`--with-review-key` for the paid full review path.
