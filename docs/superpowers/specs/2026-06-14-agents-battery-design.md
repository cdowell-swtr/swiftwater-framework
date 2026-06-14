# `--with agents` Battery — Design

> Design spec for the **`--with agents`** battery: a LiteLLM-backed LLM agent
> runtime shipped as template payload. Status: approved (brainstorming,
> 2026-06-14). This is **row 3** of the LiteLLM agent-capability roadmap
> (`2026-06-13-litellm-backend-foundation-design.md`) — the plain-LiteLLM,
> API-key capability. The subscription↔API hot-swap is the separate
> `--with HotSwapAgents` battery (FWK13).
>
> Execution: two mergeable slices — **FWK12** (runtime core) then **FWK14**
> (agentic loop). Each lands as its own plan/branch/merge.

## Context & goal

FWK5 re-homed the framework's own review/eval engine onto LiteLLM, proving the
in-process transport. This battery ships that capability *outward*: a generated
project scaffolded with `--with agents` gets an idiomatic, observable,
house-style LLM agent runtime — completion, structured output, and a bounded
tool-calling loop — built on **plain LiteLLM over a provider API key**.

The capability is provider-agnostic in principle (LiteLLM's reach) but ships
defaulting to Anthropic over an API key. Swapping the API path for the
subscription `claude-cli` provider (subscription↔API hot-swap) is explicitly the
downstream `--with HotSwapAgents` battery (FWK13); the `provider` config field
designed here is the seam it plugs into.

## Scope & slicing

One battery token, `agents`, built in two slices:

| Slice | Ships |
|-------|-------|
| **FWK12** — runtime core | config + completion service (text + structured output) + one demo route + in-process observability + tests. After this lands, `--with agents` is a complete, useful capability. |
| **FWK14** — agentic loop | tool registration + a bounded run loop + a read-only `Item` DB tool + an agentic demo route + loop/tool observability + tests. Upgrades the same battery from "completion service" to "agent". |

Battery registration (`batteries.py`):

```python
"agents": BatterySpec(
    "agents",
    "LiteLLM-backed LLM agent runtime (completion, structured output, "
    "tool-calling loop) with full observability",
    obs="in-process",
),
```

`gates_agents=()` — no existing review agent fits an LLM-agent surface; a
dedicated AI-safety reviewer is out of scope (see below). Generated-project
dependency: `litellm`, pinned to the major proven by FWK5.

## Module layout (template payload)

Rendered under `src/{{package_name}}/{% if "agents" in batteries %}agents{% endif %}/`:

| File | Slice | Purpose |
|------|-------|---------|
| `__init__.py` | FWK12 | package marker / public exports |
| `config.py` | FWK12 | derived agent-config helpers (e.g. the `provider/model` id join); the raw settings live in the central `Settings` |
| `service.py` | FWK12 (+FWK14) | `AgentService`: `complete()`, `complete_structured()`; `run()` loop added in FWK14 |
| `errors.py` | FWK12 | `AgentError` / `AgentExhausted` exception hierarchy |
| `metrics.py` | FWK12 (+FWK14) | Prometheus instruments |
| `routes.py` | FWK12 (+FWK14) | `POST /agents/complete`; `POST /agents/run` added in FWK14 |
| `tools.py` | FWK14 | tool registry + the read-only `Item` tools |

This is fresh, idiomatic template code **informed by, not copied from**, the
framework's internal `review/backend.py` / `review/agentic.py`. The framework's
internal `Message`/`BackendExhausted` seam is review-engine infrastructure and is
**not** shipped or imported.

## Configuration

All agent config flows through the central `Settings`
(`config/settings.py.jinja`, `env_prefix="APP_"`) under an `"agents" in batteries`
guard — preserving the template's one-true-config-surface doctrine:

| Setting | Env | Default | Slice |
|---------|-----|---------|-------|
| `agent_provider: str` | `APP_AGENT_PROVIDER` | `"anthropic"` | FWK12 |
| `agent_model: str` | `APP_AGENT_MODEL` | `"claude-sonnet-4-6"` | FWK12 |
| `agent_max_tokens: int` | `APP_AGENT_MAX_TOKENS` | `4096` | FWK12 |
| `agent_temperature: float` | `APP_AGENT_TEMPERATURE` | `0.0` | FWK12 |
| `agent_api_key: SecretStr` | `APP_AGENT_API_KEY` | `""` | FWK12 |
| `agent_max_iterations: int` | `APP_AGENT_MAX_ITERATIONS` | `5` | FWK14 |

`AgentService` passes `model=f"{provider}/{model}"` and
`api_key=settings.agent_api_key.get_secret_value()` **explicitly** into every
LiteLLM call — no out-of-band provider-native env lookup. The key is a typed
`SecretStr`; the `provider` field is the FWK13 hot-swap seam.

## Completion service (FWK12)

- `complete(messages, system=None) -> CompletionResult` — a non-streaming
  `litellm.completion` call returning `{text, usage}`.
- `complete_structured(messages, schema, system=None) -> SchemaModel` — typed
  structured output via LiteLLM `response_format` (a Pydantic model). **Shipped
  and proven in tests; it gets no HTTP route** (keeps the demo surface to one
  obvious endpoint).
- Usage — including cache-read tokens — is read off the LiteLLM response and
  recorded into metrics.

Demo route: `POST /agents/complete`, body `{prompt, system?}` → `{text, usage}`.

Streaming is **out of scope** for v1.

## Agentic loop (FWK14)

- `tools.py` — a small registry mapping a tool name to its JSON schema and
  handler. Ships **read-only** tools over the existing demo `Item` repository:
  `search_items(query)` and `get_item(id)`. The LLM cannot mutate state (no
  write tools) — safe by default.
- `AgentService.run(messages, system=None) -> RunResult` — the loop: call the
  model → if the response carries `tool_use`, dispatch the handler, append the
  correlated `tool_result`, and repeat → until the model stops **or** the
  iteration count reaches `agent_max_iterations` (default 5). Hitting the cap is
  a distinct `max-iterations` outcome (logged + counted), **not** an exception;
  `run()` returns the best available text plus the step trace.
- Demo route: `POST /agents/run`.

## Error handling

`errors.py` defines an independent hierarchy and maps LiteLLM exceptions:

- rate-limit / quota → `AgentExhausted`
- other provider / transport failures → `AgentError`

Demo routes map these to HTTP: **provider error → 502**, **exhaustion → 503**.
The framework-internal `BackendExhausted` is not reused.

## Observability (`in-process`)

`metrics.py` registers instruments on the app's existing `/metrics` endpoint
(no new service — `obs="in-process"`):

- `agent_calls_total{model, outcome}` — `outcome ∈ {success, error, exhausted}`
  (+ `max_iterations` in FWK14)
- `agent_call_latency_seconds` — histogram
- `agent_tokens_total{model, kind}` — `kind ∈ {input, output, cache_read}`
- `agent_cost_usd_total{model}` — LiteLLM's computed per-call cost
- FWK14: `agent_tool_calls_total{tool, outcome}`, `agent_loop_iterations`

The `in-process` surface owes an **alert** and a **dashboard**:

- **Alert:** agent error+exhaustion rate over a window exceeds a threshold
  (SLO-style, reusing the template's existing error-rate alert pattern). A
  wedged or quota-exhausted provider is the failure mode that matters most —
  not latency.
- **Dashboard:** calls / latency / tokens / cost panels (+ tool calls &
  loop iterations in FWK14).

Both are verified against the rendered template by
`tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface`
(extend the existing guard; do not reinvent it).

## Testing & proof

- **Unit (LiteLLM mocked):** completion; structured output; usage→metrics
  mapping; error/exhaustion → HTTP status mapping. FWK14: tool dispatch,
  `tool_result` correlation, and the iteration-cap guard.
- **Template-payload TDD loop:** render → `uv sync` → edit source → mirror
  (`.py` copied; `.jinja` rendered + copied) → pytest in the generated project,
  per the house template-payload loop; `ruff format --check` the rendered
  output.
- **Render + acceptance:** the generated project's own test suite + coverage
  gate + a **clean first `pre-commit`** pass. The obs-completeness guard is
  green for the new `obs` surface.
- **Eval-fixture coupling:** if any eval `change.patch` fixture anchors on a
  touched template file, re-anchor it (render + `patch --fuzz` + `git diff`).
- **Live smoke (optional, gated):** a real provider call exercising
  `complete()` (and `run()` in FWK14), kept out of the default gate.

## Out of scope

- Streaming responses.
- The subscription / `claude-cli` hot-swap — that is FWK13 (`--with
  HotSwapAgents`), which adds the externalized `litellm-claude-cli` package as a
  generated-project dependency via a **PEP 508 direct reference** (not
  `[tool.uv.sources]`; FWK11 review I2) and flips the `provider` seam.
- Multi-provider (non-Anthropic) wiring and demos.
- Write / mutating tools.
- A dedicated AI-safety / LLM review agent.

## PLAN.md

- **FWK12** keeps its line (deps: FWK5 ✓) — runtime core.
- **FWK14** added (deps: FWK12) — agentic loop.
- **FWK13** unchanged (deps: FWK11, FWK12).
