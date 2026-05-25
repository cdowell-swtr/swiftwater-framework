# Webhooks Observability Backfill (Plan 8b-1) — Design Spec

**Date:** 2026-05-24
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 8b (the webhooks battery — `routes/webhooks.py`, the `webhooks/` package, the transactional inbox), Plan 8c (the **battery observability contract** §5 — formalized + first implemented for workers), Plan 4 (`observability/recoverability.py` — the process-wide thread-safe metric-singleton pattern appended to `/metrics`), Plan 3b (the Prometheus → Alertmanager → Grafana stack; `alerts/*.yml` glob + dashboard provisioning).

---

## 1. Purpose & scope

Retrofit the 8b `webhooks` battery to the **battery observability contract** the workers battery established (8c §5): every battery that adds a runtime surface ships (a) metrics on the Prometheus pipeline, (b) a liveness signal where it runs a process, (c) alert rule(s) + a dashboard panel. Webhooks shipped without any of this; 8b-1 closes the gap. **No behavior change to the ingress** — this is additive observability only.

**In scope:**
- A `webhooks/metrics.py` in-process counter singleton (`WebhookMetrics`) exposing `app_webhooks_received_total{outcome=...}`.
- `routes/webhooks.py` increments the counter at each outcome.
- `/metrics` (in `routes/health.py`) appends the webhooks exposition, gated `{% if "webhooks" in batteries %}`.
- A conditional `webhooks_alerts.yml` (2 alert rules) + a conditional `webhooks.json` Grafana dashboard.
- Tests: unit (the singleton), functional (each outcome → `/metrics`), render, and the existing acceptance variant rides the extended functional test.

**Out of scope (deferred / YAGNI):**
- **Event-type label** — provider-defined event types are unbounded; using them as a Prometheus label is the classic cardinality-explosion anti-pattern. Outcome (4 bounded values) is the only label. Builders who want per-type breakdown add it deliberately.
- **Latency histogram** — the in-process registry is counter-based and the inline handler is the lightweight path; latency tracking is a builder add-on.
- **Inbox-table-size gauge** — `webhook_events` is an append-only dedup log that grows unbounded; its size is not an actionable SLO (the `duplicate` counter already captures dedup activity).
- **`websockets` observability** → Plan 8e-1 (sibling backfill, same contract).

## 2. Metrics — an in-process counter singleton

Webhooks runs **in the FastAPI app process** (the route handler), so — unlike workers' separate-process Celery tasks (which needed a `celery-exporter` scrape target) — the natural emitter is an **in-process thread-safe singleton**, mirroring Plan 4's `observability/recoverability.py` exactly.

- **`webhooks/metrics.py`** (new, battery package): a module-level `webhook_metrics = WebhookMetrics()` singleton.
  - `record(outcome: str) -> None` — thread-safe increment (a `threading.Lock` + a `dict[str, int]` keyed by outcome), matching `RecoverabilityMetrics`' style.
  - `render_prometheus() -> str` — emits one counter family:
    ```
    # HELP app_webhooks_received_total Inbound webhooks by processing outcome
    # TYPE app_webhooks_received_total counter
    app_webhooks_received_total{outcome="accepted"} <n>
    app_webhooks_received_total{outcome="rejected_signature"} <n>
    app_webhooks_received_total{outcome="malformed"} <n>
    app_webhooks_received_total{outcome="duplicate"} <n>
    ```
    All four outcome series are always emitted (initialized to 0), so the metric exists before the first event — avoids `absent()`-vs-zero ambiguity in alert expressions.
  - `reset()` — for test isolation (matches `recoverability.reset()`).
- **`routes/webhooks.py`** increments at each of its four return points (the outcomes already exist in the 8b route):
  - HMAC verify fails → `record("rejected_signature")` → 401.
  - `await request.json()` raises `ValueError` → `record("malformed")` → 400.
  - `IntegrityError` on the inbox insert (duplicate) → `record("duplicate")` → 200 no-op.
  - inbox insert + `handle_event` + commit succeed → `record("accepted")` → 200.
- **`routes/health.py` `/metrics`** appends `webhook_metrics.render_prometheus()` to `body`, gated `{% if "webhooks" in batteries %}` — exactly as it already appends `recoverability.render_prometheus()` (and, with workers, the DLQ gauge). The append is unconditional-safe (pure in-memory read, no I/O, cannot raise) so no try/except is needed (contrast the workers DLQ gauge, which touches the DB).

This keeps webhooks metrics self-contained in the battery package and rides the app's **existing** `/metrics` Prometheus scrape — **no new scrape target** (unlike workers).

## 3. Alert rules + dashboard (separate battery-payload files)

Following the workers pattern (separate files, not edits to the LOCKED `slo_alerts.yml`/`slo.json`):

- **`infra/observability/prometheus/alerts/{{ 'webhooks_alerts.yml' if 'webhooks' in batteries else '' }}.jinja`** (new; Prometheus already globs `alerts/*.yml`; not integrity-tracked — battery payload):
  - **HighWebhookSignatureRejectionRate** — a sustained high share of `rejected_signature` outcomes (a security/misconfig signal: a sender with the wrong secret, a rotated key not propagated, or probing). Expr compares the `rejected_signature` rate to total received, e.g. `sum(rate(app_webhooks_received_total{outcome="rejected_signature"}[5m])) / clamp_min(sum(rate(app_webhooks_received_total[5m])), 1) > 0.2`, `for: 5m`, severity warning.
  - **HighWebhookMalformedRate** — sustained `malformed` share (a misbehaving sender sending non-JSON after a valid signature): same shape on `outcome="malformed"`, `for: 5m`, warning.
  - Both are rate-based with `for` (5m) **shorter than** the rate window (5m is acceptable; the rate window is a sliding `[5m]` so the condition persists) — heeding the 8c `for`-vs-window lesson (don't set `for` ≥ a fixed `increase()` window; rate-based expressions don't have that pitfall, but keep `for` modest).
- **`infra/observability/grafana/dashboards/{{ 'webhooks.json' if 'webhooks' in batteries else '' }}.jinja`** (new; auto-provisioned from the dashboards dir; not tracked): a **"Webhooks"** dashboard (`uid: "webhooks"`), modeled on `workers.json`/`slo.json` schema — a timeseries panel of received rate stacked by `outcome`, and a stat/timeseries panel for the duplicate (dedup) rate. Minimal, valid JSON.

## 4. Integrity & rendering

- `webhooks/metrics.py` is battery payload (lives in the conditional `webhooks/` dir); `routes/webhooks.py` + `routes/health.py` are non-tracked app source; the alert + dashboard files are new untracked battery payload. **No LOCKED/HYBRID file is touched** — in particular `prometheus.yml` is unchanged (no new scrape target). So there is **no integrity-manifest impact** and no byte-identity concern beyond the standard "gated blocks render nothing when absent."
- All gated additions must keep a freshly-rendered project **pre-commit-clean** (`ruff format` + EOF) — the 8c regression lesson. The render-level format guards added in 8c cover workers/both; extend the guard (or a render test) to the **webhooks-only** combo.

## 5. Testing

- **Unit (hermetic):** `WebhookMetrics` — `record` increments the right outcome series; all four series present (0-initialized) in `render_prometheus`; `reset` clears; the exposition format is valid Prometheus text. (Ships as a generated unit test in the webhooks battery's test payload, or extends the existing webhooks unit coverage.)
- **Functional (real Postgres):** extend the generated `tests/functional/test_webhooks.py` — after exercising the valid-sig (200) / bad-sig (401) / malformed (400) / duplicate (200) cases, GET `/metrics` and assert `app_webhooks_received_total{outcome="accepted"}` etc. reflect the calls. (The webhooks route reaches its outcomes via the existing test cases; this adds the metrics assertion.)
- **Render (`tests/test_copier_runner.py`):** with `batteries=["webhooks"]` → `webhooks/metrics.py`, `webhooks_alerts.yml`, `webhooks.json` render; `/metrics` wiring (`webhook_metrics`) present in `health.py`; the alerts YAML + dashboard JSON are valid + contain literal `{{ $value }}` where templated. Without the battery → none render, and `health.py`/`prometheus.yml`/dashboards are unchanged. A webhooks-only **ruff-format-clean** guard.
- **Acceptance (Docker):** the existing `test_rendered_project_with_webhooks_battery_passes` runs the generated suite (≥70% gate) — the extended functional test rides it, proving the counters increment end-to-end against real Postgres. (No new acceptance test needed.)

## 6. Self-review

- **Placeholders:** none — the counter singleton (mirroring `recoverability.py`), the four outcomes + the route increment points (which already exist in the 8b route), the `/metrics` append, the two alert exprs (concrete PromQL), the dashboard, and the test tiers are all specified. Event-type label, latency, and the inbox-size gauge are explicitly deferred (YAGNI), each with the reason.
- **Internal consistency:** the in-process-singleton choice is the correct per-battery mirror of 8c's contract (in-process metric for an in-process surface vs. a scrape target for a separate process); the `/metrics` append matches the established `recoverability` pattern; the separate alert/dashboard files match the workers precedent and avoid touching LOCKED files; no scrape-target change means no `prometheus.yml`/integrity impact (a real simplification over workers).
- **Scope:** one cohesive backfill (counter + alerts + dashboard + tests) for a single battery. No ingress behavior change. Websockets is the sibling 8e-1.
- **Ambiguity:** "metrics" pinned to one outcome-labeled counter with 4 bounded series (no event-type label); the increment points pinned to the route's four existing outcomes; alert exprs pinned to rate-share expressions with modest `for`.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8b-1.*
