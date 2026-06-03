# Plan 13 — Generated-project end-to-end CI on real GitHub Actions (dogfood e2e)

**Date:** 2026-06-02
**Status:** Design — approved, pending spec review
**Plan:** 13 (meta-plan `docs/superpowers/plans/2026-05-20-meta-plan.md`, row 13)
**Depends on:** Plan 10 (render-matrix + `release.yml`), Plan 11 (review-runtime path + scoped keys), the published `v0.1.0` tag.

## Problem

The Plan 10 render-matrix runs each generated project's local `task ci` pre-flight (integrity + lint+actionlint + 85% coverage gate + pip-audit + openapi export). That *statically* validates the generated `.github/workflows/ci.yml` (actionlint) but **never executes it on real GitHub Actions**. Whole classes of runtime-only behavior are therefore unproven end-to-end:

- the **integrity step-0 job** — installs the framework CLI from the recorded `_commit` git tag (`uv tool install "git+https://github.com/cdowell-swtr/swiftwater-framework@<tag>"`) and runs `framework integrity --ci`;
- the **gitleaks** full-history secret scan;
- the PR-only **OpenAPI (oasdiff)** and **GraphQL (`graphql-core.find_breaking_changes`)** breaking-change contract diffs;
- the **`review-plan` → `review` matrix → `review-aggregate`** job chain (dynamic matrix from `framework review-agents`, per-agent Check Runs, sticky-comment aggregator);
- the **`contracts` (Pact) provider-verification** job (`tests/contract/` sits outside `testpaths`, so local `task ci` skips it);
- the conditional **`frontend`** job (react battery: `npm ci`/lint/typecheck/Vitest, then build + Playwright/axe e2e);
- the job-graph `needs` wiring and the `on: push` vs `on: pull_request` trigger split.

Spec §20 deliberately scoped dogfooding to "the generated project's own `task ci` passes green" — which Plan 10 satisfies. Plan 13 is the end-to-end *pipeline* extension on top of that: prove the shipped `ci.yml` actually runs green on GitHub Actions.

## Non-goals (YAGNI)

- A scheduled / `workflow_dispatch` GHA wrapper that runs the harness in the cloud (the rejected "GHA-tests-GHA" Option B). The harness logic lives in a script first; a thin wrapper can be added later if drift-detection automation is wanted.
- Throwaway-repo-per-run with `delete_repo` teardown — the current `gh` token lacks `delete_repo`; we use one dedicated repo that is reset between runs.
- Any per-commit / suite-integrated automation. This is an **operator-run** harness by nature (needs network + `gh` auth + GHA minutes, and optionally paid API), so it cannot be an ordinary hermetic pytest.

## Approach (chosen)

An **operator-run harness** in the framework repo — not shipped to generated projects, so deliberately **not** a `framework` CLI subcommand. A Python orchestrator with a thin `gh`/git subprocess shell, invoked from this dev box:

```
uv run python scripts/dogfood_e2e.py [--with-review-key]
```

It reuses the framework's own render path to generate projects and the `gh` CLI for all GitHub interaction. Modeled in spirit on the 5c-2 dind deploy e2e harness (operator-run, asserts real external behavior, records a dated scorecard) — but it talks to real GitHub Actions instead of Docker-in-Docker.

### Decisions locked during brainstorming

| Decision | Choice |
|---|---|
| Deliverable form | Operator-run harness + dated scorecard (Option A). |
| Configs dogfooded | **Two**: `baseline` + `all-batteries` (maximal: react + consumers + graphql + workers + webhooks + websockets + the db-paradigm batteries). |
| Review-matrix secret | **Configurable, default no-key.** Default run → review jobs neutral; `--with-review-key` sets the repo secret for a deliberate paid full-path run. |
| Repo strategy | **One dedicated public repo** `swiftwater-dogfood` under `cdowell-swtr`, reset between the two configs. Public → free unlimited GHA minutes. |
| gitleaks | Runs free (personal account, no `GITLEAKS_LICENSE` needed) → expected `success`. |
| Release tag | **Cut & push `v0.1.1` first** (plan task 0): push current `master` to origin, tag `v0.1.1`, push the tag (`release.yml` publishes it). Harness pins `_commit: v0.1.1` so it dogfoods the *current* template — a green run proves today's code. |

## End-to-end flow

For each config in `[baseline, all-batteries]`, sequentially against the single repo `swiftwater-dogfood`:

1. **Render** the project to a temp dir with `_commit: v0.1.0` pinned in `.copier-answers.yml` so integrity step-0 installs the real published tag. (Baseline = no batteries; all-batteries = the full selectable battery set so the conditional `frontend`/`contracts`/graphql jobs are present.)
2. **Seed**: create `swiftwater-dogfood` (public) if it does not exist; force-reset `main` to the freshly rendered commit and push. **This push triggers `ci.yml` on `push: main`** → exercises the *push-path* job set (the §7 push-subset of review agents; no PR-only oasdiff/graphql steps).
3. **PR**: create a branch, apply a **benign no-op change** (a comment-only edit to a source file — produces a diff for the review agents while leaving `openapi.json` / `schema.graphql` byte-current, so the contract staleness check passes and oasdiff/graphql see a non-breaking diff), push the branch, open a PR. **This triggers `ci.yml` on `pull_request`** → exercises the *PR-path* superset (oasdiff, graphql breaking-change, the full review matrix + aggregator).
4. **Watch & assert** both the push-triggered run and the PR-triggered run (`gh run view --json jobs,conclusion,...`).
5. **Reset** for the next config: force-reset `main` to a clean state, close the PR, delete the branch.

This proves **both** the `on: push` and `on: pull_request` paths.

## Assertion model

The "neutral" the review path produces lives in the **GitHub Check Runs**, *not* the workflow-job conclusions. Verified in `cli.py::review`: with no key the command posts a **neutral Check Run** but `raise typer.Exit(0)`, so the workflow **job** concludes `success`; with a key and blocking findings it `Exit(1)` → job `failure`. So the harness asserts on **two surfaces**:

**Surface 1 — workflow jobs** (`gh run view --json jobs`): every expected job is **present and `success`**.
- Always-on: `integrity`, `lint`, `security` (gitleaks free on a personal account), `test`, `build`, `contract`, `review-plan`, the `review (<agent>)` matrix jobs, `review-aggregate`.
- Conditional (all-batteries only): `frontend` (react), `contracts` (consumers/Pact).
- Any expected job missing, or any job not `success`, → **fail loudly** (print job name + GHA log URL).

**Surface 2 — review Check Runs** (`gh api .../commits/<sha>/check-runs` or `gh pr checks`): the `review-*` checks prove the secret-gated behavior.
- **Default (no key):** every `review-*` check is **`neutral`** (the graceful no-key path). A `failure` here is a real regression of that path → fail loudly.
- **`--with-review-key`:** the harness sets the `ANTHROPIC_SWIFTWATER_DOGFOOD_CI_RUNTIME` repo secret from the operator's local `ANTHROPIC_RUNTIME_API_KEY`; the `review-*` checks are then `success` or `neutral` (no blocking findings expected on a benign README diff). A `failure` means an agent flagged the benign change as blocking — surfaced as a warning for the operator to inspect, not a harness hard-fail.

Both the push-triggered run and the PR-triggered run are watched and asserted (surface 1 on both; surface 2 on the PR run, where the full matrix + posted checks live). The PR-only oasdiff/graphql breaking-change logic lives in *steps inside* the `contract` job (guarded `if: github.event_name == 'pull_request'`), so it is exercised by the PR run without adding a distinct job name.

## Module decomposition

Refines the brainstorm's `scripts/dogfood_e2e/{config,verdict,gh}.py` layout: the **pure** logic lives in `src/framework_cli/dogfood.py` (following the `devmatrix.py` precedent — framework-internal dogfooding logic that lives in the CLI package and therefore gets the repo's mypy/ruff/pytest rigor), and the **imperative** orchestrator + `gh`/git shell live in `scripts/dogfood_e2e.py`. Clean TDD boundary: pure logic tested hermetically in the normal suite; the shell exercised by the live run.

- `src/framework_cli/dogfood.py` — **pure, fully unit-tested:**
  - `DogfoodConfig` (battery list + the expected workflow-job set incl. conditionals) and the two instances `BASELINE` + `ALL_BATTERIES`.
  - `parse_jobs(gh_run_json) -> list[Job]` and `parse_checks(gh_checks_json) -> list[CheckRun]` — normalize the `gh ... --json` payloads.
  - `classify_jobs(jobs, config) -> JobVerdict` — surface 1: every expected job present + `success`.
  - `classify_review_checks(checks, with_key) -> CheckVerdict` — surface 2: `review-*` checks neutral (no key) / success-or-neutral (with key).
  - `render_scorecard(results) -> str` — the dated-scorecard markdown.
  - `Verdict`/`JobVerdict`/`CheckVerdict` dataclasses (`ok: bool`, `failures: list[str]`, `warnings: list[str]`).
- `scripts/dogfood_e2e.py` — the imperative orchestrator + thin `gh`/git shell: argument parsing, render (`render_project` + `record_portable_source(dest, "0.1.1")`), ensure-repo, force-reset+push, open benign-no-op PR, watch both runs, fetch jobs + check-runs JSON, set/clear the review secret, reset/cleanup, and write the scorecard. Pure helpers (argv construction, the benign-edit) get light unit tests; the network I/O is exercised by the live run.

## TDD boundary

The working agreement requires TDD. Network / `gh` orchestration cannot be hermetically tested, so the boundary is explicit:

- **Full TDD** for `framework_cli/dogfood.py` (failing test first, against captured-fixture `gh` payloads — all-green jobs, a synthetic red-job, neutral-review checks, with-key success checks, and a missing-expected-job case). These tests run in the normal hermetic suite (`tests/test_dogfood.py`) and are covered by the repo's mypy/ruff gates.
- The `scripts/dogfood_e2e.py` shell + orchestrator are validated by the **live run itself** — the harness *is* the test of the generated pipeline. The first green live run is recorded in a dated scorecard.

## Deliverables

- `src/framework_cli/dogfood.py` (pure logic) + `scripts/dogfood_e2e.py` (orchestrator + `gh`/git shell).
- Hermetic unit tests `tests/test_dogfood.py` (in the normal suite).
- A short runbook under `docs/` (or the scorecard README): prerequisites (`gh` auth with `repo` + `workflow` scopes; the `swiftwater-dogfood` repo; `v0.1.0` reachable on origin), how to run, the `--with-review-key` opt-in, and cost notes (free by default; paid only on the opt-in review run).
- The first dated green scorecard under `docs/superpowers/eval-scorecards/dogfood-e2e-<date>/` (run URLs + per-job conclusions for both configs, both triggers) — the proof-of-green artifact.
- Meta-plan status-table + CLAUDE.md Current State updates on merge.

## Risks / open edges

- **Integrity tag match (resolved).** Integrity step-0 installs the framework at the recorded `_commit` tag and runs `framework integrity --ci`; the rendered manifest must match what the *installed* CLI expects. Resolved by **plan task 0**: push current `master` to origin and cut+push **`v0.1.1`** so the installed CLI and the rendered template are the same code — the harness renders at `HEAD` and pins `_commit: v0.1.1`. A green run therefore proves today's template (covers Plan 12), not a stale tag.
- **GHA minutes / wall-clock.** All-batteries adds Playwright browser downloads + a Docker image build; runs can take many minutes. The harness polls with a generous timeout and surfaces the run URL so the operator can watch.
- **Benign-change correctness.** The PR's no-op edit must not perturb `openapi.json` / `schema.graphql` (else the contract staleness check fails for the wrong reason). A comment-only edit to a non-route Python file satisfies this; the plan pins the exact file/edit.
- **Secret hygiene.** `--with-review-key` reads `ANTHROPIC_RUNTIME_API_KEY` from the operator's env and sets it as a repo secret via `gh secret set` (never echoed). The harness does not print key material. The repo being public does not expose the secret (GitHub secrets are not readable from a public repo's logs/forks).
