# LiteLLM Backend Foundation — Design

> Design spec for **Plan 27 / FWK5** and the agent-capability roadmap it opens.
> Status: approved (brainstorming, 2026-06-13). Execution plan:
> `docs/superpowers/plans/2026-06-13-litellm-backend-foundation.md`.

## Context & goal

The review/eval engine talks to a model through a `messages.create`-shaped seam
in `src/framework_cli/review/backend.py`: a `Message`/`TextBlock`/`ToolUseBlock`/
`Usage` data model and two concrete backends — `ApiBackend` (Anthropic SDK) and
`SubagentBackend` (headless `claude -p` on the subscription). They are selected by
`_make_backend("api"|"subagent", …)` in `cli.py` and proved interchangeable by
`tests/review/test_backend_parity.py` (findings byte-identical across paths).

**Goal:** make **LiteLLM** the single transport seam under both paths — re-homing
the `claude -p` route as an in-process LiteLLM **CustomLLM** provider — so that the
engine gains LiteLLM's provider routing / retries / usage accounting / future
multi-provider reach behind one well-supported library, and so the *same*
capability can later be shipped to generated projects (Meridian) as a battery.

This is the strategic "single seam" goal (option C from brainstorming), with
multi-provider reach as a downstream consequence rather than an immediate need.

## Decomposition (one plan per row; this spec covers row 1)

| # | Work | Ships | Deps |
|---|------|-------|------|
| 1 | **LiteLLM foundation** — engine's own review/eval onto LiteLLM; `claude -p` becomes an in-tree CustomLLM plugin; parity proven | nothing external | — |
| 2 | Externalize the CustomLLM plugin to its own repo/package (entry-point registered) | a published package | 1 |
| 3 | `--with Agents` battery — LiteLLM-based agent capability as template payload | template | 1 |
| 4 | `--with HotSwapAgents` battery — adds the externalized `claude-cli` plugin as a dep for subscription↔API hot-swap | template | 2, 3 |
| 5 | *(conditional)* Refactor away the `Message` adapter — only exists if the foundation lands on the `litellm.completion` fallback path | nothing external | 1 |

Row 5 is **conditional**: see "Interface decision" below. If the foundation lands
on the `anthropic_messages` interface there is no adapter to remove and row 5
never gets created.

## Foundation design (row 1)

### The seam stays; the transport changes

Keep the public seam exactly as-is: `backend.messages.create(model, max_tokens,
system, messages, tools=None) -> Message`, the four dataclasses, and
`_make_backend`'s selection behavior. Only the *innards* of the two backends
change — both route through LiteLLM. Everything above `backend.py`
(`runner.py`, `agentic.py`, `request.py`, `engine.py`) is untouched, and the
existing parity + unit tests are the proof of behavior preservation.

The two backends differ only by **model-id prefix**: `anthropic/<model>` (API)
vs `claude-cli/<model>` (subscription). Internal tables (`DEFAULT_MODEL`,
`_MODEL_CONTEXT_TOKENS`, `spec.model`) keep bare ids; the prefix is applied at the
LiteLLM call boundary only.

### Interface decision — spike-gated, not assumed

LiteLLM offers two input surfaces, and the choice determines whether an adapter
exists at all. **We resolve this empirically (a go/no-go spike), not from docs**,
because the deciding facts are undocumented:

- **Primary — `litellm.anthropic_messages` (Anthropic `/v1/messages` shape).** The
  engine *already* speaks this shape (system blocks with `cache_control`,
  `tool_use`/`tool_result` content blocks, Anthropic-shaped `usage`/`stop_reason`).
  So inbound translation is ~zero and `_normalize_content`/`_normalize_usage`
  likely survive verbatim. A CustomLLM backs this surface by implementing
  `acompletion` ("litellm will transform it to /v1/messages" — custom-LLM docs);
  litellm bridges Anthropic↔OpenAI *internally*, so our `claude-cli` handler
  receives OpenAI-shaped messages and renders them to the `claude -p` text prompt
  — but the framework's call site and the engine stay Anthropic-shaped.
- **Fallback — `litellm.completion` (OpenAI shape).** Confirmed stable and
  confirmed to honor `custom_provider_map`, but forces a bidirectional translator
  (system→system-message, `tool_use`→`tool_calls` with correlated ids,
  `tool_result`→`role:tool`, tools→function schema, OpenAI-usage→cache tokens).
  This is the `Message`-adapter that decomposition row 5 would later remove.

**We do not justify the primary path by appeal to row 5** (that would be circular:
row 5 is an artifact of *assuming* an adapter is necessary). The merit is direct:
the Anthropic-shaped surface matches the engine, so it is less code and less risk
*if it works*. The spike decides:

- **S1 (API path):** `anthropic_messages(model="anthropic/<model>")` with an
  Anthropic system carrying `cache_control`, an agentic `tool_use`/`tool_result`
  exchange, and `tools` — returns Anthropic-shaped content and **non-zero
  `cache_read_input_tokens` on a repeated call** (caching truly passes through).
- **S2 (subscription path):** a minimal `ClaudeCliLLM(CustomLLM)` registered in
  `litellm.custom_provider_map` is actually invoked by
  `anthropic_messages(model="claude-cli/<model>")`.

GO on both → build the foundation on `anthropic_messages`; drop row 5. NO-GO on
either → fall back to `litellm.completion` + the translator; keep row 5. The
outcome is recorded in `ACTION_LOG.md`.

### The `claude-cli` CustomLLM plugin (built extraction-ready)

A `litellm.CustomLLM` subclass in its **own self-contained module** with **zero
`framework_cli` imports** — so decomposition row 2 is a lift-and-shift, not a
rewrite. It holds today's `claude -p` mechanics verbatim: system → `0o600` temp
file via `--system-prompt-file` (the `MAX_ARG_STRLEN` guard), prompt → stdin,
`_DISABLED_TOOLS`, `--output-format json`, `_parse_claude_json`, and the
`_EXHAUSTION_MARKERS` → `BackendExhausted(reset_hint=…)` mapping. Selected by
constructing `model="claude-cli/<model>"` when `--backend subagent`.

### Cross-cutting concerns

- **Dependency:** add `litellm` to the framework's own deps (pinned). *Not*
  template payload yet — that arrives with the Agents battery (row 3). Flag
  CLI cold-start cost at spike time.
- **Usage:** map LiteLLM usage (incl. `cache_creation_input_tokens` /
  `cache_read_input_tokens`) → `Usage`. The `claude-cli` handler synthesizes usage
  from `claude -p`'s JSON as today.
- **Exhaustion:** API path maps `litellm.RateLimitError` / quota errors →
  `BackendExhausted`; the `claude-cli` handler keeps the marker-regex +
  `reset_hint` extraction (the "resets 11:30am" string exists only on the
  subscription path, where we own the handler — so it survives intact).
- **Retries:** keep the `ANTHROPIC_MAX_RETRIES` env contract (default 8, cap 20)
  and feed the resolved value to LiteLLM (`num_retries=`), so `test_runner.py`'s
  retry tests hold with minimal change.
- **mypy + litellm:** if litellm ships poor/no types, add a *targeted* mypy
  override rather than a surprise — an explicit task, not silent.

## Testing & proof

- **Parity is the headline proof.** `test_backend_parity.py` (findings identical
  across api ↔ subagent) and `test_backend.py` get their mocks re-pointed at the
  LiteLLM layer and must pass unchanged in intent — that certifies the swap is
  behavior-preserving. TDD: failing test first, confirm red, implement, green.
- **Keep the live smoke.** The live `claude -p` smoke is the *only* thing that
  catches the `MAX_ARG_STRLEN` / large-input-via-stdin class (repo memory); it must
  now exercise the `claude-cli` CustomLLM path end-to-end (large system via temp
  file, big diff via stdin).
- **Caching check (real path).** Folded into the live smoke: a repeated call
  returns non-zero `cache_read_input_tokens`, confirming the cost lever survived
  (mocks can't prove passthrough).
- **Gate only, no render/acceptance:** this plan touches no template payload, so
  the bar is `pytest` + `ruff check` + `ruff format --check` + `mypy src`.

## Risks & open questions

- The two spike unknowns (custom-provider routing through `anthropic_messages`;
  request-side `cache_control` preservation). Mitigation: the spike is Task 1 and
  gates the rest.
- LiteLLM as a heavyweight dependency: cold-start and footprint. Mitigation:
  measure at spike time; lazy-import at the call boundary if needed.
- LiteLLM version pinning / churn: pin and record the version proven by the spike.

## Out of scope (this plan)

Template payload, the externalized package, the batteries (rows 2–4), and any
multi-provider (non-Anthropic) wiring. Those are downstream plans that depend on
this foundation landing and being proven.
