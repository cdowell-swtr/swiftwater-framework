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
| Configs dogfooded | **Two**: `baseline` + `all-batteries`. |
| Review-matrix secret | **Configurable, default no-key.** Default run → review jobs neutral; `--with-review-key` sets the repo secret for a deliberate paid full-path run. |
| Repo strategy | **One dedicated public repo** `swiftwater-dogfood` under `cdowell-swtr`, reset between the two configs. Public → free unlimited GHA minutes. |
| gitleaks | Runs free (personal account, no `GITLEAKS_LICENSE` needed) → expected `success`. |

## End-to-end flow

For each config in `[baseline, all-batteries]`, sequentially against the single repo `swiftwater-dogfood`:

1. **Render** the project to a temp dir with `_commit: v0.1.0` pinned in `.copier-answers.yml` so integrity step-0 installs the real published tag. (Baseline = no batteries; all-batteries = the full selectable battery set so the conditional `frontend`/`contracts`/graphql jobs are present.)
2. **Seed**: create `swiftwater-dogfood` (public) if it does not exist; force-reset `main` to the freshly rendered commit and push. **This push triggers `ci.yml` on `push: main`** → exercises the *push-path* job set (the §7 push-subset of review agents; no PR-only oasdiff/graphql steps).
3. **PR**: create a branch, apply a **benign no-op change** (a comment-only edit to a source file — produces a diff for the review agents while leaving `openapi.json` / `schema.graphql` byte-current, so the contract staleness check passes and oasdiff/graphql see a non-breaking diff), push the branch, open a PR. **This triggers `ci.yml` on `pull_request`** → exercises the *PR-path* superset (oasdiff, graphql breaking-change, the full review matrix + aggregator).
4. **Watch & assert** both the push-triggered run and the PR-triggered run (`gh run view --json jobs,conclusion,...`).
5. **Reset** for the next config: force-reset `main` to a clean state, close the PR, delete the branch.

This proves **both** the `on: push` and `on: pull_request` paths.

## Assertion model

Per run, each job is classified by its expected conclusion:

- **Expected `success`** — always-on: `integrity`, `lint`, `security` (gitleaks free on personal account), `test`, `build`, `contract`. Plus, when the config includes the battery: `frontend` (react), `contracts` (consumers/Pact).
- **Expected `neutral` / `skipped`** by default (no key): the `review` matrix jobs and `review-aggregate`. With `--with-review-key`, the harness sets the `ANTHROPIC_SWIFTWATER_DOGFOOD_CI_RUNTIME` repo secret (from the operator's local `ANTHROPIC_RUNTIME_API_KEY`) and these flip to **expected `success`**.

The harness **fails loudly** if any expected-`success` job is not green, or if any review job concluded `failure` (rather than the allowed neutral/skip). It prints the offending job name and a link to its GHA logs. Note the push run does not include the PR-only jobs (oasdiff/graphql breaking-change steps, full review matrix) — the expected-job set is **per-trigger** (push vs pull_request) as well as per-config.

## Module decomposition

Designed for isolation and a clean TDD boundary (pure logic tested hermetically; imperative shell exercised live).

- `scripts/dogfood_e2e/config.py` — the two `DogfoodConfig`s: battery list, the per-trigger expected job sets, and which jobs are secret-gated. Pure data + small helpers.
- `scripts/dogfood_e2e/verdict.py` — **pure** assertion logic: `(jobs_json, config, trigger, with_key) -> Verdict`. No I/O. Fully unit-tested against captured `gh run view --json` fixtures, including a neutral-review payload and a synthetic red-job payload.
- `scripts/dogfood_e2e/gh.py` — thin imperative shell over `gh` + `git` subprocess calls: render, ensure-repo, force-reset+push, open-PR, watch-run, set/clear repo secret, reset/cleanup. Not unit-tested; exercised by the live run.
- `scripts/dogfood_e2e.py` — the orchestrator: argument parsing, the per-config loop, scorecard emission.

## TDD boundary

The working agreement requires TDD. Network / `gh` orchestration cannot be hermetically tested, so the boundary is explicit:

- **Full TDD** for `config.py` + `verdict.py` (failing test first, against captured-fixture job payloads — neutral-review, all-green, and a synthetic red-job case; plus per-trigger expected-set computation). These tests run in the normal hermetic suite.
- The `gh.py` shell + orchestrator are validated by the **live run itself** — the harness *is* the test of the generated pipeline. The first green live run is recorded in a dated scorecard.

## Deliverables

- `scripts/dogfood_e2e.py` + the `scripts/dogfood_e2e/` package (`config.py`, `verdict.py`, `gh.py`).
- Hermetic unit tests for `verdict.py` / `config.py` (in the normal suite).
- A short runbook under `docs/` (or the scorecard README): prerequisites (`gh` auth with `repo` + `workflow` scopes; the `swiftwater-dogfood` repo; `v0.1.0` reachable on origin), how to run, the `--with-review-key` opt-in, and cost notes (free by default; paid only on the opt-in review run).
- The first dated green scorecard under `docs/superpowers/eval-scorecards/dogfood-e2e-<date>/` (run URLs + per-job conclusions for both configs, both triggers) — the proof-of-green artifact.
- Meta-plan status-table + CLAUDE.md Current State updates on merge.

## Risks / open edges

- **`v0.1.0` integrity match.** Integrity step-0 installs the framework at `v0.1.0` and runs `framework integrity --ci`. The rendered project's integrity manifest must match what the *installed `v0.1.0` CLI* expects. If the bundled template has drifted from `v0.1.0` since the tag, a fresh render at `HEAD` could mismatch. Mitigation: render with the `v0.1.0`-bundled template path, or accept that the first dogfood run validates exactly the `v0.1.0` contract and bump the pin when a newer tag ships. The plan resolves the exact render source as task 1.
- **GHA minutes / wall-clock.** All-batteries adds Playwright browser downloads + a Docker image build; runs can take many minutes. The harness polls with a generous timeout and surfaces the run URL so the operator can watch.
- **Benign-change correctness.** The PR's no-op edit must not perturb `openapi.json` / `schema.graphql` (else the contract staleness check fails for the wrong reason). A comment-only edit to a non-route Python file satisfies this; the plan pins the exact file/edit.
- **Secret hygiene.** `--with-review-key` reads `ANTHROPIC_RUNTIME_API_KEY` from the operator's env and sets it as a repo secret via `gh secret set` (never echoed). The harness does not print key material. The repo being public does not expose the secret (GitHub secrets are not readable from a public repo's logs/forks).
