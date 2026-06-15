---
name: llm-vs-agents-battery-taxonomy
description: The agent capability is TWO batteries — `--with llm` (runtime) + `--with agents` (tool loop, requires llm); hotswap extends llm and precedes agents.
metadata:
  type: project
---

The LiteLLM agent capability ships as **two batteries with honest names**, not one:

- **`--with llm`** — the LLM *runtime*: completion + structured output, config
  (`APP_LLM_*`), `LLMService`, `app_llm_*` metrics + `llm_alerts.yml`/`llm.json`,
  the `/llm/complete` route. This is what shipped in **v0.2.5 as `--with agents`**
  and was renamed to `llm` in **v0.2.6 (FWK15)**.
- **`--with agents`** — the tool-calling **loop** (registry + bounded run loop +
  read-only Item tool + agentic route), `requires=("llm",)`. The *real* agent
  (FWK14).

**Why:** a tools-less completion service is an *LLM integration*, not an *agent*
(the field, and Anthropic, draw exactly this line: LLM calls vs. loops-with-tools).
Calling the runtime "agents" oversold it. The window to fix it was free because
no consumer (Meridian) had adopted v0.2.5's `agents` yet.

**Roadmap order: `llm` → `hotswapllm` (FWK13) → `agents` (FWK14).** The
subscription↔API hot-swap is a **transport extension of `llm`** (it swaps the
provider backend — nothing to do with tool loops), so `--with hotswapllm`
`requires=("llm",)` and lands *before* `agents`. The fact that the hot-swap
doesn't belong to "agents" was itself the tell that the original single-`agents`
naming conflated two layers.

**Rename mapping (if you hit stale `agents`-named code):** token `agents`→`llm`,
module `agents/`→`llm/`, `AgentService`→`LLMService`, `Agent{Error,Exhausted,Metrics}`
→`LLM*`, `agent_*`/`APP_AGENT_*`→`llm_*`/`APP_LLM_*`, `app_agent_*`→`app_llm_*`,
`/agents/complete`→`/llm/complete`. A stray `app_agent_*` silently orphans the
alert/dashboard — grep the *rendered* project, not just source. See
[[release-cut-procedure]].
