# `--with agents` Battery — Slice 1 (Runtime Core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship FWK12 — the `--with agents` battery's runtime core: a LiteLLM-backed completion + structured-output service, one demo route, in-process observability, and tests, rendering cleanly into a generated project.

**Architecture:** New template payload under `src/{{package_name}}/{% if "agents" in batteries %}agents{% endif %}/` — a stateless `AgentService` calling `litellm.completion` over a provider API key, config through the central `APP_`-prefixed `Settings`, a hand-rolled in-process metrics singleton appended to `/metrics`, a conditional Prometheus alert + Grafana dashboard, and a `POST /agents/complete` route auto-discovered by `routes/include_routers`. Plain LiteLLM only; subscription hot-swap is FWK13.

**Tech Stack:** Python 3.12, Copier/Jinja template payload, LiteLLM (`>=1.88.1`, matching the framework pin), FastAPI, pydantic-settings, pytest. Spec: `docs/superpowers/specs/2026-06-14-agents-battery-design.md`.

---

## Execution notes (read before starting)

- **Review-model policy** ([[subagent-review-model-pattern]]): implementers → Sonnet (Haiku for trivial mechanical tasks); spec-compliance review → Sonnet; code-quality review → **Opus**; branch-end whole-branch review → **Opus**. Pass `model` explicitly per role.
- **Gate cadence** ([[gate-cadence-framework-slices]]): do **not** run the full 18-agent `framework gate` per commit — it over-fires app-review agents on template/infra files. Use a light per-task review, commit past `reviewers-gate-check.sh` with the **controller skip-marker recipe** ([[controller-skip-marker-recipe]]), and run **one** branch-end Opus review (Task 9).
- **Template-payload TDD loop** ([[template-payload-tdd-loop]]): template tests run inside a *generated* project, not the framework venv. The loop per task is: render a project to `/tmp/agentwork`, `uv sync`, edit the source under `src/framework_cli/template/`, mirror the changed file into the render (`cp` for `.py`; render+`cp` for `.jinja`), then `pytest` inside the render. Use `TMPDIR=/var/tmp` for full/acceptance runs ([[full-suite-exhausts-tmp-tmpfs-use-var-tmp]]).
- **Commit-gate hook** ([[commit-gate-hook-timing]]): stage with a separate `git add`, then `git commit` as its own call; keep the word "commit" out of Bash command *descriptions*. Every commit must stage a `PLAN.md`/`ACTION_LOG.md` change.
- The framework-level `tests/test_obs_completeness.py` is **parametrized over `battery_names()`** — the moment Task 1 registers the `agents` BatterySpec, that test demands an alert file + a dashboard for `agents` (Task 2 provides them). That coupling is the TDD driver for the obs surface.
- **No DB migration is needed** in this slice — the completion service is stateless and FWK14's read-only tool reads the existing `items` table.

### Helper: render a fresh project for the TDD loop

Used by several tasks. This calls `render_project` directly (the same entrypoint the
framework test suite uses), which pins `package_name="demo"` so the rendered tree is
`src/demo/…` and imports are `from demo.…`. Run from the repo root:

```bash
export TMPDIR=/var/tmp
rm -rf /tmp/agentwork
uv run python -c "from pathlib import Path; from framework_cli.copier_runner import render_project; render_project(Path('/tmp/agentwork'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':['agents']})"
cd /tmp/agentwork && uv sync --extra dev && cd -
```

For a **baseline (no-agents)** render to `/tmp/agentbase` (used by the guard-correctness
steps), use the same command with `dest='/tmp/agentbase'` and `'batteries':[]`.

> The CLI (`framework new NAME --with agents`) renders to `cwd/<slug>` and *derives* the
> package name from NAME, so it can't pin `demo` — use `render_project` for the TDD loop.

---

## File Structure

**Framework source (not template payload):**
- Modify: `src/framework_cli/batteries.py` — register the `agents` BatterySpec.
- Modify: `PLAN.md`, `ACTION_LOG.md` — per-commit state (every task).

**Template payload — agent runtime module** `src/framework_cli/template/src/{{package_name}}/{% if "agents" in batteries %}agents{% endif %}/`:
- Create: `__init__.py` — package marker.
- Create: `errors.py` — `AgentError`, `AgentExhausted`.
- Create: `metrics.py` — `AgentMetrics` singleton + `agent_metrics`.
- Create: `service.py` — `AgentService.complete` / `complete_structured`, `CompletionResult`.

**Template payload — wiring:**
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja` — agent settings block.
- Create: `src/framework_cli/template/src/{{package_name}}/routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja` — `POST /agents/complete`.
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja` — append agent metrics to `/metrics`.
- Modify: `src/framework_cli/template/pyproject.toml.jinja` — add `litellm` dep under the `agents` guard.

**Template payload — observability:**
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/{{ 'agents_alerts.yml' if 'agents' in batteries else '' }}.jinja`
- Create: `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'agents.json' if 'agents' in batteries else '' }}.jinja`

**Template payload — tests:**
- Create: `src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja` — metrics + service (mocked litellm), hermetic.
- Create: `src/framework_cli/template/tests/functional/{{ 'test_agents.py' if 'agents' in batteries else '' }}.jinja` — `/agents/complete` route (mocked litellm), no DB.

---

## Task 1: Register the `agents` BatterySpec (drives the obs-completeness TDD red)

**Files:**
- Modify: `src/framework_cli/batteries.py`
- Test: `tests/test_obs_completeness.py` (existing, parametrized — no edit)

- [ ] **Step 1: Run the obs-completeness test to confirm `agents` is not yet a case**

Run: `uv run pytest tests/test_obs_completeness.py -q`
Expected: PASS (no `agents` parameter exists yet).

- [ ] **Step 2: Add the BatterySpec**

In `src/framework_cli/batteries.py`, add to the `_BATTERIES` dict (after the `webhooks` entry):

```python
    "agents": BatterySpec(
        "agents",
        "LiteLLM-backed LLM agent runtime (completion, structured output, "
        "tool-calling loop) with full observability",
        obs="in-process",
    ),
```

- [ ] **Step 3: Run the obs-completeness test to confirm it now fails for `agents`**

Run: `uv run pytest "tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface[agents]" -q`
Expected: FAIL — `agents: an 'in-process' battery must add an alert-rule file` (the render ships no agents alert/dashboard yet). This red is expected and is resolved in Task 2.

- [ ] **Step 4: Confirm registry plumbing still passes**

Run: `uv run pytest tests/test_batteries.py -q` (and `tests/test_copier_runner.py -q` if it enumerates batteries)
Expected: PASS — `agents` resolves and renders an empty payload (no files reference it yet).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/batteries.py PLAN.md ACTION_LOG.md
```
Then, as a separate call:
```bash
git commit -m "feat(fwk12): register agents BatterySpec (in-process)"
```

---

## Task 2: Ship the Prometheus alert + Grafana dashboard (turn the obs-completeness test green)

**Files:**
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/{{ 'agents_alerts.yml' if 'agents' in batteries else '' }}.jinja`
- Create: `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'agents.json' if 'agents' in batteries else '' }}.jinja`
- Test: `tests/test_obs_completeness.py`

- [ ] **Step 1: Create the alert-rule file**

Path: `src/framework_cli/template/infra/observability/prometheus/alerts/{{ 'agents_alerts.yml' if 'agents' in batteries else '' }}.jinja`

```yaml
groups:
- name: agents
  rules:
  - alert: HighAgentCallFailureRate
    # Errors + provider-exhaustion as a share of all agent calls. A wedged or quota-exhausted
    # provider is the failure mode that matters; tune the 0.1 threshold per app.
    expr: sum(rate(app_agent_calls_total{outcome=~"error|exhausted"}[5m])) / clamp_min(sum(rate(app_agent_calls_total[5m])), 1) > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Over 10% of LLM agent calls are failing or hitting provider quota (check the provider key, rate limits, and budget)
```

- [ ] **Step 2: Create the dashboard file**

Path: `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'agents.json' if 'agents' in batteries else '' }}.jinja`

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
      "title": "Agent calls by outcome",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "targets": [
        {"refId": "A", "expr": "sum by (outcome) (rate(app_agent_calls_total[5m]))", "legendFormat": "__auto"}
      ],
      "fieldConfig": {"defaults": {"unit": "ops"}, "overrides": []}
    },
    {
      "id": 2,
      "title": "Call latency p99 (ms)",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "targets": [
        {"refId": "A", "expr": "app_agent_call_latency_p99_ms", "legendFormat": "p99"}
      ],
      "fieldConfig": {"defaults": {"unit": "ms"}, "overrides": []}
    },
    {
      "id": 3,
      "title": "Tokens by kind",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "targets": [
        {"refId": "A", "expr": "sum by (kind) (rate(app_agent_tokens_total[5m]))", "legendFormat": "__auto"}
      ],
      "fieldConfig": {"defaults": {"unit": "short"}, "overrides": []}
    },
    {
      "id": 4,
      "title": "Cumulative cost (USD)",
      "type": "timeseries",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
      "targets": [
        {"refId": "A", "expr": "app_agent_cost_usd_total", "legendFormat": "cost"}
      ],
      "fieldConfig": {"defaults": {"unit": "currencyUSD"}, "overrides": []}
    }
  ]
}
```

- [ ] **Step 3: Run the obs-completeness test for agents**

Run: `uv run pytest "tests/test_obs_completeness.py::test_battery_obs_matches_declared_surface[agents]" -q`
Expected: PASS — agents now adds exactly one alert file and one dashboard, no scrape/service/exporter.

- [ ] **Step 4: Confirm no other obs case regressed**

Run: `uv run pytest tests/test_obs_completeness.py -q`
Expected: PASS (all batteries).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/infra/observability/ PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk12): agents Prometheus alert + Grafana dashboard"
```

---

## Task 3: Agent settings block

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja`
- Test: render + `tests/unit/test_agents_unit.py` (Task 6 asserts settings load; here we verify render only)

- [ ] **Step 1: Add the SecretStr import behind the agents guard**

At the top of `settings.py.jinja`, after the existing `from pydantic_settings import ...` line, add a guarded import so the symbol only appears when the battery is active:

```jinja
{%- if "agents" in batteries %}
from pydantic import SecretStr
{%- endif %}
```

- [ ] **Step 2: Add the agent settings fields**

After the `webhooks` settings block (and before the `workers`/`redis` block), add:

```jinja
{%- if "agents" in batteries %}

    # LLM agent runtime (read from APP_AGENT_*). The key is passed explicitly to LiteLLM —
    # nothing is read out-of-band from provider-native env vars. `agent_provider` is the seam
    # the HotSwapAgents battery (subscription <-> API) plugs into.
    agent_provider: str = "anthropic"
    agent_model: str = "claude-sonnet-4-6"
    agent_max_tokens: int = 4096
    agent_temperature: float = 0.0
    agent_api_key: SecretStr = SecretStr("")
{%- endif %}
```

- [ ] **Step 3: Render a project and confirm settings import + parse**

Render via the helper (top of plan), then:
Run: `cd /tmp/agentwork && uv run python -c "from demo.config.settings import Settings; s=Settings(agent_api_key='x'); print(s.agent_model, s.agent_api_key.get_secret_value())"`
Expected: `claude-sonnet-4-6 x` (SecretStr round-trips; `APP_AGENT_*` env binding works via env_prefix).

- [ ] **Step 4: Confirm a no-agents render still parses (guard correctness)**

Render a baseline project without `--with agents` to `/tmp/agentbase`, then:
Run: `cd /tmp/agentbase && uv run python -c "from demo.config.settings import Settings; Settings()"`
Expected: no error, and `grep -q SecretStr src/demo/config/settings.py` returns non-zero (the import is absent when the battery is off).

- [ ] **Step 5: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk12): agent settings (provider/model/tokens/temperature/SecretStr key)"
```

---

## Task 4: Errors + metrics modules (hermetic, TDD)

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "agents" in batteries %}agents{% endif %}/__init__.py`
- Create: `.../agents/errors.py`
- Create: `.../agents/metrics.py`
- Create (this task starts it): `src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja`

> These are plain `.py` files (no Jinja) inside the conditional `{% if "agents" in batteries %}agents{% endif %}` directory, so the whole directory only renders when the battery is active. The test file IS Jinja (its filename interpolates `{{ package_name }}` in imports).

- [ ] **Step 1: Write the failing unit tests for errors + metrics**

Path: `src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja`

```python
"""Agents battery — hermetic unit tests (no network, no DB)."""

from {{ package_name }}.agents.errors import AgentError, AgentExhausted
from {{ package_name }}.agents.metrics import AgentMetrics


def test_exhausted_is_an_agent_error():
    assert issubclass(AgentExhausted, AgentError)


def test_metrics_record_call_outcomes():
    m = AgentMetrics()
    m.record_call("success")
    m.record_call("success")
    m.record_call("error")
    out = m.render_prometheus()
    assert 'app_agent_calls_total{outcome="success"} 2' in out
    assert 'app_agent_calls_total{outcome="error"} 1' in out
    assert 'app_agent_calls_total{outcome="exhausted"} 0' in out
    assert "# TYPE app_agent_calls_total counter" in out


def test_metrics_record_tokens_and_cost():
    m = AgentMetrics()
    m.record_tokens(input=10, output=5, cache_read=3)
    m.record_cost(0.0021)
    out = m.render_prometheus()
    assert 'app_agent_tokens_total{kind="input"} 10' in out
    assert 'app_agent_tokens_total{kind="output"} 5' in out
    assert 'app_agent_tokens_total{kind="cache_read"} 3' in out
    assert "app_agent_cost_usd_total 0.0021" in out


def test_metrics_latency_p99_gauge_present():
    m = AgentMetrics()
    for v in (10.0, 20.0, 30.0):
        m.record_latency_ms(v)
    out = m.render_prometheus()
    assert "# TYPE app_agent_call_latency_p99_ms gauge" in out
    assert "app_agent_call_latency_p99_ms " in out


def test_unknown_outcome_is_ignored():
    m = AgentMetrics()
    m.record_call("bogus")
    out = m.render_prometheus()
    assert 'app_agent_calls_total{outcome="success"} 0' in out
```

- [ ] **Step 2: Run the test in a render to confirm it fails (modules missing)**

Render via the helper, mirror the test file into the render:
```bash
mkdir -p /tmp/agentwork/tests/unit
# render the .jinja test for the agents context, then copy — or copy the already-rendered file:
cp /tmp/agentwork/tests/unit/test_agents_unit.py /tmp/agentwork/tests/unit/ 2>/dev/null || true
```
Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'demo.agents'`.

- [ ] **Step 3: Implement `__init__.py`**

Path: `.../agents/__init__.py`

```python
"""LiteLLM-backed LLM agent runtime (agents battery)."""
```

- [ ] **Step 4: Implement `errors.py`**

Path: `.../agents/errors.py`

```python
"""Agent error hierarchy — independent of the framework's internal review backend."""

from __future__ import annotations


class AgentError(Exception):
    """Any failure invoking the LLM provider through the agent runtime."""


class AgentExhausted(AgentError):
    """The provider rejected the call for rate-limit / quota reasons (retry later)."""
```

- [ ] **Step 5: Implement `metrics.py`**

Path: `.../agents/metrics.py`

```python
"""Process-wide agent metrics — hand-rolled Prometheus exposition (no client lib).

Mirrors the house pattern (observability/metrics.py, webhooks/metrics.py): a thread-safe
module-level singleton, label-light by design. `outcome` and `kind` are bounded enums;
the model id is deliberately NOT a label (it is effectively constant per deployment).
"""

from __future__ import annotations

import threading

CALL_OUTCOMES = ("success", "error", "exhausted")
TOKEN_KINDS = ("input", "output", "cache_read")


def _p99(samples: list[float]) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = max(0, round(0.99 * (len(ordered) - 1)))
    return ordered[idx]


class AgentMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[str, int] = {o: 0 for o in CALL_OUTCOMES}
        self._tokens: dict[str, int] = {k: 0 for k in TOKEN_KINDS}
        self._cost_usd = 0.0
        self._latencies_ms: list[float] = []

    def record_call(self, outcome: str) -> None:
        with self._lock:
            if outcome in self._calls:
                self._calls[outcome] += 1

    def record_tokens(self, *, input: int = 0, output: int = 0, cache_read: int = 0) -> None:
        with self._lock:
            self._tokens["input"] += max(0, input)
            self._tokens["output"] += max(0, output)
            self._tokens["cache_read"] += max(0, cache_read)

    def record_cost(self, usd: float) -> None:
        with self._lock:
            self._cost_usd += max(0.0, usd)

    def record_latency_ms(self, ms: float) -> None:
        with self._lock:
            self._latencies_ms.append(ms)

    def render_prometheus(self) -> str:
        with self._lock:
            calls = "".join(
                f'app_agent_calls_total{{outcome="{o}"}} {self._calls[o]}\n'
                for o in CALL_OUTCOMES
            )
            tokens = "".join(
                f'app_agent_tokens_total{{kind="{k}"}} {self._tokens[k]}\n'
                for k in TOKEN_KINDS
            )
            cost = self._cost_usd
            p99 = _p99(self._latencies_ms)
        return (
            "# HELP app_agent_calls_total LLM agent calls by outcome\n"
            "# TYPE app_agent_calls_total counter\n"
            f"{calls}"
            "# HELP app_agent_tokens_total LLM tokens consumed by kind\n"
            "# TYPE app_agent_tokens_total counter\n"
            f"{tokens}"
            "# HELP app_agent_cost_usd_total Cumulative LLM spend in USD\n"
            "# TYPE app_agent_cost_usd_total counter\n"
            f"app_agent_cost_usd_total {cost}\n"
            "# HELP app_agent_call_latency_p99_ms p99 agent-call latency in ms\n"
            "# TYPE app_agent_call_latency_p99_ms gauge\n"
            f"app_agent_call_latency_p99_ms {p99}\n"
        )

    def reset(self) -> None:
        with self._lock:
            self._calls = {o: 0 for o in CALL_OUTCOMES}
            self._tokens = {k: 0 for k in TOKEN_KINDS}
            self._cost_usd = 0.0
            self._latencies_ms = []


agent_metrics = AgentMetrics()
"""Process-wide singleton imported by the agents service and the /metrics route."""
```

- [ ] **Step 6: Mirror the new files into the render and run the test green**

```bash
D=/tmp/agentwork/src/demo/agents
mkdir -p "$D"
cp "src/framework_cli/template/src/{{package_name}}/{% if \"agents\" in batteries %}agents{% endif %}/__init__.py" "$D/__init__.py"
cp "src/framework_cli/template/src/{{package_name}}/{% if \"agents\" in batteries %}agents{% endif %}/errors.py" "$D/errors.py"
cp "src/framework_cli/template/src/{{package_name}}/{% if \"agents\" in batteries %}agents{% endif %}/metrics.py" "$D/metrics.py"
```
Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -k "metrics or error" -q`
Expected: PASS.

- [ ] **Step 7: `ruff format --check` the rendered output** ([[ruff-format-check-after-inline-edits]])

Run: `cd /tmp/agentwork && uv run ruff format --check src/demo/agents tests/unit/test_agents_unit.py`
Expected: PASS (fix formatting in the *template source* if it fails, then re-mirror).

- [ ] **Step 8: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/{% if \"agents\" in batteries %}agents{% endif %}/" "src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk12): agent errors + in-process metrics singleton"
```

---

## Task 5: `AgentService` — completion + structured output (TDD, mocked LiteLLM)

**Files:**
- Create: `.../agents/service.py`
- Modify: `src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja` (append service tests)

- [ ] **Step 1: Append failing service tests**

Add to the unit test file:

```python
import litellm
import pytest
from pydantic import BaseModel

from {{ package_name }}.agents.metrics import AgentMetrics
from {{ package_name }}.agents.service import AgentService, CompletionResult
from {{ package_name }}.config.settings import Settings


class _Msg:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Usage:
    def __init__(self):
        self.prompt_tokens = 12
        self.completion_tokens = 7
        self.cache_read_input_tokens = 4


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]
        self.usage = _Usage()


def _settings() -> Settings:
    return Settings(agent_api_key="k", agent_model="claude-sonnet-4-6", agent_provider="anthropic")


def test_complete_returns_text_and_usage(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return _Resp("hello there")

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0009)

    metrics = AgentMetrics()
    svc = AgentService(_settings(), metrics=metrics)
    result = svc.complete([{"role": "user", "content": "hi"}], system="be brief")

    assert isinstance(result, CompletionResult)
    assert result.text == "hello there"
    assert result.usage == {"input": 12, "output": 7, "cache_read": 4}
    # model id is prefixed with the provider for LiteLLM routing
    assert captured["model"] == "anthropic/claude-sonnet-4-6"
    assert captured["api_key"] == "k"
    # system is prepended as a system message (OpenAI shape)
    assert captured["messages"][0] == {"role": "system", "content": "be brief"}
    # metrics recorded
    out = metrics.render_prometheus()
    assert 'app_agent_calls_total{outcome="success"} 1' in out
    assert 'app_agent_tokens_total{kind="input"} 12' in out
    assert "app_agent_cost_usd_total 0.0009" in out


def test_complete_maps_rate_limit_to_exhausted(monkeypatch):
    def boom(**_):
        raise litellm.exceptions.RateLimitError(
            message="slow down", model="claude-sonnet-4-6", llm_provider="anthropic"
        )

    monkeypatch.setattr(litellm, "completion", boom)
    metrics = AgentMetrics()
    svc = AgentService(_settings(), metrics=metrics)
    from {{ package_name }}.agents.errors import AgentExhausted

    with pytest.raises(AgentExhausted):
        svc.complete([{"role": "user", "content": "hi"}])
    assert 'app_agent_calls_total{outcome="exhausted"} 1' in metrics.render_prometheus()


def test_complete_maps_generic_error(monkeypatch):
    def boom(**_):
        raise litellm.exceptions.APIError(
            status_code=500, message="kaboom", model="m", llm_provider="anthropic"
        )

    monkeypatch.setattr(litellm, "completion", boom)
    metrics = AgentMetrics()
    svc = AgentService(_settings(), metrics=metrics)
    from {{ package_name }}.agents.errors import AgentError

    with pytest.raises(AgentError):
        svc.complete([{"role": "user", "content": "hi"}])
    assert 'app_agent_calls_total{outcome="error"} 1' in metrics.render_prometheus()


def test_complete_structured_parses_into_schema(monkeypatch):
    class Person(BaseModel):
        name: str
        age: int

    monkeypatch.setattr(litellm, "completion", lambda **_: _Resp('{"name": "Ada", "age": 36}'))
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)

    svc = AgentService(_settings(), metrics=AgentMetrics())
    person = svc.complete_structured([{"role": "user", "content": "x"}], Person)
    assert person == Person(name="Ada", age=36)
```

- [ ] **Step 2: Mirror the test + run to confirm red**

Mirror the test file into the render, then:
Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -k "complete" -q`
Expected: FAIL — `No module named 'demo.agents.service'`.

- [ ] **Step 3: Implement `service.py`**

Path: `.../agents/service.py`

```python
"""AgentService — a thin, observable LiteLLM wrapper over a provider API key.

Plain LiteLLM (OpenAI-shaped `litellm.completion`); the provider key is passed explicitly.
Stateless. The HotSwapAgents battery later swaps the provider/model prefix to route to the
subscription `claude-cli` provider — this service does not change for that.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel

from ..config.settings import Settings
from .errors import AgentError, AgentExhausted
from .metrics import AgentMetrics, agent_metrics

T = TypeVar("T", bound=BaseModel)

Message = dict[str, Any]


@dataclass
class CompletionResult:
    text: str
    usage: dict[str, int]


class AgentService:
    def __init__(self, settings: Settings, *, metrics: AgentMetrics | None = None) -> None:
        self._settings = settings
        self._metrics = metrics or agent_metrics

    @property
    def _model(self) -> str:
        return f"{self._settings.agent_provider}/{self._settings.agent_model}"

    def _with_system(self, messages: list[Message], system: str | None) -> list[Message]:
        if system is None:
            return messages
        return [{"role": "system", "content": system}, *messages]

    def _call(self, messages: list[Message], **extra: Any) -> Any:
        # Lazy import keeps litellm off the import path until an agent call actually happens.
        import litellm

        started = perf_counter()
        try:
            response = litellm.completion(
                model=self._model,
                api_key=self._settings.agent_api_key.get_secret_value(),
                max_tokens=self._settings.agent_max_tokens,
                temperature=self._settings.agent_temperature,
                messages=messages,
                **extra,
            )
        except litellm.exceptions.RateLimitError as exc:
            self._metrics.record_call("exhausted")
            raise AgentExhausted(str(exc)) from exc
        except litellm.exceptions.APIError as exc:
            self._metrics.record_call("error")
            raise AgentError(str(exc)) from exc
        except Exception as exc:  # transport / unexpected provider failure
            self._metrics.record_call("error")
            raise AgentError(str(exc)) from exc

        self._metrics.record_latency_ms((perf_counter() - started) * 1000)
        self._metrics.record_call("success")
        self._record_usage(response)
        return response

    def _record_usage(self, response: Any) -> None:
        import litellm

        usage = getattr(response, "usage", None)
        if usage is not None:
            self._metrics.record_tokens(
                input=getattr(usage, "prompt_tokens", 0) or 0,
                output=getattr(usage, "completion_tokens", 0) or 0,
                cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0,
            )
        try:
            self._metrics.record_cost(litellm.completion_cost(completion_response=response))
        except Exception:
            pass  # cost is best-effort; never fail a call over accounting

    @staticmethod
    def _usage_dict(response: Any) -> dict[str, int]:
        usage = getattr(response, "usage", None)
        return {
            "input": getattr(usage, "prompt_tokens", 0) or 0,
            "output": getattr(usage, "completion_tokens", 0) or 0,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        }

    def complete(self, messages: list[Message], system: str | None = None) -> CompletionResult:
        response = self._call(self._with_system(messages, system))
        text = response.choices[0].message.content or ""
        return CompletionResult(text=text, usage=self._usage_dict(response))

    def complete_structured(
        self, messages: list[Message], schema: type[T], system: str | None = None
    ) -> T:
        response = self._call(self._with_system(messages, system), response_format=schema)
        content = response.choices[0].message.content or ""
        return schema.model_validate_json(content)
```

- [ ] **Step 4: Mirror + run the service tests green**

Run: `cd /tmp/agentwork && uv run pytest tests/unit/test_agents_unit.py -q`
Expected: PASS (all unit tests).

- [ ] **Step 5: Type-check the service against the framework's mypy view**

The template payload is excluded from `mypy src`, but a render is type-checkable with the generated project's own config:
Run: `cd /tmp/agentwork && uv run mypy src/demo/agents`
Expected: PASS. (If litellm lacks stubs, add a *targeted* `ignore_missing_imports` for `litellm.*` in the **template's** mypy config under the agents guard — note it, do not silence broadly.)

- [ ] **Step 6: `ruff format --check` the rendered output**

Run: `cd /tmp/agentwork && uv run ruff format --check src/demo/agents`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/{% if \"agents\" in batteries %}agents{% endif %}/service.py" "src/framework_cli/template/tests/unit/{{ 'test_agents_unit.py' if 'agents' in batteries else '' }}.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk12): AgentService completion + structured output"
```

---

## Task 6: Demo route `POST /agents/complete` + metrics wiring (TDD, mocked LiteLLM, no DB)

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja`
- Create: `src/framework_cli/template/tests/functional/{{ 'test_agents.py' if 'agents' in batteries else '' }}.jinja`

- [ ] **Step 1: Write the failing route test**

Path: `src/framework_cli/template/tests/functional/{{ 'test_agents.py' if 'agents' in batteries else '' }}.jinja`

```python
"""Agents battery — functional tests for the /agents/complete route (mocked LiteLLM, no DB)."""

import litellm
import pytest
from fastapi.testclient import TestClient

from {{ package_name }}.config.settings import Settings
from {{ package_name }}.main import create_app


class _Msg:
    content = "the answer is 42"
    tool_calls = None


class _Choice:
    message = _Msg()


class _Usage:
    prompt_tokens = 5
    completion_tokens = 3
    cache_read_input_tokens = 0


class _Resp:
    choices = [_Choice()]
    usage = _Usage()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(litellm, "completion", lambda **_: _Resp())
    monkeypatch.setattr(litellm, "completion_cost", lambda **_: 0.0)
    app = create_app(Settings(agent_api_key="k", serve_spa=False))
    with TestClient(app) as c:
        yield c


def test_complete_route_returns_text_and_usage(client):
    r = client.post("/agents/complete", json={"prompt": "what is the answer?"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "the answer is 42"
    assert body["usage"] == {"input": 5, "output": 3, "cache_read": 0}


def test_complete_route_exhaustion_maps_to_503(client, monkeypatch):
    def boom(**_):
        raise litellm.exceptions.RateLimitError(
            message="quota", model="m", llm_provider="anthropic"
        )

    monkeypatch.setattr(litellm, "completion", boom)
    r = client.post("/agents/complete", json={"prompt": "hi"})
    assert r.status_code == 503


def test_complete_route_provider_error_maps_to_502(client, monkeypatch):
    def boom(**_):
        raise litellm.exceptions.APIError(
            status_code=500, message="down", model="m", llm_provider="anthropic"
        )

    monkeypatch.setattr(litellm, "completion", boom)
    r = client.post("/agents/complete", json={"prompt": "hi"})
    assert r.status_code == 502


def test_metrics_endpoint_includes_agent_series(client):
    client.post("/agents/complete", json={"prompt": "hi"})
    body = client.get("/metrics").text
    assert "app_agent_calls_total" in body
    assert "app_agent_cost_usd_total" in body
```

- [ ] **Step 2: Mirror + run to confirm red**

Render with `--with agents`, mirror the functional test, then:
Run: `cd /tmp/agentwork && uv run pytest tests/functional/test_agents.py -q`
Expected: FAIL — 404 on `/agents/complete` (route not yet present) and no `app_agent_*` in `/metrics`.

- [ ] **Step 3: Implement the route**

Path: `src/framework_cli/template/src/{{package_name}}/routes/{{ 'agents.py' if 'agents' in batteries else '' }}.jinja`

```python
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from {{ package_name }}.agents.errors import AgentExhausted
from {{ package_name }}.agents.metrics import agent_metrics
from {{ package_name }}.agents.service import AgentService

router = APIRouter()


class CompleteRequest(BaseModel):
    prompt: str
    system: str | None = None


class CompleteResponse(BaseModel):
    text: str
    usage: dict[str, int]


@router.post("/agents/complete", response_model=CompleteResponse)
def complete(body: CompleteRequest, request: Request) -> CompleteResponse:
    """One-shot LLM completion — demonstrates the agent runtime end to end."""
    service = AgentService(request.app.state.settings, metrics=agent_metrics)
    try:
        result = service.complete([{"role": "user", "content": body.prompt}], system=body.system)
    except AgentExhausted as exc:
        raise HTTPException(status_code=503, detail="agent provider exhausted") from exc
    except Exception as exc:  # AgentError and any other provider/transport failure
        raise HTTPException(status_code=502, detail="agent provider error") from exc
    return CompleteResponse(text=result.text, usage=result.usage)
```

> `AgentExhausted` must be caught before the broad `Exception` (it subclasses `AgentError`).

- [ ] **Step 4: Wire agent metrics into `/metrics`**

In `routes/health.py.jinja`, after the existing `{%- if "graphql" in batteries %}` metrics block, add:

```jinja
{%- if "agents" in batteries %}

    from {{ package_name }}.agents.metrics import agent_metrics

    body += agent_metrics.render_prometheus()
{%- endif %}
```

- [ ] **Step 5: Mirror (render+cp the two `.jinja` files and health.py) + run green**

Run: `cd /tmp/agentwork && uv run pytest tests/functional/test_agents.py -q`
Expected: PASS (route returns text/usage; 503/502 mapping; `/metrics` carries `app_agent_*`).

- [ ] **Step 6: Format-check the rendered output**

Run: `cd /tmp/agentwork && uv run ruff format --check src/demo/routes/agents.py src/demo/routes/health.py tests/functional/test_agents.py`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/routes/" "src/framework_cli/template/tests/functional/{{ 'test_agents.py' if 'agents' in batteries else '' }}.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk12): POST /agents/complete route + /metrics wiring"
```

---

## Task 7: Add the `litellm` dependency to the template (under the agents guard)

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja`

- [ ] **Step 1: Add the dependency**

In the `dependencies = [` list of `pyproject.toml.jinja`, add a guarded entry alongside the other battery deps:

```jinja
{% if "agents" in batteries %}    "litellm>=1.88.1",
{% endif %}
```

(Match the surrounding `{% if ... %}    "<dep>",\n{% endif %}` formatting exactly so `ruff`/`toml` stay clean.)

- [ ] **Step 2: Render with agents and confirm the dep is present and resolves**

Render with `--with agents`, then:
Run: `cd /tmp/agentwork && grep -n litellm pyproject.toml && uv lock && uv sync --extra dev`
Expected: `litellm>=1.88.1` present; lock + sync succeed.

- [ ] **Step 3: Confirm a baseline (no-agents) render omits litellm**

Render to `/tmp/agentbase` without agents, then:
Run: `grep -c litellm /tmp/agentbase/pyproject.toml`
Expected: `0`.

- [ ] **Step 4: Commit**

```bash
git add "src/framework_cli/template/pyproject.toml.jinja" PLAN.md ACTION_LOG.md
```
Then separately:
```bash
git commit -m "feat(fwk12): add litellm dep to generated projects under agents guard"
```

---

## Task 8: Full render + acceptance + eval-fixture coupling check

**Files:**
- Run-only (framework tests): `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`, `tests/test_obs_completeness.py`
- Possibly modify: eval fixtures under `tests/eval/fixtures/` *only if* a touched template file anchors a `change.patch`.

- [ ] **Step 1: Run the framework gate (source-level)**

Run:
```bash
uv run pytest -q -k "not acceptance"
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. (mypy excludes the template payload; this checks `batteries.py` etc.)

- [ ] **Step 2: Run the copier-runner + obs tests**

Run: `uv run pytest tests/test_copier_runner.py tests/test_obs_completeness.py -q`
Expected: PASS — agents renders and interpolates; obs surface satisfied.

- [ ] **Step 3: Run acceptance (the generated project's own suite, coverage, pre-commit)**

Run: `TMPDIR=/var/tmp uv run pytest tests/acceptance/test_rendered_project.py -q`
Expected: PASS, **including `test_rendered_project_precommit_runs_clean`** for an agents-inclusive render (clean first `pre-commit`). Investigate any failure with [[systematic-debugging]] — do not paper over.

- [ ] **Step 4: Check eval-fixture coupling** ([[eval-fixtures-coupled-to-template]])

Run: `git grep -l "agents\|litellm" tests/eval/fixtures/ || echo "no fixture coupling"`
Expected: `no fixture coupling` (this slice adds new files; it does not edit files existing fixtures anchor on). If any fixture references a touched file, re-anchor it (render + `patch --fuzz` + `git diff`) and scan with that fixture's own batteries.

- [ ] **Step 5: Commit any fixture re-anchoring (only if needed)**

```bash
git add tests/eval/fixtures PLAN.md ACTION_LOG.md
```
Then separately (skip if nothing changed):
```bash
git commit -m "test(fwk12): re-anchor eval fixtures after agents template additions"
```

---

## Task 9: Branch-end review + finish

**Files:**
- Update: `PLAN.md` (tick FWK12 → Done), `ACTION_LOG.md` (completion entry).

- [ ] **Step 1: Branch-end whole-branch code-quality review (Opus)**

Dispatch one Opus reviewer over the full branch diff ([[subagent-review-model-pattern]]). Focus: secret handling (`SecretStr` never logged; key not echoed), error-mapping completeness, metric label-cardinality, `in-process` obs correctness, Jinja guard correctness (no agents symbols leak into a no-agents render), and house-style fit. Address findings; re-run Task 8 gates after any change.

- [ ] **Step 2: Verify the commit-gate marker path** ([[controller-skip-marker-recipe]])

If committing through `reviewers-gate-check.sh`, generate `framework gate-prepare`, write `.framework/audit/marker.json` (`staged_hash`, verdict PASS, drift false) as one `git add`+marker call, then commit separately.

- [ ] **Step 2.5: Verify all subagent work was actually committed** ([[subagent-implementers-stop-before-commit]])

Run: `git status --short && git log --oneline master..HEAD`
Expected: clean tree; one commit per task. Finish any commit an implementer staged but did not complete.

- [ ] **Step 3: Update PLAN.md + ACTION_LOG.md**

Move FWK12 to `Done` in `PLAN.md`; append an `ACTION_LOG.md` completion entry (next `#00NN`). Stage both with the final commit.

- [ ] **Step 4: Finish the branch** ([[finishing-a-development-branch]])

Push `fwk12-agents-battery`, open a single PR to `master` (squash-friendly), and confirm required checks (`gate`, `build`, `render-complete`) go green before self-merge. After merge, grep `master` for an agents marker to confirm the tip landed ([[verify-master-content-after-pr-merge]]).

---

## Self-Review (completed by plan author)

- **Spec coverage:** config (Task 3) · completion + structured output service (Task 5) · demo route (Task 6) · error→HTTP 502/503 (Task 6) · in-process metrics + alert + dashboard (Tasks 2, 4, 6) · obs-completeness guard (Tasks 1–2, 8) · litellm dep (Task 7) · template-payload TDD + render/acceptance + pre-commit + eval coupling (Task 8) · BatterySpec `gates_agents=()` (Task 1). Structured output is shipped + tested with no route (Task 5), per spec. Streaming, tools, hot-swap: out of scope (FWK14/FWK13).
- **Refinements vs spec (flagged to user):** latency realized as a p99 **gauge** (house metrics style) rather than a histogram; `model` dropped as a metric label (house label-light doctrine). Both preserve the intended signals.
- **Type consistency:** `AgentService.complete(messages, system=None) -> CompletionResult{text, usage}`; `complete_structured(messages, schema, system=None) -> T`; `agent_metrics` singleton + `AgentMetrics` methods `record_call/record_tokens/record_cost/record_latency_ms/render_prometheus/reset`; settings `agent_provider/agent_model/agent_max_tokens/agent_temperature/agent_api_key` — names identical across Tasks 3–6.
- **No placeholders:** every code/alert/dashboard/test block is complete.
