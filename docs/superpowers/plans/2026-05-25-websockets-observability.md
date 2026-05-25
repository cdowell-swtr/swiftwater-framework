# Websockets Observability Backfill (Plan 8e-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrofit the websockets battery to the §5 battery-observability contract — an in-process active-connections gauge + message/connection counters on `/metrics`, plus alert rules and a Grafana dashboard.

**Architecture:** A process-wide thread-safe `WebSocketMetrics` singleton (mirroring `webhooks/metrics.py`) holds an active-connections gauge (inc/dec in lockstep with the `ConnectionManager`'s `_active`, floored at 0) and three counters. The manager + `/ws` route call it; `/metrics` appends its exposition (gated). Alerts + dashboard ship as new conditional battery-payload files. No `/ws` behavior change; no new Prometheus scrape target → no `prometheus.yml`/integrity impact.

**Tech Stack:** FastAPI WebSockets, stdlib `threading`, Prometheus exposition text, Copier templating, pytest (TestClient WebSocket) + testcontainers.

**Reference spec:** `docs/superpowers/specs/2026-05-25-websockets-observability-design.md`. This is the sibling of Plan 8b-1 (webhooks observability) — follow the same patterns.

---

## Conventions (every task)

- The `websockets` battery renders when `"websockets" in batteries`. Files with `{{ }}` must end `.jinja` (`copier.yml` `_templates_suffix: .jinja`); plain relative-import/stdlib files stay `.py`. Conditional files use the templated-path form.
- `src/framework_cli/template/` is PAYLOAD — not linted/typed as framework source. The framework's own tests (`tests/test_copier_runner.py`) ARE linted/typed.
- Render-test helper: `render_project(dest, {**DATA, "batteries": [...]})` from `framework_cli.copier_runner`; `DATA` has `package_name="demo"`, no `batteries` key.
- **Commit-gate hook:** `git commit` is blocked unless a `CLAUDE.md` change is staged. Before each task commit, edit ONLY the `- **Last updated:**` line in `CLAUDE.md`; use SEPARATE `git add` and `git commit` Bash calls (a combined call trips the hook).
- **Jinja brace safety:** the websocket metrics are UNLABELED (`app_websocket_connections_active`, no `{...}` selector), so assert strings + PromQL exprs contain no `{`/`}` at all — zero Jinja-collision risk. Never introduce an f-string with literal `{{`/`}}` in a `.jinja`.
- No LOCKED/HYBRID file is touched (no `prometheus.yml`, no compose, no `slo_alerts.yml`/`slo.json`) → no integrity work beyond "gated blocks render nothing when absent."

## File Structure

- **Create** `template/src/{{package_name}}/{% if "websockets" in batteries %}websockets{% endif %}/metrics.py` — the `WebSocketMetrics` singleton (plain `.py`; stdlib only).
- **Create** `template/tests/unit/{{ 'test_websockets_unit.py' if 'websockets' in batteries else '' }}.jinja` — generated hermetic unit tests.
- **Modify** `template/src/{{package_name}}/{% if "websockets" in batteries %}websockets{% endif %}/connection_manager.py` — emit opened/closed/sent.
- **Modify** `template/src/{{package_name}}/routes/{{ 'websockets.py' if 'websockets' in batteries else '' }}.jinja` — emit message_received.
- **Modify** `template/src/{{package_name}}/routes/health.py.jinja` — append the ws exposition to `/metrics`, gated.
- **Modify** `template/tests/functional/{{ 'test_websockets.py' if 'websockets' in batteries else '' }}.jinja` — assert metrics via `/metrics`.
- **Create** `template/infra/observability/prometheus/alerts/{{ 'websockets_alerts.yml' if 'websockets' in batteries else '' }}.jinja` — 2 alert rules.
- **Create** `template/infra/observability/grafana/dashboards/{{ 'websockets.json' if 'websockets' in batteries else '' }}.jinja` — "WebSockets" dashboard.
- **Modify** `tests/test_copier_runner.py` — render tests + a websockets-only ruff-format-clean guard.

---

### Task 1: `WebSocketMetrics` singleton + generated unit test

**Files:**
- Create: `template/src/{{package_name}}/{% if "websockets" in batteries %}websockets{% endif %}/metrics.py`
- Create: `template/tests/unit/{{ 'test_websockets_unit.py' if 'websockets' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render tests** (in `tests/test_copier_runner.py`)

```python
def test_render_websockets_metrics_module(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    assert (dest / "src" / DATA["package_name"] / "websockets" / "metrics.py").exists()
    assert (dest / "tests" / "unit" / "test_websockets_unit.py").exists()

def test_render_no_websockets_metrics_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "src" / DATA["package_name"] / "websockets" / "metrics.py").exists()
```

- [ ] **Step 2: Run it, confirm fail**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k websockets_metrics -v` → FAIL.

- [ ] **Step 3: Create the singleton** `websockets/metrics.py` (plain `.py`):

```python
"""Process-wide WebSocket metrics — an active-connections gauge + lifecycle/message counters.

A module-level singleton (like observability/recoverability.py / webhooks/metrics.py), updated
by the connection manager + the /ws route and appended to the /metrics exposition. Label-light
by design (no per-connection / per-message-type labels — cardinality).
"""

from __future__ import annotations

import threading


class WebSocketMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._opened = 0
        self._received = 0
        self._sent = 0

    def connection_opened(self) -> None:
        with self._lock:
            self._active += 1
            self._opened += 1

    def connection_closed(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)  # floored — never negative on a double-close

    def message_received(self) -> None:
        with self._lock:
            self._received += 1

    def message_sent(self) -> None:
        with self._lock:
            self._sent += 1

    def render_prometheus(self) -> str:
        with self._lock:
            active, opened, received, sent = self._active, self._opened, self._received, self._sent
        return (
            "# HELP app_websocket_connections_active Currently open WebSocket connections\n"
            "# TYPE app_websocket_connections_active gauge\n"
            f"app_websocket_connections_active {active}\n"
            "# HELP app_websocket_connections_opened_total WebSocket connections accepted\n"
            "# TYPE app_websocket_connections_opened_total counter\n"
            f"app_websocket_connections_opened_total {opened}\n"
            "# HELP app_websocket_messages_received_total Inbound WebSocket messages\n"
            "# TYPE app_websocket_messages_received_total counter\n"
            f"app_websocket_messages_received_total {received}\n"
            "# HELP app_websocket_messages_sent_total Outbound WebSocket messages (broadcast fan-out)\n"
            "# TYPE app_websocket_messages_sent_total counter\n"
            f"app_websocket_messages_sent_total {sent}\n"
        )

    def reset(self) -> None:
        with self._lock:
            self._active = 0
            self._opened = 0
            self._received = 0
            self._sent = 0


ws_metrics = WebSocketMetrics()
"""The process-wide singleton imported by the connection manager, the /ws route, and /metrics."""
```

- [ ] **Step 4: Create the generated unit test** `tests/unit/{{ 'test_websockets_unit.py' if 'websockets' in batteries else '' }}.jinja` (hermetic — fresh instances, no singleton/network):

```jinja
"""Websockets battery — unit tests for the in-process metrics (hermetic)."""

from {{ package_name }}.websockets.metrics import WebSocketMetrics


def test_connection_open_close_tracks_active_gauge():
    m = WebSocketMetrics()
    m.connection_opened()
    m.connection_opened()
    m.connection_closed()
    out = m.render_prometheus()
    assert "app_websocket_connections_active 1" in out
    assert "app_websocket_connections_opened_total 2" in out


def test_connection_closed_floors_at_zero():
    m = WebSocketMetrics()
    m.connection_closed()  # close with nothing open
    m.connection_closed()
    assert "app_websocket_connections_active 0" in m.render_prometheus()


def test_message_counters_increment():
    m = WebSocketMetrics()
    m.message_received()
    m.message_sent()
    m.message_sent()
    out = m.render_prometheus()
    assert "app_websocket_messages_received_total 1" in out
    assert "app_websocket_messages_sent_total 2" in out


def test_render_has_gauge_and_counter_types_at_zero():
    out = WebSocketMetrics().render_prometheus()
    assert "# TYPE app_websocket_connections_active gauge" in out
    assert "# TYPE app_websocket_connections_opened_total counter" in out
    assert "app_websocket_connections_active 0" in out


def test_reset_clears():
    m = WebSocketMetrics()
    m.connection_opened()
    m.message_received()
    m.reset()
    out = m.render_prometheus()
    assert "app_websocket_connections_active 0" in out
    assert "app_websocket_messages_received_total 0" in out
```

- [ ] **Step 5: Run the render tests, confirm pass**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k websockets_metrics -v` → PASS. Render with websockets; ast.parse the rendered `websockets/metrics.py` + `tests/unit/test_websockets_unit.py` (valid Python; `{{ package_name }}` → `demo`). `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 6: Commit** (stage template files + test file first, then bump CLAUDE.md `Last updated` and `git add CLAUDE.md` separately; see the commit-gate convention)

```bash
git commit -m "feat(websockets-obs): WebSocketMetrics gauge+counters singleton + unit test"
```

---

### Task 2: Emission wiring + `/metrics` append + functional test

**Files:**
- Modify: `template/src/{{package_name}}/{% if "websockets" in batteries %}websockets{% endif %}/connection_manager.py`
- Modify: `template/src/{{package_name}}/routes/{{ 'websockets.py' if 'websockets' in batteries else '' }}.jinja`
- Modify: `template/src/{{package_name}}/routes/health.py.jinja`
- Modify: `template/tests/functional/{{ 'test_websockets.py' if 'websockets' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render tests**

```python
def test_render_websockets_emits_metrics(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    mgr = (dest / "src" / DATA["package_name"] / "websockets" / "connection_manager.py").read_text()
    assert "ws_metrics.connection_opened" in mgr
    assert "ws_metrics.connection_closed" in mgr
    assert "ws_metrics.message_sent" in mgr
    route = (dest / "src" / DATA["package_name"] / "routes" / "websockets.py").read_text()
    assert "ws_metrics.message_received" in route
    health = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "ws_metrics.render_prometheus" in health

def test_render_health_clean_without_websockets(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    health = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "ws_metrics" not in health
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Wire `connection_manager.py`.** Add the import + 3 emission calls (emit `connection_closed` INSIDE the existing `if ws in self._active:` guard, after `remove`, so the gauge stays in lockstep). Final file:

```python
"""Minimal WebSocket connection registry."""

from __future__ import annotations

from fastapi import WebSocket

from .metrics import ws_metrics


class ConnectionManager:
    def __init__(self) -> None:
        self._active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.append(ws)
        ws_metrics.connection_opened()

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._active:
            self._active.remove(ws)
            ws_metrics.connection_closed()

    async def broadcast(self, message: str) -> None:
        for ws in list(self._active):
            await ws.send_text(message)
            ws_metrics.message_sent()
```

- [ ] **Step 4: Wire the `/ws` route.** In `routes/{{ 'websockets.py' ... }}.jinja`, add the import + `message_received` after each receive:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from {{ package_name }}.websockets.connection_manager import ConnectionManager
from {{ package_name }}.websockets.metrics import ws_metrics

router = APIRouter()
_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Echo + broadcast: each received message is broadcast to all connections."""
    await _manager.connect(ws)
    try:
        while True:
            message = await ws.receive_text()
            ws_metrics.message_received()
            await _manager.broadcast(message)
    except WebSocketDisconnect:
        _manager.disconnect(ws)
```

- [ ] **Step 5: Append the exposition in `/metrics`.** In `routes/health.py.jinja`'s `metrics()` handler, add a gated websockets block alongside the existing recoverability/webhooks/workers appends. **Mirror the EXACT whitespace handling of the webhooks block** (it uses `{%- if %}` strip-before to stay ruff-format-clean across combos). Read the current `health.py.jinja` and add, after the webhooks block (or adjacent to it):

```jinja
{% if "websockets" in batteries %}
    from {{ package_name }}.websockets.metrics import ws_metrics

    body += ws_metrics.render_prometheus()
{% endif %}
```

> Use the same `{%-`/`-%}` strip pattern the webhooks block uses so all combos render format-clean (Task 4's guard verifies this). No try/except — `render_prometheus` is pure in-memory.

- [ ] **Step 6: Extend the functional test.** Append to `tests/functional/{{ 'test_websockets.py' ... }}.jinja` (reset the process-wide singleton first; the existing test uses `TestClient(create_app())` + `client.websocket_connect`):

```jinja
def test_metrics_track_connection_and_messages() -> None:
    from {{ package_name }}.websockets.metrics import ws_metrics

    ws_metrics.reset()
    client = TestClient(create_app())
    with client.websocket_connect("/ws") as ws:
        ws.send_text("hello")
        assert ws.receive_text() == "hello"
        body = client.get("/metrics").text
        assert "app_websocket_connections_active 1" in body
        assert "app_websocket_connections_opened_total 1" in body
        assert "app_websocket_messages_received_total 1" in body
        assert "app_websocket_messages_sent_total 1" in body
    # exiting the context closes the socket → the route's WebSocketDisconnect handler
    # disconnects → the gauge returns to 0.
    assert "app_websocket_connections_active 0" in client.get("/metrics").text
```

> All assert strings are plain literals with NO braces (unlabeled metrics) — no Jinja collision. If the post-`with` gauge==0 assertion proves timing-flaky under TestClient (the disconnect runs on context exit), drop just that last line — the in-`with` assertions are the deterministic core. Note which you kept in your report.

- [ ] **Step 7: Run + verify.**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k "websockets" -v` → all pass (new + existing, no regression). Render with websockets; ast.parse the rendered `connection_manager.py`, `routes/websockets.py`, `routes/health.py` (valid Python); render WITHOUT websockets → `health.py` has no `ws_metrics` and is valid Python. `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(websockets-obs): emit gauge+counters from the manager/route + expose on /metrics"
```

---

### Task 3: Alert rules + Grafana dashboard

**Files:**
- Create: `template/infra/observability/prometheus/alerts/{{ 'websockets_alerts.yml' if 'websockets' in batteries else '' }}.jinja`
- Create: `template/infra/observability/grafana/dashboards/{{ 'websockets.json' if 'websockets' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render tests**

```python
def test_render_websockets_alerts_and_dashboard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    alerts = dest / "infra" / "observability" / "prometheus" / "alerts" / "websockets_alerts.yml"
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "websockets.json"
    assert alerts.exists() and dash.exists()
    import yaml as _yaml
    import json as _json
    parsed = _yaml.safe_load(alerts.read_text())
    assert parsed["groups"][0]["name"] == "websockets"
    assert len(parsed["groups"][0]["rules"]) == 2
    _json.loads(dash.read_text())  # valid JSON

def test_render_no_websockets_alerts_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "infra" / "observability" / "prometheus" / "alerts" / "websockets_alerts.yml").exists()
    assert not (dest / "infra" / "observability" / "grafana" / "dashboards" / "websockets.json").exists()
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Create `websockets_alerts.yml.jinja`** (no `{{ }}` in the body — single-token PromQL, no label selectors — so it renders verbatim, conditioned only by the templated filename):

```jinja
groups:
- name: websockets
  rules:
  - alert: HighWebSocketConnectionChurn
    expr: rate(app_websocket_connections_opened_total[5m]) / clamp_min(app_websocket_connections_active, 1) > 0.5
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: High WebSocket connection churn (clients reconnecting/flapping) — app-specific default, tune or remove
  - alert: WebSocketConnectionsIdle
    expr: app_websocket_connections_active > 0 and rate(app_websocket_messages_received_total[10m]) == 0
    for: 20m
    labels:
      severity: warning
    annotations:
      summary: WebSocket connections open but no inbound messages for 20m (possible stuck/half-open) — expected for server-push-only apps; widen the window or remove this rule
```

> Verify the rendered file parses as YAML with `groups[0].name == "websockets"` and 2 rules. Both exprs are rate/gauge-based (no `increase()`+`for≥window` pitfall). `clamp_min(...,1)` guards div-by-zero.

- [ ] **Step 4: Create `websockets.json.jinja`** — a minimal valid Grafana dashboard, `title: "WebSockets"`, `uid: "websockets"`. **Read the existing `infra/observability/grafana/dashboards/{{ 'webhooks.json' if 'webhooks' in batteries else '' }}.jinja`** for the exact schema (schemaVersion, datasource uid, panel/target/fieldConfig shape) and model `websockets.json` on it with three panels (separate targets, plain legends — no `{{...}}` legend vars, so no Jinja escaping):
  - a `stat` panel "Active connections" → `app_websocket_connections_active`;
  - a `timeseries` panel "Message rate" with two targets `rate(app_websocket_messages_received_total[5m])` (legend "received") and `rate(app_websocket_messages_sent_total[5m])` (legend "sent");
  - a `timeseries` panel "Connection open rate" → `rate(app_websocket_connections_opened_total[5m])`.
  Must be valid JSON. Match `webhooks.json`'s structure exactly — no invented fields.

- [ ] **Step 5: Run the render tests, confirm pass.**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k "websockets" -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(websockets-obs): connection-churn + idle alert rules + grafana dashboard"
```

---

### Task 4: Pre-commit-clean guard + verification

**Files:**
- Modify: `tests/test_copier_runner.py`

- [ ] **Step 1: Add a websockets-only ruff-format-clean render guard.** Find the existing webhooks/workers format guards (`grep -n "ruff_format_clean\|_assert_ruff_format_clean" tests/test_copier_runner.py`) and add an analogous one, mirroring its EXACT shape/helper:

```python
def test_render_websockets_battery_is_ruff_format_clean(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["websockets"]})
    _assert_ruff_format_clean(dest)   # use whatever helper/inline form the webhooks guard uses
```

> Copy the existing webhooks guard verbatim, changing only `batteries=["websockets"]`. If it's an inline `subprocess.run([...ruff, format, --check...])`, replicate that.

- [ ] **Step 2: Run it, confirm green.** If it FAILS, the Task 2 gated `health.py` block left the render format-dirty — fix the `{%- %}` whitespace until the websockets render is `ruff format`-clean (the 8c/8b-1 regression class).

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k "websockets" -v`

- [ ] **Step 3: Full framework render-test pass + lint/type:**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -q` → all green. `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 4: Docker acceptance** — the existing `test_rendered_project_with_websockets_battery_passes` runs the generated suite incl. the new functional metrics test:

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/acceptance/test_rendered_project.py -k "websockets" -v`
Expected: PASS (the generated `test_websockets.py::test_metrics_track_connection_and_messages` runs here, proving the gauge + counters work end-to-end). Paste the summary line. If it fails, read the captured output + fix the root cause.

- [ ] **Step 5: Commit**

```bash
git commit -m "test(websockets-obs): websockets render is ruff-format-clean (pre-commit guard)"
```

---

## Final verification (controller, before finishing the branch)

```bash
uv run ruff check .
uv run mypy src
uv lock --check
rm -rf /tmp/pytest-of-$USER
uv run pytest -q          # full suite incl. Docker acceptance — all green
uv build
```

Manual spot check (no Docker): `framework new --with websockets` → `websockets/metrics.py` present; `connection_manager.py` emits opened/closed/sent; `routes/websockets.py` emits received; `/metrics` in `health.py` appends `ws_metrics.render_prometheus()`; `websockets_alerts.yml` + `websockets.json` present + valid; `framework integrity --ci` green (no LOCKED file changed). `framework new` (no battery) → none present, `health.py` has no `ws_metrics`. `framework downskill websockets` → removed, integrity green, **no `--force` needed** (8b-1's byte-identity exclusion handles the gated `health.py` import).

---

## Self-Review (against the spec)

**Spec coverage:**
- §2 in-process singleton (gauge + 3 counters, floored close) → Task 1.
- §3 emission points (manager connect/disconnect-in-guard/broadcast, route receive, `/metrics` append) → Task 2.
- §4 alerts (churn + idle, tunable warnings) + dashboard → Task 3.
- §5 testing: unit (Task 1), functional incl. floored-gauge + message counts (Tasks 1–2), render (Tasks 1–3), format guard (Task 4), acceptance rides existing (Task 4).
- §6 no scrape target / no LOCKED file / downskill handled by 8b-1 → verified in Tasks 2–4 + final spot check.
- Out-of-scope (labels, histograms, closed_total, manager hardening) → correctly omitted.

**Placeholder scan:** none — concrete code for the singleton, all 4 emission points, the `/metrics` append, both alert exprs, the unit + functional tests; the dashboard JSON points at the existing `webhooks.json` for the boilerplate schema (panels/queries specified), matching how 8b-1/8c handled dashboards.

**Type consistency:** `WebSocketMetrics` methods `connection_opened()`/`connection_closed()`/`message_received()`/`message_sent()`/`render_prometheus()`/`reset()`, the `ws_metrics` singleton, and the metric names `app_websocket_connections_active`/`_connections_opened_total`/`_messages_received_total`/`_messages_sent_total` are consistent across Tasks 1–3 and the manager/route/health wiring.

---

*End of plan. Next step: execution via superpowers:subagent-driven-development.*
