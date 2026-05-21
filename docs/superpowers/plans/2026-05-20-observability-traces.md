# Observability Traces (Plan 3b-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the generated FastAPI app with OpenTelemetry tracing, ship spans through an OTEL Collector to Tempo, surface traces in Grafana, and wire trace↔log correlation (`trace_id` in the structlog logs + a Loki→Tempo derived field) — all in the `dev` Compose profile, and a clean no-op everywhere tracing isn't wanted.

**Architecture:** A new `observability/tracing.py` configures an OTel `TracerProvider` + OTLP/gRPC exporter and auto-instruments FastAPI — but only when `settings.otel_enabled` is true (default **false**; the dev Compose `app` sets `APP_OTEL_ENABLED=true`). So `lite`, local `uvicorn`, and the test suite never start an exporter or depend on a collector. The dev `app` exports OTLP → `otel-collector:4317` → Tempo (OTLP). A structlog processor injects the active span's `trace_id` into every log line; Grafana's Loki datasource gets a `derivedFields` link from `trace_id` to the Tempo datasource (and Tempo→Loki the other way), giving bidirectional trace↔log navigation. This **completes the 3b observability stack** (metrics 3b-1, logs 3b-2, traces 3b-3).

**Tech Stack:** OpenTelemetry Python (`opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc`, `opentelemetry-instrumentation-fastapi`); Grafana Tempo; OpenTelemetry Collector; Grafana datasource provisioning; Docker Compose profiles; Copier/Jinja; `pytest`.

**Spec reference:** `docs/superpowers/specs/2026-05-20-framework-design.md` — §8 (Tempo = distributed trace storage; OpenTelemetry Collector = unified pipeline exporting traces→Tempo; trace-to-log correlation via Loki; correlation IDs). Builds on **3a** (`logging_config.py`, `config/settings.py`, `create_app`, dev profile), **3b-1** (Grafana + provisioning + datasource layout), **3b-2** (Loki datasource, Promtail JSON pipeline).

**Scope boundaries (NOT in this plan):**
- **Unified metrics/logs routing through the collector** — the collector is traces-only here; metrics stay on the Prometheus scrape (3b-1) and logs on Promtail (3b-2). Routing them through the collector too is a future enhancement (the seam exists).
- **Manual/custom spans, DB/HTTP-client instrumentation** — only FastAPI server spans (auto). Builders add more instrumentation later.
- **Tempo metrics-generator / service graphs, sampling tuning, auth, retention** — local dev defaults.
- **Tracing in non-dev environments** — off by default; turning it on in staging/prod is a deployment concern (Plan 5+).

---

## Design Decisions (made per "decide & document")

1. **`otel_enabled` defaults to `false`; the dev Compose `app` sets `APP_OTEL_ENABLED=true`.** Rationale: only the full `dev` stack has a collector. Tests/`lite`/local-uvicorn run with it off — `create_app` skips `configure_tracing` entirely, so no exporter thread, no connection noise, no crash. The OTel SDK/exporter/instrumentation packages are imported *inside* `configure_tracing` (not at module load), so when off they're never imported.
2. **`opentelemetry-api` IS imported at `logging_config` module load** (for the `add_trace_context` processor). It's a transitive dep of the SDK packages we add, so it's always installed. When no span is active (tracing off), `get_current_span()` returns the invalid span and the processor adds nothing — safe.
3. **app → collector → Tempo** (OTLP/gRPC, `insecure=True` plaintext on the local network), per spec §8. The collector (`otel/opentelemetry-collector`) has only an OTLP receiver + OTLP/Tempo exporter for now.
4. **Trace↔log correlation (forward direction):** structlog processor adds `trace_id` (32-hex) + `span_id` (16-hex) when a span is active; Loki datasource `derivedFields` regex-extracts `trace_id` from the JSON log line and links to `datasourceUid: tempo`. The `trace_id` field flows: app span → log JSON → Promtail (already ships the line) → Loki → derived field → Tempo. (The reverse trace→logs `tracesToLogsV2` link is deferred — see the note in Task 4: the OTel `service.name` doesn't match the Loki `service` label, so it can't be wired cleanly here.)
5. **OTel dep version-coupling is the top risk:** the `opentelemetry-instrumentation-*` (`0.XXbY`) versions are pinned to the core (`1.XX`) line. Specify compatible lower bounds and let `uv` resolve; the rendered project's `uv sync` (acceptance test) validates they install + import together. If `uv` reports a resolution conflict, the implementer adjusts the bounds and notes it.
6. **No new Copier questions** (YAGNI). Everything is `dev`-profile only; `lite` untouched.

---

## File Structure

```
src/framework_cli/template/
  pyproject.toml.jinja                                   # EDIT: add opentelemetry sdk/otlp/fastapi-instrumentation deps
  src/{{package_name}}/
    config/settings.py.jinja                             # EDIT: add otel_enabled + otel_exporter_otlp_endpoint
    observability/tracing.py                             # NEW (static): configure_tracing (gated; OTLP exporter; FastAPI instrument)
    logging_config.py                                    # EDIT: add_trace_context processor (inject trace_id/span_id)
    main.py.jinja                                        # EDIT: call configure_tracing(app, settings) in create_app
  tests/unit/test_tracing.py.jinja                       # NEW: settings defaults + disabled-is-no-op
  tests/unit/test_logging.py.jinja                       # EDIT: add_trace_context with/without active span
  infra/observability/
    tempo/tempo.yml                                      # NEW (static): Tempo (OTLP receiver, local storage)
    otel/otel-collector.yml                              # NEW (static): OTLP receiver -> Tempo exporter
    grafana/provisioning/datasources/tempo.yml           # NEW (static): Tempo datasource (+ tracesToLogsV2 -> Loki)
    grafana/provisioning/datasources/loki.yml            # EDIT: add jsonData.derivedFields (trace_id -> Tempo)
  infra/compose/dev.yml.jinja                            # EDIT: add tempo + otel-collector services; app gets APP_OTEL_ENABLED + endpoint
tests/test_copier_runner.py                              # EDIT: render assertions
tests/acceptance/test_rendered_project.py                # EDIT: docker-gated live trace test
docs/superpowers/plans/2026-05-20-meta-plan.md           # EDIT (Task 5, controller at finish): mark 3b-3 done
```

---

## Task 1: OTel deps, settings, tracing module, wire into the app

**Files:**
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja`
- Create: `src/framework_cli/template/src/{{package_name}}/observability/tracing.py` (static — relative `TYPE_CHECKING` imports)
- Modify: `src/framework_cli/template/src/{{package_name}}/main.py.jinja`
- Test: `src/framework_cli/template/tests/unit/test_tracing.py.jinja`

- [ ] **Step 1: Add the OTel deps**

In `pyproject.toml.jinja`, add to `[project]` `dependencies` (alongside fastapi/uvicorn/pydantic-settings/structlog):

```toml
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-grpc>=1.27",
    "opentelemetry-instrumentation-fastapi>=0.48b0",
```

> If `uv sync` (in verification) reports a resolution conflict between these, adjust the lower bounds so the `0.XXbY` instrumentation matches the resolved `1.XX` core (they release in lockstep), and note the resolved versions in your report.

- [ ] **Step 2: Add the settings fields**

In `config/settings.py.jinja`, add two fields to `Settings` (after `slo_error_rate_pct`):

```python
    # OpenTelemetry tracing (off unless enabled; the dev Compose app turns it on).
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"
```

- [ ] **Step 3: Write the failing test**

Create `src/framework_cli/template/tests/unit/test_tracing.py.jinja`:

```python
from fastapi import FastAPI

from {{ package_name }}.config.settings import Settings
from {{ package_name }}.observability.tracing import configure_tracing


def test_otel_settings_default_off():
    s = Settings()
    assert s.otel_enabled is False
    assert s.otel_exporter_otlp_endpoint == "http://otel-collector:4317"


def test_configure_tracing_disabled_is_noop():
    # Disabled: returns None, raises nothing, and does not import/instrument.
    app = FastAPI()
    assert configure_tracing(app, Settings(otel_enabled=False)) is None
    # No OTel ASGI middleware was added when disabled.
    assert all(
        "OpenTelemetry" not in m.cls.__name__ for m in app.user_middleware
    )
```

- [ ] **Step 4: Run to verify it fails**

Run (rendered project): `uv run pytest tests/unit/test_tracing.py -q`
Expected: FAIL — `ModuleNotFoundError: …observability.tracing`.

- [ ] **Step 5: Implement `observability/tracing.py`** (static, no Jinja)

```python
"""OpenTelemetry tracing setup.

Off unless settings.otel_enabled (the dev Compose app sets APP_OTEL_ENABLED=true). When on,
auto-instruments FastAPI and exports spans via OTLP/gRPC to the OTEL Collector, which forwards
them to Tempo. The OTel SDK/exporter/instrumentation are imported lazily here so a disabled app
(tests, lite, local uvicorn) never imports them or starts an exporter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ..config.settings import Settings


def configure_tracing(app: "FastAPI", settings: "Settings") -> None:
    if not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        )
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
```

- [ ] **Step 6: Wire it into `create_app`**

In `main.py.jinja`, add the import and call. The file becomes:

```python
from fastapi import FastAPI

from {{ package_name }}.config.settings import Settings, get_settings
from {{ package_name }}.logging_config import configure_logging
from {{ package_name }}.middleware.observability import ObservabilityMiddleware
from {{ package_name }}.observability.metrics import MetricsRegistry
from {{ package_name }}.observability.tracing import configure_tracing
from {{ package_name }}.routes import health


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.resolved_log_level)

    app = FastAPI(title=settings.service_name)
    app.state.settings = settings
    app.state.metrics = MetricsRegistry()
    app.add_middleware(ObservabilityMiddleware, metrics=app.state.metrics)
    app.include_router(health.router)
    configure_tracing(app, settings)
    return app


app = create_app()
```

- [ ] **Step 7: Run to verify it passes**

Run (rendered project): `uv run pytest tests/unit/test_tracing.py -q`
Expected: PASS — both tests. (`configure_tracing` returns early when disabled, so no OTel middleware is added; the existing functional tests still pass because the default `Settings()` has `otel_enabled=False`.)

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/pyproject.toml.jinja \
        "src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja" \
        "src/framework_cli/template/src/{{package_name}}/observability/tracing.py" \
        "src/framework_cli/template/src/{{package_name}}/main.py.jinja" \
        "src/framework_cli/template/tests/unit/test_tracing.py.jinja"
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit -m "feat(template): opentelemetry tracing setup (gated, OTLP -> collector)"
```

> NOTE for all tasks: do NOT touch `CLAUDE.md`/meta-plan/plan-doc; the controller updates those at the finish. If a hook/classifier blocks the commit demanding `CLAUDE.md`, do not touch it — report and stop.

---

## Task 2: Inject trace context into logs (trace↔log correlation, app side)

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/logging_config.py`
- Test: `src/framework_cli/template/tests/unit/test_logging.py.jinja`

- [ ] **Step 1: Add the failing test**

Append to `tests/unit/test_logging.py.jinja`:

```python
def test_add_trace_context_injects_trace_id_when_span_active():
    from opentelemetry.sdk.trace import TracerProvider

    from {{ package_name }}.logging_config import add_trace_context

    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("unit"):
        event = add_trace_context(None, "info", {"event": "hi"})
    assert len(event["trace_id"]) == 32
    assert len(event["span_id"]) == 16


def test_add_trace_context_omits_when_no_span():
    from {{ package_name }}.logging_config import add_trace_context

    event = add_trace_context(None, "info", {"event": "hi"})
    assert "trace_id" not in event
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_logging.py -k trace_context -q`
Expected: FAIL — `ImportError: cannot import name 'add_trace_context'`.

- [ ] **Step 3: Add the processor to `logging_config.py`**

In `logging_config.py`, add the import near the top (with the other imports):

```python
from opentelemetry import trace
```

Add the processor function (next to `add_correlation_id`):

```python
def add_trace_context(logger, method_name, event_dict):  # noqa: ANN001, ARG001
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict
```

And insert `add_trace_context` into the `configure_logging` processors list, right after `add_correlation_id`:

```python
        processors=[
            structlog.contextvars.merge_contextvars,
            add_correlation_id,
            add_trace_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_logging.py -q`
Expected: PASS — the new trace-context tests and all existing logging tests. (`get_current_span()` outside a span returns `INVALID_SPAN`, whose context `is_valid` is False → no `trace_id` added.)

- [ ] **Step 5: Commit**

```bash
git add "src/framework_cli/template/src/{{package_name}}/logging_config.py" \
        "src/framework_cli/template/tests/unit/test_logging.py.jinja"
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit -m "feat(template): inject OTel trace_id into structlog logs"
```

---

## Task 3: Tempo + OTEL Collector config and services

**Files:**
- Create: `src/framework_cli/template/infra/observability/tempo/tempo.yml` (static)
- Create: `src/framework_cli/template/infra/observability/otel/otel-collector.yml` (static)
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` (add `tempo` + `otel-collector` services; set the app's OTel env)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

In `tests/test_copier_runner.py` add:

```python
def test_render_tempo_otel_collector(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    obs = dest / "infra" / "observability"

    tempo = yaml.safe_load((obs / "tempo" / "tempo.yml").read_text())
    assert "otlp" in tempo["distributor"]["receivers"]
    assert tempo["storage"]["trace"]["backend"] == "local"

    col = yaml.safe_load((obs / "otel" / "otel-collector.yml").read_text())
    assert "otlp" in col["receivers"]
    assert col["exporters"]["otlp/tempo"]["endpoint"] == "tempo:4317"
    assert col["service"]["pipelines"]["traces"]["exporters"] == ["otlp/tempo"]

    dev = yaml.safe_load((dest / "infra" / "compose" / "dev.yml").read_text())
    for name in ("tempo", "otel-collector"):
        assert dev["services"][name]["profiles"] == ["dev"]
    # the app exports traces to the collector, with tracing turned on in dev
    app_env = dev["services"]["app"]["environment"]
    assert app_env["APP_OTEL_ENABLED"] == "true"
    assert app_env["APP_OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector:4317"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_tempo_otel_collector -q`
Expected: FAIL — Tempo/collector config and services don't exist.

- [ ] **Step 3: Create `tempo/tempo.yml`** (static)

```yaml
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: "0.0.0.0:4317"

ingester:
  max_block_duration: 5m

storage:
  trace:
    backend: local
    local:
      path: /var/tempo/blocks
    wal:
      path: /var/tempo/wal
```

- [ ] **Step 4: Create `otel/otel-collector.yml`** (static)

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"

exporters:
  otlp/tempo:
    endpoint: "tempo:4317"
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/tempo]
```

- [ ] **Step 5: Add `tempo` + `otel-collector` services and the app's OTel env to `dev.yml.jinja`**

First, on the existing `app` service in `dev.yml.jinja`, add OTel env vars to its `environment:` map (it already has `WATCHFILES_FORCE_POLLING`):

```yaml
    environment:
      WATCHFILES_FORCE_POLLING: "true"  # reliable reload on Windows/WSL bind mounts
      APP_OTEL_ENABLED: "true"
      APP_OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
```

Then append the two services under `services:`:

```yaml
  tempo:
    image: grafana/tempo:2.6.1
    profiles: ["dev"]
    command: ["-config.file=/etc/tempo/tempo.yml"]
    ports:
      - "3200:3200"
    volumes:
      - "../observability/tempo/tempo.yml:/etc/tempo/tempo.yml:ro"

  otel-collector:
    image: otel/opentelemetry-collector:0.111.0
    profiles: ["dev"]
    command: ["--config=/etc/otel/otel-collector.yml"]
    volumes:
      - "../observability/otel/otel-collector.yml:/etc/otel/otel-collector.yml:ro"
    depends_on:
      - tempo
```

> The `app` exports to `otel-collector:4317` only when its `APP_OTEL_ENABLED=true` (set here, dev only). In `lite`/`test`/local-uvicorn the app has `otel_enabled=False` and never connects — graceful degradation. `BatchSpanProcessor` also exports asynchronously, so even a momentarily-unavailable collector never blocks a request.

- [ ] **Step 6: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_tempo_otel_collector -q`
Expected: PASS. The existing compose render tests still pass (additive; `app` env gains keys but the `lite` profile and other assertions are unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/observability/tempo/ \
        src/framework_cli/template/infra/observability/otel/ \
        src/framework_cli/template/infra/compose/dev.yml.jinja \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit -m "feat(template): tempo + otel collector services (dev profile)"
```

---

## Task 4: Grafana Tempo datasource + Loki→Tempo derived field

**Files:**
- Create: `src/framework_cli/template/infra/observability/grafana/provisioning/datasources/tempo.yml` (static)
- Modify: `src/framework_cli/template/infra/observability/grafana/provisioning/datasources/loki.yml` (add `derivedFields`)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

In `tests/test_copier_runner.py` add:

```python
def test_render_tempo_datasource_and_loki_link(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    ds_dir = dest / "infra" / "observability" / "grafana" / "provisioning" / "datasources"

    tempo = yaml.safe_load((ds_dir / "tempo.yml").read_text())["datasources"][0]
    assert tempo["uid"] == "tempo"
    assert tempo["type"] == "tempo"
    assert tempo["url"] == "http://tempo:3200"

    loki = yaml.safe_load((ds_dir / "loki.yml").read_text())["datasources"][0]
    df = loki["jsonData"]["derivedFields"][0]
    assert df["name"] == "trace_id"
    assert df["datasourceUid"] == "tempo"
    # the regex must match the ACTUAL structlog JSON line (JSONRenderer puts a space
    # after the colon), not merely contain "trace_id" — guards the Loki->Tempo link.
    import re

    sample = json.dumps({"event": "request", "trace_id": "0af7651916cd43dd8448eb211c80319c"})
    m = re.search(df["matcherRegex"], sample)
    assert m and m.group(1) == "0af7651916cd43dd8448eb211c80319c"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_render_tempo_datasource_and_loki_link -q`
Expected: FAIL — `tempo.yml` datasource missing / `loki.yml` has no `derivedFields`.

- [ ] **Step 3: Create the Tempo datasource** `grafana/provisioning/datasources/tempo.yml` (static)

```yaml
apiVersion: 1
datasources:
  - name: Tempo
    uid: tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
```

> **trace→logs back-link is intentionally NOT included.** Grafana's `tracesToLogsV2` builds a Loki stream selector from a span-attribute→label `tags` mapping, but the trace's `service.name` (the OTel service name = `settings.service_name`, e.g. `demo`) does not equal the Loki `service` label (the Compose service name, `app`), so no clean mapping yields a query that finds the logs. Rather than ship a dead "Logs for this span" button, 3b-3 ships only the **forward** log→trace link (Task 4 below), which works and is the more-used direction. trace→logs is a follow-up that needs the OTel service name reconciled with the Loki `service` label (or a `customQuery`).

- [ ] **Step 4: Add `derivedFields` to the Loki datasource**

Replace `grafana/provisioning/datasources/loki.yml` with (adds `jsonData.derivedFields`; the rest is unchanged from 3b-2):

```yaml
apiVersion: 1
datasources:
  - name: Loki
    uid: loki
    type: loki
    access: proxy
    url: http://loki:3100
    jsonData:
      derivedFields:
        - name: trace_id
          matcherType: regex
          matcherRegex: '"trace_id":\s*"(\w+)"'
          url: "${__value.raw}"
          datasourceUid: tempo
```

> `loki.yml` is a **static** file (no `.jinja`), so `${__value.raw}` (a Grafana template token) is copied verbatim — no `$$`-escaping needed. The `\s*` in the regex is **required**: structlog's `JSONRenderer` (json.dumps) emits `"trace_id": "<hex>"` WITH a space after the colon, so a no-space regex would silently extract nothing and the Loki→Tempo link would never fire. The Step-1 render test asserts the regex matches a real `json.dumps` line, guarding exactly this.

- [ ] **Step 5: Run the render test to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_render_tempo_datasource_and_loki_link -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/observability/grafana/provisioning/datasources/tempo.yml \
        src/framework_cli/template/infra/observability/grafana/provisioning/datasources/loki.yml \
        tests/test_copier_runner.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit -m "feat(template): grafana tempo datasource + loki->tempo trace link"
```

---

## Task 5: Docs, Docker-gated live trace test, meta-plan

**Files:**
- Modify: `src/framework_cli/template/SERVICES.md.jinja`
- Modify: `src/framework_cli/template/README.md.jinja`
- Modify: `tests/test_copier_runner.py`
- Modify: `tests/acceptance/test_rendered_project.py`
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md` (controller, at finish)

- [ ] **Step 1: Add tempo/otel-collector rows to `SERVICES.md.jinja`**

```markdown
| tempo | `tempo:3200` (query), `tempo:4317` (OTLP) | `http://localhost:3200` | Distributed trace store; queried in Grafana (dev profile) |
| otel-collector | `otel-collector:4317` (OTLP) | (no host port) | Receives app traces (OTLP), forwards to Tempo (dev profile) |
```

- [ ] **Step 2: Note traces in `README.md.jinja`**

In `## Local stack (HTTPS)`, add:

```markdown
Requests are traced with OpenTelemetry (enabled in the `dev` stack) and stored in Tempo — view traces in Grafana, and jump from a log line to its trace via the `trace_id` derived field (Loki→Tempo). Tracing is off in `lite`/local runs.
```

- [ ] **Step 3: Add render assertion for docs**

In `tests/test_copier_runner.py` add:

```python
def test_render_docs_mention_traces(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert "tempo:3200" in (dest / "SERVICES.md").read_text()
    assert "OpenTelemetry" in (dest / "README.md").read_text()
```

- [ ] **Step 4: Add the Docker-gated live trace test**

In `tests/acceptance/test_rendered_project.py` append (reuses `_docker_available()` + existing imports):

```python
@pytest.mark.skipif(not _docker_available(), reason="uv and docker are required for the live-stack test")
def test_rendered_project_traces_reach_tempo(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", "-f", base, "-f", dev, "--profile", "dev", "down", "-v"]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen("http://localhost:8000/heartbeat", timeout=3).read()
                break
            except OSError:
                time.sleep(2)
        for _ in range(5):
            try:
                urllib.request.urlopen("http://localhost:8000/heartbeat", timeout=3).read()
            except OSError:
                pass
        # Tempo search for the app's traces (export -> collector -> tempo has lag, so poll)
        deadline = time.time() + 120
        found = False
        while time.time() < deadline and not found:
            try:
                with urllib.request.urlopen(
                    'http://localhost:3200/api/search?q=%7Bresource.service.name%3D%22demo%22%7D&limit=1',
                    timeout=5,
                ) as resp:
                    data = json.loads(resp.read())
                    if data.get("traces"):
                        found = True
                        break
            except OSError:
                pass
            time.sleep(4)
        assert found, "no app traces reached Tempo within the timeout"
    finally:
        subprocess.run(down, cwd=dest)
```

> The query is TraceQL `{resource.service.name="demo"}` (URL-encoded) against Tempo's search API; `demo` is the rendered `service_name` (== `package_name` from `DATA`). Tracing is on in dev (`APP_OTEL_ENABLED=true`), so hitting `/heartbeat` produces a server span exported app→collector→Tempo. Skips without Docker.

- [ ] **Step 5: Run the framework gate**

Run (in-sandbox): `uv run pytest tests/test_copier_runner.py -q`, `uv run ruff check .`, `uv run mypy src` → green; `uv run pytest tests/acceptance/test_rendered_project.py --collect-only -q` → new test collects.
Run (sandbox-disabled): `uv run pytest tests/acceptance/test_rendered_project.py -q -rs` → rendered suite passes (the rendered project's `uv sync` now installs the OTel deps and runs `test_tracing` + the new `test_logging` trace tests); the now-four Docker-gated tests skip.

- [ ] **Step 6: Meta-plan + CLAUDE.md (controller, at finish)**

Controller marks `3b-3` ✅ in the meta-plan (3b observability stack complete; Next → 3c or Plan 4) and advances `CLAUDE.md` Current State. Implementers do not touch these.

- [ ] **Step 7: Commit (implementer commits only template + test files)**

```bash
git add src/framework_cli/template/SERVICES.md.jinja src/framework_cli/template/README.md.jinja \
        tests/test_copier_runner.py tests/acceptance/test_rendered_project.py
git -c user.name="Chris Dowell" -c user.email="chris@swiftwaterhorizon.com" commit -m "feat(template): traces docs + docker-gated tempo trace test"
```

---

## Self-Review

**1. Spec coverage (Plan 3b-3 subset of §8):**
- Tempo = distributed trace storage → Task 3 (`tempo.yml` + service). ✓
- OpenTelemetry Collector exports traces→Tempo → Task 3 (`otel-collector.yml` + service; app→collector→Tempo). ✓
- App emits traces (OpenTelemetry) → Task 1 (instrumentation, gated). ✓
- Trace-to-log correlation (viewable in Grafana with trace↔log) → Task 2 (`trace_id` in logs) + Task 4 (Loki `derivedFields` → Tempo; Tempo `tracesToLogsV2` → Loki). ✓
- Correlation IDs already propagated (3a); now joined by `trace_id`. ✓
- **Deferred (stated):** unified metrics/logs routing through the collector; custom/DB/client spans; Tempo metrics-generator/sampling/auth; tracing in non-dev envs.

**2. Placeholder scan:** No "TBD"/"handle appropriately". All Python and config shown complete. Two explicit risk notes (not deferrals): the OTel dep version-coupling (adjust bounds if `uv` conflicts) and the `${__value.raw}` single-`$` instruction for the static `loki.yml`. The Tempo/collector/OTel config correctness is validated by the Docker-gated live test and the Opus review (render tests only check structure).

**3. Type/consistency check:** `configure_tracing(app, settings)` (Task 1) is imported + called in `main.py` (Task 1 Step 6). `otel_enabled`/`otel_exporter_otlp_endpoint` settings (Task 1) drive both the gate (Task 1) and the dev compose env keys `APP_OTEL_ENABLED`/`APP_OTEL_EXPORTER_OTLP_ENDPOINT` (Task 3, `APP_`-prefixed per `settings.py` `env_prefix`). `add_trace_context` (Task 2) emits `trace_id` as 32-hex, matching the Loki `derivedFields` regex `"trace_id":"(\w+)"` (Task 4) and the structlog JSON. Service/port names align: app→`otel-collector:4317` (Task 1 default + Task 3 env + collector receiver), collector→`tempo:4317` (Task 3 exporter + Tempo OTLP receiver), Grafana→`tempo:3200` (Task 4 datasource + Tempo `http_listen_port` + Task 3 port). Datasource uids `tempo`/`loki` cross-reference correctly (Task 4). The live test queries `service.name="demo"` == `Resource` `service.name=settings.service_name` (Task 1) == rendered `package_name`. All `dev`-profile only; `lite` untouched.

---

*End of plan.*
