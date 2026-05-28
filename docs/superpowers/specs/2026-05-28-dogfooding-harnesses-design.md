# Plan 10 — Dogfooding: the Harnesses (§20 Self-Quality) — Design

**Date:** 2026-05-28
**Status:** Design (brainstormed, pending plan)
**Spec source:** `docs/superpowers/specs/2026-05-20-framework-design.md` §20 (Framework Self-Quality)
**Roadmap:** `docs/superpowers/plans/2026-05-20-meta-plan.md` row 10

---

## 1. Purpose

The framework imposes TDD, linting, CI, quality gates, and a render-then-validate
discipline on generated projects. §20 requires it to hold itself to the same standard: the
framework repository is itself a project with these gates. This slice builds the framework's
**own CI** so it eats its own dog food end to end.

Concretely, after this slice the framework repo's GitHub Actions runs, on the right triggers:

- a **fast tier** — lint, format-check, type-check, the CLI/unit/render/upskill/integrity
  suite, lock-check, and a wheel build;
- a **template render matrix** — render real projects across battery combinations and run
  each rendered project's own gate, with coverage that grows over time;
- the **agent evals** (already authored) — scored on a schedule and on agent changes;
- **release automation** — a tagged commit cuts a GitHub Release only if everything is green.

It also ships a builder-facing **`SECRETS.md`** in the template, codifying the secret-naming
convention the harness's own CI uses.

This is dogfooding, not a new product surface: the framework's workflow files live at the
repo root and are **not template payload**. The only template change is adding `SECRETS.md`.

## 2. Context and prerequisites

### 2.1 Dev-environment parity (already done, 2026-05-28)

Before this design, the sandbox could not run the react frontend toolchain or BuildKit image
builds — not a fundamental limit, just two missing tools. Both are now installed (env-level,
not in the repo):

- native **Linux Node 22** in `~/.local/bin` (shadows the broken Windows `npm` that was on
  PATH via `/mnt/c/...`);
- **`docker buildx` v0.34.1** in `~/.docker/cli-plugins/`.

So `framework new --with react` → `npm ci`/`tsc`/`vitest`/`vite build` and the multi-stage
image build now run locally. This parity is what lets us design and validate the render matrix
without flying blind until GitHub Actions. (Re-installing on a fresh machine: see the meta-plan
Environment Notes.)

That first local react render immediately surfaced two real react-battery defects, fixed in a
standalone commit (`2a0589f`) ahead of this slice: a broken production build (missing
`@types/node`) and Vitest collecting the Playwright `e2e/**` specs. The render matrix's react
job is the automated regression gate that prevents their recurrence.

### 2.2 What already exists

- The framework test suite already contains everything the harness needs to *run*: CLI tests,
  ~191 render tests (`test_copier_runner.py`), upskill/integrity/downskill/batteries/wizard/obs
  tests — ~485 fast tests plus a Docker-gated `tests/acceptance/` tier.
- `.github/workflows/agent-evals.yml` already exists at the repo root, correctly wired
  (`ANTHROPIC_FRAMEWORK_CI_EVAL` secret → `ANTHROPIC_API_KEY` env, `--require-key`).
- `RELEASING.md` documents the manual release procedure and the invariant
  (tag `vX.Y.Z` == `pyproject` version == the bundled template at that commit).
- The framework repo currently has **no main CI workflow** — only `agent-evals.yml`.

### 2.3 Out of scope

- Real-key *scoring* of the review agents (incl. `review-contracts`,
  `review-observability-infra`, `review-observability-db`) and threshold tuning — that is
  **Plan 11**; this slice only ensures `agent-evals.yml` is correctly triggered and documented.
- The full GitHub Actions confirmation of the react Playwright/axe e2e and end-to-end image
  build on `ubuntu-latest` — **Plan 11** (this slice builds the matrix that runs them).
- PyPI publication — distribution stays git-tags-only.

## 3. Design overview

Five components, one plan, built subagent-driven (a task per component, each TDD where code is
involved). The render matrix is the substantial piece.

```
repo root (NOT template payload):
  .github/workflows/
    ci.yml            # §4  fast tier — PR + push
    render-matrix.yml # §5  render real projects per combo, run their gates
    release.yml       # §7  tag-triggered GitHub Release + invariant guard
    agent-evals.yml   # §6  (exists) verify triggers + document the secret
  src/framework_cli/
    devmatrix.py      # §5  combo-generator (representative / pairwise / sample)
    cli.py            # §5  `framework dev-combos` subcommand (emits matrix JSON)

template payload (the one rendered change):
  src/framework_cli/template/SECRETS.md.jinja   # §8
```

## 4. Component 1 — Framework `ci.yml` (the fast tier)

A new repo-root `.github/workflows/ci.yml`, on `pull_request` and `push` to `master`:

1. `actions/checkout@v4`, `astral-sh/setup-uv@v5`
2. `uv sync`
3. `uv run ruff check .`
4. `uv run ruff format --check .`
5. `uv run mypy src`
6. `uv run pytest -q --ignore=tests/acceptance` (the ~485 fast tests)
7. `uv lock --check`
8. `uv build`

This mirrors the project's own quality gate (CLAUDE.md) plus the release-shape checks
(`uv lock --check`, `uv build`). It deliberately **excludes** the Docker-gated
`tests/acceptance/` tier — heavy render validation is the render matrix's job (§5), so the
fast tier stays a quick signal on every change. `ubuntu-latest` provides Docker, but the fast
tier does not need it.

## 5. Component 2 — Template render matrix (`render-matrix.yml`)

The most safety-critical asset is the template: a bad conditional silently breaks every new
project of a given battery combination. The render matrix renders real projects and runs each
one's own gate.

### 5.1 Mechanism — GHA `strategy.matrix` per combo, dynamically generated

A two-job workflow:

**Job `generate-matrix`** runs the combo-generator and sets a JSON output:

```yaml
jobs:
  generate-matrix:
    runs-on: ubuntu-latest
    outputs:
      combos: ${{ steps.gen.outputs.combos }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - id: gen
        run: echo "combos=$(uv run framework dev-combos --strategy "$STRATEGY" --seed "$SEED")" >> "$GITHUB_OUTPUT"
        env:
          STRATEGY: ${{ github.event_name == 'pull_request' && 'representative' || 'broad' }}
          SEED: ${{ github.run_number }}
```

**Job `render`** fans out over that JSON, one parallel job per combo, `fail-fast: false`:

```yaml
  render:
    needs: generate-matrix
    strategy:
      fail-fast: false
      matrix:
        combo: ${{ fromJSON(needs.generate-matrix.outputs.combos) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      # react combos only:
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
        if: contains(matrix.combo.batteries, 'react')
      - run: uv sync
      - run: uv tool install .            # install the framework CLI
      - run: framework new demo ${{ matrix.combo.with_flags }}
      - run: uv sync
        working-directory: demo
      - run: framework integrity --ci
        working-directory: demo
      - run: task ci
        working-directory: demo
      # react: frontend gate (+ image build on the broad tier — see 5.4)
```

Each matrix entry is an object `{ name, batteries: [...], with_flags: "--with a --with b ...",
alerts: "..." }` so steps can both render and conditionally enable Node.

This is the **real builder path** (`framework new`), which is truer dogfooding than calling
`render_project()` from a test. The existing `tests/acceptance/` pytest suite stays as the
**local, assertion-rich depth tier** (asserts specific battery files/behaviors); the matrix is
the **CI breadth mechanism**. Running each rendered project's own `task ci` + `framework
integrity --ci` is the per-combo correctness signal.

### 5.2 Triggers — change-driven, not clock-driven

- **`pull_request`** → the fixed **representative** set. Deterministic, fast feedback on every
  PR.
- **`push` to `master`** → the **broad** set (§5.3). The template just changed; verify breadth.
- **`schedule` (weekly) + `workflow_dispatch`** → the broad set as a **backstop**. Its job is
  to catch **external drift** in anything we depend on (transitive deps, GitHub Actions, Docker
  base images, the Anthropic API) when our own code is quiet. A new random seed each run means
  the schedule also expands cumulative coverage rather than re-running an identical list.

We deliberately do **not** call this "nightly": the render matrix's content only changes when
the template changes, so the broad set is anchored to `push`-to-master, with the schedule as a
drift backstop — not a clock for its own sake.

### 5.3 Coverage strategy — pairwise floor + random rotation

The configuration space is the **2^11 = 2,048 subsets** of the eleven batteries (websockets,
webhooks, workers, graphql, react, consumers, pgvector, mongodb, timescaledb, age, redis), times
alert-channel/python variants. Battery selection is order-independent — `--with workers --with
redis` renders byte-identically to the reverse, and migration ordering is computed from
*presence* via the canonical `MIGRATION_ORDER`, not flag order — so it is subsets, not
orderings. 2,048 is far too many to run exhaustively.

The **broad** set therefore combines two techniques:

- **Pairwise (all-pairs) floor — always run.** A generated set in which *every pair* of
  batteries appears together in at least one combo, achievable in roughly a dozen jobs. Most
  interaction bugs are 2-way, so this guarantees the high-value interaction coverage on every
  broad run, deterministically.
- **Seeded random rotation — added each broad run.** A pseudo-random sample of N additional
  combos, seeded by the run number. Over many broad runs the *union* of tested combos grows and
  asymptotically approaches the whole space, and explores higher-order (3+-way) combinations the
  pairwise floor does not.

The **representative** set (PR tier) is a small fixed, hand-picked list chosen for fast,
legible feedback and to exercise the known interaction classes:

| combo | what it exercises |
|-------|-------------------|
| `baseline` (no batteries) | the always-on relational spine, no-op conditionals |
| `webhooks + workers` | battery composition + the `0001→0002→0003` migration chain |
| `graphql + react` | API surface + the frontend/Node toolchain job |
| `mongodb + pgvector` | separate-service + extension DB paradigms (+ their obs) |
| `workers + redis` | the shared redis service gate |
| `full` (all batteries + all alert channels) | maximal conditional interaction |

### 5.4 The react / frontend job

A combo containing `react` adds `actions/setup-node@v4` (Node 22, matching the template pins)
and runs the frontend gate the generated project's Python `task ci` does not cover:
`npm ci` → `npm run lint` → `npm run typecheck` → `npm test` → `npm run build`. This is the
automated regression gate for the §2.1 defects. The heavy **BuildKit multi-stage image build**
(the `frontend-build` stage) runs only on the **broad** tier (push/schedule), not on every PR,
to bound PR cost. (`docker buildx` is available on `ubuntu-latest`.)

### 5.5 The combo-generator (`framework dev-combos`)

A small framework-internal module `src/framework_cli/devmatrix.py` plus a `framework dev-combos`
CLI subcommand. It is **framework tooling, not template payload**, and it is **unit-tested**
(TDD):

- `--strategy representative` → the fixed list in §5.3.
- `--strategy pairwise` → a generated all-pairs set (a greedy all-pairs algorithm is
  sufficient).
- `--strategy sample --seed N` → the pairwise floor plus a seeded random sample.
- `--strategy broad --seed N` → pairwise + sample (what the broad tier uses).

Output is the matrix JSON consumed by `fromJSON`. Each combo carries its `--with` flags and any
`--alerts` value. Tests assert: every battery pair appears in the pairwise output; the same seed
yields the same sample (determinism); every emitted combo is valid (resolvable batteries); the
representative set is exactly the documented list.

## 6. Component 3 — agent-evals (already authored)

`agent-evals.yml` exists and is correctly wired. This slice:

- verifies the triggers (weekly schedule + on changes to agent prompts / review logic / eval
  fixtures) are still correct after the agents added since (`review-contracts`,
  `review-observability-infra`, `review-observability-db`);
- documents the `ANTHROPIC_FRAMEWORK_CI_EVAL` secret (in the framework repo and, for the
  builder-facing analogue, in `SECRETS.md`).

The real-key scoring run and threshold tuning are **Plan 11**.

## 7. Component 4 — Release automation (`release.yml`)

Tag-triggered (`on: push: tags: ['v*']`):

1. **Invariant guard** — assert the tag equals the `pyproject` version (the `RELEASING.md`
   invariant). Fail loudly on mismatch so a misnamed tag never ships.
2. **Green gate** — run the full gate and the render matrix on the tagged commit. *The template
   is never released unless rendered projects are green* (§20). Reuse the existing workflows via
   `workflow_call` where practical rather than duplicating steps.
3. **Build** — `uv build` the wheel.
4. **Release** — create a GitHub Release for the tag with generated notes and the wheel
   attached.

Distribution stays git-tag-based (`uv tool install git+<repo>@vX.Y.Z`); no PyPI. `RELEASING.md`
is updated to note that the release is now automated on tag push (the human step is bump +
tag).

## 8. Component 5 — `SECRETS.md` (template payload)

A new `SECRETS.md.jinja` at the template root, alongside `DEPLOY.md.jinja` / `SERVICES.md.jinja`
/ `README.md.jinja`. It is the targeted, builder-facing secrets doc (the comprehensive
cross-cutting home for conventions is the Plan 12 docs pack, which this cross-links to).

Contents:

- **The two-tier secret-naming convention.** A full *descriptive label* in the provider console
  (`<service>_<package>_<owner>_<env>_<host>_<scope>_<created>_<rand>`, e.g.
  `anthropic_acme_jane_ci_gha_eval_20260601_3f8d0c1e`) for audit/rotation, mapped to a stable
  *boring name* where the secret is consumed (the env var locally; a GH-legal secret name in
  Actions, mapped into the boring env var the consumer reads).
- **The secrets a generated project uses**, each with its descriptive-label shape, its GH secret
  name, and the env var it maps to: the review-agents Anthropic key (e.g.
  `ANTHROPIC_<APP>_CI_RUNTIME` → `ANTHROPIC_API_KEY`), `GITLEAKS_LICENSE`, deploy/GHCR
  credentials, and the per-channel alert secrets from 8f-w (`slack_api_url_file` /
  `smtp_auth_password_file` / `routing_key_file`).
- A note on the framework's *own* CI secret `ANTHROPIC_FRAMEWORK_CI_EVAL`, documented for
  builders as the worked example of the convention.

### 8.1 File class and the manifest shift

Adding any rendered file changes every project's render, so this is a **deliberate one-time
baseline manifest shift** (precedented by OBS-PROD / SVC-PROD / 8f-w). `SECRETS.md`'s integrity
class is a plan-time sub-decision: a plain **rendered** doc (builders extend their own secrets
list freely) is the default; a **hybrid** file (a framework-owned `FRAMEWORK:BEGIN/END` section
for the convention + a builder-owned remainder) is the alternative if we want the convention
text tamper-evident. `LOCKED` is unlikely — builders need to add their project's secrets.

## 9. Testing strategy

- **Combo-generator** (`devmatrix.py`): unit tests for all-pairs coverage, seed determinism,
  combo validity, and the exact representative set (TDD; pure logic, fast).
- **Workflows**: extend `tests/test_workflows.py` to assert the new repo-root workflows exist,
  have the intended triggers, and reference the generator correctly. Where feasible, validate
  YAML with `actionlint` (already a pre-commit hook in generated projects; usable here too).
- **`SECRETS.md`**: a render assertion (the file renders and interpolates; managed section
  checksums if hybrid) and the baseline manifest re-generation; integrity green with the new
  file present.
- **Local validation**: with parity (§2.1), run a representative render-matrix combo locally
  (`framework new --with <combo>` → its gate) before relying on CI, including a `--with react`
  combo through the frontend gate.
- The full framework gate stays green: `ruff` / `ruff format --check` / `mypy src` /
  `pytest` / `uv lock --check` / `uv build`.

## 10. Risks and mitigations

- **CI cost of the broad matrix.** ~12 pairwise + N sample (+ the react image build) per master
  push is many parallel jobs. Mitigated by `fail-fast: false` (isolate failures), keeping the
  PR tier small and fixed, and bounding N. N is a tunable plan-time sub-decision.
- **`uv tool install .` vs editable install in CI.** The matrix must install the framework CLI
  so `framework new` is on PATH; confirm the install step renders from the *working-tree*
  template (not a published tag) so a PR's template changes are what gets tested.
- **Dynamic-matrix JSON shape.** GHA `fromJSON` into `strategy.matrix` requires a top-level JSON
  array; the generator must emit exactly that. Covered by a generator unit test plus a first
  live run.
- **Manifest shift churn.** Existing projects pick up `SECRETS.md` on `framework upskill`; this
  is the accepted, precedented one-time cost.

## 11. Plan-time sub-decisions (non-blocking)

- `SECRETS.md` file class (rendered vs hybrid).
- Random-sample size N for the broad tier.
- The exact pairwise generation (greedy all-pairs is acceptable).
- Whether `release.yml` reuses `ci.yml` / `render-matrix.yml` via `workflow_call` or inlines a
  trimmed gate.

## 12. Success criteria

- Framework `ci.yml` runs the fast gate green on PR and push.
- `render-matrix.yml` renders the representative set green on PR and the broad set (pairwise +
  rotating sample) on push/schedule, with the react job exercising the frontend toolchain.
- The combo-generator is unit-tested (all-pairs, determinism, validity).
- `release.yml` cuts a GitHub Release on a `vX.Y.Z` tag only when the gate + matrix are green,
  and refuses a tag/version mismatch.
- Generated projects ship `SECRETS.md`; integrity is green with it present; the one-time
  baseline manifest shift is recorded.
- The framework's own quality gate stays green throughout.
```
