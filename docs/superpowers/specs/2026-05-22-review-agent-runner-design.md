# Layer-3 Review Agent Runner (Plan 7a) — Design Spec

**Date:** 2026-05-22
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** the generated-project CI pipeline (Plan 5a, the `review` job seam) and framework design spec §7 (the 15 AI review agents) + §20 (agent evals). This is the **first sub-project** of Plan 7; it establishes the execution mechanism the rest plug into.

---

## 1. Purpose & scope

Plan 7 (spec §7) is the Layer-3 "integration intelligence" layer: 15 AI review agents that run as GitHub Check Runs on PRs, with cross-agent interactions, an aggregator, and an eval harness. That is four subsystems sharing one execution mechanism. **Plan 7a builds only that mechanism, proven end-to-end with one agent** (`review-security`):

- a template-shipped Python runner that fetches the PR diff, calls the Anthropic Messages API with an agent's prompt, parses **structured JSON findings**, and posts a GitHub **Check Run** + inline annotations;
- one agent (`review-security`) defined against that contract;
- the generated `ci.yml` `review` job wired to run it (opt-in by the `ANTHROPIC_API_KEY` secret).

**Deferred to later sub-projects:** 7b — the other 14 agents + the always/battery/file-trigger/advisory triggering matrix; 7c — cross-agent interactions + the single-PR-comment aggregator; 7d — the eval harness (golden fixtures + threshold-based real-quality assertions, §20).

## 2. Decisions (settled in brainstorm)

- **Runner model:** a template-shipped Python runner calling the **Anthropic API directly** (not `claude-code-action`, not a third-party bot) — chosen for the structured-finding contract, unit-testable plumbing, per-agent model control, and prompt-caching the shared diff.
- **Findings are structured JSON**, parsed into a typed contract.
- **Testability split:** deterministic plumbing (parse → conclusion → annotations) is unit-tested with a **mocked** client; the LLM's review *quality* is the eval harness's job (7d), not 7a's unit tests.
- **Infra failure ≠ merge block:** API errors / malformed output / missing key → a `neutral` Check Run, never a CI hard-fail. Only findings at/above an agent's block-threshold produce `failure`.
- **`anthropic` is a CI-only dependency**, imported lazily so the modules + tests work without it installed.
- **Opt-in by secret:** the review job runs only when `ANTHROPIC_API_KEY` is present; absent → neutral skip.
- **Model default = Claude Sonnet**, per-agent overridable; the diff is a cached prompt prefix.

## 3. What ships (template payload — runs in the builder's CI, reviews the builder's PRs)

A `scripts/review/` package in the generated project:

- **`findings.py`** — the contract. `Finding(path: str, line: int, severity: Severity, message: str, suggestion: str | None)` where `Severity` is `Literal["critical","high","medium","low","info"]`. A `parse_findings(text) -> list[Finding]` tolerant of the model wrapping JSON in prose/code-fences (extracts the JSON array). No `anthropic` import.
- **`registry.py`** — `AgentSpec(name, prompt, block_threshold: Severity, active_when, model)` and a registry mapping agent name → spec (prompt text loaded from `agents/<name>.md`). 7a registers only `review-security`. No `anthropic` import.
- **`agents/security.md`** — the `review-security` system prompt: auth / injection / secrets / CVEs / OWASP Top 10; instructs the agent to review **only the diff**, cite real file + line, and return **JSON only** matching the `Finding` schema; `block_threshold = high`; `active_when = always`.
- **`runner.py`** — `run_agent(diff: str, spec: AgentSpec, client) -> list[Finding]`: builds the request (diff as a **cached prefix**, the agent prompt as the variable part), calls the API, returns parsed findings. The `client` is **injected** (tests pass a mock). `anthropic` is imported **lazily** only inside the default-client constructor used by `run.py`.
- **`github_checks.py`** — `to_check_run(spec, findings) -> CheckRun` mapping: `conclusion = "failure"` if any finding's severity ≥ `spec.block_threshold`, else `"neutral"` (no findings) / `"success"`; findings → inline annotations (`path`, `start_line`, `annotation_level`, `message`, optional suggestion). Posting uses the GitHub Checks API via `GITHUB_TOKEN`. No `anthropic` import.
- **`run.py`** — the CLI entrypoint the workflow calls: `python scripts/review/run.py <agent>`. Resolves the spec, computes the PR diff, constructs the real Anthropic client (lazy import) **unless `ANTHROPIC_API_KEY` is absent** (→ post a neutral "review skipped" Check Run, exit 0), runs the agent, posts the Check Run. Any execution error → neutral Check Run + exit 0 (infra failure never blocks).

## 4. The finding → Check Run contract

- An agent emits a JSON array of findings; each has a `severity`. Severity ordering: `critical > high > medium > low > info`.
- `block_threshold` (per agent) is the severity at/above which findings make the Check Run **fail**. `review-security` = `high` (blocks on high + critical; medium/low/info are advisory annotations on a neutral check).
- The Check Run's `output` lists every finding as an inline annotation regardless of severity; only the *conclusion* is gated by the threshold.
- **"Blocks merge" is enforced by the builder's branch protection**, not the framework — a failing Check Run only blocks if the repo requires it. The generated README/DEPLOY docs instruct the builder to require the `review-*` checks in branch protection.

## 5. CI wiring

The generated `ci.yml` `review` job (today an echo placeholder, `needs: [test, contract]`) becomes:
- a matrix over the active agents (7a: just `security`);
- permissions `checks: write`, `contents: read`, `pull-requests: read`;
- a checkout with enough history to diff against the PR base;
- a step `uv run --with anthropic python scripts/review/run.py ${{ matrix.agent }}` with env `ANTHROPIC_API_KEY` (secret) + `GITHUB_TOKEN`;
- `anthropic` is installed ad-hoc via `--with` (never added to the app's runtime deps).

On a PR the diff is `base...head`; on a push to `main` the §7 always-on agents diff the pushed range (7a wires the PR path; the push-to-main subset is refined in 7b alongside the triggering matrix).

## 6. Testing

- **Hermetic unit tests (no real API, no key):**
  - `parse_findings` — well-formed JSON, JSON inside code-fences/prose, malformed → raises a parse error the runner turns into neutral.
  - `to_check_run` — a `high` finding → `failure`; only `low`/`info` → `neutral`; no findings → `success`/`neutral`; every finding becomes an annotation.
  - `run_agent` with a **mocked client** returning canned JSON → expected `Finding`s.
  - `run.py` — `ANTHROPIC_API_KEY` absent → neutral "skipped" Check Run + exit 0; a mocked client error → neutral + exit 0 (never blocks).
  - `registry` — loads `review-security` with `block_threshold = high`, `active_when = always`, model set.
- **Render assertions:** the generated project ships `scripts/review/{findings,registry,runner,github_checks,run}.py` + `agents/security.md`; the `ci.yml` `review` job has the agent matrix, the `checks: write` permission, and the `ANTHROPIC_API_KEY` env.
- **Generated-project cleanliness:** the shipped `scripts/review/` must keep the freshly generated project's **first pre-commit pass green** (`test_rendered_project_precommit_runs_clean`). `mypy` is `src`-scoped so `scripts/` isn't type-checked; `ruff` checks `.` but doesn't resolve the lazy `anthropic` import. **Plan-time check (task 1):** confirm the generated project's pre-commit/mypy scope so the runner code is clean without `anthropic` installed; if any hook type-checks `scripts/`, keep the `anthropic` import lazy/guarded so it stays green.
- **Manual smoke (documented, not automated):** run `review-security` against a real diff with a key — the one thing unit tests can't cover. Real review *quality* is 7d's eval harness.

## 7. Self-review

- **Placeholders:** none — the runner modules, the finding/Check-Run contract, the one agent, the CI wiring, and the test set are all concrete. The one unknown (the generated project's pre-commit/mypy scope vs. `scripts/`) is an explicit plan-time check in §6, not a hand-wave.
- **Internal consistency:** the testability split (mock client in units, real quality in 7d) is consistent with "infra failure → neutral"; opt-in-by-secret + lazy `anthropic` import keep both the generated project's CI and the framework's own acceptance suite green without a key.
- **Scope:** one mechanism + one agent; the other 14 agents, interactions/aggregator, and evals are explicitly deferred to 7b/7c/7d.
- **Ambiguity:** "blocks merge" is explicitly the builder's branch-protection responsibility, not framework-enforced.

---

*End of design. Next step (when ready): `superpowers:writing-plans` for Plan 7a. Plan 7b/7c/7d get their own brainstorm → spec → plan cycles.*
