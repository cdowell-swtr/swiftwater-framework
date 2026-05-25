# Webhooks Observability Backfill (Plan 8b-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrofit the webhooks battery to the §5 battery-observability contract — an in-process outcome counter on `/metrics`, plus alert rules and a Grafana dashboard.

**Architecture:** A process-wide thread-safe `WebhookMetrics` singleton (mirroring `observability/recoverability.py`) is incremented by `routes/webhooks.py` at each of its four outcomes and appended to `/metrics`. Alert rules and a dashboard ship as new conditional battery-payload files. No ingress behavior change; no new Prometheus scrape target (webhooks runs in the app process), so no `prometheus.yml`/integrity impact.

**Tech Stack:** FastAPI, stdlib `threading`, Prometheus exposition text, Copier templating, pytest + testcontainers.

**Reference spec:** `docs/superpowers/specs/2026-05-24-webhooks-observability-design.md`.

---

## Conventions (every task)

- The `webhooks` battery renders when `"webhooks" in batteries`. Files with `{{ }}` must end `.jinja` (`copier.yml` `_templates_suffix: .jinja`); plain relative-import files stay `.py`. Conditional files use the templated-path form `{{ 'name' if 'webhooks' in batteries else '' }}.jinja`.
- `src/framework_cli/template/` is PAYLOAD — not linted/typed as framework source. The framework's own tests (`tests/test_copier_runner.py`) ARE linted/typed.
- Render-test helper: `render_project(dest, {**DATA, "batteries": [...]})` from `framework_cli.copier_runner`; `DATA` has `package_name="demo"`, no `batteries` key (bare `DATA` = none).
- **Commit-gate hook:** `git commit` is blocked unless a `CLAUDE.md` change is staged. Before each task commit, edit ONLY the `- **Last updated:**` line in `CLAUDE.md` to note the task; use SEPARATE `git add` and `git commit` Bash calls (a combined call trips the hook).
- No LOCKED/HYBRID file is touched (no `prometheus.yml`, no compose) — so no integrity/byte-identity work beyond "gated blocks render nothing when absent."

## File Structure

- **Create** `template/src/{{package_name}}/{% if "webhooks" in batteries %}webhooks{% endif %}/metrics.py` — the `WebhookMetrics` singleton (plain `.py`; stdlib only, no `{{ }}`).
- **Create** `template/tests/unit/{{ 'test_webhooks_unit.py' if 'webhooks' in batteries else '' }}.jinja` — generated hermetic unit tests for the singleton.
- **Modify** `template/src/{{package_name}}/routes/{{ 'webhooks.py' if 'webhooks' in batteries else '' }}.jinja` — increment the counter at the four outcomes.
- **Modify** `template/src/{{package_name}}/routes/health.py.jinja` — append the webhooks exposition to `/metrics`, gated on webhooks.
- **Modify** `template/tests/functional/{{ 'test_webhooks.py' if 'webhooks' in batteries else '' }}.jinja` — assert the counters via `/metrics`.
- **Create** `template/infra/observability/prometheus/alerts/{{ 'webhooks_alerts.yml' if 'webhooks' in batteries else '' }}.jinja` — 2 alert rules.
- **Create** `template/infra/observability/grafana/dashboards/{{ 'webhooks.json' if 'webhooks' in batteries else '' }}.jinja` — "Webhooks" dashboard.
- **Modify** `tests/test_copier_runner.py` — render tests + a webhooks-only ruff-format-clean guard.

---

### Task 1: `WebhookMetrics` singleton + generated unit test

**Files:**
- Create: `template/src/{{package_name}}/{% if "webhooks" in batteries %}webhooks{% endif %}/metrics.py`
- Create: `template/tests/unit/{{ 'test_webhooks_unit.py' if 'webhooks' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test** (in `tests/test_copier_runner.py`)

```python
def test_render_webhooks_metrics_module(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    assert (dest / "src" / DATA["package_name"] / "webhooks" / "metrics.py").exists()
    assert (dest / "tests" / "unit" / "test_webhooks_unit.py").exists()

def test_render_no_webhooks_metrics_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "src" / DATA["package_name"] / "webhooks" / "metrics.py").exists()
```

- [ ] **Step 2: Run it, confirm fail**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k webhooks_metrics -v`
Expected: FAIL (files don't exist).

- [ ] **Step 3: Create the singleton** `webhooks/metrics.py` (plain `.py`):

```python
"""Process-wide webhook ingress metrics — counts inbound webhooks by outcome.

A module-level singleton (like observability/recoverability.py), incremented by the webhook
route and appended to the /metrics exposition. Label-light by design: `outcome` is bounded
(4 values); the provider-defined event type is deliberately NOT a label (cardinality).
"""

from __future__ import annotations

import threading

OUTCOMES = ("accepted", "rejected_signature", "malformed", "duplicate")

_HEADER = (
    "# HELP app_webhooks_received_total Inbound webhooks by processing outcome\n"
    "# TYPE app_webhooks_received_total counter\n"
)


class WebhookMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {o: 0 for o in OUTCOMES}

    def record(self, outcome: str) -> None:
        """Increment one outcome. Unknown outcomes are ignored (never crash the request,
        never create an unbounded series)."""
        with self._lock:
            if outcome in self._counts:
                self._counts[outcome] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                f'app_webhooks_received_total{{outcome="{o}"}} {self._counts[o]}'
                for o in OUTCOMES
            ]
        return _HEADER + "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counts = {o: 0 for o in OUTCOMES}


webhook_metrics = WebhookMetrics()
"""The process-wide singleton imported by routes/webhooks.py and the /metrics route."""
```

- [ ] **Step 4: Create the generated unit test** `tests/unit/{{ 'test_webhooks_unit.py' if 'webhooks' in batteries else '' }}.jinja` (hermetic — fresh instances, no singleton/DB/network):

```jinja
"""Webhooks battery — unit tests for the in-process metrics counter (hermetic)."""

from {{ package_name }}.webhooks.metrics import OUTCOMES, WebhookMetrics


def test_record_increments_outcome():
    m = WebhookMetrics()
    m.record("accepted")
    m.record("accepted")
    m.record("duplicate")
    out = m.render_prometheus()
    assert 'app_webhooks_received_total{outcome="accepted"} 2' in out
    assert 'app_webhooks_received_total{outcome="duplicate"} 1' in out


def test_all_outcomes_present_at_zero():
    out = WebhookMetrics().render_prometheus()
    for o in OUTCOMES:
        assert f'outcome="{o}"' in out
    assert "# TYPE app_webhooks_received_total counter" in out


def test_unknown_outcome_is_ignored():
    m = WebhookMetrics()
    m.record("nonsense")  # must not raise, must not add a series
    assert "nonsense" not in m.render_prometheus()


def test_reset_clears_counts():
    m = WebhookMetrics()
    m.record("accepted")
    m.reset()
    assert 'app_webhooks_received_total{outcome="accepted"} 0' in m.render_prometheus()
```

- [ ] **Step 5: Run the render tests, confirm pass**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k webhooks_metrics -v` → PASS.
Then `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "feat(webhooks-obs): WebhookMetrics counter singleton + unit test"
```
(Stage the new template files + the test file too: `git add src/framework_cli/template tests/test_copier_runner.py` before the CLAUDE.md edit; see the commit-gate convention.)

---

### Task 2: Route increments + `/metrics` append + functional test

**Files:**
- Modify: `template/src/{{package_name}}/routes/{{ 'webhooks.py' if 'webhooks' in batteries else '' }}.jinja`
- Modify: `template/src/{{package_name}}/routes/health.py.jinja`
- Modify: `template/tests/functional/{{ 'test_webhooks.py' if 'webhooks' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

```python
def test_render_webhooks_route_records_metrics(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    route = (dest / "src" / DATA["package_name"] / "routes" / "webhooks.py").read_text()
    assert "webhook_metrics.record" in route
    health = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "webhook_metrics.render_prometheus" in health

def test_render_health_clean_without_webhooks(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    health = (dest / "src" / DATA["package_name"] / "routes" / "health.py").read_text()
    assert "webhook_metrics" not in health
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Add the import + increments to the webhooks route.** In `routes/{{ 'webhooks.py' ... }}.jinja`, add the import under the existing `from ..webhooks.signature import verify`:

```python
from ..webhooks.metrics import webhook_metrics
```

Then add a `webhook_metrics.record(...)` before each of the four returns (the route's existing outcomes). The final route body becomes:

```python
    raw = await request.body()
    secret = request.app.state.settings.webhook_signing_secret
    if not verify(raw, request.headers.get(_SIGNATURE_HEADER, ""), secret):
        webhook_metrics.record("rejected_signature")
        return Response(status_code=401)
    try:
        event = await request.json()
    except ValueError:  # json.JSONDecodeError subclasses ValueError
        webhook_metrics.record("malformed")
        return Response(status_code=400)
    key = hashlib.sha256(raw).hexdigest()
    try:
        record(session, key)
        handle_event(event)
        session.commit()
    except IntegrityError:
        session.rollback()
        webhook_metrics.record("duplicate")
        return Response(status_code=200)  # duplicate delivery — already processed
    webhook_metrics.record("accepted")
    return Response(status_code=200)
```

> Note: `record(session, key)` (the inbox function) and `webhook_metrics.record(...)` (the counter method) are distinct — no collision.

- [ ] **Step 4: Append the exposition in `/metrics`.** In `routes/health.py.jinja`, inside the `metrics()` handler, after the `body = (... recoverability.render_prometheus())` assignment and BEFORE the `{% if "workers" in batteries %}` block, add a gated webhooks block:

```jinja
{% if "webhooks" in batteries %}
    from {{ package_name }}.webhooks.metrics import webhook_metrics

    body += webhook_metrics.render_prometheus()
{% endif %}
```

> Function-local import gated on the battery (mirrors the workers block), so the no-webhooks render carries no webhooks import. No try/except needed — `render_prometheus()` is a pure in-memory read that cannot raise (contrast the workers DLQ gauge, which touches the DB).

- [ ] **Step 5: Extend the functional test.** Append to `tests/functional/{{ 'test_webhooks.py' ... }}.jinja` (the metrics singleton is process-wide, so `reset()` first for determinism, then drive one of each outcome):

```jinja
def test_metrics_count_outcomes(client: TestClient):
    from {{ package_name }}.webhooks.metrics import webhook_metrics

    webhook_metrics.reset()

    good = json.dumps({"type": "ping"}).encode()
    client.post("/webhooks", content=good, headers={"X-Webhook-Signature": _sign(good)})  # accepted
    client.post("/webhooks", content=good, headers={"X-Webhook-Signature": "bad"})  # rejected_signature
    bad = b"not json{"
    client.post("/webhooks", content=bad, headers={"X-Webhook-Signature": _sign(bad)})  # malformed
    dup = json.dumps({"type": "ping", "id": "evt_dup"}).encode()
    h = {"X-Webhook-Signature": _sign(dup)}
    client.post("/webhooks", content=dup, headers=h)  # accepted
    client.post("/webhooks", content=dup, headers=h)  # duplicate

    body = client.get("/metrics").text
    assert 'app_webhooks_received_total{outcome="accepted"} 2' in body
    assert 'app_webhooks_received_total{outcome="rejected_signature"} 1' in body
    assert 'app_webhooks_received_total{outcome="malformed"} 1' in body
    assert 'app_webhooks_received_total{outcome="duplicate"} 1' in body
```

> The `client` fixture's app is created with the test signing secret; `/metrics` is unauthenticated (same as the other routes). `reset()` makes the test independent of the other functional tests' increments. (If the generated suite ever runs under `pytest-xdist`, a process-wide singleton + reset would race — the generated project runs serially, so this is fine; note it.)

- [ ] **Step 6: Run the render tests, confirm pass; ruff/mypy clean.**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k "webhooks" -v` → PASS (incl. the existing webhooks render tests — no regression). `uv run ruff check . && uv run mypy src` → clean.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(webhooks-obs): record outcomes in the route + expose on /metrics"
```
(Stage CLAUDE.md separately per the commit-gate convention.)

---

### Task 3: Alert rules + Grafana dashboard

**Files:**
- Create: `template/infra/observability/prometheus/alerts/{{ 'webhooks_alerts.yml' if 'webhooks' in batteries else '' }}.jinja`
- Create: `template/infra/observability/grafana/dashboards/{{ 'webhooks.json' if 'webhooks' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render tests**

```python
def test_render_webhooks_alerts_and_dashboard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    alerts = dest / "infra" / "observability" / "prometheus" / "alerts" / "webhooks_alerts.yml"
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "webhooks.json"
    assert alerts.exists() and dash.exists()
    import yaml as _yaml, json as _json
    parsed = _yaml.safe_load(alerts.read_text())
    assert parsed["groups"][0]["name"] == "webhooks"
    _json.loads(dash.read_text())  # valid JSON

def test_render_no_webhooks_alerts_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "infra" / "observability" / "prometheus" / "alerts" / "webhooks_alerts.yml").exists()
    assert not (dest / "infra" / "observability" / "grafana" / "dashboards" / "webhooks.json").exists()
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Create `webhooks_alerts.yml.jinja`** (Prometheus globs `alerts/*.yml`; the content has no `{{ }}` — single-brace PromQL label selectors are not Jinja delimiters — so it renders verbatim, conditioned only by the templated filename):

```jinja
groups:
- name: webhooks
  rules:
  - alert: HighWebhookSignatureRejectionRate
    expr: sum(rate(app_webhooks_received_total{outcome="rejected_signature"}[5m])) / clamp_min(sum(rate(app_webhooks_received_total[5m])), 1) > 0.2
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Over 20% of inbound webhooks are failing signature verification (wrong secret, rotated key, or probing)
  - alert: HighWebhookMalformedRate
    expr: sum(rate(app_webhooks_received_total{outcome="malformed"}[5m])) / clamp_min(sum(rate(app_webhooks_received_total[5m])), 1) > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Over 10% of signed webhooks have malformed bodies (misbehaving sender)
```

> Verify the rendered `webhooks_alerts.yml` parses as YAML and the PromQL label braces survive (they will — only `{{`/`{%`/`{#` are Jinja). `for: 5m` with a sliding `rate(...[5m])` is fine (rate-based, not the `increase()`+`for≥window` pitfall from 8c).

- [ ] **Step 4: Create `webhooks.json.jinja`** — a minimal valid Grafana dashboard titled `"Webhooks"`, `uid: "webhooks"`. **Read the existing `infra/observability/grafana/dashboards/{{ 'workers.json' if 'workers' in batteries else '' }}.jinja`** (and `slo.json`) for the exact schema (`schemaVersion`, datasource uid, panel/target/fieldConfig shape) and model `webhooks.json` on it with two panels:
  - a `timeseries` panel "Webhooks by outcome" with one target per outcome: `sum(rate(app_webhooks_received_total{outcome="accepted"}[5m]))` (and `rejected_signature`, `malformed`, `duplicate`) — or a single `sum by (outcome) (rate(app_webhooks_received_total[5m]))` target with a legend `{{ '{{' }} outcome {{ '}}' }}` (escape the Grafana template var through Jinja);
  - a `stat` panel "Duplicate rate" → `sum(rate(app_webhooks_received_total{outcome="duplicate"}[5m]))`.
  It must be valid JSON (the Grafana provisioner rejects malformed JSON). Keep it small; match `workers.json`'s structure — do not invent extra fields.

- [ ] **Step 5: Run the render tests, confirm pass.**

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k "webhooks" -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py
git commit -m "feat(webhooks-obs): signature-rejection + malformed alert rules + grafana dashboard"
```

---

### Task 4: Pre-commit-clean guard + verification

**Files:**
- Modify: `tests/test_copier_runner.py`

- [ ] **Step 1: Add a webhooks-only ruff-format-clean render guard** (the 8c lesson — gated blocks must not leave a freshly-rendered project format-dirty). Mirror the existing `test_render_workers_battery_is_ruff_format_clean` guard added in 8c (find it in `tests/test_copier_runner.py` and copy its shape — it renders and runs `uv run ruff format --check` on the rendered `src`/`tests`):

```python
def test_render_webhooks_battery_is_ruff_format_clean(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks"]})
    result = subprocess.run(
        ["uv", "run", "ruff", "format", "--check", str(dest / "src"), str(dest / "tests")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

> Match the EXACT shape/imports of the existing workers guard (it may use a helper or a marker). If `subprocess`/the helper differs, follow the existing one verbatim. If a webhooks-only guard already exists, skip this step.

- [ ] **Step 2: Run it, confirm green** (the Task 1–3 additions render format-clean). If it FAILS, fix the gated-block whitespace in the touched `.jinja` files (`health.py.jinja` etc.) until the webhooks render is `ruff format`-clean — a real defect to fix here.

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/test_copier_runner.py -k "webhooks" -v`

- [ ] **Step 3: Full verification (Docker)** — the existing `test_rendered_project_with_webhooks_battery_passes` runs the generated suite incl. the new functional metrics test against real Postgres:

Run: `rm -rf /tmp/pytest-of-chris; uv run pytest tests/acceptance/test_rendered_project.py -k "webhooks" -v`
Expected: PASS (the webhooks variant + the downskill variant). The generated `test_webhooks.py::test_metrics_count_outcomes` runs here, proving the counters increment end-to-end.

- [ ] **Step 4: Commit**

```bash
git add tests/test_copier_runner.py
git commit -m "test(webhooks-obs): webhooks render is ruff-format-clean (pre-commit guard)"
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

Manual spot check (no Docker): `framework new --with webhooks` → `src/<pkg>/webhooks/metrics.py` present; `routes/webhooks.py` calls `webhook_metrics.record` at all four outcomes; `/metrics` in `health.py` appends `webhook_metrics.render_prometheus()`; `webhooks_alerts.yml` + `webhooks.json` present and valid; `framework integrity --ci` green (no LOCKED file changed). `framework new` (no battery) → none of these present, `health.py` has no `webhook_metrics`. `framework downskill webhooks` (may need `--force`) → all the above removed, integrity green.

---

## Self-Review (against the spec)

**Spec coverage:**
- §2 in-process counter singleton + 4 outcomes + route increments + `/metrics` append → Tasks 1, 2. ✓
- §3 alert rules (signature-rejection, malformed) + dashboard → Task 3. ✓
- §4 no LOCKED/HYBRID file touched, no `prometheus.yml`, gated-clean → Tasks 2–4 (no scrape-target edit; format guard). ✓
- §5 testing: unit (Task 1), functional (Task 2), render (Tasks 1–3), acceptance rides existing (Task 4), format guard (Task 4). ✓
- Out-of-scope (event-type label, latency, inbox-size gauge) → correctly omitted. ✓

**Placeholder scan:** none — concrete code for the singleton, the route increments, the `/metrics` append, the alert YAML, the unit + functional tests; the dashboard JSON points at the existing `workers.json` for the large boilerplate schema (specified panels/queries), matching how 8c handled it.

**Type consistency:** `WebhookMetrics.record(outcome: str)`, `render_prometheus()`, `reset()`, `webhook_metrics` singleton, `OUTCOMES`, metric `app_webhooks_received_total{outcome=...}`, outcome literals `accepted`/`rejected_signature`/`malformed`/`duplicate` — consistent across Tasks 1–3.

---

*End of plan. Next step: execution via superpowers:subagent-driven-development.*
