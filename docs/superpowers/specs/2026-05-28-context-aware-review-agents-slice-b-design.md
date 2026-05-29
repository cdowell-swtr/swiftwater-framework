# Context-aware review agents — Slice B (agentic tier) design

**Date:** 2026-05-28
**Status:** Approved (brainstorm).
**Parent design:** `docs/superpowers/specs/2026-05-28-context-aware-review-agents-design.md` (§7 Slice B).
**Builds on:** Slice A (the target-agnostic context spine — `ContextPolicy`/`Bundle`/`ReviewTarget`/`assemble`/`run_agent`/`realize_fixture`), merged to `master` (FF `1c051cd`).

## 1. Problem

Slice A migrated the 11 static-`bundle`-tier agents. The remaining **7 agents must follow references across the repo** — a bounded glob subtree can't satisfy them:

- **architecture** (module/dependency graph), **data-lineage** (cross-file data flow), **privacy** (data-flow tracing) — trace from a changed file outward.
- **api-design** (a contract can match while the both-ends usage is wrong → must see consumers), **contracts** (Pact: consumer client + provider in different files), **observability-infra** (infra obs correctness depends on the app's instrumentation + topology), **observability-db** (db problems surface in *app* files, not just the data layer).

These stay on `strategy="diff"` after Slice A. Slice B gives them an **agentic** strategy: a tool-using loop that explores the project tree on demand.

## 2. Goals / non-goals

**Goals**
- An agentic execution path: a Messages-API tool-use loop with custom, read-only, root-confined file-exploration tools (`read_file`, `grep`, `glob`).
- A predictable budget: turn cap + graceful finalize + per-result truncation; per-agent override.
- Flip the 7 agents to `strategy="agentic"`.
- Keep the machinery **target-agnostic** (the only target-specific artifact remains `ReviewTarget`) and fully **hermetically testable** (no API key).

**Non-goals**
- Rendered-project fixtures for the 7 agents + real-key scoring → **Slice D** (the 7 keep their legacy `.diff` fixtures meanwhile, so the coverage gate stays green).
- Prompt rewrites, template-payload changes, eval-harness scoring-loop changes.
- Incremental prompt-caching of growing tool-result turns (noted future optimization).

## 3. Architecture & integration

A new focused module `src/framework_cli/review/agentic.py`:

```python
def run_agent_agentic(
    diff: str, root: Path, spec: AgentSpec, client: Any, *, max_turns: int
) -> list[Finding]: ...
```

Target-blind — it takes `root`/`diff`, never target identity. `run_agent` (Slice A) stays the single-call diff/bundle path, untouched.

**CLI dispatch** (`cli.py` `_review_run`/`_eval_run`, which already hold the root): branch on `spec.context.strategy` — `"agentic"` → `run_agent_agentic(diff, root, spec, client, max_turns=...)`; otherwise the existing `assemble` + `run_agent`. (No `assemble` for agentic — it already returns a diff-only bundle, so we skip straight to the loop.) The target-agnostic invariant from Slice A holds: only `ReviewTarget` differs per target.

The default turn cap is a module constant (e.g. `_DEFAULT_MAX_TURNS = 12`); `spec.context.max_agentic_turns` overrides it when set.

## 4. Tools (custom, in-process, read-only, root-confined)

Defined in `agentic.py`, executed against `root`:

- **`read_file(path)`** → file contents, truncated to a cap (~50 KB / ~400 lines, whichever first), with a truncation marker.
- **`grep(pattern, path_glob=None)`** → up to ~100 `relpath:line: text` matches; pure-Python `re` over files under `root` (optionally filtered by `path_glob` via `root.glob`); a capped/over-limit result is marked truncated.
- **`glob(pattern)`** → up to ~200 matching relative paths under `root`.

**Safety:** every `path`/`pattern` resolves against `root`; a path that escapes `root` (via `..` or an absolute path) is rejected. No shell. A tool error (missing file, invalid regex, escape attempt) returns an **error string** as the `tool_result` (the model adapts) — it never raises into the loop. Binary/undecodable files read with `errors="replace"`.

Tool JSON schemas are passed in the Messages `tools` param (not the system blocks).

## 5. The loop

1. **Seed message:** system = a cached diff block (`{"type":"text","text":"Review this unified diff:\n\n"+diff,"cache_control":{"type":"ephemeral"}}`) + the agent prompt block; `tools=[read_file, grep, glob]`; an initial user message instructing exploration + "return findings as a JSON array when done".
2. **Loop:** the model emits `tool_use` block(s) → execute each against `root` → append an assistant turn (the tool_use) and a user turn (the `tool_result`s) → call again. Continue while the response `stop_reason == "tool_use"`.
3. **Termination (normal):** the model returns a final message with no tool calls → `parse_findings` on its text.
4. **Termination (budget):** when `max_turns` tool-use rounds have elapsed, send one final user message — "return your findings now as a JSON array; do not request more tools" — with `tools` omitted/none, and `parse_findings` the reply. Guarantees a findings list (partial signal preserved).

`_MAX_TOKENS = 4096` per call (as in `run_agent`). The diff is a cached prefix; growing tool-result turns are uncached (incremental caching deferred).

## 6. Registry / policy

- Add `max_agentic_turns: int | None = None` to `ContextPolicy` (registry.py).
- Flip the 7 agents to `ContextPolicy("agentic")` (no globs needed; optional `max_agentic_turns` for a heavier explorer like `architecture`).
- The `test_agentspec_context_defaults_to_diff` invariant gains a parallel assertion: the 7 listed agents are `"agentic"`, the 11 are `"bundle"`, and **no agent remains `"diff"`** (every agent now has an explicit strategy).

## 7. Error handling

- Tool failures → error string in the `tool_result`; loop continues.
- Budget exhausted → finalize step → parse.
- A `parse_findings` failure or an SDK exception **propagates** to the CLI's existing `try/except`, which already maps it to a neutral check-run in production and a non-detection in eval — behavior unchanged from Slice A. The loop never raises on tool execution.

## 8. Testing (all hermetic — no API key)

A `_FakeClient` whose `messages.create` returns a scripted sequence of tool-use / final responses (mirroring the Slice A runner-test fake).

- **Tools** (against a real rendered baseline project via `realize_fixture`):
  - `read_file` returns real contents; truncates a large file with a marker.
  - `grep` finds real matches as `relpath:line: text`; caps hits.
  - `glob` lists real paths under root; caps.
  - **Confinement:** `read_file("../../etc/passwd")`, an absolute path, and a `..`-escaping glob are each rejected with an error string (no read outside `root`).
- **Loop:** a fake client scripted to request `glob` then `read_file` then return findings JSON → assert the tools executed against the tree, results were fed back, and `parse_findings` produced the expected findings.
- **Budget:** a fake client that *always* requests a tool → assert the loop stops at `max_turns`, issues the finalize message (tools omitted), and still returns parsed findings; assert `spec.context.max_agentic_turns` overrides the default.
- **Registry:** the 7 are `"agentic"`; the ledger invariant updated (no agent left `"diff"`).
- **Full gate** green; ruff/format/mypy clean; no template-payload or prompt changes.

## 9. Components / files

- `src/framework_cli/review/agentic.py` (new) — tools (`read_file`/`grep`/`glob` + their JSON schemas + a `_resolve_within_root` guard), `run_agent_agentic`, the loop, `_DEFAULT_MAX_TURNS`.
- `src/framework_cli/review/registry.py` (modify) — `ContextPolicy.max_agentic_turns`; flip the 7 agents to `"agentic"`.
- `src/framework_cli/cli.py` (modify) — `_review_run`/`_eval_run` dispatch on `strategy == "agentic"`.
- `tests/review/test_agentic.py` (new) — tools, loop, budget, confinement (hermetic).
- `tests/review/test_context_policy.py` (modify) — agentic-tier ledger assertion.

## 10. Risks

- **Runaway cost/latency** — bounded by the turn cap + per-result truncation + the 4096 output cap; the finalize step guarantees termination. Real cost is observed in Slice D scoring.
- **Tool-surface safety** — read-only + root-confinement + no shell; covered by confinement tests.
- **Non-determinism** — inherent to agentic review; Slice B tests the *machinery* deterministically (fake client); real recall/precision is a Slice D concern.
- **The 7 agents are not end-to-end exercised until Slice D** — same posture as Slice A's bundle agents (machinery proven hermetically; real scoring deferred). Accepted.
