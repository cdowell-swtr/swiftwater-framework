# Full Review Agent Set + Triggering Matrix (Plan 7b) — Design Spec

**Date:** 2026-05-22
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 7a (the `framework review <agent>` runner: `findings`/`registry`/`runner`/`checks`/`diff`, the Check-Run contract, the generated `ci.yml` review job). Realizes the rest of framework design spec §7 (the agent matrix + triggering). Second sub-project of Plan 7.

---

## 1. Purpose & scope

Plan 7a shipped the runner + one agent (`review-security`). 7b adds **the remaining "always" agents + the file-trigger agent + the triggering matrix** so the generated CI runs the full §7 review set in parallel, with the right agents on PRs vs. pushes to `main`.

**In scope — 11 new agents + the matrix mechanism:**
- The 10 "always" agents: `data-integrity`, `data-lineage`, `application-logic`, `observability`, `test-quality`, `architecture`, `performance`, `compliance`, `privacy`, `documentation`.
- The 1 file-trigger agent: `dependency` (runs only when dependency files change).
- The triggering matrix: a `framework review-agents` command + a dynamic CI matrix; the §7 push-to-main subset; the file-trigger self-skip; advisory (never-block) agents.

**Out of scope (deferred):**
- The 3 **battery-gated** agents — `api-design` (REST/GraphQL), `accessibility` + `usability` (React) — to **Plan 8**, where batteries and battery-detection exist to gate them.
- Cross-agent interactions + the aggregator → **Plan 7c**.
- The eval harness / real-quality assertions → **Plan 7d**. (7b's tests remain hermetic, mocked-client; real review quality is 7d's job.)

## 2. Decisions (settled in brainstorm)

- **Agent set:** 10 always + `dependency`; the 3 battery agents deferred to Plan 8 (they can only be gated by batteries that don't yet exist).
- **CI execution:** a parallel GitHub **matrix** (per §7 "agents run in parallel"), populated by a `framework review-agents` command (the registry is the single source of truth — no agent list duplicated in the workflow).
- **File-trigger** handled **inside** the agent run (the `dependency` agent self-skips → neutral when no dependency file changed), not by varying the matrix.
- **Advisory agents** (`documentation`, `dependency`) never block (`block_threshold = None`).

## 3. Registry extensions (`registry.py`)

`AgentSpec` gains three fields:
- `block_threshold: Severity | None` — severity at/above which findings fail the check; **`None` = advisory** (annotate only, never `failure`).
- `on_push: bool = False` — `True` marks the §7 push-to-main subset.
- `trigger_globs: tuple[str, ...] | None = None` — for file-trigger agents; the agent self-skips (neutral) when no changed file matches any glob.

**The agent set** (each is an `agents/<name>.md` prompt following the 7a `security.md` pattern — review the diff only, cite real file+line, return strict JSON `Finding`s — plus a registry entry):

| Agent | name | block_threshold | active_when | on_push | trigger_globs |
|---|---|---|---|---|---|
| security (7a; set `on_push=True`) | review-security | `high` | always | ✓ | — |
| data-integrity | review-data-integrity | `info` (any blocks) | always | ✓ | — |
| data-lineage | review-data-lineage | `high` | always | ✓ | — |
| application-logic | review-application-logic | `info` (any blocks) | always | — | — |
| observability | review-observability | `high` | always | ✓ | — |
| test-quality | review-test-quality | `high` | always | — | — |
| architecture | review-architecture | `high` | always | — | — |
| performance | review-performance | `high` | always | — | — |
| compliance | review-compliance | `high` | always | — | — |
| privacy | review-privacy | `high` | always | — | — |
| documentation | review-documentation | `None` (advisory) | always | — | — |
| dependency | review-dependency | `None` (advisory) | file-trigger | — | `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json` |

`block_threshold = "info"` means *any* finding blocks (rank ≥ info), matching §7's "Any finding" for data-integrity and application-logic. Each prompt instructs the agent to assign severities so the threshold maps to §7's blocking intent (e.g. observability marks an untraced new code path `high`).

**`active_agents(event: str) -> list[str]`:** `event == "pull_request"` → all agents whose `active_when` is `always` or `file-trigger` (battery excluded); `event == "push"` → agents with `on_push == True` (security, data-integrity, data-lineage, observability). Returns sorted names.

## 4. The `review-agents` command & file-trigger

- **`framework review-agents [--event <event>]`** (new CLI command): prints a JSON array of `active_agents(event)`; `event` defaults from `GITHUB_EVENT_NAME`. The CI matrix consumes it via `fromJSON`.
- **`diff.changed_files(diff: str) -> list[str]`** (new): parses the unified diff's `+++ b/<path>` lines into changed paths (pure string parse — testable).
- **File-trigger in `framework review <agent>`:** if the agent has `trigger_globs`, compute `changed_files(pr_diff())`; if **none** match any glob → post a neutral "not triggered (no <kind> files changed)" Check Run and **skip the LLM call** (exit 0). Otherwise proceed as in 7a.
- **`to_check_run` (checks.py) advisory tweak:** when `spec.block_threshold is None`, the conclusion is `success` (no findings) or `neutral` (findings present) — never `failure`. (The 7a severity-threshold path is unchanged for non-None thresholds.)

## 5. CI wiring (`ci.yml.jinja`)

Replace the single `review-security` step with two jobs:
- **`review-plan`** — installs the framework at the recorded `_commit` (the 6b pattern), runs `framework review-agents` (event-aware), and exposes the JSON array as a job output `agents`.
- **`review`** — `needs: [test, contract, review-plan]`; `strategy.matrix.agent: {% raw %}${{ fromJSON(needs.review-plan.outputs.agents) }}{% endraw %}`; `permissions: {contents: read, checks: write, pull-requests: read}`; each matrix job checks out (full history), installs the framework, and runs `framework review {% raw %}${{ matrix.agent }}{% endraw %}` with `ANTHROPIC_API_KEY` + `GITHUB_TOKEN`. Opt-in by the secret carries over from 7a (each agent neutral-skips without it).

The "blocks merge = builder branch protection" guidance (7a) extends to all `review-*` checks.

## 6. Testing (all hermetic — mocked client, no API key, no network)

- **`registry`:** `active_agents("pull_request")` = the 11 expected names (sorted, no battery); `active_agents("push")` = the 4 subset; a parametrized test over `agent_names()` asserting each agent's prompt loads, is non-empty, and instructs JSON output; the per-agent `block_threshold`/`on_push`/`trigger_globs` values match this spec.
- **`review-agents` command:** `--event pull_request` → JSON of 11; `--event push` → JSON of 4.
- **`diff.changed_files`:** parses `+++ b/<path>` lines (incl. renames/additions) into paths.
- **file-trigger:** `framework review dependency` with a diff touching no dependency file → neutral "not triggered", **no client call** (monkeypatched seam asserts the runner wasn't invoked); with `pyproject.toml` in the diff → proceeds (mocked client).
- **advisory `to_check_run`:** `block_threshold=None` + a `high` finding → `neutral` (not `failure`); + no findings → `success`.
- **CI render (`tests/test_copier_runner.py`):** the rendered `ci.yml` has a `review-plan` job running `framework review-agents` with an `agents` output, and a `review` job whose matrix is `fromJSON(needs.review-plan.outputs.agents)` running `framework review`.
- **Generated-project cleanliness:** only `ci.yml` changes ship into projects (the agents/runner are framework source), so the acceptance suite stays green by construction.

## 7. Self-review

- **Placeholders:** none — the agent set, per-agent config, the matrix mechanism, the command, and the tests are concrete. The 3 battery agents are explicitly deferred (Plan 8), not hand-waved.
- **Internal consistency:** the file-trigger self-skip lives in the agent run (not the matrix), consistent with "the registry is the single source of truth for the matrix"; advisory (`None` threshold) composes with 7a's `to_check_run` via one guarded branch.
- **Scope:** one cohesive subsystem (the full always-set + file-trigger + matrix); battery agents, interactions/aggregator, and evals deferred to 8/7c/7d.
- **Ambiguity:** "Any finding blocks" (data-integrity, application-logic) is made concrete as `block_threshold="info"`; advisory as `None`; the push subset is the explicit `on_push` set.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 7b.*
