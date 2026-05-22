# Layer-3 Review Agent Runner (Plan 7a) — Design Spec

**Date:** 2026-05-22
**Status:** Approved (brainstorm); revised at plan-writing time — the runner lives in the installed CLI (`framework review`), not template payload (see §2/§3).
**Builds on:** the generated-project CI pipeline (Plan 5a, the `review` job seam), Plan 6a (`framework integrity` — the installed-CLI-owned check pattern), Plan 6b (the CLI is installed in CI via `uv tool install git+<repo>@<_commit>`), and framework design spec §7 (the 15 AI review agents) + §20 (agent evals). First sub-project of Plan 7; establishes the execution mechanism the rest plug into.

---

## 1. Purpose & scope

Plan 7 (spec §7) is the Layer-3 layer: 15 AI review agents that run as GitHub Check Runs on PRs, with cross-agent interactions, an aggregator, and an eval harness — four subsystems sharing one execution mechanism. **Plan 7a builds only that mechanism, proven end-to-end with one agent** (`review-security`):

- a **`framework review <agent>` CLI subcommand** that fetches the PR diff, calls the Anthropic Messages API with an agent's prompt, parses **structured JSON findings**, and posts a GitHub **Check Run** + inline annotations;
- one agent (`review-security`) defined against that contract;
- the generated `ci.yml` `review` job wired to install the framework (the Plan 6b mechanism) and run `framework review security` (opt-in by the `ANTHROPIC_API_KEY` secret).

**Deferred to later sub-projects:** 7b — the other 14 agents + the always/battery/file-trigger/advisory triggering matrix; 7c — cross-agent interactions + the single-PR-comment aggregator; 7d — the eval harness (golden fixtures + threshold-based real-quality assertions, §20).

## 2. Decisions (settled in brainstorm + the plan-writing revision)

- **Runner home — the installed CLI (`framework review`), not template payload.** Discovered at plan-writing time: template-payload Python isn't cleanly framework-testable, and per-project prompt files would need copier-merging on `upskill`. Putting the runner + prompts in the CLI (like `framework integrity`, §17) makes it normally testable, versions the prompts with the framework (so `upskill` updates them with no per-project merge), keeps it framework-owned (builders can't disable it), and reuses Plan 6b's CI install. The generated project ships only the thin `ci.yml` review-job change.
- **LLM = Anthropic API directly** (not `claude-code-action`, not a third-party bot) — for the structured-finding contract, unit-testable plumbing, per-agent model control, and prompt-caching the shared diff.
- **`anthropic` is a CLI dependency**, imported **lazily** (so the review modules import + unit-test without constructing a real client, and `framework`'s other commands don't load it).
- **Findings are structured JSON**, parsed into a typed contract.
- **Testability split:** deterministic plumbing (parse → conclusion → annotations) is unit-tested with a **mocked** client; the LLM's review *quality* is the eval harness's job (7d), not 7a's unit tests.
- **Infra failure ≠ merge block:** API errors / malformed output / missing key → a `neutral` Check Run, never a CI hard-fail. Only findings at/above an agent's block-threshold produce `failure`.
- **Opt-in by secret:** `framework review` posts a neutral "skipped" Check Run (exit 0) when `ANTHROPIC_API_KEY` is absent.
- **Model default = Claude Sonnet**, per-agent overridable; the diff is a cached prompt prefix.

## 3. What gets built

**Framework source — `src/framework_cli/review/`:**
- **`findings.py`** — the contract. `Finding(path: str, line: int, severity: Severity, message: str, suggestion: str | None)`, `Severity = Literal["critical","high","medium","low","info"]`, and `parse_findings(text) -> list[Finding]` tolerant of the model wrapping the JSON array in prose/code-fences (raises a `FindingsParseError` on genuinely unparseable output). No `anthropic` import.
- **`registry.py`** — `AgentSpec(name, prompt, block_threshold: Severity, active_when, model)` + a registry mapping agent name → spec (prompt text loaded from `agents/<name>.md`, packaged with the CLI). 7a registers only `review-security`. No `anthropic` import.
- **`agents/security.md`** — the `review-security` system prompt: auth / injection / secrets / CVEs / OWASP Top 10; review **only the diff**, cite real file + line, return **JSON only** matching the `Finding` schema; `block_threshold = high`; `active_when = always`.
- **`runner.py`** — `run_agent(diff: str, spec: AgentSpec, client) -> list[Finding]`: builds the request (diff as a **cached prefix**, agent prompt as the variable part), calls the API, returns parsed findings. The `client` is **injected** (tests pass a mock); a `default_client()` helper constructs the real Anthropic client with a **lazy** `import anthropic`.
- **`checks.py`** — `to_check_run(spec, findings) -> CheckRunPayload`: `conclusion="failure"` if any finding's severity ≥ `spec.block_threshold`, else `"neutral"` (no findings) / `"success"`; findings → inline annotations (`path`, `start_line`, `annotation_level`, `message`, optional suggestion). Plus `post_check_run(payload, token, repo, sha)` via the GitHub Checks API. No `anthropic` import.
- **`diff.py`** — `pr_diff()` computes the diff to review from the CI environment (`GITHUB_BASE_REF`/`GITHUB_SHA` → `git diff`), with a size cap. Pure git/subprocess; injectable for tests.

**CLI — `src/framework_cli/cli.py`:** a `review(agent: str)` Typer command — resolve the spec; if `ANTHROPIC_API_KEY` is absent → post a neutral "skipped" Check Run + exit 0; else compute the diff, `run_agent`, `to_check_run`, `post_check_run`; any execution error → neutral Check Run + exit 0 (infra failure never blocks). Mirrors the `integrity` command's shape.

**Dependencies — `pyproject.toml`:** add `anthropic` to `[project] dependencies` (imported lazily).

**Template payload — `src/framework_cli/template/.github/workflows/ci.yml.jinja`:** the `review` job (today an echo placeholder, `needs: [test, contract]`) installs the framework at the recorded `_commit` (the Plan 6b pattern) and runs `framework review security`, with `checks: write`/`contents: read`/`pull-requests: read` permissions and `ANTHROPIC_API_KEY` + `GITHUB_TOKEN` env. Nothing else ships into the project.

## 4. The finding → Check Run contract

- An agent emits a JSON array of findings; each has a `severity` (`critical > high > medium > low > info`).
- `block_threshold` (per agent) is the severity at/above which findings make the Check Run **fail**. `review-security` = `high`.
- The Check Run `output` lists every finding as an inline annotation; only the *conclusion* is gated by the threshold.
- **"Blocks merge" is the builder's branch protection**, not the framework — a failing Check Run only blocks if the repo requires it. The generated README/DEPLOY docs instruct the builder to require the `review-*` checks.

## 5. CI wiring

The generated `ci.yml` `review` job becomes (mirroring the Plan 6b integrity job):
- `needs: [test, contract]`; permissions `checks: write`, `contents: read`, `pull-requests: read`;
- checkout with enough history to diff the PR base;
- install the framework: `ref="$(awk '/^_commit:/ {print $2}' .copier-answers.yml)"; uv tool install "git+https://github.com/cdowell-swtr/swiftwater-framework@${ref}"`;
- run `framework review security` with env `ANTHROPIC_API_KEY` (secret) + `GITHUB_TOKEN`.

7a wires the PR path; the §7 push-to-main subset is refined in 7b alongside the triggering matrix. (7a uses a single `security` step; the agent **matrix** lands in 7b with the full set.)

## 6. Testing

- **Hermetic framework unit tests (no real API, no key) — `tests/review/`:**
  - `parse_findings` — well-formed JSON; JSON inside code-fences/prose; unparseable → `FindingsParseError`.
  - `to_check_run` — a `high` finding → `failure`; only `low`/`info` → `neutral`; no findings → `success`/`neutral`; every finding → an annotation.
  - `run_agent` with a **mocked client** returning canned JSON → expected `Finding`s.
  - the `review` CLI command (via `CliRunner`) — `ANTHROPIC_API_KEY` absent → neutral "skipped" + exit 0; a mocked client/posting error → neutral + exit 0 (never blocks). Posting is stubbed (no real GitHub call).
  - `registry` — loads `review-security` with `block_threshold = high`, `active_when = always`, model set.
- **Render assertion (`tests/test_copier_runner.py`):** the generated `ci.yml` `review` job installs the framework and runs `framework review security` with `checks: write` + `ANTHROPIC_API_KEY`.
- **Generated-project cleanliness:** the only project change is `ci.yml`, so the acceptance suite (`test_rendered_project_precommit_runs_clean`) stays green by construction — no `scripts/review/` payload to keep lint-clean, and the runner is never imported by the generated project.
- **Manual smoke (documented, not automated):** `framework review security` against a real diff with a key — the one thing unit tests can't cover. Real review *quality* is 7d's eval harness.

## 7. Self-review

- **Placeholders:** none — the modules, the finding/Check-Run contract, the one agent, the CLI command, the CI wiring, and the test set are concrete. The earlier "pre-commit/mypy scope" unknown is **resolved** by moving the runner into the CLI (framework source, normally tested); the generated project gains only the `ci.yml` change.
- **Internal consistency:** the testability split (mock client in units, real quality in 7d) is consistent with "infra failure → neutral"; opt-in-by-secret + lazy `anthropic` import keep both the generated project's CI and the framework's own tests green without a key.
- **Scope:** one mechanism + one agent; the other 14 agents, interactions/aggregator, and evals are deferred to 7b/7c/7d. The CLI-subcommand home matches the framework's "logic lives in the installed CLI" principle (§17) and reuses Plan 6b's CI install.
- **Ambiguity:** "blocks merge" is explicitly the builder's branch-protection responsibility.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 7a. 7b/7c/7d get their own brainstorm → spec → plan cycles.*
