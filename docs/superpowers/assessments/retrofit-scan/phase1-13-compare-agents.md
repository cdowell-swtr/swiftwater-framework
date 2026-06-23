# Phase 1 retrofit scan — Comparative scan: agent frameworks / harnesses

**Agent:** compare-agents
**Area:** Comparative scan of AI-agent frameworks/harnesses — LangGraph, CrewAI, AutoGen/AG2, Mastra, Vercel AI SDK, LlamaIndex, Claude Agent SDK, OpenAI Agents SDK, Pydantic AI, Letta/MemGPT, Dify, LiteLLM proxy, Langfuse.

## What the framework's llm/agents batteries already are (baseline)

Read from the template payload before researching, so each seam is scored against the real surface, not a guess:

- **`llm` battery** (`template/.../llm/`): a thin observable LiteLLM wrapper (`service.py`). `complete()`, `complete_structured()` (pydantic `response_format`), and a tool-capable `respond()`. `profiles.py` is a (default ← named overlay ← per-call) provider/model/key/max_tokens/temperature resolver. `metrics.py` is a hand-rolled Prometheus exposition: `app_llm_calls_total` (profile×outcome), `app_llm_tokens_total` (input/output/cache_read), `app_llm_cost_usd_total` (per profile, via `litellm.completion_cost`), `app_llm_call_latency_p99_ms`. `errors.py` has `LLMError`/`LLMExhausted` (rate-limit/quota, with a `reset_hint`).
- **`agents` battery** (`template/.../agents/`): `runner.py` is a bounded tool-calling loop (`max_iterations=5`) over `service.respond()`; `tools.py` is a `ToolRegistry` of **read-only** domain tools (`get_item`, `search_items`) — read-only **by design** (the docstring is explicit: "no repository writes, no mutating tools"). `metrics.py` counts `app_agent_tool_calls_total` (tool×outcome) and `app_agent_runs_total` (completed/max_iterations/error).

The batteries are call-level wrappers with cost/usage *observability*. What the comparison frameworks make **first-class** and the batteries do **not**: durable/resumable run state, persistent agent memory, guardrails/tripwires, run-level **tracing** (spans, not just counters), eval-as-a-CI-gate, cost **enforcement** (vs. observation), human approval interrupts, and a standardized tool protocol. The seams below are ordered by retrofit cost.

---

## Seam 1 — Durable / resumable agent run state (checkpointer + thread_id)

**The seam.** A persistence boundary around the agent loop: every run keyed by a durable `thread_id`/`run_id`, its message history + step cursor checkpointed to a store (DB) at each step, so a run can be **resumed exactly where it left off** after a crash, a deploy, or a pause-for-human. The framework's `AgentRunner.run()` keeps `msgs` and `called` in a local Python list — when the process dies mid-loop (OOM, redeploy, a worker eviction, an `LLMExhausted` on iteration 4 of 5), the entire run and every token already spent are gone, and the only recovery is to start over from the user's first message.

**Why late is expensive (the retrofit story).** LangGraph makes this its central primitive: "a checkpointer ... persist[s] a thread's graph state as checkpoints," supporting "conversation continuity, human-in-the-loop workflows, time travel, and fault tolerance" ([LangChain — Durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)). The three problems it names are exactly what an in-memory loop cannot do: "continue a conversation," "resume after an interruption," "recover from a failure." Retrofitting this is brutal because **durability is a cross-cutting shape, not a feature you bolt onto the end**: every place that holds run state (the `msgs` list, the iteration cursor, tool results, partial assistant turns) has to be moved behind a serializable, addressable store and made re-entrant; the loop has to become idempotent on replay (re-running a tool on resume must not double-charge a side effect); and a `thread_id`/`run_id` has to be threaded from the HTTP boundary all the way down — a contract you cannot add without touching every caller. The durability mode is itself a design decision LangGraph forces up front (sync = "writes every checkpoint before continuing ... high durability at the cost of some performance"; async = "small risk that LangGraph does not write checkpoints if the process crashes"). Diagrid's critique sharpens the bar — naive checkpoints still aren't true durable execution for production workflows ([Diagrid — Checkpoints aren't durable execution](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows)) — which is the point: a scaffold that ships even the *thread_id + checkpoint store* seam saves the builder from re-plumbing their whole loop later.

**retrofit_cost: H.** Once real long-running agent runs exist (and especially once they have side effects), making the loop resumable means re-architecting state ownership and re-entrancy across the whole run path — and any run in flight when you ship it can't be migrated.

**Early scaffolding looks like.** A `RunStore` seam behind `AgentRunner`: persist `{run_id, thread_id, messages, cursor, status}` to a table after each step (the `workers`/DB surface already exists); `run(resume_from=run_id)` rehydrates and continues; tool dispatch carries a replay guard so resumed runs don't re-execute completed steps. Even shipping just the addressable `run_id` + a checkpoint row (no time-travel) inverts the retrofit from "re-architect" to "extend."

**Disposition: battery** (extends `agents`; an opt-in `durable`/`agent-runs` surface, `requires=("agents",)`).
**Overlaps:** `workers` battery (the DB-backed run table rides the existing async/DB surface); cross-references Seam 4 (human-approval interrupts are the *reason* you pause, durability is *how* you resume) and Seam 2 (semantic memory is distinct from execution checkpoints — keep them separate; LangGraph's checkpointer conflates them).

---

## Seam 2 — Persistent, first-class agent memory (memory blocks, not prompt history)

**The seam.** Treat memory as a **database-backed primitive with stable identity**, not as conversation history stuffed back into the prompt. Letta's case: "Letta's memory blocks are individually persisted in the DB, with a unique `block_id` to access them via the API"; memory "survives across agent invocations, remains editable independently of context window compilation, [and] can be shared across multiple agents" ([Letta — Memory blocks](https://www.letta.com/blog/memory-blocks)). The framework's agent is fully stateless: `run()` takes a `messages` list and returns; nothing the agent learns is durable, and there is no place for facts to live between calls.

**Why late is expensive (the retrofit story).** Letta's argument is precisely a retrofit-cost argument: when memory is an afterthought (history appended to prompts), agents "forget critical user information or must redundantly ask for it in each step," and "developers lose visibility into what occupies the context window, making performance optimization impossible." The killer line for scaffolding: "Building memory into the architecture from the start enables sophisticated patterns (multi-agent shared memory, sleep-time compute) that are nearly impossible to bolt on later when memory lives only in prompt strings." The retrofit is expensive for a data-shape reason, not a code reason: by the time you want durable memory you already have months of conversations that exist *only* as ephemeral request bodies — there is no schema, no `block_id`, no archival store, and no backfill path. You're not adding a feature; you're inventing a persistence model after the data that should have populated it has already evaporated. Letta's OS-inspired tiers (core in-context block / recall searchable history / archival vector-backed cold storage) are the canonical shape ([Letta walkthrough](https://sureprompts.com/blog/letta-memgpt-walkthrough); [Atlan — memory frameworks 2026](https://atlan.com/know/best-ai-agent-memory-frameworks-2026/)).

**retrofit_cost: H.** This is data-shaped: the value of memory is the *accumulated* facts, and you can't retroactively capture what was never persisted. A schema added on day 400 starts empty.

**Early scaffolding looks like.** A `memory` table/seam keyed per subject (user/session): durable, editable "blocks" with a stable id, plus a tool the loop can call to read/write them (the existing read-only `ToolRegistry` already proves the tool seam). The archival/recall tier rides the **`pgvector` battery** for semantic recall.

**Disposition: battery** (`agent-memory`, `requires=("agents",)`; archival tier `requires=("pgvector",)`).
**Overlaps:** **AI-retrieval (vector-store/RAG/GraphRAG) board battery** — Letta's archival tier *is* vector-backed recall, so this seam shares that battery's substrate; the distinction is that memory is **agent-writable, identity-bearing state**, where RAG is read-only retrieval over a corpus. Also overlaps the `pgvector` battery directly.

---

## Seam 3 — Guardrails: interception hook points + tripwire in the loop

**The seam.** A first-class place to intercept **before** the model runs (input guardrail) and **before** the output reaches the user (output guardrail), with a tripwire that halts the run. OpenAI Agents SDK makes this structural: guardrails attach to the agent via `@input_guardrail`/`@output_guardrail`, return a `GuardrailFunctionOutput` whose `tripwire_triggered=true` "immediately raise[s] a `{Input,Output}GuardrailTripwireTriggered` exception and halt[s] the Agent execution" ([OpenAI Agents SDK — Guardrails](https://openai.github.io/openai-agents-python/guardrails/)). The framework's loop has **no interception points at all** — `runner.py` goes straight from `messages` into `service.respond()` and straight from `message.content` back to the caller.

**Why late is expensive (the retrofit story).** The SDK's own rationale is a cost-and-safety one: "imagine you have an agent that uses a very smart (and hence slow/expensive) model ... You wouldn't want malicious users to ask the model to help them with their math homework"; blocking-mode input guardrails "prevent token consumption and tool execution" before the expensive model ever runs. Retrofitting interception into an **in-memory loop** after the fact is genuinely painful: the loop's control flow (the `for iteration in range(...)` with early returns and per-tool dispatch) has no seam for "run a check, and if it trips, unwind cleanly" — you'd thread tripwire handling through every return path, and every existing caller of `run()` would need to handle a new halt-exception class it never expected. Output guardrails ("PII detection, compliance checking, content policy enforcement," per the search synthesis) are most valuable *redacting* before egress — a behaviour you cannot insert non-invasively once responses already flow straight through.

**retrofit_cost: H** for the interception/tripwire seam (control-flow surgery on every run path + a new exception contract for every caller). The check *implementations* are pluggable later; the **hook points** are the expensive part.

**Early scaffolding looks like.** `AgentRunner.run(input_guardrails=[...], output_guardrails=[...])` with a `Guardrail` protocol returning `(tripwire: bool, reason: str)`, a `GuardrailTripped` exception, and `app_agent_guardrail_trips_total{rail,phase}` metric. Ship the seam empty (no-op rails) so adding a real PII/moderation rail is config, not surgery.

**Disposition: concern** (posture decision scaffolded early — the *interception architecture* — with a thin opt-in battery for shipped rails).
**Overlaps:** the **second half of guardrails is reviewer-enforced, see Seam 7**; cross-references Seam 6 (cost) since input guardrails are also a cost-control lever.

---

## Seam 4 — Human-approval interrupts for sensitive actions

**The seam.** A first-class "pause the run, surface the proposed action, wait for a human yes/no, resume" path — the connective tissue between durability (Seam 1) and tool least-privilege (Seam 7). It shows up independently in *both* of this area's strongest sources: LangGraph's interrupts "allow you to pause graph execution and wait for human input" and are *the* motivating case for durable execution ("particularly useful in scenarios that require human-in-the-loop, where users can inspect, validate, or modify the process before continuing") ([LangChain — Durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)); and OWASP's agent-injection guidance names "human confirmation for sensitive actions" / "human approval for high-risk actions" as a primary mitigation ([OWASP LLM Top 10 — Prompt injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)). The framework's loop dispatches every tool call autonomously; there is no place to interpose a human.

**Why late is expensive (the retrofit story).** An approval interrupt is only implementable on top of a **resumable** loop: you have to suspend mid-run, persist the pending action, return control to a human surface, and resume on approval — which is why LangGraph couples it to the checkpointer. Bolt it on after the loop is synchronous and in-memory and you're forced to do Seam 1's whole re-architecture as a prerequisite, *plus* invent an approval store and a resume API. Today the framework dodges this by making tools read-only by design — but the moment a builder adds one mutating tool (the natural next step), the absence of an approval seam means the agent can act irreversibly with no checkpoint.

**retrofit_cost: H** (it inherits Seam 1's re-architecture as a hard prerequisite).

**Early scaffolding looks like.** Mark tools `requires_approval: bool` in the `ToolRegistry`; when the loop hits one, checkpoint (Seam 1) + raise a `PendingApproval` carrying the proposed call; a `resume(run_id, approved=...)` continues or aborts. Empty by default (read-only tools never trip it), wired the day a mutating tool lands.

**Disposition: battery** (folds into the Seam 1 durable-runs battery; gated by a mutating-tool surface).
**Overlaps:** Seam 1 (durability is the substrate); Seam 7 (least-privilege tooling is the same threat model from the static side).

---

## Seam 5 — Run-level tracing with OTel GenAI semantic conventions

**The seam.** Emit the agent run as an **OpenTelemetry span tree** with `gen_ai.*` attributes — one span per LLM call and per tool call, nested under a run span — *not just* the hand-rolled Prometheus **counters** the batteries emit today. This is a gap **inside a strength**: the framework already ships the full OTel/Tempo/Grafana infrastructure (already-covered), but `service.py`/`runner.py` only `record_*` into counter dicts. There is no span, no parent/child linkage, no per-step latency/error attribution, no prompt/response capture — so when an agent misbehaves you can count that runs failed but cannot see *why* a specific run took the path it did.

**Why late is expensive (the retrofit story).** The whole value of agent tracing is per-step causality: "every LLM call, tool invocation, and intermediate reasoning step is observable, so you can understand why an agent took a certain action instead of having to infer it from the logs" ([LangChain — LangSmith observability](https://www.langchain.com/langsmith/observability)). OTel's GenAI semantic conventions now standardize this — spans for inference ("a client call to [a] Generative AI model ... that generates a response or requests a tool call"), agent, and retrieval operations, with a vendor-neutral schema for "prompts, model responses, token usage, tool/agent calls, and provider metadata" ([OpenTelemetry — GenAI agent spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/); [OTel GenAI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)). Retrofit cost is "re-instrument every call site": spans must be opened/closed and **correctly nested** at each `litellm.completion` and each `registry.dispatch`, with context propagated through the loop — touching exactly the hot paths in `service.py` and `runner.py`. Choosing the attribute schema *after* you've shipped ad-hoc telemetry means a second migration (your dashboards/queries are keyed to the old names). Doing it once, conformant to `gen_ai.*`, means your agent stack is "agent-native at development time and still ... standards-based in production" ([DEV — AI agent observability 2026](https://dev.to/chunxiaoxx/ai-agent-observability-in-2026-openai-agents-sdk-langsmith-and-opentelemetry-3ale)).

**retrofit_cost: H** — re-instrumenting every model/tool call site for correct span nesting + context propagation, then re-keying dashboards if the attribute schema changes, is far more painful than wiring spans at the call sites from day one.

**Early scaffolding looks like.** Wrap each `service.respond()` and each `registry.dispatch()` in an OTel span with `gen_ai.operation.name`, `gen_ai.system`/`gen_ai.provider.name`, token counts, and the profile; parent them under a run span in `AgentRunner.run()`. The exporter/collector/Tempo already exist — this is *call-site instrumentation*, not new infra.

**Disposition: concern** (instrument the call sites early, conformant to the GenAI semconv) — implemented as an extension of the existing `llm`/`agents` batteries' obs surface.
**Overlaps:** **already-covered full observability stack (OTel/Tempo/Grafana)** — frame this explicitly so a reader doesn't reject it: the *infrastructure* is covered, the *span instrumentation at the agent call sites* is the gap. Complements (does not replace) the existing `app_llm_*`/`app_agent_*` counters.

---

## Seam 6 — Cost-budget enforcement (a gate, not a counter)

**The seam.** A pre-call **gate** that rejects (or downgrades) a request when a budget is exceeded — distinct from the cost *observability* the `llm` battery already has. `app_llm_cost_usd_total` is a counter you can graph; it cannot stop a runaway agent loop or a hostile user from spending the month's budget in an afternoon. LiteLLM's proxy makes enforcement first-class: "With hard budget enforcement enabled, every budgeted request validates spend against the authoritative database before being admitted, covering key, team, user, organization, end-user, tag, and per-window budgets. The proxy automatically rejects further requests with a clear error until the budget resets" ([LiteLLM — Budgets & Rate Limits](https://docs.litellm.ai/docs/proxy/users); [LiteLLM — Spend tracking](https://docs.litellm.ai/docs/proxy/cost_tracking)).

**Why late is expensive (the retrofit story).** Enforcement is an admission-control seam that must run *before* `litellm.completion` on **every** call path — once cost-bearing code is sprinkled across routes, agent loops, and workers with no central gate, adding one means finding and wrapping every call site and inventing the per-subject accounting store (LiteLLM's "authoritative database") that admission control reads. Multiple windows (24h guardrail + 30d ceiling) and per-subject scoping (per virtual key / tag) are design decisions cheap to seam early and expensive to layer onto an unprotected codebase. The blast radius of *not* having it is unbounded spend from an agent that loops or a prompt-injected tool storm.

**retrofit_cost: M–H** — M because the framework already centralizes calls in `LLMService` (one natural gate point), pushing toward H once cost-bearing calls exist outside it (workers, multiple routes) and you need per-subject windowed accounting.

**Early scaffolding looks like.** A `BudgetGate` checked in `LLMService._call` before dispatch: per-profile/per-subject windowed spend (reuse the cost already computed via `litellm.completion_cost`), raising a typed `BudgetExceeded`; budgets in settings. Or, at the deployment posture level, route through a LiteLLM proxy and inherit hard-budget enforcement.

**Disposition: concern** (admission-control posture scaffolded at the single `LLMService` gate) with an optional proxy-backed battery.
**Overlaps:** **already-covered rate-limiting** — same admission-control family, **different axis**: rate-limiting is requests/time, this is **cost/time** (and per-subject spend). Cross-references Seam 3 (input guardrails are also a spend lever).

---

## Seam 7 — Tool least-privilege + injection-aware tool gating (reviewer-enforced)

**The seam.** The *static* half of agent safety: tools scoped to least privilege, and a guard against the canonical agent attack — **untrusted tool output / retrieved content concatenated into a privileged prompt**, then acted on. OWASP ranks prompt injection #1 and is explicit on the agent shape: "an agent with email sending permission becomes an exfiltration tool, an agent with database write becomes a record manipulation vector"; mitigation is "explicit least privilege per tool" and "evaluate each proposed tool call against the original user intent" ([OWASP LLM Top 10 — Prompt injection cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html); [Promptfoo — OWASP LLM Top 10](https://www.promptfoo.dev/docs/red-team/owasp-llm-top-10/)). The framework's loop is **read-only-tools by design**, so the posture is *partly already made* — the value of a reviewer is to **guard that invariant against regression** the moment a builder adds a mutating or broadly-scoped tool, and to flag tool handlers that feed untrusted content into a privileged path.

**Why this is reviewer-enforced, not scaffolded.** This is the exact shape of the task's GDPR-right-to-erasure example (owned by a reviewer, not a scaffold): it's a *posture you continuously verify against code*, not a runtime surface you render once. A scaffold can ship read-only tools (and it does), but it cannot *prevent* the builder from later registering `delete_user(id)` with no scope check or piping a fetched webpage straight into the system prompt — only a reviewer reading the diff catches "this new tool widens privilege" or "untrusted tool output reaches a privileged instruction." OWASP's own guidance is review-shaped: "neither RAG nor fine-tuning fully mitigates the LLM01 class; instead ... defense-in-depth with least-privilege tooling, input/output filtering, human approval for high-risk actions, and regular adversarial testing."

**retrofit_cost: M** as a *reviewer* (registering/tuning an agent-tool-safety reviewer is cheap and incremental). The *consequence* of catching it late is H, which is why the review gate matters from the first mutating tool.

**Early scaffolding looks like.** Not a scaffold — an **agentic reviewer** (or extension of an existing privacy/security reviewer) that fires when `agents`/`llm` are present: flags new mutating/broad-scope tools without explicit authorization scoping; flags untrusted tool-output/retrieved-content flowing into a privileged prompt without isolation; recommends per-tool least privilege + human-approval (Seam 4) for high-risk actions.

**Disposition: reviewer-enforced.**
**Overlaps:** Seam 3 (the *runtime* interception half — guardrails); Seam 4 (human-approval is the runtime control for the same threat); the framework's existing privacy/security review agents (extend, don't reinvent — per the repo's "check agent prompt-fit before adding to a target's active set" memory).

---

## Seam 8 — Agent eval harness as a CI gate (for the *generated app's* agent)

**The seam.** A dataset of golden cases + evaluators (assertion + LLM-judge) that run the app's agent and **fail the build** on regression. Pydantic Evals makes this a pass/fail surface: "two surfaces for running evals against a ... agent: your terminal ... or your CI pipeline as a pass/fail gate," where you "define an `EvaluationDataset` ... parametrize the test over its goldens, call the agent inside the test, and let `assert_test` evaluate the trace" ([Pydantic AI — Evals overview](https://ai.pydantic.dev/evals/evaluators/overview/); [LLM-as-a-judge](https://pydantic.dev/articles/llm-as-a-judge)). The framework ships rich TDD/quality gates but **no eval surface for a generated project's own agent** — nothing exercises `AgentRunner` against expected behaviours, so a prompt or model change can silently regress with green unit tests.

**Why late is expensive (the retrofit story).** The eval *infrastructure* is partly retrofittable (you can add a dataset later) — but the **value is the accumulated regression cases**, and those only exist if you've been writing one per incident/behaviour from day one. A team that adds evals on day 300 starts from an empty dataset and has lost the 300 days of "this is the case that broke last time" goldens that make the gate worth anything. Early scaffolding's job is to make capturing a golden case the *default reflex* (a place to drop it, a gate that runs it) so the corpus compounds.

**retrofit_cost: M** — the harness is bolt-on-able; the lost asset is the regression corpus you didn't accumulate.

**Early scaffolding looks like.** Ship a tiny `tests/agent_evals/` with a golden-case dataset format, an assertion + LLM-judge evaluator, and a (off-by-default-in-CI, keyless-friendly) pytest gate exercising `AgentRunner` over the demo tools — so the builder's first instinct on a behaviour bug is "add a golden case here."

**Disposition: battery** (a thin `agent-evals` test surface, `requires=("agents",)`).
**Overlaps:** the board's **queued "AI-eval for the builder's own agents"** — *distinct*: that item evals the **framework's review agents**; this seam evals the **generated application's** agent. Same technique, different target. Also cross-references Seam 5 (Pydantic Evals evaluates the *trace* — evals and tracing share the span surface).

---

## Conscious parks & honest demotions (named, not silently dropped)

- **MCP / standardized tool protocol (Claude Agent SDK).** MCP "connect[s] AI agents to external tools ... without writing custom tool implementations," and adds dynamic tool discovery (`defer_loading`, ~85% token reduction with 50+ tools) ([Claude Agent SDK — MCP](https://platform.claude.com/docs/en/agent-sdk/mcp); [Anthropic — advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)). **retrofit_cost: M, park.** The framework's `ToolRegistry` is already a clean abstraction seam — adopting MCP is *adopt-a-standard at a defined boundary*, not paint-out-of-corner. Worth noting an MCP-shaped registry adapter as a future battery, but not a high-retrofit seam.

- **Provider retries / fallback chains (LiteLLM Router).** Context-window, content-policy, and general fallbacks with weighted failover, and LiteLLM "strips unsupported parameters (e.g. `response_format`) when switching models" ([LiteLLM — Reliability/Fallbacks](https://docs.litellm.ai/docs/proxy/reliability)). **retrofit_cost: L, park.** `service.py` calls `litellm.completion` directly, but the Router does failover natively — the retrofit is *config* (swap to `Router`/`completion_with_fallbacks`), not surgery. Low pull.

- **Prompt/model-config versioning + rollback (Langfuse).** Externalize prompts, tag a version "production," roll back by reassigning the label "without changing code" ([Langfuse — Prompt version control](https://langfuse.com/docs/prompt-management/features/prompt-version-control)). **retrofit_cost: M, park (borderline).** Externalizing prompts later is moderately painful, not brutal; the framework's profiles already externalize *model config*. Note as a candidate, below the cut.

- **Multi-agent orchestration / handoffs (CrewAI, AutoGen/AG2, OpenAI handoffs).** First-class across the named frameworks (role-based crews, conversational handoffs). **Park** — for a single-service FastAPI scaffold this is out of scope; a builder who needs multi-agent topology has outgrown the scaffold's shape. Called out explicitly so it isn't read as an omission.

---

## Summary table

| # | Seam | retrofit_cost | Disposition | Primary overlap |
|---|------|:---:|------|------|
| 1 | Durable / resumable run state (checkpoint + thread_id) | H | battery | `workers`/DB; → Seams 2, 4 |
| 2 | Persistent first-class agent memory (blocks) | H | battery | AI-retrieval board battery; `pgvector` |
| 3 | Guardrails: interception hook points + tripwire | H | concern (+thin battery) | → Seam 7 (static half) |
| 4 | Human-approval interrupts for sensitive actions | H | battery (folds into S1) | Seams 1, 7 |
| 5 | Run-level OTel GenAI-semconv tracing (spans) | H | concern | already-covered obs stack |
| 6 | Cost-budget **enforcement** (gate, not counter) | M–H | concern (+proxy battery) | already-covered rate-limiting |
| 7 | Tool least-privilege + injection-aware gating | M (reviewer) | reviewer-enforced | Seams 3, 4; privacy/security reviewers |
| 8 | Agent eval harness as a CI gate (app's agent) | M | battery | queued builder-eval item; Seam 5 |
