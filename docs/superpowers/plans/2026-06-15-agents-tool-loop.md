# `--with agents` Tool-Calling Loop (FWK14) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **⚠ Builds on the merged `llm` battery (v0.2.8).** Branch `fwk14-agents-loop` off `master`. Supersedes the stale `2026-06-14-agents-battery-loop.md`.

**Goal:** Add the `--with agents` battery — a bounded tool-calling agent loop on top of the `llm` runtime: a tool registry, read-only `Item` tools, an `AgentRunner` loop, a `POST /agents/run` route, and tool/run observability.

**Architecture:** `agents` is a separate battery (`requires=("llm",)`, `obs="in-process"`). One small `llm`-battery change adds `LLMService.respond()` (raw tool-capable completion; `complete()` refactored onto it). A new `agents/` module holds `tools.py` (read-only Item tools), `runner.py` (the loop, delegating model calls to `LLMService.respond`), and `metrics.py` (tool/run series). The agent inherits profiles + the subscription backend for free.

**Tech Stack:** Python 3.12, Copier/Jinja template payload, LiteLLM (`litellm.completion(tools=…, tool_choice="auto")`), FastAPI, SQLAlchemy, pytest. Spec: `docs/superpowers/specs/2026-06-15-agents-tool-loop-design.md`.

---

## Execution notes

- **Review-model policy** ([[subagent-review-model-pattern]]): Sonnet implementers; **Opus** on the `respond()` seam (Task 2) + the runner loop (Task 6) + branch-end. **Implementers stage, controller commits** ([[subagent-implementers-stop-before-commit]], [[commit-gate-hook-timing]] — separate `git add` then `git commit`; if a `git add` is gate-blocked, stage `PLAN.md`/`ACTION_LOG.md` first).
- **Template-payload TDD loop** ([[template-payload-tdd-loop]]): render the **resolved** set (`resolve(['agents'])` → `['agents','llm']`), `uv sync`, run in the render. Grep the RENDERED project.
- **Do NOT regress the `llm` battery:** Task 2 refactors `complete()` onto `respond()` — the existing llm unit + functional tests must stay green (behavior-preserving).
- Release **v0.2.9** after merge.

### Helper: render the resolved agents project (run from repo root)
```bash
export TMPDIR=/var/tmp
rm -rf /tmp/agwork
uv run python -c "from pathlib import Path; from framework_cli.batteries import resolve; from framework_cli.copier_runner import render_project; render_project(Path('/tmp/agwork'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':resolve(['agents'])})"
cd /tmp/agwork && uv sync && cd -
```
(Plain `uv sync`.) The `agents` module dir is `src/framework_cli/template/src/{{package_name}}/{% if "agents" in batteries %}agents{% endif %}/`; the `llm` module dir is the `{% if "llm" in batteries %}llm{% endif %}/` sibling.

---

## File Structure

- Modify: `src/framework_cli/batteries.py` — `agents` BatterySpec (framework source).
- Modify: `<llm-dir>/service.py` — add `respond()`, refactor `complete()` (the only llm change).
- Modify: `.../config/settings.py.jinja` — `agent_max_iterations` (agents guard).
- Create: `<agents-dir>/__init__.py`, `tools.py`, `runner.py`, `metrics.py`.
- Create: `.../routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja` — `POST /agents/run`.
- Modify: `.../routes/health.py.jinja` — append agent metrics under the agents guard.
- Create: obs `agents_alerts.yml` + `agents.json` (brace-conditional jinja).
- Create: unit + functional tests (brace-conditional jinja).
- Modify: `tests/acceptance/test_rendered_project.py` — agents acceptance (resolved set).
- Framework source: `PLAN.md`, `ACTION_LOG.md` per commit; release files (Task 9).

---

## Task 1: `agents` BatterySpec + obs alert & dashboard

**Files:** Modify `batteries.py`; Create the alert + dashboard jinja files.

- [ ] **Step 1: Add the BatterySpec** (after `"llm"`):
```python
    "agents": BatterySpec(
        "agents",
        "LLM agent: a bounded tool-calling loop over read-only domain tools "
        "(POST /agents/run). requires the llm battery",
        requires=("llm",),
        obs="in-process",
    ),
```

- [ ] **Step 2: Create the alert** `infra/observability/prometheus/alerts/{{ 'agents_alerts.yml' if 'agents' in batteries else '' }}.jinja`:
```yaml
groups:
- name: agents
  rules:
  - alert: HighAgentRunFailureRate
    # Share of agent runs that errored or hit the iteration cap (a non-converging or
    # failing agent). Tune the 0.2 threshold per app.
    expr: sum(rate(app_agent_runs_total{outcome=~"error|max_iterations"}[5m])) / clamp_min(sum(rate(app_agent_runs_total[5m])), 1) > 0.2
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: Over 20% of agent runs failed or hit the iteration cap (check tools, prompts, and the model)
```

- [ ] **Step 3: Create the dashboard** `infra/observability/grafana/dashboards/{{ 'agents.json' if 'agents' in batteries else '' }}.jinja`:
```json
{
  "uid": "agents",
  "title": "Agents",
  "tags": ["agents"],
  "schemaVersion": 39,
  "version": 1,
  "time": {"from": "now-1h", "to": "now"},
  "panels": [
    {
      "id": 1,
      "title": "Tool calls by tool and outcome",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "targets": [
        {"refId": "A", "expr": "sum by (tool, outcome) (rate(app_agent_tool_calls_total[5m]))", "legendFormat": "__auto"}
      ],
      "fieldConfig": {"defaults": {"unit": "ops"}, "overrides": []}
    },
    {
      "id": 2,
      "title": "Run outcomes",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "targets": [
        {"refId": "A", "expr": "sum by (outcome) (rate(app_agent_runs_total[5m]))", "legendFormat": "__auto"}
      ],
      "fieldConfig": {"defaults": {"unit": "ops"}, "overrides": []}
    }
  ]
}
```

- [ ] **Step 4: Verify.** `uv run python -c "from framework_cli.batteries import resolve; print(resolve(['agents']))"` → `['agents','llm']`. Then `uv run pytest tests/test_batteries.py "tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface[agents]" tests/test_copier_runner.py -q` → PASS (agents renders alone with its own alert+dashboard → `in-process` holds). `uv run ruff check src/framework_cli/batteries.py`.

- [ ] **Step 5: Stage** `batteries.py` + the two jinja files + PLAN/ACTION_LOG; commit `feat(fwk14): agents BatterySpec + obs alert & dashboard`.

---

## Task 2: `LLMService.respond()` + refactor `complete()` (the llm seam, Opus review)

**Files:** Modify `<llm-dir>/service.py`; Modify the llm unit test file.

- [ ] **Step 1: Append failing tests** (to the llm unit test file; `_psettings`/`_Resp`/`_new_metrics` helpers exist):
```python
def test_respond_returns_raw_response_and_passes_tools(monkeypatch):
    import litellm

    from {{ package_name }}.llm.service import LLMService

    captured = {}
    monkeypatch.setattr(litellm, "completion", lambda **k: captured.update(k) or _Resp("hi"))
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
    resp = LLMService(_psettings(), metrics=_new_metrics()).respond(
        [{"role": "user", "content": "x"}], tools=tools
    )
    assert resp.choices[0].message.content == "hi"  # raw response, not extracted text
    assert captured["tools"] == tools
    assert captured["tool_choice"] == "auto"


def test_respond_omits_tools_when_none(monkeypatch):
    import litellm

    from {{ package_name }}.llm.service import LLMService

    captured = {}
    monkeypatch.setattr(litellm, "completion", lambda **k: captured.update(k) or _Resp("h"))
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    LLMService(_psettings(), metrics=_new_metrics()).respond([{"role": "user", "content": "x"}])
    assert "tools" not in captured and "tool_choice" not in captured
```
(The existing `complete()` tests stay — they prove the refactor is behavior-preserving.)

- [ ] **Step 2: Render the resolved set + confirm red** (`respond` missing).

- [ ] **Step 3: Add `respond()` + refactor `complete()`** in `service.py`. Add `respond()` immediately before `complete()`:
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
    ) -> Any:
        """Raw model response (choices[0].message has content + tool_calls; .usage present).

        The tool-capable lower-level call the agent loop builds on. Honors profiles, cost
        metrics, exhaustion, and the key fail-fast exactly as complete() does.
        """
        resolved = resolve_profile(
            self._settings, profile, provider=provider, model=model
        )
        extra: dict[str, Any] = {}
        if tools:
            extra["tools"] = tools
            extra["tool_choice"] = "auto"
        return self._call(self._with_system(messages, system), resolved, **extra)
```
Replace the body of `complete()` to delegate:
```python
    def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        *,
        profile: str = "default",
        provider: str | None = None,
        model: str | None = None,
    ) -> CompletionResult:
        response = self.respond(
            messages, system, profile=profile, provider=provider, model=model
        )
        text = response.choices[0].message.content or ""
        return CompletionResult(text=text, usage=self._usage_dict(response))
```
(Leave `complete_structured` unchanged — it passes `response_format`, a different extra.)

- [ ] **Step 4: Re-render + run the FULL llm unit + functional suites** → all green (the new respond tests + every existing complete/profile/exhaustion test). `uv run mypy src/demo/llm` + ruff clean.

- [ ] **Step 5: Stage** `service.py` + the unit test + PLAN/ACTION_LOG; commit `feat(fwk14): LLMService.respond() seam + complete() refactor`. (Opus code-quality review after — focus: behavior-preservation of complete(), respond() returns the raw response, tools/tool_choice only when tools given.)

---

## Task 3: `agent_max_iterations` setting

**Files:** Modify `.../config/settings.py.jinja`.

- [ ] **Step 1: Add the field** inside an agents-guarded block (after the llm settings block):
```jinja
{%- if "agents" in batteries %}

    # Agent tool-loop: hard cap on tool-calling rounds per run (APP_AGENT_MAX_ITERATIONS).
    agent_max_iterations: int = 5
{%- endif %}
```

- [ ] **Step 2: Verify.** Render the resolved set, then `cd /tmp/agwork && uv run python -c "from demo.config.settings import Settings; print(Settings(llm_api_key='k').agent_max_iterations)"` → `5`. A no-agents (`['llm']`) render omits it: `grep -c agent_max_iterations /tmp/<llm-only-render>/src/demo/config/settings.py` → `0`.

- [ ] **Step 3: Format-check + stage**; `feat(fwk14): agent_max_iterations setting`.

---

## Task 4: `agents/tools.py` — registry + read-only Item tools (TDD)

**Files:** Create `<agents-dir>/__init__.py`, `<agents-dir>/tools.py`; Create the unit test file (hermetic) + a functional test (DB).

- [ ] **Step 1: Write the hermetic registry test** + the functional Item-tools test.
Unit test `tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja`:
```python
"""agents battery — hermetic tool-registry + loop tests (no network, no DB)."""


def test_registry_dispatch_and_schemas():
    from {{ package_name }}.agents.tools import Tool, ToolContext, ToolRegistry

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="echo",
            description="echo back",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            handler=lambda args, ctx: f"echo:{args['x']}",
        )
    )
    schemas = reg.schemas()
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "echo"
    assert reg.dispatch("echo", {"x": "hi"}, ToolContext(session=None)) == "echo:hi"


def test_registry_unknown_tool_returns_error_string():
    from {{ package_name }}.agents.tools import ToolContext, ToolRegistry

    out = ToolRegistry().dispatch("nope", {}, ToolContext(session=None))
    assert out.startswith("error:") and "unknown tool" in out.lower()
```
Functional test `tests/functional/{{ 'test_agents_tools.py' if 'agents' in batteries else '' }}.jinja`:
```python
"""agents battery — read-only Item tools over a real Postgres."""

import pytest
from sqlalchemy import Engine

from {{ package_name }}.agents.tools import ToolContext, default_registry
from {{ package_name }}.db.engine import build_session_factory
from {{ package_name }}.db.repository import create_item


@pytest.fixture
def session(engine: Engine):
    factory = build_session_factory(engine)
    with factory() as s:
        create_item(s, "alpha widget")
        create_item(s, "beta gadget")
        yield s
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE items RESTART IDENTITY CASCADE"))
        conn.commit()


def test_get_item_returns_known_row(session):
    out = default_registry().dispatch("get_item", {"id": 1}, ToolContext(session=session))
    assert "alpha widget" in out


def test_get_item_missing_is_graceful(session):
    out = default_registry().dispatch("get_item", {"id": 9999}, ToolContext(session=session))
    assert "not found" in out.lower()


def test_search_items_filters_by_name(session):
    out = default_registry().dispatch("search_items", {"query": "beta"}, ToolContext(session=session))
    assert "beta gadget" in out and "alpha widget" not in out
```
Render the resolved set; confirm RED (`No module named 'demo.agents.tools'`).

- [ ] **Step 2: Implement `__init__.py`**: `"""LLM agent: tool-calling loop over the llm runtime (agents battery)."""`

- [ ] **Step 3: Implement `tools.py`**:
```python
"""Tool registry + read-only Item tools for the agent loop.

Read-only by design: tools query the existing items table directly (no repository writes,
no mutating tools), so the LLM can inspect domain data but never change it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ..db.models import Item
from ..db.repository import list_items


@dataclass
class ToolContext:
    session: Session | None


ToolHandler = Callable[[dict[str, Any], ToolContext], str]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any], ctx: ToolContext) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"error: unknown tool {name!r}"
        return tool.handler(args, ctx)


def _get_item(args: dict[str, Any], ctx: ToolContext) -> str:
    if ctx.session is None:
        return "error: no database session"
    item = ctx.session.get(Item, int(args["id"]))
    if item is None:
        return f"item {args['id']} not found"
    return json.dumps({"id": item.id, "name": item.name})


def _search_items(args: dict[str, Any], ctx: ToolContext) -> str:
    if ctx.session is None:
        return "error: no database session"
    query = str(args.get("query", "")).lower()
    matches = [
        {"id": i.id, "name": i.name}
        for i in list_items(ctx.session, limit=100)
        if query in i.name.lower()
    ]
    return json.dumps(matches)


def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="get_item",
            description="Fetch a single item by its integer id.",
            parameters={
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
            handler=_get_item,
        )
    )
    reg.register(
        Tool(
            name="search_items",
            description="Search items whose name contains the query substring.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=_search_items,
        )
    )
    return reg
```

- [ ] **Step 4: Re-render + run** the hermetic test (`uv run pytest tests/unit/test_agents_unit.py -k registry`) green, then the functional test (`TMPDIR=/var/tmp ... tests/functional/test_agents_tools.py`, needs Docker) green. mypy + ruff clean on `src/demo/agents`.

- [ ] **Step 5: Stage** `__init__.py`, `tools.py`, both test files + PLAN/ACTION_LOG; `feat(fwk14): agent tool registry + read-only Item tools`.

---

## Task 5: `agents/metrics.py` — tool/run metrics (TDD)

**Files:** Create `<agents-dir>/metrics.py`; Modify the unit test file.

- [ ] **Step 1: Append failing tests:**
```python
def test_agent_metrics_tool_calls_and_runs():
    from {{ package_name }}.agents.metrics import AgentMetrics

    m = AgentMetrics()
    m.record_tool_call("get_item", "success")
    m.record_tool_call("get_item", "success")
    m.record_tool_call("search_items", "error")
    m.record_run("completed")
    m.record_run("max_iterations")
    out = m.render_prometheus()
    assert 'app_agent_tool_calls_total{tool="get_item",outcome="success"} 2' in out
    assert 'app_agent_tool_calls_total{tool="search_items",outcome="error"} 1' in out
    assert 'app_agent_runs_total{outcome="completed"} 1' in out
    assert 'app_agent_runs_total{outcome="max_iterations"} 1' in out
    assert 'app_agent_runs_total{outcome="error"} 0' in out
    assert "# TYPE app_agent_tool_calls_total counter" in out
```

- [ ] **Step 2: Render + confirm red.**

- [ ] **Step 3: Implement `metrics.py`** (house hand-rolled exposition, mirroring `llm/metrics.py`):
```python
"""Process-wide agent metrics — hand-rolled Prometheus exposition (no client lib).

Tool calls and run outcomes; the loop's MODEL calls are counted in app_llm_* (per profile)
by LLMService, so model cost is on the llm panels and tool/run health here.
"""

from __future__ import annotations

import threading

RUN_OUTCOMES = ("completed", "max_iterations", "error")


class AgentMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tool_calls: dict[tuple[str, str], int] = {}  # (tool, outcome) -> count
        self._runs: dict[str, int] = {o: 0 for o in RUN_OUTCOMES}

    def record_tool_call(self, tool: str, outcome: str) -> None:
        if outcome not in ("success", "error"):
            return
        with self._lock:
            key = (tool, outcome)
            self._tool_calls[key] = self._tool_calls.get(key, 0) + 1

    def record_run(self, outcome: str) -> None:
        with self._lock:
            if outcome in self._runs:
                self._runs[outcome] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            tool_calls = "".join(
                f'app_agent_tool_calls_total{{tool="{t}",outcome="{o}"}} {n}\n'
                for (t, o), n in sorted(self._tool_calls.items())
            )
            runs = dict(self._runs)
        return (
            "# HELP app_agent_tool_calls_total Agent tool invocations by tool and outcome\n"
            "# TYPE app_agent_tool_calls_total counter\n"
            f"{tool_calls}"
            "# HELP app_agent_runs_total Agent run loops by terminal outcome\n"
            "# TYPE app_agent_runs_total counter\n"
            + "".join(
                f'app_agent_runs_total{{outcome="{o}"}} {runs[o]}\n' for o in RUN_OUTCOMES
            )
        )

    def reset(self) -> None:
        with self._lock:
            self._tool_calls = {}
            self._runs = {o: 0 for o in RUN_OUTCOMES}


agent_metrics = AgentMetrics()
"""Process-wide singleton imported by the runner and the /metrics route."""
```

- [ ] **Step 4: Re-render + run green; ruff/mypy clean. Stage**; `feat(fwk14): agent tool/run metrics`.

---

## Task 6: `agents/runner.py` — the bounded loop (TDD, Opus review)

**Files:** Create `<agents-dir>/runner.py`; Modify the unit test file.

- [ ] **Step 1: Append failing loop tests** (hermetic — a stub service + fake responses, no LLMService/litellm):
```python
class _ToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"
        self.function = type("F", (), {"name": name, "arguments": arguments})()


class _Msg:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Resp:
    def __init__(self, content, tool_calls=None):
        self.choices = [type("C", (), {"message": _Msg(content, tool_calls)})()]


class _StubService:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def respond(self, messages, system=None, *, profile="default", tools=None):
        self.calls.append({"messages": list(messages), "profile": profile, "tools": tools})
        return self._responses.pop(0)


def _echo_registry():
    from {{ package_name }}.agents.tools import Tool, ToolRegistry

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="lookup",
            description="lookup",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
            handler=lambda args, ctx: f"value-for-{args['q']}",
        )
    )
    return reg


def test_run_dispatches_tool_then_completes():
    from {{ package_name }}.agents.metrics import AgentMetrics
    from {{ package_name }}.agents.runner import AgentRunner, RunResult
    from {{ package_name }}.agents.tools import ToolContext

    svc = _StubService([
        _Resp(None, tool_calls=[_ToolCall("c1", "lookup", '{"q": "x"}')]),
        _Resp("final answer", tool_calls=None),
    ])
    m = AgentMetrics()
    result = AgentRunner(svc, max_iterations=5, metrics=m).run(
        [{"role": "user", "content": "do it"}], registry=_echo_registry(), context=ToolContext(session=None)
    )
    assert isinstance(result, RunResult)
    assert result.text == "final answer"
    assert result.outcome == "completed"
    assert result.iterations == 2
    assert result.tool_calls == ["lookup"]
    # second model call saw the tool result appended
    assert any(
        msg.get("role") == "tool" and "value-for-x" in msg.get("content", "")
        for msg in svc.calls[1]["messages"]
    )
    out = m.render_prometheus()
    assert 'app_agent_tool_calls_total{tool="lookup",outcome="success"} 1' in out
    assert 'app_agent_runs_total{outcome="completed"} 1' in out


def test_run_passes_profile_through():
    from {{ package_name }}.agents.runner import AgentRunner
    from {{ package_name }}.agents.tools import ToolContext

    svc = _StubService([_Resp("done", tool_calls=None)])
    AgentRunner(svc, max_iterations=5).run(
        [{"role": "user", "content": "x"}], profile="sub", context=ToolContext(session=None)
    )
    assert svc.calls[0]["profile"] == "sub"


def test_run_stops_at_iteration_cap():
    from {{ package_name }}.agents.metrics import AgentMetrics
    from {{ package_name }}.agents.runner import AgentRunner
    from {{ package_name }}.agents.tools import ToolContext

    always = [_Resp(None, tool_calls=[_ToolCall("c", "lookup", '{"q": "x"}')]) for _ in range(10)]
    svc = _StubService(always)
    m = AgentMetrics()
    result = AgentRunner(svc, max_iterations=3, metrics=m).run(
        [{"role": "user", "content": "loop"}], registry=_echo_registry(), context=ToolContext(session=None)
    )
    assert result.outcome == "max_iterations"
    assert result.iterations == 3
    assert 'app_agent_runs_total{outcome="max_iterations"} 1' in m.render_prometheus()


def test_run_records_error_outcome_on_llm_error(monkeypatch):
    from {{ package_name }}.agents.metrics import AgentMetrics
    from {{ package_name }}.agents.runner import AgentRunner
    from {{ package_name }}.agents.tools import ToolContext
    from {{ package_name }}.llm.errors import LLMError

    class _Boom:
        def respond(self, *a, **k):
            raise LLMError("kaboom")

    import pytest

    m = AgentMetrics()
    with pytest.raises(LLMError):
        AgentRunner(_Boom(), max_iterations=5, metrics=m).run(
            [{"role": "user", "content": "x"}], context=ToolContext(session=None)
        )
    assert 'app_agent_runs_total{outcome="error"} 1' in m.render_prometheus()
```

- [ ] **Step 2: Render + confirm red.**

- [ ] **Step 3: Implement `runner.py`**:
```python
"""AgentRunner — a bounded tool-calling loop over LLMService.respond().

Read-only tools; capped at max_iterations. The loop's model calls are recorded in app_llm_*
(per profile) by the service; this records tool calls + the run's terminal outcome.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from ..llm.errors import LLMError
from .metrics import AgentMetrics, agent_metrics
from .tools import ToolContext, ToolRegistry, default_registry


class _Responder(Protocol):
    def respond(
        self, messages: list[dict[str, Any]], system: str | None = ..., *,
        profile: str = ..., tools: list[dict[str, Any]] | None = ...,
    ) -> Any: ...


@dataclass
class RunResult:
    text: str
    outcome: str  # "completed" | "max_iterations" | "error"
    iterations: int
    tool_calls: list[str]


class AgentRunner:
    def __init__(
        self, service: _Responder, *, max_iterations: int = 5, metrics: AgentMetrics | None = None
    ) -> None:
        self._service = service
        self._max_iterations = max_iterations
        self._metrics = metrics or agent_metrics

    def run(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        *,
        profile: str = "default",
        registry: ToolRegistry | None = None,
        context: ToolContext | None = None,
    ) -> RunResult:
        registry = registry or default_registry()
        context = context or ToolContext(session=None)
        msgs = list(messages)
        called: list[str] = []
        last_text = ""
        try:
            for iteration in range(1, self._max_iterations + 1):
                response = self._service.respond(
                    msgs, system, profile=profile, tools=registry.schemas()
                )
                message = response.choices[0].message
                last_text = message.content or last_text
                tool_calls = getattr(message, "tool_calls", None)
                if not tool_calls:
                    self._metrics.record_run("completed")
                    return RunResult(message.content or "", "completed", iteration, called)
                msgs.append(message)
                for call in tool_calls:
                    name = call.function.name
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        result = registry.dispatch(name, args, context)
                        outcome = "error" if result.startswith("error:") else "success"
                    except Exception as exc:  # noqa: BLE001  # malformed args / handler crash
                        result = f"error: {exc}"
                        outcome = "error"
                    called.append(name)
                    self._metrics.record_tool_call(name, outcome)
                    msgs.append({"role": "tool", "tool_call_id": call.id, "content": result})
        except LLMError:
            self._metrics.record_run("error")
            raise
        self._metrics.record_run("max_iterations")
        return RunResult(last_text, "max_iterations", self._max_iterations, called)
```

- [ ] **Step 4: Re-render + run the full unit suite green; mypy + ruff clean. Stage**; `feat(fwk14): bounded agent run loop`. (Opus code-quality review after — focus: loop-bound correctness, tool_result correlation by tool_call_id, the error-outcome path, no unbounded growth, read-only guarantee.)

---

## Task 7: `POST /agents/run` route + /metrics wiring (TDD, DB)

**Files:** Create `.../routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja`; Modify `.../routes/health.py.jinja`; Create a functional route test.

- [ ] **Step 1: Failing functional test** `tests/functional/{{ 'test_agents_run.py' if 'agents' in batteries else '' }}.jinja`:
```python
"""agents battery — POST /agents/run over seeded items (mocked litellm)."""

import litellm
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from {{ package_name }}.config.settings import Settings
from {{ package_name }}.db.engine import build_session_factory, get_session
from {{ package_name }}.db.repository import create_item
from {{ package_name }}.main import create_app


class _ToolCall:
    id = "c1"
    type = "function"

    class function:
        name = "search_items"
        arguments = '{"query": "alpha"}'


class _Step1:
    content = None
    tool_calls = [_ToolCall()]


class _Step2:
    content = "Found: alpha widget"
    tool_calls = None


class _Usage:
    prompt_tokens = 4
    completion_tokens = 2
    prompt_tokens_details = None


def _resp(message):
    return type("R", (), {"choices": [type("C", (), {"message": message})()], "usage": _Usage()})()


@pytest.fixture
def client(engine: Engine, monkeypatch):
    factory = build_session_factory(engine)
    with factory() as s:
        create_item(s, "alpha widget")
        s.commit()
    responses = [_resp(_Step1()), _resp(_Step2())]
    monkeypatch.setattr(litellm, "completion", lambda **_: responses.pop(0))
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)

    def override():
        with factory() as session:
            yield session

    app = create_app(Settings(llm_api_key="k", database_url=str(engine.url), serve_spa=False))
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE items RESTART IDENTITY CASCADE"))
        conn.commit()


def test_run_route_executes_tool_then_answers(client):
    r = client.post("/agents/run", json={"prompt": "find alpha"})
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "completed"
    assert body["text"] == "Found: alpha widget"
    assert body["tool_calls"] == ["search_items"]


def test_metrics_endpoint_includes_agent_series(client):
    client.post("/agents/run", json={"prompt": "find alpha"})
    out = client.get("/metrics").text
    assert "app_agent_tool_calls_total" in out
    assert "app_agent_runs_total" in out
```
Render the resolved set, run → confirm RED (404 on `/agents/run`).

- [ ] **Step 2: Implement the route** `routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja`:
```python
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from {{ package_name }}.agents.metrics import agent_metrics
from {{ package_name }}.agents.runner import AgentRunner
from {{ package_name }}.agents.tools import ToolContext, default_registry
from {{ package_name }}.db.engine import get_session
from {{ package_name }}.llm.errors import LLMExhausted
from {{ package_name }}.llm.service import LLMService

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


class RunRequest(BaseModel):
    prompt: str
    system: str | None = None
    profile: str = "default"


class RunResponse(BaseModel):
    text: str
    outcome: str
    iterations: int
    tool_calls: list[str]


@router.post("/agents/run", response_model=RunResponse)
def run(body: RunRequest, request: Request, session: SessionDep) -> RunResponse:
    """Agentic run — the model may call read-only Item tools, bounded by agent_max_iterations."""
    settings = request.app.state.settings
    runner = AgentRunner(
        LLMService(settings),
        max_iterations=settings.agent_max_iterations,
        metrics=agent_metrics,
    )
    try:
        result = runner.run(
            [{"role": "user", "content": body.prompt}],
            system=body.system,
            profile=body.profile,
            registry=default_registry(),
            context=ToolContext(session=session),
        )
    except LLMExhausted as exc:
        raise HTTPException(status_code=503, detail="LLM provider exhausted") from exc
    except Exception as exc:  # noqa: BLE001  # LLMError and any other provider/transport failure
        raise HTTPException(status_code=502, detail="LLM provider error") from exc
    return RunResponse(
        text=result.text,
        outcome=result.outcome,
        iterations=result.iterations,
        tool_calls=result.tool_calls,
    )
```

- [ ] **Step 3: Wire agent metrics into `/metrics`** — in `routes/health.py.jinja`, after the `{%- if "llm" in batteries %}` metrics block, add:
```jinja
{%- if "agents" in batteries %}

    from {{ package_name }}.agents.metrics import agent_metrics

    body += agent_metrics.render_prometheus()
{%- endif %}
```

- [ ] **Step 4: Re-render + run** the functional test green (needs Docker). ruff + mypy clean on `src/demo/routes/agents.py`.

- [ ] **Step 5: Stage** the route, health.py, the functional test + PLAN/ACTION_LOG; `feat(fwk14): POST /agents/run + /metrics wiring`.

---

## Task 8: Full render + acceptance (resolved) + obs + eval coupling

**Files:** Modify `tests/acceptance/test_rendered_project.py`.

- [ ] **Step 1: Add the acceptance test** (mirror the claudesubscriptioncli one; render the resolved set):
```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_agents_battery_passes(tmp_path: Path):
    # agents requires llm, so render the dependency-closed set (as the CLI does).
    data = {**DATA, "batteries": resolve(["agents"])}
    dest = tmp_path / "demo"
    render_project(dest, data)

    assert (dest / "src" / "demo" / "agents" / "runner.py").exists(), (
        "agents/runner.py was not rendered"
    )
    assert (dest / "src" / "demo" / "routes" / "agents.py").exists(), (
        "routes/agents.py was not rendered"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the agents battery project:\n"
        + result.stdout
        + result.stderr
    )
```
(`resolve` is already imported at the top of the file from the FWK16 work.)

- [ ] **Step 2: Run it** — `TMPDIR=/var/tmp uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_with_agents_battery_passes" -q` → PASS.

- [ ] **Step 3: Source gate + obs + copier.** `uv run pytest -q -k "not acceptance" && uv run ruff check . && uv run ruff format --check . && uv run mypy src` → green. `uv run pytest tests/test_obs_completeness.py tests/test_copier_runner.py -q` → PASS.

- [ ] **Step 4: Grep the RENDERED resolved project** — confirm `app_agent_*` series consistent between `metrics.py`, the alert, and the dashboard; no stray references. Eval-fixture coupling: `git grep -l "app_agent_\|/agents/run\|agents.runner" tests/eval/fixtures/ || echo "no coupling"`.

- [ ] **Step 5: Stage** the acceptance file (+ any fixups) + PLAN/ACTION_LOG; `test(fwk14): agents acceptance (resolved set)`.

---

## Task 9: Branch-end review + release v0.2.9

- [ ] **Step 1: Branch-end Opus review** ([[subagent-review-model-pattern]]) over the full branch diff. Focus: the `llm` change is ONLY `respond()` + the behavior-preserving `complete()` refactor (existing llm tests green); loop correctness (bound, tool_call_id correlation, error outcome, read-only); guard isolation (no agents symbols in a no-agents render; agents requires llm); obs series ↔ metrics/alert/dashboard consistency; profiles flow through (`run(profile="sub")`). Address findings; re-run Task 8.
- [ ] **Step 2: Verify subagent commits landed** ([[subagent-implementers-stop-before-commit]]): `git status --short && git log --oneline master..HEAD`.
- [ ] **Step 3: PLAN/ACTION_LOG.** Move FWK14 → Done; append the completion entry. Commit.
- [ ] **Step 4: Cut v0.2.9** ([[release-cut-procedure]]): bump `pyproject` 0.2.8→0.2.9, `uv lock`, `DOGFOOD_COMMIT`→`"v0.2.9"`; `uv build`; version-consistency tests; commit `chore(release): v0.2.9`. Bundle into the FWK14 PR.
- [ ] **Step 5: Finish the branch** ([[finishing-a-development-branch]]): push `fwk14-agents-loop`, open one PR, confirm `gate`/`build`/`render-complete` green, squash-merge, tag `v0.2.9` → `release.yml`, verify the published Release, grep `master` for a marker ([[verify-master-content-after-pr-merge]]).

---

## Self-Review (completed by plan author)

- **Spec coverage:** battery + requires + in-process obs (Task 1) · `respond()` seam + `complete()` refactor (Task 2) · `agent_max_iterations` (Task 3) · read-only Item tools + registry (Task 4) · tool/run metrics (Task 5) · bounded loop with profile pass-through + error outcome (Task 6) · `POST /agents/run` + /metrics (Task 7) · acceptance with requires resolved + obs (Task 8) · release (Task 9). The obs-test needs no `requires` change (agents adds its own alert+dashboard, renders clean alone) — only the acceptance test resolves. Out of scope (write tools, multi-agent, memory, streaming, parallel dispatch) honored.
- **Type/name consistency:** `LLMService.respond(messages, system=None, *, profile, provider, model, tools=None)` · `ToolContext(session)` / `Tool` / `ToolRegistry.register/schemas/dispatch` / `default_registry()` · `AgentRunner(service, *, max_iterations=5, metrics=None).run(messages, system=None, *, profile="default", registry=None, context=None) -> RunResult{text,outcome,iterations,tool_calls}` · `AgentMetrics.record_tool_call(tool,outcome)` / `record_run(outcome)` · metrics `app_agent_tool_calls_total{tool,outcome}` / `app_agent_runs_total{outcome}` — consistent across tasks and with the route + dashboard + alert.
- **No placeholders:** every code/test/yaml/json block is complete.
