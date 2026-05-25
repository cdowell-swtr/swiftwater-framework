# Websockets Observability Backfill (Plan 8e-1) — Design Spec

**Date:** 2026-05-25
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 8e (the websockets battery — `routes/websockets.py`, `websockets/connection_manager.py`), Plan 8b-1 (the webhooks observability backfill — the in-process metric-singleton pattern + the separate-alert/dashboard-file pattern + the downskill `usage_references` byte-identity exclusion), Plan 8c (the §5 battery-observability contract), Plan 4 (`observability/recoverability.py` — the thread-safe metric-singleton appended to `/metrics`).

---

## 1. Purpose & scope

Retrofit the 8e `websockets` battery to the **battery-observability contract** (8c §5): metrics on the Prometheus pipeline, alert rules, a dashboard. The websockets battery shipped without observability; 8e-1 closes the gap, mirroring 8b-1 (webhooks). **No behavior change** to the `/ws` echo/broadcast endpoint — additive observability only.

**In scope:**
- A `websockets/metrics.py` in-process `WebSocketMetrics` thread-safe singleton: an **active-connections gauge** + three counters (opened / messages-received / messages-sent).
- Emission wired into `connection_manager.py` (connect/disconnect/broadcast) and `routes/websockets.py` (receive); `/metrics` (in `health.py`) appends the exposition, gated `{% if "websockets" in batteries %}`.
- A conditional `websockets_alerts.yml` (2 tunable warning rules: connection-churn + idle-connections) + a conditional `websockets.json` Grafana dashboard.
- Tests: unit (the singleton), functional (TestClient WebSocket → `/metrics`), render, format guard; the existing acceptance variant rides the extended functional test.

**Out of scope (deferred / YAGNI):**
- **Per-connection or per-message-type labels** — unbounded cardinality (same stance as 8b-1's no-event-type label).
- **Message latency / size histograms** — builder add-on; the in-process registry is counter/gauge based.
- **A `closed_total` counter** — the active gauge + `opened_total` already cover open/close + churn.
- **Hardening the `ConnectionManager`'s cleanup** (it can leak a connection if a non-`WebSocketDisconnect` error skips `disconnect`) — a pre-existing robustness concern, not an observability change. The gauge faithfully mirrors the manager's `_active`, including any such leak.

## 2. Metrics — an in-process singleton

WebSockets run **in the app process** (the route + the manager), so — like webhooks, unlike workers — the emitter is an **in-process thread-safe singleton**, mirroring `webhooks/metrics.py` / `observability/recoverability.py`.

`websockets/metrics.py` (new, battery package): a module-level `ws_metrics = WebSocketMetrics()` singleton with one `threading.Lock` guarding:
- **`app_websocket_connections_active`** (gauge) — current open connections.
- **`app_websocket_connections_opened_total`** (counter) — every accepted connection.
- **`app_websocket_messages_received_total`** (counter) — every inbound message.
- **`app_websocket_messages_sent_total`** (counter) — every outbound `send_text` (broadcast fan-out: N per broadcast to N peers).

Methods (all lock-guarded):
- `connection_opened()` → `active += 1`, `opened_total += 1`.
- `connection_closed()` → `active = max(0, active - 1)` (floored — never negative even on a double-close).
- `message_received()` → `received_total += 1`.
- `message_sent()` → `sent_total += 1`.
- `render_prometheus() -> str` — emits the gauge (`# TYPE ... gauge`) + the 3 counters (`# TYPE ... counter`), each `# HELP`/`# TYPE`/value, all initialized so the series exist before the first connection.
- `reset()` — test isolation.

## 3. Emission points (lockstep with manager state)

- **`ConnectionManager.connect`** — after `await ws.accept()` + `self._active.append(ws)`, call `ws_metrics.connection_opened()`.
- **`ConnectionManager.disconnect`** — call `ws_metrics.connection_closed()` **inside** the existing `if ws in self._active:` guard, after `self._active.remove(ws)` (only when a connection is actually removed → gauge stays in lockstep, never double-decrements).
- **`ConnectionManager.broadcast`** — `ws_metrics.message_sent()` per `await ws.send_text(message)`.
- **`routes/websockets.py`** — `ws_metrics.message_received()` after each `await ws.receive_text()`.
- **`routes/health.py` `/metrics`** — gated `{% if "websockets" in batteries %}` block: a function-local `from {{ package_name }}.websockets.metrics import ws_metrics` + `body += ws_metrics.render_prometheus()`. No try/except (pure in-memory). Placed alongside the existing recoverability/webhooks/workers appends.

The manager + route import `ws_metrics` from `..websockets.metrics`. The gauge reflects the manager's `_active` faithfully; a manager-level leak (out of scope, §1) would be mirrored — which is itself useful operational signal.

## 4. Alerts + dashboard (separate battery-payload files)

Following 8b-1 / workers (separate files, never the LOCKED `slo_alerts.yml`/`slo.json`):

- **`infra/observability/prometheus/alerts/{{ 'websockets_alerts.yml' if 'websockets' in batteries else '' }}.jinja`** (new; Prometheus globs `alerts/*.yml`; not integrity-tracked). Two **warning** rules, both annotated as **app-specific defaults to tune or remove**:
  - **HighWebSocketConnectionChurn** — `rate(app_websocket_connections_opened_total[5m]) / clamp_min(app_websocket_connections_active, 1) > 0.5`, `for: 10m`. Opens-per-second far exceeding the steady connection count → reconnect storm / flapping clients. `clamp_min(...,1)` guards div-by-zero.
  - **WebSocketConnectionsIdle** — `app_websocket_connections_active > 0 and rate(app_websocket_messages_received_total[10m]) == 0`, `for: 20m`. Connections open but no inbound traffic for 20m → possible stuck/half-open connections. Annotation states explicitly: *expected for server-push-only apps — widen the window or remove this rule if your connections are legitimately idle.* The long `for` + caveat keep it from being startup/idle noise.
  - Both are rate/gauge-based (no `increase()`+`for≥window` pitfall from 8c). Single-brace PromQL label selectors are safe in a `.jinja` (only `{{`/`{%`/`{#` are Jinja).
- **`infra/observability/grafana/dashboards/{{ 'websockets.json' if 'websockets' in batteries else '' }}.jinja`** (new; auto-provisioned; not tracked): a **"WebSockets"** dashboard (`uid: "websockets"`), modeled on `webhooks.json`/`workers.json` schema — an active-connections stat panel, a messages-rate timeseries (received vs sent), and a connection-opens (churn) rate panel. Minimal, valid JSON, separate targets with plain legends (no `{{outcome}}`-style legend vars → no Jinja-escaping needed).

## 5. Testing (mirrors 8b-1)

- **Unit (hermetic, fresh instances):** `connection_opened`/`connection_closed` inc/dec the gauge; `connection_closed` floors at 0 (open once, close twice → active stays 0, never negative); `opened_total`/`received_total`/`sent_total` increment; `render_prometheus` emits the gauge + 3 counters with correct `# TYPE` lines + 0-initialized values; `reset` clears. Ships as a generated unit test in the websockets battery payload.
- **Functional (TestClient WebSocket):** using the generated test's WebSocket client, connect (assert gauge→1, opened_total→1 via `/metrics`), send one message (received_total→1; sent_total→1 — broadcast to the single peer echoes back), disconnect (gauge→0). `ws_metrics.reset()` first (process-wide singleton). Extend the existing generated `test_websockets.py`.
- **Render (`tests/test_copier_runner.py`):** with `["websockets"]` → `websockets/metrics.py`, `websockets_alerts.yml`, `websockets.json` render; `/metrics` wiring (`ws_metrics`) present in `health.py`; alerts YAML + dashboard JSON valid. Without → none render, `health.py`/`prometheus.yml` unchanged. A **websockets-only ruff-format-clean** render guard (mirror the webhooks/workers guards).
- **Acceptance (Docker):** the existing `test_rendered_project_with_websockets_battery_passes` runs the generated suite — the extended functional test rides it, proving the gauge + counters work end-to-end.

## 6. Integrity & consistency

Same clean story as 8b-1: `websockets/metrics.py` is battery payload; the route + `connection_manager.py` + `health.py` are non-tracked app source; the alert + dashboard files are new untracked battery payload. **No scrape target, no `prometheus.yml` change, no LOCKED/HYBRID file touched** → zero integrity-manifest impact. The downskill `usage_references` byte-identity exclusion (added in 8b-1) already handles the gated `health.py` import, so `framework downskill websockets` stays clean **without `--force`** — add a render-then-downskill assertion only if cheap (otherwise the 8b-1 mechanism is already proven).

## 7. Self-review

- **Placeholders:** none — the singleton API (gauge + 3 counters, floored close), the four emission points (with the in-guard disconnect detail), the `/metrics` append, the two concrete alert exprs (with `for` + tuning caveats), the dashboard, and the test tiers are all specified. Labels/histograms/`closed_total`/manager-hardening are explicitly deferred (YAGNI), each with the reason.
- **Internal consistency:** the in-process singleton mirrors 8b-1 exactly (in-process metric for an in-process surface); the gauge-in-lockstep-with-`_active` (emission inside the manager's guard) avoids drift/negatives; the alert/dashboard live in separate untracked files (no LOCKED edit, no scrape target) → the same zero-integrity-impact story as 8b-1; downskill is already handled by 8b-1's exclusion.
- **Scope:** one cohesive backfill (gauge + counters + 2 alerts + dashboard + tests) for one battery; no `/ws` behavior change. Sibling of 8b-1; the websockets+webhooks/workers combos are unaffected (independent in-process metrics).
- **Ambiguity:** "active gauge" pinned to inc/dec in lockstep with the manager's `_active` (floored at 0), emitted inside the disconnect guard; "messages sent" pinned to per-`send_text` fan-out; the idle alert pinned to `active>0 and rate(received)==0` with a long `for` + a documented tuning caveat.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8e-1.*
