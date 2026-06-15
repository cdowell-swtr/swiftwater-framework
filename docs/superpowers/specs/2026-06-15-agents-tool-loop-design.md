# `--with agents` — Tool-Calling Loop — Design

> Design spec for the **`--with agents`** battery (FWK14): a bounded tool-calling
> agent loop built on the `llm` runtime. Status: approved (brainstorming,
> 2026-06-15). **Supersedes** the agents section of
> `2026-06-14-agents-battery-design.md` and the stale plan
> `2026-06-14-agents-battery-loop.md`, both written before the `llm` rename,
> profiles, and the separate-battery taxonomy.

## Context & goal

The LLM capability now ships as `--with llm` (runtime: completion + structured
output + named **profiles** + per-profile cost; v0.2.6–v0.2.7) and
`--with claudesubscriptioncli` (the Claude-subscription provider; v0.2.8). The
final piece is the **agent**: a bounded tool-calling loop that lets the model take
actions over the app's own data.

`--with agents` is a *separate* battery, `requires=("llm",)`, that adds **only**
the loop + tools on top of the `llm` runtime. It inherits profiles + the
subscription backend for free: `run(..., profile="sub")` runs the agent on your
Claude subscription; `profile="smart"` runs it on a strong API model — without the
agents battery knowing anything about providers.

## The seam: `LLMService.respond()` (the one `llm`-battery change)

The agent loop needs the **raw** model response (content + `tool_calls`), which
`complete()` discards (it returns text only). Add one public method to
`LLMService`:

```python
def respond(
    self,
    messages: list[Message],
    system: str | None = None,
    *,
    profile: str = "default",
    provider: str | None = None,
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> Any:  # the raw litellm response (choices[0].message has content + tool_calls; .usage present)
    resolved = resolve_profile(self._settings, profile, provider=provider, model=model)
    extra: dict[str, Any] = {}
    if tools:
        extra["tools"] = tools
        extra["tool_choice"] = "auto"
    return self._call(self._with_system(messages, system), resolved, **extra)
```

`complete()` is refactored to call `respond()` and extract text — removing the
existing duplication (both wrapped `_call`). This is the **only** modification to
the `llm` battery; profiles, cost metrics, exhaustion, and the key fail-fast are
unchanged and shared by both paths.

## Agent module (`src/{{package_name}}/{% if "agents" in batteries %}agents{% endif %}/`)

- **`tools.py`** — `ToolContext(session)`, `Tool{name, description, parameters, handler}`,
  `ToolRegistry` (`register` / `schemas` → OpenAI function shape / `dispatch`), and
  `default_registry()` shipping **read-only** `Item` tools: `search_items(query)`
  and `get_item(id)` over the existing `db/repository.py` + a direct `session.get`.
  **Read-only by design** — no write tools, so the LLM can inspect domain data but
  never mutate it (safe-by-default, house value). Tools return strings (JSON for
  data); handlers take `(args: dict, ctx: ToolContext)`.

- **`runner.py`** — `AgentRunner(service: LLMService, *, metrics=agent_metrics)` with:
  ```python
  def run(self, messages, system=None, *, profile="default",
          registry=None, context=None) -> RunResult: ...
  ```
  The bounded loop, mirroring how the framework's own `review/agentic.py` drives
  tool use:
  1. `response = service.respond(msgs, system, profile=profile, tools=registry.schemas())`
  2. `message = response.choices[0].message`; if no `tool_calls` → terminal:
     record `runs_total{outcome="completed"}`, return `RunResult(text, "completed", …)`.
  3. else append the assistant message, then for each `tool_call`: `registry.dispatch(name, json.loads(args), context)`, record `tool_calls_total{tool, outcome}`, append a correlated `{"role":"tool","tool_call_id":…,"content":result}`. Repeat.
  4. After `agent_max_iterations` (new agents-guarded setting, default 5): record
     `runs_total{outcome="max_iterations"}`, return the best text + the step trace.
     Hitting the cap is an *outcome*, not an exception.

  `RunResult{text: str, outcome: str, iterations: int, tool_calls: list[str]}`.
  `LLMExhausted`/`LLMError` from `respond()` propagate (the route maps them).

- **`metrics.py`** — hand-rolled exposition singleton (`agent_metrics`):
  `app_agent_tool_calls_total{tool, outcome}` and
  `app_agent_runs_total{outcome ∈ completed|max_iterations|error}`. Wired into
  `/metrics` via `routes/health.py.jinja` under the `agents` guard. The loop's
  *model* calls are already counted in `app_llm_*` (per profile) by `LLMService`,
  so agent model-cost shows on the llm panels and tool/run health on the agent
  panels. No new errors module — reuse `llm`'s `LLMError`/`LLMExhausted`.

## Route

`routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja` (auto-discovered),
`POST /agents/run`, body `{prompt: str, system?: str, profile?: str = "default"}`.
Builds an `AgentRunner(LLMService(settings))`, a `ToolContext(session)` from a
`SessionDep` (the read-only Item tools need a DB session), runs the default
registry, returns `{text, outcome, iterations, tool_calls}`. Error mapping mirrors
`/llm/complete`: `LLMExhausted` → 503, other → 502.

## Settings

One agents-guarded field added to `Settings`: `agent_max_iterations: int = 5`
(env `APP_AGENT_MAX_ITERATIONS`).

## Observability

`obs="in-process"` — agents owes an alert + dashboard:
- **Alert** (`agents_alerts.yml`): the run failure rate —
  `app_agent_runs_total{outcome=~"error|max_iterations"}` as a share of all runs —
  exceeding a threshold (a wedged or non-converging agent is the failure mode that
  matters).
- **Dashboard** (`agents.json`): two panels over the metrics that exist — tool
  calls by tool + outcome (`sum by (tool, outcome) (rate(app_agent_tool_calls_total[5m]))`)
  and run outcomes (`sum by (outcome) (rate(app_agent_runs_total[5m]))`). Agent
  **cost** lives on the existing `llm` dashboard (the loop's model calls are
  `app_llm_cost_usd_total{profile}`), so it is not duplicated here.

`test_obs_completeness` passes for `agents` rendered alone (it adds its own alert +
dashboard, no scrape/service) — no obs-test change needed.

## Cross-cutting

- **`requires` ↔ acceptance test:** `agents` requires `llm`, so the **acceptance
  test renders the dependency-closed set** (`resolve(["agents"])` =
  `["agents","llm"]`, as the CLI does) and runs it — mirroring the
  `claudesubscriptioncli` acceptance test. The obs test needs no change.
- **Read-only:** no write tools; no DB migration (the Item tools read the existing
  `items` table).
- The model-call path is unchanged from `llm` — exhaustion, profiles, and cost all
  behave identically inside the loop.

## Testing

- **Hermetic loop unit tests** (no DB, no network): a custom registry of
  pure-function tools + a fake `respond` returning canned responses (tool-call
  round then a final answer). Prove: tool dispatch + `tool_call_id` correlation,
  the iteration cap (`max_iterations` outcome), tool/run metric labels, and that
  `run(profile="sub")` passes the profile through to `respond`.
- **Functional tests** (Postgres): the real `Item` tools — `get_item`,
  `search_items`, missing-id graceful path — over a seeded `items` table.
- **Route test:** `POST /agents/run` drives a tool round then a final answer
  (mocked litellm), asserts `outcome="completed"` + the tool was called.
- **Render + acceptance** with `requires` resolved; obs-completeness green;
  eval-fixture coupling checked; clean first pre-commit.
- The `llm` `respond()`/`complete()` refactor: existing llm unit + functional
  tests must stay green (behavior-preserving).

## Out of scope

- Write / mutating tools (read-only only).
- Multi-agent / sub-agent orchestration; planning; memory/state across runs.
- Streaming the loop.
- Parallel tool execution (tools dispatch sequentially).

## PLAN re-keying

- **FWK14** → this design: `--with agents` tool-calling loop, `requires=("llm",)`.
- The stale `2026-06-14-agents-battery-loop.md` plan is **superseded** by the new
  FWK14 plan derived from this spec.
