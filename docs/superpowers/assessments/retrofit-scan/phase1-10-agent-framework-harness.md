# Phase 1 Retrofit Scan — Agent-Framework / Harness Retrofit

**Agent:** `agent-framework-harness`
**Date:** 2026-06-22
**Area:** What an AI-agent harness must bake in early — durable state, tool-loop tracing, tool permissioning, cost governance, prompt/eval management, structured-output enforcement, HITL, idempotency.

## What the framework ships today (baseline read of the code)

I read the actual battery payload before researching so every seam below is measured against what *exists*, not a strawman:

- **`llm` battery** (`template/src/{{package_name}}/llm/`): a stateless `LLMService` wrapping LiteLLM. Profiles (`profiles.py`: provider/model/temp/max_tokens, default→named→per-call override). Token/cost/latency **Prometheus counters** (`metrics.py`), exhaustion handling, key fail-fast. `complete_structured()` validates a Pydantic schema **single-shot** — on `ValidationError` it raises `LLMError`, no repair/retry.
- **`agents` battery** (`template/src/{{package_name}}/agents/`): `AgentRunner` — a bounded tool loop (`max_iterations=5`), OpenAI wire-format history kept **in a local `msgs` list that is discarded when `run()` returns**. `ToolRegistry` with two **read-only, hardcoded** tools (`get_item`, `search_items`); read-only "by design" (docstring), no per-tool authz/scope/idempotency seam. `AgentMetrics`: flat `app_agent_tool_calls_total{tool,outcome}` and `app_agent_runs_total{outcome}` **counters** — the per-run structure is thrown away.

So the batteries give you a *call wrapper* and a *toy tool loop*. The harness seams that make an agent **operable, debuggable, safe, and affordable in production** are the gaps. The six below are ordered by retrofit pain.

---

## Seam 1 — Durable run / conversation state persistence (the run is ephemeral)

**The seam.** `AgentRunner.run()` builds `msgs` locally and returns a `RunResult`; the conversation thread, tool-call inputs/outputs, and loop position evaporate the moment the function returns. There is **no thread/run table, no checkpoint, no resume**. The `llm` service is explicitly "Stateless." Nothing in either battery persists what the agent did or where it was.

**Why late is expensive (the retrofit story).** Durable state is not a feature you sprinkle on a working agent — it is a *data model and a control-flow shape* that everything else hangs off. The 12-factor-agents canon makes this the load-bearing factor: unify execution state and business state into one serializable thread so the agent becomes "trivially serializable/deserializable" and you "can resume from any point by just loading the thread" ([12-factor-agents, Factor 5](https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-05-unify-execution-state.md)). LangGraph's entire production story is built on this: a checkpointer "saves the exact state of the graph (including the stack and local variables) before an interrupt," so "the agent can be paused for hours or days" and resumes "as if milliseconds had passed" ([LangChain Interrupts docs](https://docs.langchain.com/oss/python/langgraph/interrupts); [Vadim's blog, durable execution](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off)). The guidance is blunt: "go straight to PostgresSaver for production" — `MemorySaver` is a dev toy, which is exactly what the framework's in-memory `msgs` list is.

The retrofit pain is that **persistence is upstream of four other capabilities you can't add without it**:
- **Human-in-the-loop** — you cannot pause for approval and resume what you didn't persist. LangGraph's `interrupt()` *requires* a checkpointer + thread_id ("To use interrupt, you need a checkpointer to persist the graph state").
- **Failure recovery** — a worker crash mid-run loses the whole run; nothing to resume from.
- **Run history / audit / debugging** — once thousands of runs have executed and been discarded, there is **no backfill**; the data is simply gone.
- **Multi-turn conversation** — a "stateless reducer" still needs the thread re-loaded each turn from a store.

Retrofitting later means: introduce a thread/run schema, thread a thread-id through every call site, change `RunResult` and route signatures, and migrate or abandon all historical runs. This is a cross-cutting rewrite of the loop *and* the data model after the product already has live conversations.

**retrofit_cost: H.** It is a data-model + interface lock-in that grows with every run executed and every call site that assumed statelessness. Pre-data it's a table and a thread-id parameter; post-data it's a migration + a control-flow rewrite + permanently lost history.

**What early scaffolding looks like.** A `runs`/`threads` table (the framework already ships Alembic + an expand-only migration contract — reuse it). `AgentRunner.run(thread_id=...)` loads/appends the serialized thread each step and persists after each tool turn (the natural checkpoint boundary). A `RunStore` protocol with an in-memory impl for tests and a Postgres impl for prod (mirrors the LiteLLM/profile seam already in the codebase). This unlocks resume, HITL, recovery, and audit for free later.

**Proposed disposition: battery** (extends `agents`; "durable-runs" sub-capability). The persistence shape is opt-in surface, not a posture.

**Overlaps.** Distinct from the board's `audit-log/activity-trail` (that's a generic domain-mutation trail; this is the agent-run thread the loop resumes from) — but they should share the storage seam. Note for the board.

---

## Seam 2 — Agent-run record / GenAI trace schema (counters throw the run away)

**The seam.** `AgentMetrics` emits flat Prometheus counters (`app_agent_tool_calls_total`, `app_agent_runs_total`). There is **no per-run record** — no parent agent span, no child tool/LLM spans, no conversation id, no per-call token/cost attribution tied to a run. You can see "47 tool calls failed" but never reconstruct *which run, in what order, with what arguments, costing what*.

**Why late is expensive.** This is explicitly **not** "add the observability stack" — the framework already ships OTel/Tempo/Loki/Prometheus/Grafana. The gap is the **GenAI span schema**: the agent battery emits aggregate metrics where it should emit a structured per-run trace. OTel's GenAI semantic conventions (exited experimental for client spans in early 2026) define exactly the shape the battery is missing: a parent `invoke_agent {gen_ai.agent.name}` span with **child `execute_tool` spans** (`gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`) and child chat spans (`gen_ai.request.model`, `gen_ai.usage.input_tokens`/`output_tokens`), correlated by `gen_ai.conversation.id` ([OTel GenAI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/); [techbytes cheat sheet 2026](https://techbytes.app/posts/opentelemetry-genai-agent-semconv-cheat-sheet-2026/)). The whole point: "each tool call, LLM invocation, and retrieval step becomes a child span, producing a full trace of the reasoning chain" ([Uptrace](https://uptrace.dev/blog/opentelemetry-ai-systems)).

The retrofit pain is **irreversible data loss**. A flat counter "tallies total tokens but hides cost structure" — flattening "loses the causal relationships—you can't correlate token spend to specific agent decisions or tool failures within that run" ([Uptrace](https://uptrace.dev/blog/opentelemetry-ai-systems)). Once a year of production runs is recorded only as counters, you **cannot reconstruct traces for debugging or backfill an eval dataset** — the per-run structure was never captured. Worse, retrofitting the schema means re-instrumenting *every call site* in the loop and you still have no history. Capturing the right span schema *the first time* is cheap; recreating lost runs is impossible.

**retrofit_cost: H.** The cost is the unrecoverable historical data + re-instrumentation, not wiring a collector (which exists). Conforming to the OTel GenAI schema at the seam now is near-free; backfilling is impossible.

**What early scaffolding looks like.** Wrap the loop in an OTel `invoke_agent` span; emit `execute_tool` child spans per `registry.dispatch` and chat spans per `service.respond`, with `gen_ai.*` attributes. Persist a per-run record (couples to Seam 1's `runs` table — they are the same write). Keep the existing counters as the aggregate metrics layer; add the trace layer beneath.

**Proposed disposition: concern** (posture: "the agent loop emits OTel-GenAI-conforming run records"). It's a schema decision the scaffold should make once, not an opt-in capability.

**Overlaps.** Riffs against board's already-covered "full observability stack" — explicitly NOT that. This is the GenAI **span/record schema** the stack carries. Shares the `runs` write with Seam 1.

---

## Seam 3 — Tool permission / capability model (read-only-by-fiat has no authz seam)

**The seam.** Tools are read-only "by design" via a docstring and hand-written handlers; `ToolRegistry.dispatch` has **no scope, no per-tool authorization, no caller identity, no idempotency hook**. The day a builder adds a mutating tool (send-email, refund, write-record — the obvious next step), there is no seam to constrain it. The framework has pre-baked the *least* dangerous case and left the dangerous one structureless.

**Why late is expensive.** This is OWASP **LLM06 Excessive Agency** and the **lethal trifecta** territory, and both sources insist the defense is *architectural, design-time*, not a later bolt-on. OWASP: excessive agency is "granted too much autonomy, permissions, or functionality" and chains with prompt injection — "an attacker injects instructions that cause the model to generate malicious output, and the application executes it" ([Aembit OWASP LLM Top 10](https://aembit.io/blog/owasp-top-10-llm-risks-explained/); [Promptfoo OWASP LLM](https://www.promptfoo.dev/docs/red-team/owasp-llm-top-10/)). Simon Willison is emphatic that detection fails and only structure works: "once an LLM agent has ingested untrusted input, it must be constrained so that it is impossible for that input to trigger any consequential actions"; guardrails that catch "95% of attacks" are a *failure* in a security context; "the only reliable defence is structural: cut one of the three legs by architectural design rather than relying on detection" ([Simon Willison, the lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)). The named real exploits — GitHub's official MCP server, M365 Copilot, GitLab Duo — all chained private-data access + untrusted content + exfiltration *because the tools had no capability scoping*.

The retrofit pain: scoping/permissioning is a property of the **tool-registry interface**. If the registry never carried a capability/scope/side-effect annotation, every tool added across the lifetime of the product was written assuming none — retrofitting means re-auditing and re-annotating *every* tool, adding identity/scope plumbing through `dispatch` and `ToolContext`, and re-reviewing the whole tool surface for trifecta legs. Anthropic's framing reinforces that tool design is first-class: "plan to invest just as much effort in creating good agent-computer interfaces (ACI)" as human ones, and "tool definitions and specifications should be given just as much prompt engineering attention as your overall prompts" ([Anthropic, Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)).

**Folded-in sub-seam — mutating-tool idempotency.** In *isolation*, idempotency is **LOW** (read-only tools have no idempotency problem). But it activates the instant a mutating tool exists, and the failure is concrete: crewAI shipped a real bug — *"Tool re-execution on task retry has no idempotency guard — duplicate payments, emails, trades possible"* ([crewAI issue #5802](https://github.com/crewAIInc/crewAI/issues/5802)). The fix is an idempotency key "derived from the turn ID plus the tool name (not a fresh UUID per call)" passed on every write ([buildmvpfast](https://www.buildmvpfast.com/blog/idempotent-ai-agent-retry-safe-patterns-production-workflow-2026)). This belongs to the *same registry seam* — a `mutates: bool` / `idempotency_key()` annotation on `Tool`.

**retrofit_cost: H** (for the permission/scope model) / **M** (idempotency alone, and only once mutating tools land). The registry interface is the lock-in; annotating it now is one field, re-auditing every tool later is a project.

**What early scaffolding looks like.** Extend `Tool` with `scope`/`capabilities`, a `mutates: bool` flag, and an optional `idempotency_key(args, ctx)`; have `dispatch` enforce scope against `ToolContext` identity and short-circuit duplicate mutating calls via a key store. Ship the read-only tools annotated `mutates=False` so the seam is *used* from day one (the scaffold demonstrates the contract). Document the lethal-trifecta "cut a leg" rule in the battery README.

**Proposed disposition: split.** The capability/scope *interface* is **battery** surface (extends `agents` tool registry). The per-PR check — *"this tool mutates and has no scope/idempotency key"* — is **reviewer-enforced**: an agentic reviewer flagging a mutating tool with no `scope`/`idempotency_key` is the right enforcement, not a static scaffold (matches the task's hint).

**Overlaps.** No board item covers agent tool permissioning. Adjacent to board's `shared-auth`/composability (caller identity) — the `ToolContext` identity should ride that seam.

---

## Seam 4 — Cost / budget enforcement at the LLM-call seam (metrics, no caps)

**The seam.** `LLMService` *records* cost (`record_cost`, best-effort) but **never enforces a budget**. There is no pre-call check, no session/run cap, no per-tenant ledger, no circuit breaker. The agent loop's only ceiling is `max_iterations=5` — which bounds turns, not dollars, and says nothing about a single runaway prompt or a multi-tenant noisy neighbor.

**Why late is expensive.** This is **NOT** the framework's existing HTTP rate-limiting — that throttles requests; this caps *token spend*. The failure mode is well-documented and financial: "a retry loop, an overly verbose chain-of-thought, or a stuck tool call can silently 10x your bill before you notice"; one documented incident "accumulated 847,000 API calls and $3,847 in OpenAI charges," another "racked up $15 in API costs in under 10 minutes" per agent ([AI Security Gateway](https://aisecuritygateway.ai/blog/llm-token-budget-strategies-for-agents); [RelayPlane](https://relayplane.com/blog/agent-runaway-costs-2026)). The fix is a *pre-call gate*: "Before any LLM call leaves the application, check whether the caller (agent, workflow, tenant) has remaining budget. If not, deny the call. The runaway-agent scenario goes from a five-figure incident to 'the agent got BUDGET_EXCEEDED on its 41st loop and stopped.'"

The retrofit argument is precisely about the **single call seam**: distributed, per-call-site checks are fragile — "a developer forgets to add the check in a new agent, there is no safety net" — whereas enforcement works only when "every request passes through it... budget enforcement happens in one place" ([RelayPlane](https://relayplane.com/blog/agent-runaway-costs-2026)). The framework already *has* that single seam — `LLMService._call()` — so the gate is cheap *now*. Retrofitting later, if call sites have proliferated and bypassed the service, means re-routing all of them through a gateway: an architectural refactor.

**retrofit_cost: M.** The framework's centralized `LLMService` makes the seam available, which lowers the cost from H to M — but it's M not L because per-tenant attribution couples to the (in-flight) multitenancy concern, and adding the ledger after live multi-tenant traffic means backfilling attribution. Posture now is one `if` in `_call`.

**What early scaffolding looks like.** A `BudgetGuard` protocol checked in `_call()` *before* `litellm.completion`: per-run and per-tenant ceilings, raising a `BudgetExceeded` (sibling to the existing `LLMExhausted`) that the loop catches and terminates cleanly. Per-tenant ledger keyed on the multitenancy tenant id. The cost is already computed (`completion_cost`); this just decrements a ledger and gates.

**Proposed disposition: concern** (posture: "every model call passes a budget gate"). The enforcement point is a once-decided architectural seam, not opt-in.

**Overlaps.** Distinct from board's already-covered "rate-limiting (HTTP)." Per-tenant attribution rides the board's **multitenancy** concern — flag the coupling.

---

## Seam 5 — Prompt registry + app-agent eval harness (no versioning, no regression gate)

**The seam.** Prompts/system strings are inline literals passed to `respond()`. There is **no prompt registry, no version pin on a run, no golden-set eval, no regression gate** for the agent the builder ships. A prompt edit is an undiffable, untestable, un-rollback-able change to production behavior.

**Why late is expensive.** These two couple tightly (versioning is pointless without an eval to regress against; eval is unactionable without a version to attribute a regression to), so I treat them as one seam. The canon: "Own Your Prompts" — treat prompts "as first-class code that can be explicitly defined, tested, and versioned" ([12-factor-agents Factor 2](https://deepwiki.com/humanlayer/12-factor-agents/3.2-factor-2:-own-your-prompts)). The LLMOps consensus is a CI gate: "Every prompt change should be a versioned artifact in a prompt registry, with CI automatically running eval suites against a golden dataset"; "a PR that regresses quality past the acceptable threshold does not merge" with "a regression golden set (≥30 cases)... typically ±3% on key metrics" ([MyEngineeringPath LLMOps](https://myengineeringpath.dev/genai-engineer/llmops/); [DeepEval eval harness](https://deepeval.com/blog/what-is-an-eval-harness)). Crucially the eval "lives in the offline/dev-time path, not in the live request path" — it's a *test seam*, exactly what a TDD-first scaffold should own.

The retrofit pain: an eval harness needs a **golden dataset**, and the cheapest source of goldens is *captured production traces* — which require Seams 1+2 to exist first ("turns production traces into evaluation datasets" — [Langfuse](https://medium.com/@adnanmasood/langfuse-for-tracing-debugging-prompt-management-and-evals-the-llm-gateway-playbook-part-4-c76e45d389d5)). Bolt eval on after a year of un-traced, un-versioned prompt drift and you have no golden set, no version history to attribute regressions to, and no way to know which prompt edit broke things. The framework is *uniquely positioned* here — it already ships its own reviewer-agent eval harness (`tests/eval/`, golden fixtures, thresholds, CI gate) and a strong TDD/quality-gate culture; the same shape should be scaffolded *into generated projects* for their agent. One caution from the sources: "never let the agent write its own ground truth" — goldens are human-validated ([Adaline guide](https://www.adaline.ai/blog/complete-guide-llm-ai-agent-evaluation-2026)).

**retrofit_cost: M.** Lower than the data-model seams because a prompt registry can be introduced over inline strings without losing data — but the *golden dataset* is the brutal part (you can't fabricate representative history), and the missed-regression cost compounds the longer prompts drift untracked. M, trending H the longer it's deferred.

**What early scaffolding looks like.** A `prompts/` module with named, version-tagged prompt artifacts (a content hash on each run record ties output→prompt version — couples to Seam 1). A `tests/agent_eval/` skeleton mirroring the framework's own eval harness: a small golden set, an LLM-as-judge or assertion scorer, and a CI gate that fails the build on regression past a threshold. The framework can render a *working example* eval from the two demo tools.

**Proposed disposition: battery** (a "prompt-registry + agent-eval" capability layered on `agents`). The framework's own eval infra is the template to copy.

**Overlaps.** **Explicitly distinct** from the board's queued "AI-eval for the builder's OWN agents" (that evaluates the *framework's* reviewer agents). This is an eval harness shipped *into the generated project* for the *builder's* agent — a different consumer entirely. Calling this out per the task. Shares the run-record write with Seams 1+2.

---

## Seam 6 — Structured-output repair + HITL checkpoint (localized, lower)

**The seam.** `complete_structured()` validates a Pydantic schema **once** and raises on `ValidationError` — no repair retry, no re-prompt with the error. And there is **no human-in-the-loop checkpoint** primitive in the loop (no pause-for-approval before a consequential step).

**Why late is (somewhat) expensive — and where it isn't.** The repair pattern is well-established and *cheap to add later because it's localized to one method*: a validate-retry loop where "typically 2 iterations catches 95%+ of failures, improving JSON parse success rate from 60% to 97%," feeding the validation error back to the model ([collinwilkins structured output](https://collinwilkins.com/articles/structured-output); [DEV repair loop](https://dev.to/novaelvaris/json-first-prompting-valid-structured-output-plus-a-repair-loop-2hkb)). Because it wraps a single existing seam (`complete_structured`), it has **none of the data-model lock-in** of Seams 1–3 — you can add the retry wrapper any time without touching call sites. That makes it genuinely **LOW** retrofit cost.

HITL is the higher-stakes half, but per Seam 1 it is *downstream of durable state* — you cannot meaningfully add pause-for-approval without the checkpoint/resume seam, and Anthropic frames it as a loop-design property: agents should "pause for human feedback at checkpoints or when encountering blockers," with explicit stopping conditions ([Anthropic, Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)). So HITL's retrofit cost is *inherited from Seam 1*, not independent — building Seam 1 with a checkpoint boundary makes HITL cheap; building it without makes HITL an H retrofit. I therefore park HITL *as a design note on Seam 1* rather than a separate headline seam.

**retrofit_cost: L** (structured-output repair, standalone) — it's a wrapper, addable anytime.

**What early scaffolding looks like.** A bounded repair loop inside `complete_structured()` (re-prompt with the `ValidationError` text, cap at ~2 retries, count repairs in metrics). For HITL: ensure Seam 1's checkpoint boundary is a clean pause point and expose an `awaiting_approval` run state — but *only as a consequence of building Seam 1*.

**Proposed disposition: park** (structured-output repair — real but low pull; a small quality-of-life addition to `complete_structured` whenever convenient). HITL → **rolled into Seam 1** as a design constraint, not a separate item.

**Overlaps.** None on the board. HITL coupling to Seam 1 noted above; structured-output enforcement is adjacent to board's already-covered Pact contract testing but operates at the model-output layer (a different contract surface).

---

## Summary table

| # | Seam | retrofit_cost | Disposition | Strongest evidence |
|---|------|---------------|-------------|--------------------|
| 1 | Durable run/conversation state persistence | **H** | battery | 12-factor F5; LangGraph checkpointer/interrupt |
| 2 | Agent-run record / GenAI trace schema | **H** | concern | OTel GenAI semconv (`invoke_agent`/`execute_tool`); Uptrace |
| 3 | Tool permission/capability model (+idempotency) | **H** / M | battery + reviewer-enforced | OWASP LLM06; Willison lethal trifecta; crewAI #5802 |
| 4 | Cost/budget enforcement at the call seam | **M** | concern | RelayPlane; AI Security Gateway ($3,847 / 847k calls) |
| 5 | Prompt registry + app-agent eval harness | **M** | battery | 12-factor F2; LLMOps eval-gate consensus |
| 6 | Structured-output repair (+ HITL→Seam 1) | **L** | park | structured-output repair loop; Anthropic checkpoints |

**Headline picks:** Seams 1, 2, 3 are the genuine HIGH-retrofit, data-model/interface-lock-in seams an opinionated scaffold exists to bake in early — they are upstream of resume, audit, HITL, eval-goldens, and tool safety, and they share a single `runs` write. Seams 4–5 round out the harness at MEDIUM. Seam 6 is honestly LOW and parked.
