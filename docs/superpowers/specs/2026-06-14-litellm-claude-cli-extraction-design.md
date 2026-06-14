# `litellm-claude-cli` Extraction — Design

> Design spec for **FWK11**: extract the in-tree `claude -p` LiteLLM provider into a
> standalone, git-tag-distributed package that both the framework and generated
> projects depend on. Status: approved (brainstorming, 2026-06-14).
> Follows the Plan 27 / FWK5 foundation (the provider was built extraction-ready).

## Context & goal

FWK5 re-homed the subscription `claude -p` path as an in-process LiteLLM `CustomLLM`
living at `src/framework_cli/review/litellm_provider.py` — deliberately built with
**zero `framework_cli` imports** so it could be lifted out later. FWK11 lifts it.

**Goal:** publish the provider as a small standalone package
(`cdowell-swtr/litellm-claude-cli`) so it has a single, versioned source of truth
that the framework depends on **and** generated projects can install via the future
`--with HotSwapAgents` battery (FWK13). Fixes flow through one version bump rather
than being duplicated across the framework and every scaffolded project.

**Settled decisions (brainstorming):** external package (not template-payload
duplication); **git-tag** distribution (no PyPI); the **framework depends on it**
(deletes its in-tree copy); HotSwapAgents (FWK13, out of scope here) ships it to
projects.

## §1 — Package identity & shape

- A **new minimal library repo**, hand-rolled (NOT a `framework new` scaffold — the
  framework template is app-shaped: FastAPI, docker, observability, migrations;
  overkill for a ~350-line single-module provider).
- Repo `cdowell-swtr/litellm-claude-cli`; import package `litellm_claude_cli`
  (src-layout: `src/litellm_claude_cli/__init__.py`). Name reads as exactly what it
  is — a litellm provider backed by the `claude` CLI subscription — and follows the
  informal `litellm-<provider>` convention.
- Held to the **framework's own quality bar**: `ruff` + `ruff format` + `mypy` +
  `pytest`, GitHub Actions pinned to the Node-24-capable versions the framework
  mandates. No framework-specific tiers (render-matrix, review-agents, docker).
- **Scope discipline:** contains *only* the provider — `ClaudeCliLLM`,
  `ClaudeExhausted`, `register()`, and the private render/parse helpers — and keeps
  its zero-`framework_cli`-imports property. No framework concepts leak in.

## §2 — Registration & public contract

Public names: `ClaudeCliLLM` (the `CustomLLM`, runner-injectable), `ClaudeExhausted`,
`register()`. Registration works at two levels:

- **Auto-registration via a litellm entry point (the elegant goal):** the package
  declares a `pyproject` entry point so that merely *installing* it makes litellm
  discover the `claude-cli` provider — no consumer code. Ideal UX for HotSwapAgents.
- **Explicit `register()` + runner injection (the guaranteed path):** `register()`
  registers a default real-subprocess handler; `ClaudeCliLLM(runner=…)` injects a
  fake runner for tests. The **framework keeps doing explicit registration** in its
  `backend.py` seam (it must, to bind a fake runner in tests), so framework
  correctness never depends on the entry point.

**Entry-point support is unverified** — it traces to a litellm PR (#15881); whether
it shipped in **1.88.1** (the framework's pinned version) is unknown. It is therefore
a **go/no-go spike (plan Task 1)**, exactly like FWK5's `anthropic_messages` gate:

- **GO** → consumers get auto-registration for free; document it.
- **NO-GO** → the package still ships `register()`; HotSwapAgents (FWK13) wires a
  one-line `register()` call into the generated project's app startup.

Either way the package's public API and the framework's behavior are unchanged — the
spike only decides whether *consumers* get auto-registration or call `register()`.

## §3 — What moves, and the framework cutover

- **Moves to the package repo:** the provider module
  (`src/framework_cli/review/litellm_provider.py` → `src/litellm_claude_cli/__init__.py`)
  and its unit tests (`tests/review/test_litellm_provider.py` → the package's `tests/`).
- **Stays in the framework:** `backend.py` (the seam); its two imports change source
  to `from litellm_claude_cli import ClaudeCliLLM, ClaudeExhausted`. The framework
  keeps the tests that exercise *its use* of the package — the seam exhaustion test
  in `test_backend.py`, the S2 routing guard (`test_litellm_spike.py`), and the live
  smoke. The in-tree module is **deleted** (full reliance).
- **New framework dependency:**
  `litellm-claude-cli @ git+https://github.com/cdowell-swtr/litellm-claude-cli@v0.1.0`,
  then `uv lock`.

**Two-repo sequencing (FWK11 is not a single-repo change):**

1. **Stand up the package repo first** — extract code + tests, add `pyproject`/CI,
   cut a **real `v0.1.0` tag** (the framework can't depend on a git-tag that does not
   exist — same lesson as scaffolding from a real tag, not a branch HEAD).
2. **Then flip the framework** — add the git-tag dep, delete the in-tree module,
   repoint the imports, adjust tests, `uv lock`, confirm gate + render stay green.

For developing the two together before the tag exists, use a uv local-path source
override (`[tool.uv.sources]` → local package checkout), then swap to the
`git+…@v0.1.0` pin for the committed framework change — never blocked on the tag
during development, but the merged framework depends on the real release.

## §4 — Release & CI on the new repo

- **Lean CI:** `pytest` + `ruff check` + `ruff format --check` + `mypy`, on push/PR,
  Node-24-pinned actions; none of the framework-specific machinery.
- **Release = a lightweight `vX.Y.Z` git tag**, semver, no PyPI. Bumping the plugin:
  tag the package repo → bump the framework's `@vX.Y.Z` pin + `uv lock`. Infrequent.
- **Branch protection: light** — a required `CI` check on `master` so a red lib can't
  land, but not the framework's heavyweight ruleset.

## §5 — Testing strategy (three layers)

1. **Unit** — call `ClaudeCliLLM.completion()` and the render/parse helpers directly
   with a fake runner. Fast; covers the `claude -p` mechanics, the `MAX_ARG_STRLEN`
   argv guard, exhaustion→`ClaudeExhausted`, OpenAI-shape→claude-text rendering.
   (Bypasses litellm by design — internals only.)
2. **litellm-dispatch integration (the critical layer):** register the *real*
   `ClaudeCliLLM(runner=fake)` in `custom_provider_map`, drive
   `litellm.anthropic_messages(model="claude-cli/<model>", …)`, and assert the
   round-trip — litellm dispatches to our handler, hands it the right shape, our
   `ModelResponse` returns as a well-formed `AnthropicMessagesResponse` (dict
   content/usage/stop_reason matching the fake runner's output). **Fully offline**
   (fake subprocess, no network/key/real `claude`), so it runs on **every** CI push.
   This proves the provider actually plugs into litellm — without it the unit tests
   could all pass while dispatch is silently broken. Subsumes FWK5's S2 probe, but
   stronger (real provider, not a trivial `_Probe`).
3. **Live smoke (gated)** — the real `claude` CLI end-to-end, opt-in
   (`RUN_LIVE_SMOKE`-style), for the genuine subscription path. The package owns the
   `claude -p` mechanics now, so it carries this independently.

Plus the **entry-point spike (§2)** as a kept test with an integration variant:
register via the entry point (not manual `custom_provider_map`) and confirm dispatch
— proving auto-registration is wired, or recording NO-GO.

**Framework-side acceptance (phase 2):** after the dependency swap, the framework's
seam tests + live smoke + the full gate/render must stay green with
`litellm-claude-cli` installed as a git dep. The framework's live smoke now
transitively exercises the *installed* package — the integration we want covered.

## Risks & open questions

- **Entry-point support in litellm 1.88.1** — unverified; gated by the Task-1 spike
  (§2). NO-GO degrades to a one-line explicit `register()` for consumers, not a
  redesign.
- **Git-dependency in CI / consumer `pyproject`** — both the framework's CI and (via
  FWK13) generated projects fetch the package from GitHub. Acceptable given the
  repo's gh-centric posture, but it makes GitHub availability a hard dependency of
  the framework's review path (already effectively true).
- **History preservation** — the ~350-line module can be copied into the fresh repo
  (history not load-bearing) or `git filter`-extracted; copy is simplest. Decide at
  plan time; not architecturally significant.

## Out of scope

- **FWK12** (`--with Agents` battery, plain LiteLLM) and **FWK13**
  (`--with HotSwapAgents`, which adds *this* package as a generated-project
  dependency). Those consume the package this spec produces.
- Any change to the framework's review behavior — FWK11 is a pure extraction +
  dependency swap; behavior is unchanged and proven by the unchanged seam tests.
