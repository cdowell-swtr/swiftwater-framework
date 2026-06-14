# `--with agents` Battery — Slice 2 (Agentic Loop) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **⚠ Execute only after FWK12 (runtime core) has merged to `master`.** This plan extends the FWK12 modules (`agents/service.py`, `agents/metrics.py`, `agents/errors.py`, `routes/agents.py`). Before starting, **reconcile each referenced signature against the landed FWK12 code** — if FWK12 shipped a method name or field differently than this plan assumes, follow the merged code and adjust the steps below. Start a fresh branch `fwk14-agents-loop` off the merged `master`.

**Goal:** Ship FWK14 — upgrade the `agents` battery from a completion service to a real agent: a tool registry, a bounded tool-calling run loop, a read-only `Item` DB tool, an agentic demo route, and loop/tool observability.

**Architecture:** Add `agents/tools.py` (a `ToolRegistry` + read-only `Item` tools doing direct SQLAlchemy reads — base `db/` files stay untouched), extend `AgentService` with `run()` (call → dispatch `tool_use` → `tool_result` → repeat, bounded by `agent_max_iterations`), extend `AgentMetrics` with tool-call + run-outcome series, and add `POST /agents/run`. Read-only only — the LLM cannot mutate state.

**Tech Stack:** Same as FWK12 — LiteLLM `litellm.completion(tools=…, tool_choice="auto")` (OpenAI tool shape), FastAPI, SQLAlchemy, pytest. Spec: `docs/superpowers/specs/2026-06-14-agents-battery-design.md`.

---

## Execution notes

- Same review-model policy, gate cadence, template-payload TDD loop, and commit-gate discipline as the FWK12 plan ([[subagent-review-model-pattern]], [[gate-cadence-framework-slices]], [[template-payload-tdd-loop]], [[commit-gate-hook-timing]]). Render helper is identical (`framework new /tmp/agentwork … --with agents`).
- **Loop unit tests are hermetic** (custom registry of pure-function tools, mocked LiteLLM, no DB). **Tool-data tests are functional** (real `Item` tools over a testcontainer Postgres, mocked LiteLLM). This split keeps loop logic provable without a database.
- No DB migration: the `Item` tools read the existing `items` table.

---

## File Structure

**Template payload (extends FWK12):**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "agents" in batteries %}agents{% endif %}/tools.py` — `ToolContext`, `Tool`, `ToolRegistry`, the read-only `Item` tools, `default_registry()`.
- Modify: `.../agents/service.py` — add `RunResult` + `AgentService.run()`.
- Modify: `.../agents/metrics.py` — add tool-call + run-outcome series.
- Create: `src/framework_cli/template/src/{{package_name}}/routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja` already exists — **modify** it to add `POST /agents/run`.
- Modify: `tests/unit/{{ 'test_agents_unit.py' ... }}.jinja` — loop + metrics unit tests.
- Create: `tests/functional/{{ 'test_agents_run.py' if 'agents' in batteries else '' }}.jinja` — `/agents/run` over seeded items (DB).

**Framework source:** `PLAN.md`, `ACTION_LOG.md` per commit.

---

## Task 1: Extend `AgentMetrics` with tool-call + run-outcome series (TDD, hermetic)

**Files:**
- Modify: `.../agents/metrics.py`
- Modify: `tests/unit/{{ 'test_agents_unit.py' ... }}.jinja`

- [ ] **Step 1: Append failing metrics tests**

```python
def test_metrics_record_tool_calls():
    from {{ package_name }}.agents.metrics import AgentMetrics

    m = AgentMetrics()
    m.record_tool_call("get_item", "success")
    m.record_tool_call("get_item", "success")
    m.record_tool_call("search_items", "error")
    out = m.render_prometheus()
    assert 'app_agent_tool_calls_total{tool="get_item",outcome="success"} 2' in out
    assert 'app_agent_tool_calls_total{tool="search_items",outcome="error"} 1' in out


def test_metrics_record_run_outcomes():
    from {{ package_name }}.agents.metrics import AgentMetrics

    m = AgentMetrics()
    m.record_run("completed")
    m.record_run("max_iterations")
    out = m.render_prometheus()
    assert 'app_agent_runs_total{outcome="completed"} 1' in out
    assert 'app_agent_runs_total{outcome="max_iterations"} 1' in out
    assert 'app_agent_runs_total{outcome="error"} 0' in out
```

- [ ] **Step 2: Mirror + confirm red**

Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -k "tool_calls or run_outcomes" -q`
Expected: FAIL — `AttributeError: 'AgentMetrics' object has no attribute 'record_tool_call'`.

- [ ] **Step 3: Extend `metrics.py`**

Add the run-outcome enum near the top:

```python
RUN_OUTCOMES = ("completed", "max_iterations", "error")
```

In `AgentMetrics.__init__`, add:

```python
        self._tool_calls: dict[tuple[str, str], int] = {}
        self._runs: dict[str, int] = {o: 0 for o in RUN_OUTCOMES}
```

Add methods:

```python
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
```

In `render_prometheus`, inside the lock snapshot add:

```python
            tool_items = sorted(self._tool_calls.items())
            runs = dict(self._runs)
```

and append to the returned exposition string (after the latency gauge block):

```python
            + "# HELP app_agent_tool_calls_total Tool invocations by tool and outcome\n"
            "# TYPE app_agent_tool_calls_total counter\n"
            + "".join(
                f'app_agent_tool_calls_total{{tool="{t}",outcome="{o}"}} {n}\n'
                for (t, o), n in tool_items
            )
            + "# HELP app_agent_runs_total Agentic run loops by terminal outcome\n"
            "# TYPE app_agent_runs_total counter\n"
            + "".join(
                f'app_agent_runs_total{{outcome="{o}"}} {runs[o]}\n' for o in RUN_OUTCOMES
            )
```

Add to `reset()`:

```python
            self._tool_calls = {}
            self._runs = {o: 0 for o in RUN_OUTCOMES}
```

- [ ] **Step 4: Mirror + run green**

Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -q`
Expected: PASS (all FWK12 + new metrics tests).

- [ ] **Step 5: Format-check + commit**

```bash
cd /tmp/agentwork && uv run ruff format --check src/demo/agents/metrics.py; cd -
git add "src/framework_cli/template/src/{{package_name}}/{% if \"agents\" in batteries %}agents{% endif %}/metrics.py" "src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk14): agent tool-call + run-outcome metrics"
```

---

## Task 2: Tool registry + read-only `Item` tools (TDD, functional for data, hermetic for registry)

**Files:**
- Create: `.../agents/tools.py`
- Modify: `tests/unit/{{ 'test_agents_unit.py' ... }}.jinja` (registry shape, hermetic)
- Create: `tests/functional/{{ 'test_agents_tools.py' if 'agents' in batteries else '' }}.jinja` (Item tools over DB)

- [ ] **Step 1: Write the hermetic registry test**

Append to the unit test file:

```python
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


def test_registry_dispatch_unknown_tool_returns_error_string():
    from {{ package_name }}.agents.tools import ToolContext, ToolRegistry

    reg = ToolRegistry()
    out = reg.dispatch("nope", {}, ToolContext(session=None))
    assert "unknown tool" in out.lower()
```

- [ ] **Step 2: Write the functional Item-tools test**

Path: `tests/functional/{{ 'test_agents_tools.py' if 'agents' in batteries else '' }}.jinja`

```python
"""Agents battery — read-only Item tools over a real Postgres (mocked LiteLLM not needed)."""

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
    reg = default_registry()
    out = reg.dispatch("get_item", {"id": 1}, ToolContext(session=session))
    assert "alpha widget" in out


def test_get_item_missing_is_graceful(session):
    reg = default_registry()
    out = reg.dispatch("get_item", {"id": 9999}, ToolContext(session=session))
    assert "not found" in out.lower()


def test_search_items_filters_by_name(session):
    reg = default_registry()
    out = reg.dispatch("search_items", {"query": "beta"}, ToolContext(session=session))
    assert "beta gadget" in out
    assert "alpha widget" not in out
```

- [ ] **Step 3: Mirror + confirm red**

Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -k registry -q`
Expected: FAIL — `No module named 'demo.agents.tools'`.

- [ ] **Step 4: Implement `tools.py`**

Path: `.../agents/tools.py`

```python
"""Tool registry + read-only Item tools for the agentic loop.

Read-only by design: tools query the existing `items` table directly (no repository changes,
no write tools), so the LLM can inspect domain data but never mutate it.
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
    """Ambient dependencies handed to every tool handler."""

    session: Session | None


ToolHandler = Callable[[dict[str, Any], ToolContext], str]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the arguments object
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

- [ ] **Step 5: Mirror + run unit (hermetic) green**

Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -k registry -q`
Expected: PASS.

- [ ] **Step 6: Seed items + run functional (DB) green**

Run: `TMPDIR=/var/tmp` then `cd /tmp/agentwork && uv run pytest tests/functional/test_agents_tools.py -q`
Expected: PASS (requires Docker for the testcontainer Postgres; fails-not-skips without it).

- [ ] **Step 7: Format-check + mypy the render + commit**

```bash
cd /tmp/agentwork && uv run ruff format --check src/demo/agents/tools.py && uv run mypy src/demo/agents; cd -
git add "src/framework_cli/template/src/{{package_name}}/{% if \"agents\" in batteries %}agents{% endif %}/tools.py" "src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja" "src/framework_cli/template/tests/functional/{{ 'test_agents_tools.py' if 'agents' in batteries else '' }}.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk14): tool registry + read-only Item tools"
```

---

## Task 3: `AgentService.run()` — the bounded tool-calling loop (TDD, hermetic)

**Files:**
- Modify: `.../agents/service.py`
- Modify: `tests/unit/{{ 'test_agents_unit.py' ... }}.jinja`

- [ ] **Step 1: Write failing loop tests (mocked LiteLLM, custom pure-function registry)**

Append to the unit test file:

```python
class _ToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.type = "function"

        class _Fn:
            pass

        self.function = _Fn()
        self.function.name = name
        self.function.arguments = arguments


class _LoopMsg:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _LoopResp:
    def __init__(self, content, tool_calls=None):
        self.choices = [type("C", (), {"message": _LoopMsg(content, tool_calls)})()]
        self.usage = _Usage()


def _tool_registry():
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


def test_run_dispatches_tool_then_returns_final_answer(monkeypatch):
    from {{ package_name }}.agents.service import AgentService, RunResult
    from {{ package_name }}.agents.tools import ToolContext

    responses = [
        _LoopResp(None, tool_calls=[_ToolCall("call_1", "lookup", '{"q": "x"}')]),
        _LoopResp("final answer", tool_calls=None),
    ]
    captured_messages = []

    def fake_completion(**kwargs):
        captured_messages.append(list(kwargs["messages"]))
        return responses.pop(0)

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)

    metrics = AgentMetrics()
    svc = AgentService(_settings(), metrics=metrics)
    result = svc.run(
        [{"role": "user", "content": "do it"}],
        registry=_tool_registry(),
        context=ToolContext(session=None),
    )
    assert isinstance(result, RunResult)
    assert result.text == "final answer"
    assert result.outcome == "completed"
    assert result.iterations == 2
    assert result.tool_calls == ["lookup"]
    # the second call saw the tool result appended
    assert any(m.get("role") == "tool" and "value-for-x" in m.get("content", "") for m in captured_messages[1])
    out = metrics.render_prometheus()
    assert 'app_agent_tool_calls_total{tool="lookup",outcome="success"} 1' in out
    assert 'app_agent_runs_total{outcome="completed"} 1' in out


def test_run_stops_at_iteration_cap(monkeypatch):
    from {{ package_name }}.agents.service import AgentService
    from {{ package_name }}.agents.tools import ToolContext

    def always_tool(**_):
        return _LoopResp(None, tool_calls=[_ToolCall("c", "lookup", '{"q": "x"}')])

    monkeypatch.setattr(litellm, "completion", always_tool)
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)

    metrics = AgentMetrics()
    svc = AgentService(Settings(agent_api_key="k", agent_max_iterations=3), metrics=metrics)
    result = svc.run(
        [{"role": "user", "content": "loop"}],
        registry=_tool_registry(),
        context=ToolContext(session=None),
    )
    assert result.outcome == "max_iterations"
    assert result.iterations == 3
    assert 'app_agent_runs_total{outcome="max_iterations"} 1' in metrics.render_prometheus()
```

- [ ] **Step 2: Mirror + confirm red**

Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -k run -q`
Expected: FAIL — `AgentService has no attribute 'run'` / `RunResult` undefined.

- [ ] **Step 3: Implement `run()` in `service.py`**

Add imports at the top of `service.py`:

```python
import json

from .tools import ToolContext, ToolRegistry, default_registry
```

Add the result type next to `CompletionResult`:

```python
@dataclass
class RunResult:
    text: str
    outcome: str  # "completed" | "max_iterations" | "error"
    iterations: int
    tool_calls: list[str]
```

Add the method to `AgentService`:

```python
    def run(
        self,
        messages: list[Message],
        system: str | None = None,
        *,
        registry: ToolRegistry | None = None,
        context: ToolContext | None = None,
    ) -> RunResult:
        """Bounded tool-calling loop. Read-only tools; capped at agent_max_iterations."""
        registry = registry or default_registry()
        context = context or ToolContext(session=None)
        msgs = self._with_system(messages, system)
        schemas = registry.schemas()
        called: list[str] = []
        cap = self._settings.agent_max_iterations
        last_text = ""

        for iteration in range(1, cap + 1):
            response = self._call(msgs, tools=schemas, tool_choice="auto")
            message = response.choices[0].message
            last_text = message.content or last_text
            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                self._metrics.record_run("completed")
                return RunResult(
                    text=message.content or "",
                    outcome="completed",
                    iterations=iteration,
                    tool_calls=called,
                )
            msgs.append(message)
            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                    result = registry.dispatch(name, args, context)
                    outcome = "error" if result.startswith("error:") else "success"
                except Exception as exc:  # malformed args / handler crash
                    result = f"error: {exc}"
                    outcome = "error"
                called.append(name)
                self._metrics.record_tool_call(name, outcome)
                msgs.append({"role": "tool", "tool_call_id": call.id, "content": result})

        self._metrics.record_run("max_iterations")
        return RunResult(
            text=last_text, outcome="max_iterations", iterations=cap, tool_calls=called
        )
```

- [ ] **Step 4: Mirror + run loop tests green**

Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -q`
Expected: PASS (all unit tests, FWK12 + FWK14).

- [ ] **Step 5: Format-check + mypy + commit**

```bash
cd /tmp/agentwork && uv run ruff format --check src/demo/agents/service.py && uv run mypy src/demo/agents; cd -
git add "src/framework_cli/template/src/{{package_name}}/{% if \"agents\" in batteries %}agents{% endif %}/service.py" "src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk14): bounded tool-calling run loop"
```

---

## Task 4: `POST /agents/run` demo route (TDD, DB + mocked LiteLLM)

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja`
- Create: `tests/functional/{{ 'test_agents_run.py' if 'agents' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing route test (seeded items, mocked LiteLLM, DB override)**

Path: `tests/functional/{{ 'test_agents_run.py' if 'agents' in batteries else '' }}.jinja`

```python
"""Agents battery — functional test for POST /agents/run over seeded items."""

import litellm
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from {{ package_name }}.config.settings import Settings
from {{ package_name }}.db.engine import build_session_factory, get_session
from {{ package_name }}.db.repository import create_item
from {{ package_name }}.main import create_app


class _ToolCall:
    id = "call_1"
    type = "function"

    class function:
        name = "search_items"
        arguments = '{"query": "alpha"}'


class _Step1Msg:
    content = None
    tool_calls = [_ToolCall()]


class _Step2Msg:
    content = "Found: alpha widget"
    tool_calls = None


class _Usage:
    prompt_tokens = 4
    completion_tokens = 2
    cache_read_input_tokens = 0


def _resp(message):
    return type("R", (), {"choices": [type("C", (), {"message": message})()], "usage": _Usage()})()


@pytest.fixture
def client(engine: Engine, monkeypatch):
    factory = build_session_factory(engine)
    with factory() as s:
        create_item(s, "alpha widget")
        s.commit()

    responses = [_resp(_Step1Msg()), _resp(_Step2Msg())]
    monkeypatch.setattr(litellm, "completion", lambda **_: responses.pop(0))
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)

    def override():
        with factory() as session:
            yield session

    app = create_app(Settings(agent_api_key="k", database_url=str(engine.url), serve_spa=False))
    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE items RESTART IDENTITY CASCADE"))
        conn.commit()


def test_run_route_executes_tool_and_returns_answer(client):
    r = client.post("/agents/run", json={"prompt": "find alpha"})
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "completed"
    assert body["text"] == "Found: alpha widget"
    assert body["tool_calls"] == ["search_items"]
```

- [ ] **Step 2: Mirror + confirm red**

Run: `TMPDIR=/var/tmp uv run --project ... ` then `cd /tmp/agentwork && uv run pytest tests/functional/test_agents_run.py -q`
Expected: FAIL — 404 on `/agents/run`.

- [ ] **Step 3: Add the route**

Append to `routes/{{ 'agents.py' ... }}.jinja` (which already holds `/agents/complete`):

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from {{ package_name }}.agents.tools import ToolContext, default_registry
from {{ package_name }}.db.engine import get_session

SessionDep = Annotated[Session, Depends(get_session)]


class RunRequest(BaseModel):
    prompt: str
    system: str | None = None


class RunResponse(BaseModel):
    text: str
    outcome: str
    iterations: int
    tool_calls: list[str]


@router.post("/agents/run", response_model=RunResponse)
def run(body: RunRequest, request: Request, session: SessionDep) -> RunResponse:
    """Agentic run — the model may call read-only Item tools, bounded by agent_max_iterations."""
    service = AgentService(request.app.state.settings, metrics=agent_metrics)
    try:
        result = service.run(
            [{"role": "user", "content": body.prompt}],
            system=body.system,
            registry=default_registry(),
            context=ToolContext(session=session),
        )
    except AgentExhausted as exc:
        raise HTTPException(status_code=503, detail="agent provider exhausted") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="agent provider error") from exc
    return RunResponse(
        text=result.text,
        outcome=result.outcome,
        iterations=result.iterations,
        tool_calls=result.tool_calls,
    )
```

> Consolidate imports at the top of the file (don't duplicate the `Request`/`HTTPException`/`BaseModel`/`AgentService`/`agent_metrics`/`AgentExhausted` imports the FWK12 route already declares).

- [ ] **Step 4: Mirror + run green**

Run: `cd /tmp/agentwork && uv run pytest tests/functional/test_agents_run.py -q`
Expected: PASS.

- [ ] **Step 5: Format-check + commit**

```bash
cd /tmp/agentwork && uv run ruff format --check src/demo/routes/agents.py tests/functional/test_agents_run.py; cd -
git add "src/framework_cli/template/src/{{package_name}}/routes/" "src/framework_cli/template/tests/functional/{{ 'test_agents_run.py' if 'agents' in batteries else '' }}.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk14): POST /agents/run agentic demo route"
```

---

## Task 5: Update the dashboard with tool + run panels

**Files:**
- Modify: `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'agents.json' ... }}.jinja`

- [ ] **Step 1: Add two panels to the agents dashboard**

Append to the `panels` array:

```json
    {
      "id": 5,
      "title": "Tool calls by tool",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
      "targets": [
        {"refId": "A", "expr": "sum by (tool) (rate(app_agent_tool_calls_total[5m]))", "legendFormat": "__auto"}
      ],
      "fieldConfig": {"defaults": {"unit": "ops"}, "overrides": []}
    },
    {
      "id": 6,
      "title": "Run outcomes",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 16},
      "targets": [
        {"refId": "A", "expr": "sum by (outcome) (rate(app_agent_runs_total[5m]))", "legendFormat": "__auto"}
      ],
      "fieldConfig": {"defaults": {"unit": "ops"}, "overrides": []}
    }
```

(Insert a comma after the prior last panel's closing `}`.)

- [ ] **Step 2: Validate JSON + obs-completeness still green**

Render with agents, then:
Run: `python -c "import json,sys; json.load(open('/tmp/agentwork/infra/observability/grafana/dashboards/agents.json'))"`
Run: `uv run pytest "tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface[agents]" -q`
Expected: both PASS.

- [ ] **Step 3: Commit**

```bash
git add "src/framework_cli/template/infra/observability/grafana/dashboards/" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk14): agents dashboard tool + run-outcome panels"
```

---

## Task 6: Full render + acceptance + branch-end review + finish

**Files:**
- Run-only framework tests; `PLAN.md` (tick FWK14 → Done), `ACTION_LOG.md`.

- [ ] **Step 1: Source gate**

Run: `uv run pytest -q -k "not acceptance" && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: green.

- [ ] **Step 2: Render + obs + acceptance**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py tests/test_obs_completeness.py tests/acceptance/test_rendered_project.py -q`
Expected: PASS, including a clean first `pre-commit` for an agents render.

- [ ] **Step 3: Eval-fixture coupling check** ([[eval-fixtures-coupled-to-template]])

Run: `git grep -l "agents\|litellm" tests/eval/fixtures/ || echo "no fixture coupling"`
Expected: `no fixture coupling` (or re-anchor if a touched file is referenced).

- [ ] **Step 4: Branch-end Opus review** ([[subagent-review-model-pattern]])

One Opus reviewer over the full branch diff. Focus: loop-bound correctness (no unbounded recursion; cap honored), tool-result correlation (`tool_call_id` round-trip), read-only guarantee (no write path reachable from a tool), metric cardinality (tool label bounded by the registry), and error mapping. Address findings; re-run Steps 1–2.

- [ ] **Step 5: Verify subagent commits landed** ([[subagent-implementers-stop-before-commit]])

Run: `git status --short && git log --oneline master..HEAD`
Expected: clean tree; one commit per task.

- [ ] **Step 6: Finish the branch** ([[finishing-a-development-branch]])

Move FWK14 → `Done` in `PLAN.md`, append the `ACTION_LOG.md` completion entry, push `fwk14-agents-loop`, open one PR, confirm `gate`/`build`/`render-complete` green, self-merge, and grep `master` for a loop marker post-merge ([[verify-master-content-after-pr-merge]]).

---

## Self-Review (completed by plan author)

- **Spec coverage:** tool registry + read-only Item tools (Task 2) · bounded run loop with iteration cap + distinct `max_iterations` outcome (Task 3) · agentic demo route (Task 4) · tool-call + run-outcome metrics + dashboard panels (Tasks 1, 5) · error→HTTP mapping reused (Task 4) · read-only guarantee (Task 2, no write tools). Multi-tool selection, streaming, write tools, hot-swap: out of scope.
- **Type consistency:** `Tool{name,description,parameters,handler}` · `ToolContext{session}` · `ToolRegistry.register/schemas/dispatch` · `default_registry()` · `AgentService.run(messages, system=None, *, registry=None, context=None) -> RunResult{text,outcome,iterations,tool_calls}` · `AgentMetrics.record_tool_call(tool,outcome)` / `record_run(outcome)` — names identical across tasks and consistent with the FWK12 plan's `_call(...)`/`_with_system(...)`/`agent_metrics`.
- **Cross-slice dependency:** every reference to FWK12 code (`_call`, `_with_system`, `CompletionResult`, `agent_metrics`, the existing `/agents/complete` route file, settings fields) is called out for reconciliation against merged `master` in the header.
- **No placeholders:** all code/test/JSON blocks are complete.
