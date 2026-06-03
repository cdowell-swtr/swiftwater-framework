# Dogfood E2E — running the generated-project pipeline on real GitHub Actions

Proves the shipped generated `.github/workflows/ci.yml` actually runs green on **real**
GitHub Actions (Plan 13) — the gap the Plan 10 render-matrix leaves open (it only runs each
generated project's local `task ci`, never executes the workflow on GHA). Operator-run; not
part of the hermetic test suite.

## What it exercises that nothing else does
The integrity step-0 job (installs the framework at the recorded `_commit` tag), the gitleaks
full-history scan, the PR-only OpenAPI/GraphQL breaking-change diffs, the `review-plan` →
`review` matrix → `review-aggregate` chain (and its neutral-on-no-key safety path), the
`contracts` (Pact) provider-verification job, the conditional `frontend` job, and the job-graph
`needs` wiring — across both the `on: push` and `on: pull_request` triggers.

## Prerequisites
- `gh` authenticated as `cdowell-swtr` with scopes `repo` + `workflow` (`gh auth status`).
- The framework tag in `framework_cli.dogfood.DOGFOOD_COMMIT` (currently `v0.1.2`) is pushed to
  origin and installable: `uv tool install "git+https://github.com/cdowell-swtr/swiftwater-framework@v0.1.2"`.
- Run from the repo root, on a branch whose template == the `DOGFOOD_COMMIT` tag's template (the
  generated integrity step-0 checks the rendered manifest against the installed tag's CLI).

## Run (default — free; review jobs post neutral Check Runs)
    uv run python scripts/dogfood_e2e.py

Renders the `baseline` + `all-batteries` projects, pushes each to the public repo
`cdowell-swtr/swiftwater-dogfood` (reset between configs), seeds `main` (an `on: push` run) and
opens a benign-no-op PR (an `on: pull_request` run), watches both runs, and asserts two surfaces:
- **Surface 1 — workflow jobs:** every expected job concluded `success`.
- **Surface 2 — review Check Runs:** the `review-*` checks are `neutral` (the no-key safety path).

It prints a scorecard and exits non-zero on any failure. Progress is logged with `[dogfood]`
lines (the run takes many minutes per config — Playwright + the image build dominate
all-batteries).

## Run (paid — full review path)
    ANTHROPIC_RUNTIME_API_KEY=sk-... uv run python scripts/dogfood_e2e.py --with-review-key

Sets the `ANTHROPIC_SWIFTWATER_DOGFOOD_CI_RUNTIME` repo secret so the review matrix + aggregator
do real work; the `review-*` checks then conclude `success`/`neutral` (a `failure` means an agent
flagged the benign README diff as blocking — surfaced as a warning to inspect, not a hard fail).
Costs paid Anthropic API (one call per active agent per config). The secret is cleared on the
next default run.

## Notes
- The dogfood repo is **reset, not deleted** (the `gh` token lacks `delete_repo`).
- All-batteries adds Playwright browser downloads + a Docker image build; expect long runs. The
  harness polls with a generous timeout and head-SHA-guards run selection (the repo is reused, so
  a stale prior-config run must not be mistaken for the current one).
- Record each green run's scorecard under `docs/superpowers/eval-scorecards/dogfood-e2e-<date>/`.
- If a job fails for an external/transient reason (e.g. a Docker Hub 5xx pulling testcontainers
  images), re-run — that is infra flake, not a generated-pipeline defect.
