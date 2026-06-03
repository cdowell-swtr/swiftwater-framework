# Frontend Observability Surface + `review-observability-fe` (Plan 16) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the react battery an in-process Real-User-Monitoring surface — Core Web Vitals + JS errors + page-view navigation (with a UTM-default query-param allowlist for attribution) — riding the app's existing `/metrics`, plus the deferred `review-observability-fe` reviewer.

**Architecture:** The browser collects telemetry (web-vitals lib + window error handlers + a page-view on load), batches it, and `navigator.sendBeacon`s it to a backend `POST /internal/rum`. The route validates, re-applies the allowlist, and folds events into a thread-safe `FrontendMetrics` singleton whose `render_prometheus()` is appended to `/metrics` inside a react-gated block in `health.py` — exactly the webhooks/websockets in-process precedent. No new scrape target, exporter, or prod compose service. React's `BatterySpec.obs` flips `rides-existing` → `in-process`, so the existing `test_obs_completeness` guard auto-asserts new alerts + dashboard.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic (backend); Vite + TypeScript + Vitest + the `web-vitals` npm library (frontend); Prometheus alert YAML + Grafana dashboard JSON; Copier Jinja template payload; the `framework_cli.review` agent registry + eval harness.

**Spec:** `docs/superpowers/specs/2026-06-04-frontend-observability-design.md`

---

## Orientation — read before starting

**This is template-payload work.** Files under `src/framework_cli/template/` are *rendered into generated projects*, not framework source. They are NOT linted/typed as framework code (the framework's mypy excludes that dir). They are validated two ways:
- **Framework tests** (`tests/*.py`, run with `uv run pytest`) render the template and assert on the output (`test_copier_runner.py`, `test_obs_completeness.py`, `test_batteries.py`, `tests/review/test_registry.py`).
- **Generated-project tests** (the template's own `tests/unit`, `tests/functional`, and `frontend/src/*.test.tsx`) run *inside a rendered project*. The framework venv lacks their deps, so you exercise them via the **template-payload TDD loop** below.

**Template-payload TDD loop** (memory: `[[template-payload-tdd-loop]]`) — use this for every task that adds/edits template payload with a generated-project test:
```bash
# One-time per task: render a react project to a scratch dir
WORK=/tmp/p16-work
rm -rf "$WORK" && uv run python -c "
from pathlib import Path
from framework_cli.copier_runner import render_project
render_project(Path('$WORK/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':['react']})
"
# Backend deps:
(cd "$WORK/demo" && uv sync --quiet)
# Frontend deps (once):
(cd "$WORK/demo/frontend" && npm install --silent)

# Edit the framework template source, then MIRROR the change into the render:
#   - plain .py  → cp src/.../file.py            "$WORK/demo/src/demo/.../file.py"
#   - .jinja     → re-render (rerun render_project) OR hand-apply the rendered text
#   - .ts/.tsx   → cp the rendered file into $WORK/demo/frontend/src/...
# Then run the generated-project test:
(cd "$WORK/demo" && uv run pytest tests/unit/<file>.py -q)              # backend
(cd "$WORK/demo/frontend" && npm test)                                 # frontend vitest
```
Mirror direction is always **framework template → render**; never edit the render directly as the source of truth.

**Conventions that bite (memories):**
- `[[ruff-format-check-after-inline-edits]]` — after editing rendered Python, the generated project must pass `ruff format --check`. The framework guards this; run `ruff format --check` on the rendered output before committing.
- `[[subagent-implementers-stop-before-commit]]` — implementers stage + pass the commit-gate but do NOT run `git commit`; the controller verifies and commits.
- `[[gate-cadence-framework-slices]]` — do NOT run a full per-commit review on every task; use the lighter per-task review and ONE branch-end full review (Task 11).
- `[[eval-fixtures-coupled-to-template]]` — eval fixtures are git patches against a rendered project; re-anchor with render + `git diff`, and scan each fixture with its OWN batteries.

**Branch:** all work lands on `plan-16-frontend-observability` (already created; the design spec is committed there).

**Naming locked across tasks (use these exact identifiers):**
- Backend package dir: `src/{{package_name}}/frontend_rum/` (react-gated) with `__init__.py` + `metrics.py`.
- Singleton: `frontend_metrics` (instance of `FrontendMetrics`) in `frontend_rum/metrics.py`.
- Route module: `routes/frontend_rum.py` (react-gated), exposing `router`; endpoint `POST /internal/rum`.
- Metric names: `app_frontend_web_vitals_lcp_milliseconds`, `app_frontend_web_vitals_inp_milliseconds`, `app_frontend_web_vitals_cls` (histograms); `app_frontend_js_errors_total{type}`, `app_frontend_page_views_total{route}`, `app_frontend_attribution_total{utm_source,utm_medium,utm_campaign}`, `app_frontend_referrers_total{referrer}`, `app_frontend_rum_beacons_total{status}` (counters).
- Setting: `frontend_rum_allowed_query_params: list[str]`.
- Frontend module: `frontend/src/observability/rum.ts` exposing `initRum()`.
- Agent: short name `observability-fe`, display `review-observability-fe`, prompt `src/framework_cli/review/agents/observability-fe.md`.

---

## File structure

**Backend template payload** (`src/framework_cli/template/`):
- Create `src/{{package_name}}/{% raw %}{% if "react" in batteries %}frontend_rum{% endif %}{% endraw %}/__init__.py` — empty package marker.
- Create `src/{{package_name}}/{% raw %}{% if "react" in batteries %}frontend_rum{% endif %}{% endraw %}/metrics.py` — `FrontendMetrics` singleton (plain `.py`, stdlib only).
- Create `src/{{package_name}}/routes/{% raw %}{{ 'frontend_rum.py' if 'react' in batteries else '' }}{% endraw %}.jinja` — the ingest route.
- Modify `src/{{package_name}}/routes/health.py.jinja` — append react-gated exposition to `/metrics`.
- Modify `src/{{package_name}}/config/settings.py.jinja` — add the allowlist setting (react-gated).
- Create `tests/unit/{% raw %}{{ 'test_frontend_rum_unit.py' if 'react' in batteries else '' }}{% endraw %}.jinja` — singleton + route unit tests.
- Create `tests/functional/{% raw %}{{ 'test_frontend_rum.py' if 'react' in batteries else '' }}{% endraw %}.jinja` — `/metrics` exposition functional test.

**Frontend template payload** (`src/framework_cli/template/{% raw %}{% if "react" in batteries %}frontend{% endif %}{% endraw %}/`):
- Modify `package.json` + `package-lock.json` — add `web-vitals`.
- Create `src/observability/rum.ts` — `initRum()`.
- Create `src/observability/rum.test.ts` — Vitest unit test.
- Modify `src/main.tsx` — call `initRum()`.
- Modify `vite.config.ts` — add `/internal/rum` to the dev proxy.

**Observability artifacts** (`src/framework_cli/template/infra/observability/`):
- Create `prometheus/alerts/{% raw %}{{ 'frontend_alerts.yml' if 'react' in batteries else '' }}{% endraw %}.jinja`.
- Create `grafana/dashboards/{% raw %}{{ 'frontend.json' if 'react' in batteries else '' }}{% endraw %}.jinja`.

**Framework source** (NOT template payload — real framework code, linted/typed):
- Modify `src/framework_cli/batteries.py` — flip react `obs`, add `observability-fe` to react `gates_agents`.
- Modify `src/framework_cli/review/registry.py` — register the `observability-fe` agent.
- Create `src/framework_cli/review/agents/observability-fe.md` — the prompt.

**Tests + eval** (framework):
- Modify `tests/test_copier_runner.py` — render assertions for the new files.
- Modify `tests/test_batteries.py` — react `obs == "in-process"` + gates_agents.
- Modify `tests/review/test_registry.py` — agent registered + battery-gated.
- Create `tests/eval/fixtures/observability-fe/{bad,good}/...` — 3 bad / 1 good.
- Create `tests/eval/fixtures/privacy/bad/rum-allowlists-pii/...` — 1 privacy fixture.
- Modify `tests/eval/fixtures/thresholds.yaml` — `observability-fe` entry.

> **Note on `{% raw %}…{% endraw %}` above:** that is only escaping for *this markdown doc* so the Jinja isn't interpreted by anything reading the plan. The actual filenames on disk are the literal Copier templated names (e.g. `{{ 'frontend_rum.py' if 'react' in batteries else '' }}.jinja`), exactly like the existing `routes/{{ 'websockets.py' if 'websockets' in batteries else '' }}.jinja`.

---

## Task 1: `FrontendMetrics` singleton (backend)

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "react" in batteries %}frontend_rum{% endif %}/__init__.py`
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "react" in batteries %}frontend_rum{% endif %}/metrics.py`
- Test: `src/framework_cli/template/tests/unit/{{ 'test_frontend_rum_unit.py' if 'react' in batteries else '' }}.jinja`

This mirrors `src/{{package_name}}/{% if "websockets" in batteries %}websockets{% endif %}/metrics.py` (a plain stdlib `.py` with a `threading.Lock` singleton + `render_prometheus()`), extended with hand-rolled histograms for the vitals.

- [ ] **Step 1: Write the failing unit test** (template payload). Create the test file with this content:

```python
"""Frontend RUM battery — unit tests for the in-process metrics (hermetic)."""

from {{ package_name }}.frontend_rum.metrics import FrontendMetrics


def test_web_vital_histograms_observe_and_render() -> None:
    m = FrontendMetrics()
    m.observe_web_vital("lcp", 1500.0)
    m.observe_web_vital("lcp", 3000.0)
    out = m.render_prometheus()
    assert "# TYPE app_frontend_web_vitals_lcp_milliseconds histogram" in out
    # 1500 falls in le="2000"; cumulative le="2500" includes both? no — 3000 > 2500.
    assert 'app_frontend_web_vitals_lcp_milliseconds_bucket{le="2500"} 1' in out
    assert 'app_frontend_web_vitals_lcp_milliseconds_bucket{le="+Inf"} 2' in out
    assert "app_frontend_web_vitals_lcp_milliseconds_count 2" in out


def test_unknown_vital_name_ignored() -> None:
    m = FrontendMetrics()
    m.observe_web_vital("ttfb", 10.0)  # not one of lcp/inp/cls
    assert "app_frontend_web_vitals_lcp_milliseconds_count 0" in m.render_prometheus()


def test_js_errors_counter_by_bounded_type() -> None:
    m = FrontendMetrics()
    m.record_error("error")
    m.record_error("unhandledrejection")
    m.record_error("totally-made-up")  # coerced to "error"
    out = m.render_prometheus()
    assert 'app_frontend_js_errors_total{type="error"} 2' in out
    assert 'app_frontend_js_errors_total{type="unhandledrejection"} 1' in out


def test_page_views_route_label_and_cap() -> None:
    m = FrontendMetrics()
    m.record_page_view("/items", {}, None)
    m.record_page_view("/items", {}, None)
    out = m.render_prometheus()
    assert 'app_frontend_page_views_total{route="/items"} 2' in out


def test_page_view_route_cap_folds_to_other() -> None:
    m = FrontendMetrics()
    for i in range(FrontendMetrics.MAX_ROUTES + 5):
        m.record_page_view(f"/r{i}", {}, None)
    out = m.render_prometheus()
    assert 'route="other"' in out  # overflow bucketed, cardinality bounded


def test_attribution_and_referrer_counters() -> None:
    m = FrontendMetrics()
    m.record_page_view(
        "/", {"utm_source": "google", "utm_medium": "cpc", "utm_campaign": "spring"}, "news.example.com"
    )
    out = m.render_prometheus()
    assert (
        'app_frontend_attribution_total{utm_source="google",utm_medium="cpc",utm_campaign="spring"} 1'
        in out
    )
    assert 'app_frontend_referrers_total{referrer="news.example.com"} 1' in out


def test_beacon_status_counter() -> None:
    m = FrontendMetrics()
    m.record_beacon("accepted")
    m.record_beacon("rejected")
    m.record_beacon("garbage")  # coerced to "rejected"
    out = m.render_prometheus()
    assert 'app_frontend_rum_beacons_total{status="accepted"} 1' in out
    assert 'app_frontend_rum_beacons_total{status="rejected"} 2' in out


def test_label_values_are_sanitized() -> None:
    m = FrontendMetrics()
    m.record_page_view('/x"; evil', {}, None)
    out = m.render_prometheus()
    assert '"; evil' not in out  # quotes/spaces stripped, exposition stays valid


def test_reset_clears() -> None:
    m = FrontendMetrics()
    m.observe_web_vital("lcp", 100.0)
    m.record_error("error")
    m.reset()
    out = m.render_prometheus()
    assert "app_frontend_web_vitals_lcp_milliseconds_count 0" in out
    assert "app_frontend_js_errors_total" not in out  # no error labels after reset
```

- [ ] **Step 2: Run it (red).** Use the template-payload loop (render react project, then run in the render):

Run: `(cd /tmp/p16-work/demo && uv run pytest tests/unit/test_frontend_rum_unit.py -q)`
Expected: FAIL — `ModuleNotFoundError: ... frontend_rum.metrics` (the module + render don't exist yet).

- [ ] **Step 3: Create the package marker.** `frontend_rum/__init__.py`:

```python
```
(empty file — package marker, like `websockets/__init__.py`.)

- [ ] **Step 4: Implement `FrontendMetrics`** in `frontend_rum/metrics.py`:

```python
"""Process-wide frontend RUM metrics — Core Web Vitals (histograms) + JS errors,
page-view navigation, query-param attribution, and beacon-ingest health (counters).

A module-level singleton (like observability/recoverability.py / websockets/metrics.py),
fed by the POST /internal/rum route and appended to the /metrics exposition. Cardinality is
bounded by construction: vital names + error types + beacon statuses are fixed enums; route
and attribution labels are capped with an "other" overflow bucket; all label values are
sanitized. No free-text (error messages, full URLs, query strings) is ever stored.
"""

from __future__ import annotations

import re
import threading

# Core Web Vitals histogram buckets. LCP/INP in milliseconds; CLS is unitless.
_LCP_BUCKETS = (1000.0, 2000.0, 2500.0, 4000.0)
_INP_BUCKETS = (100.0, 200.0, 500.0, 1000.0)
_CLS_BUCKETS = (0.1, 0.25, 0.5, 1.0)

_VITALS = {
    "lcp": ("app_frontend_web_vitals_lcp_milliseconds", _LCP_BUCKETS, "Largest Contentful Paint (ms)"),
    "inp": ("app_frontend_web_vitals_inp_milliseconds", _INP_BUCKETS, "Interaction to Next Paint (ms)"),
    "cls": ("app_frontend_web_vitals_cls", _CLS_BUCKETS, "Cumulative Layout Shift (unitless)"),
}
_ERROR_TYPES = ("error", "unhandledrejection")
_BEACON_STATUSES = ("accepted", "rejected")
_ATTRIBUTION_KEYS = ("utm_source", "utm_medium", "utm_campaign")

_SAN = re.compile(r"[^A-Za-z0-9_./:-]")


def _san(value: str, limit: int = 64) -> str:
    """Sanitize a label value: drop exposition-breaking chars, bound length."""
    return _SAN.sub("_", value)[:limit]


def _g(value: float) -> str:
    return f"{value:g}"


class _Histogram:
    """A minimal Prometheus histogram (no labels). Buckets are non-cumulative internally;
    rendered cumulatively per the exposition format."""

    def __init__(self, buckets: tuple[float, ...]) -> None:
        self._buckets = buckets
        self._counts = [0] * len(buckets)
        self._total = 0
        self._sum = 0.0

    def observe(self, value: float) -> None:
        self._sum += value
        self._total += 1
        for i, edge in enumerate(self._buckets):
            if value <= edge:
                self._counts[i] += 1
                break

    def render(self, name: str, help_text: str) -> str:
        out = [f"# HELP {name} {help_text}", f"# TYPE {name} histogram"]
        cumulative = 0
        for i, edge in enumerate(self._buckets):
            cumulative += self._counts[i]
            out.append(f'{name}_bucket{{le="{_g(edge)}"}} {cumulative}')
        out.append(f'{name}_bucket{{le="+Inf"}} {self._total}')
        out.append(f"{name}_sum {self._sum:g}")
        out.append(f"{name}_count {self._total}")
        return "\n".join(out) + "\n"


class FrontendMetrics:
    MAX_ROUTES = 32
    MAX_ATTRIBUTION = 64
    MAX_REFERRERS = 32

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._vitals = {k: _Histogram(v[1]) for k, v in _VITALS.items()}
        self._errors: dict[str, int] = {}
        self._page_views: dict[str, int] = {}
        self._attribution: dict[tuple[str, str, str], int] = {}
        self._referrers: dict[str, int] = {}
        self._beacons: dict[str, int] = {}

    def observe_web_vital(self, name: str, value: float) -> None:
        key = name.lower()
        if key not in self._vitals:
            return
        with self._lock:
            self._vitals[key].observe(value)

    def record_error(self, error_type: str) -> None:
        t = error_type if error_type in _ERROR_TYPES else "error"
        with self._lock:
            self._errors[t] = self._errors.get(t, 0) + 1

    def record_page_view(
        self, route: str, params: dict[str, str], referrer: str | None
    ) -> None:
        route = _san(route)
        attribution = tuple(_san(params.get(k, "")) for k in _ATTRIBUTION_KEYS)
        with self._lock:
            self._bump_capped(self._page_views, route, self.MAX_ROUTES)
            if any(attribution):
                self._bump_capped(
                    self._attribution, attribution, self.MAX_ATTRIBUTION,
                    overflow=("other", "other", "other"),
                )
            if referrer:
                self._bump_capped(self._referrers, _san(referrer), self.MAX_REFERRERS)

    def record_beacon(self, status: str) -> None:
        s = status if status in _BEACON_STATUSES else "rejected"
        with self._lock:
            self._beacons[s] = self._beacons.get(s, 0) + 1

    @staticmethod
    def _bump_capped(store, key, cap, overflow="other"):
        if key not in store and len(store) >= cap:
            key = overflow
        store[key] = store.get(key, 0) + 1

    def render_prometheus(self) -> str:
        with self._lock:
            parts = [self._vitals[k].render(_VITALS[k][0], _VITALS[k][2]) for k in _VITALS]
            parts.append(self._render_counter(
                "app_frontend_js_errors_total", "Uncaught frontend JS errors",
                [(f'type="{t}"', n) for t, n in sorted(self._errors.items())]))
            parts.append(self._render_counter(
                "app_frontend_page_views_total", "Frontend page views by route",
                [(f'route="{r}"', n) for r, n in sorted(self._page_views.items())]))
            parts.append(self._render_counter(
                "app_frontend_attribution_total", "Frontend page views by UTM attribution",
                [(f'utm_source="{a[0]}",utm_medium="{a[1]}",utm_campaign="{a[2]}"', n)
                 for a, n in sorted(self._attribution.items())]))
            parts.append(self._render_counter(
                "app_frontend_referrers_total", "Frontend page views by referrer host",
                [(f'referrer="{r}"', n) for r, n in sorted(self._referrers.items())]))
            parts.append(self._render_counter(
                "app_frontend_rum_beacons_total", "RUM beacon ingest outcomes",
                [(f'status="{s}"', n) for s, n in sorted(self._beacons.items())]))
        return "".join(parts)

    @staticmethod
    def _render_counter(name: str, help_text: str, series: list[tuple[str, int]]) -> str:
        out = [f"# HELP {name} {help_text}", f"# TYPE {name} counter"]
        for labels, value in series:
            out.append(f"{name}{{{labels}}} {value}")
        return "\n".join(out) + "\n"

    def reset(self) -> None:
        with self._lock:
            for h in self._vitals.values():
                h.__init__(h._buckets)  # type: ignore[misc]
            self._errors.clear()
            self._page_views.clear()
            self._attribution.clear()
            self._referrers.clear()
            self._beacons.clear()


frontend_metrics = FrontendMetrics()
"""The process-wide singleton imported by the /internal/rum route and /metrics."""
```

- [ ] **Step 5: Mirror + run (green).** Re-render (or `cp` the two new files into `/tmp/p16-work/demo/src/demo/frontend_rum/`), then:

Run: `(cd /tmp/p16-work/demo && uv run pytest tests/unit/test_frontend_rum_unit.py -q)`
Expected: PASS (8 tests). *(The route tests in this file come in Task 2 — until then, restrict to the metric tests if the route import fails: `-k "vital or error or page or attribution or beacon or reset or sanitized"`.)*

- [ ] **Step 6: Format check.** Run: `(cd /tmp/p16-work/demo && uv run ruff format --check src/demo/frontend_rum/ tests/unit/test_frontend_rum_unit.py)`
Expected: "would reformat" → 0 files. If it reformats, copy the formatted text back into the template source and re-verify.

- [ ] **Step 7: Stage (do NOT commit — controller commits).**
```bash
git add "src/framework_cli/template/src/{{package_name}}/{% if \"react\" in batteries %}frontend_rum{% endif %}/__init__.py" \
        "src/framework_cli/template/src/{{package_name}}/{% if \"react\" in batteries %}frontend_rum{% endif %}/metrics.py" \
        "src/framework_cli/template/tests/unit/{{ 'test_frontend_rum_unit.py' if 'react' in batteries else '' }}.jinja"
```

---

## Task 2: `POST /internal/rum` ingest route + allowlist setting (backend)

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/routes/{{ 'frontend_rum.py' if 'react' in batteries else '' }}.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja`
- Test: append to `tests/unit/{{ 'test_frontend_rum_unit.py' if 'react' in batteries else '' }}.jinja` (route tests)

The route is auto-discovered by `routes/__init__.py::include_routers` (any module exposing `router`), so no `main.py` edit is needed. The SPA static mount in `main.py` happens *after* `include_routers`, so `/internal/rum` takes precedence over the `/` SPA mount.

- [ ] **Step 1: Add the failing route tests** (append to the Task 1 test file):

```python
from fastapi.testclient import TestClient

from {{ package_name }}.main import create_app


def _client():
    from {{ package_name }}.frontend_rum.metrics import frontend_metrics

    frontend_metrics.reset()
    return TestClient(create_app())


def test_ingest_accepts_and_folds_events() -> None:
    client = _client()
    resp = client.post("/internal/rum", json={"events": [
        {"kind": "vital", "name": "lcp", "value": 1800.0},
        {"kind": "error", "type": "unhandledrejection"},
        {"kind": "pageview", "path": "/items", "params": {"utm_source": "google"}, "referrer": "ex.com"},
    ]})
    assert resp.status_code == 204
    body = client.get("/metrics").text
    assert "app_frontend_web_vitals_lcp_milliseconds_count 1" in body
    assert 'app_frontend_js_errors_total{type="unhandledrejection"} 1' in body
    assert 'app_frontend_page_views_total{route="/items"} 1' in body
    assert 'app_frontend_rum_beacons_total{status="accepted"} 1' in body


def test_ingest_strips_query_string_from_path() -> None:
    client = _client()
    client.post("/internal/rum", json={"events": [
        {"kind": "pageview", "path": "/search?q=secret", "params": {}, "referrer": None},
    ]})
    body = client.get("/metrics").text
    assert 'route="/search"' in body
    assert "secret" not in body  # query string never enters the series


def test_ingest_drops_non_allowlisted_params() -> None:
    client = _client()
    client.post("/internal/rum", json={"events": [
        {"kind": "pageview", "path": "/", "params": {"utm_source": "google", "email": "a@b.co"}, "referrer": None},
    ]})
    body = client.get("/metrics").text
    assert 'utm_source="google"' in body
    assert "a@b.co" not in body  # email is not in the allowlist → dropped


def test_ingest_rejects_malformed_without_500() -> None:
    client = _client()
    resp = client.post("/internal/rum", content=b"not json")
    assert resp.status_code == 204  # never leak a 5xx to the browser
    assert 'app_frontend_rum_beacons_total{status="rejected"} 1' in client.get("/metrics").text


def test_ingest_caps_event_count() -> None:
    client = _client()
    resp = client.post("/internal/rum", json={"events": [
        {"kind": "error", "type": "error"} for _ in range(200)
    ]})
    assert resp.status_code == 204  # over-long batch is rejected, not processed
    assert 'app_frontend_rum_beacons_total{status="rejected"} 1' in client.get("/metrics").text
```

- [ ] **Step 2: Run (red).** Run: `(cd /tmp/p16-work/demo && uv run pytest tests/unit/test_frontend_rum_unit.py -q)`
Expected: FAIL — the route 404s / `frontend_rum_allowed_query_params` setting missing.

- [ ] **Step 3: Add the allowlist setting.** In `config/settings.py.jinja`, add this react-gated block (place it after the `consumers` block, before the `resolved_log_level` property — i.e. just before line `    @property` for `resolved_log_level`):

```jinja
{%- if "react" in batteries %}

    # Frontend RUM: query-string params captured for attribution (fail-closed allowlist).
    # Defaults to the UTM set; the backend re-applies this on ingest (never trusts the browser).
    # Adding a PII-bearing key here (e.g. "email") is flagged by review-privacy.
    frontend_rum_allowed_query_params: list[str] = [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
    ]
{%- endif %}
```

- [ ] **Step 4: Implement the route** in `routes/{{ 'frontend_rum.py' if 'react' in batteries else '' }}.jinja`:

```jinja
"""Frontend RUM ingest. A public, unauthenticated beacon endpoint (browsers hit it before
any login), so it is hardened: strict schema + bounded event count, no free-text stored, a
fail-closed query-param allowlist re-applied here (the browser is never trusted), and malformed
payloads are counted + dropped rather than 500'd. Auto-discovered by routes/__init__.py."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from {{ package_name }}.frontend_rum.metrics import frontend_metrics

router = APIRouter()

_MAX_EVENTS = 64


class RumEvent(BaseModel):
    model_config = {"extra": "ignore"}

    kind: str
    name: str | None = None
    value: float | None = None
    type: str | None = None
    path: str | None = None
    params: dict[str, str] = Field(default_factory=dict)
    referrer: str | None = None


class RumBeacon(BaseModel):
    events: list[RumEvent] = Field(default_factory=list, max_length=_MAX_EVENTS)


@router.post("/internal/rum", status_code=204)
async def ingest_rum(request: Request) -> Response:
    allow = set(request.app.state.settings.frontend_rum_allowed_query_params)
    try:
        beacon = RumBeacon.model_validate(await request.json())
    except Exception:
        frontend_metrics.record_beacon("rejected")
        return Response(status_code=204)

    for ev in beacon.events:
        if ev.kind == "vital" and ev.name and ev.value is not None:
            frontend_metrics.observe_web_vital(ev.name, ev.value)
        elif ev.kind == "error" and ev.type:
            frontend_metrics.record_error(ev.type)
        elif ev.kind == "pageview":
            path = (ev.path or "/").split("?", 1)[0].split("#", 1)[0]
            params = {k: v for k, v in ev.params.items() if k in allow}
            frontend_metrics.record_page_view(path, params, ev.referrer)
    frontend_metrics.record_beacon("accepted")
    return Response(status_code=204)
```

- [ ] **Step 5: Mirror + run (green).** Re-render the project (settings + route are `.jinja`, so re-run `render_project` into `/tmp/p16-work/demo`, or hand-apply the rendered text), then:

Run: `(cd /tmp/p16-work/demo && uv run pytest tests/unit/test_frontend_rum_unit.py -q)`
Expected: PASS (13 tests total).

- [ ] **Step 6: Format check.** Run: `(cd /tmp/p16-work/demo && uv run ruff format --check src/demo/routes/frontend_rum.py src/demo/config/settings.py tests/unit/test_frontend_rum_unit.py)`
Expected: 0 reformats.

- [ ] **Step 7: Stage** (`git add` the route, settings, and test `.jinja` files — do NOT commit).

---

## Task 3: Wire frontend RUM exposition into `/metrics` (functional test)

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja`
- Test: `src/framework_cli/template/tests/functional/{{ 'test_frontend_rum.py' if 'react' in batteries else '' }}.jinja`

> The route in Task 2 already exposes the series through the singleton, but `/metrics` only includes a battery's exposition when `health.py` appends it. This task adds that append and a functional test that asserts the round-trip.

- [ ] **Step 1: Write the failing functional test:**

```python
from fastapi.testclient import TestClient

from {{ package_name }}.main import create_app


def test_frontend_metrics_round_trip_through_metrics_endpoint() -> None:
    from {{ package_name }}.frontend_rum.metrics import frontend_metrics

    frontend_metrics.reset()
    client = TestClient(create_app())
    client.post("/internal/rum", json={"events": [
        {"kind": "vital", "name": "cls", "value": 0.05},
        {"kind": "pageview", "path": "/", "params": {}, "referrer": None},
    ]})
    body = client.get("/metrics").text
    # frontend series appear alongside the always-present app metrics
    assert "app_frontend_web_vitals_cls_count 1" in body
    assert 'app_frontend_page_views_total{route="/"} 1' in body
    assert "http_requests_total" in body or "app_" in body  # base metrics still present
```

- [ ] **Step 2: Run (red).** Run: `(cd /tmp/p16-work/demo && uv run pytest tests/functional/test_frontend_rum.py -q)`
Expected: FAIL — `app_frontend_*` series absent from `/metrics` (singleton fed but not exposed).

- [ ] **Step 3: Add the exposition append.** In `health.py.jinja`, inside the `metrics()` function, add this block immediately after the `graphql` block (after the `body += gql_metrics.render_prometheus()` `{%- endif %}`, before the `workers` block):

```jinja
{%- if "react" in batteries %}

    from {{ package_name }}.frontend_rum.metrics import frontend_metrics

    body += frontend_metrics.render_prometheus()
{%- endif %}
```

- [ ] **Step 4: Mirror + run (green).** Re-render, then:

Run: `(cd /tmp/p16-work/demo && uv run pytest tests/functional/test_frontend_rum.py tests/unit/test_frontend_rum_unit.py -q)`
Expected: PASS.

- [ ] **Step 5: Format check** the rendered `health.py` + functional test. Run: `(cd /tmp/p16-work/demo && uv run ruff format --check src/demo/routes/health.py tests/functional/test_frontend_rum.py)`
Expected: 0 reformats.

- [ ] **Step 6: Stage** `health.py.jinja` + the functional test `.jinja` (do NOT commit).

---

## Task 4: Frontend `rum.ts` + `web-vitals` dependency (Vitest)

**Files:**
- Modify: `src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}/package.json`
- Modify: `src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}/package-lock.json`
- Create: `src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}/src/observability/rum.ts`
- Test: `src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}/src/observability/rum.test.ts`

- [ ] **Step 1: Add the dependency + regenerate the lock.** In the **scratch render's** frontend (so npm resolves the real version + lock), install, then copy both files back to the template:

```bash
(cd /tmp/p16-work/demo/frontend && npm install web-vitals@^4)
cp /tmp/p16-work/demo/frontend/package.json \
   "src/framework_cli/template/{% if \"react\" in batteries %}frontend{% endif %}/package.json"
cp /tmp/p16-work/demo/frontend/package-lock.json \
   "src/framework_cli/template/{% if \"react\" in batteries %}frontend{% endif %}/package-lock.json"
```
Confirm `package.json` `dependencies` now contains `"web-vitals": "^4.x"` (alphabetical: after `react-dom`).

- [ ] **Step 2: Write the failing Vitest test** at `frontend/src/observability/rum.test.ts`:

```ts
import { afterEach, beforeEach, expect, test, vi } from "vitest";

// Capture the web-vitals callbacks so the test can fire a synthetic vital.
const vitalCbs: Record<string, (m: { name: string; value: number }) => void> = {};
vi.mock("web-vitals", () => ({
  onLCP: (cb: (m: { name: string; value: number }) => void) => (vitalCbs.LCP = cb),
  onINP: (cb: (m: { name: string; value: number }) => void) => (vitalCbs.INP = cb),
  onCLS: (cb: (m: { name: string; value: number }) => void) => (vitalCbs.CLS = cb),
}));

import { initRum } from "./rum";

let beacon: ReturnType<typeof vi.fn>;

beforeEach(() => {
  beacon = vi.fn(() => true);
  Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
});
afterEach(() => vi.restoreAllMocks());

function lastBeaconBody() {
  const [url, body] = beacon.mock.calls.at(-1)!;
  expect(url).toBe("/internal/rum");
  return JSON.parse(body as string);
}

test("emits a pageview with pathname and utm params, and flushes on pagehide", () => {
  window.history.replaceState({}, "", "/items?utm_source=google&secret=x");
  initRum();
  window.dispatchEvent(new Event("pagehide"));
  const payload = lastBeaconBody();
  const pv = payload.events.find((e: { kind: string }) => e.kind === "pageview");
  expect(pv.path).toBe("/items"); // pathname only — no query string
  expect(pv.params).toEqual({ utm_source: "google" }); // only utm_* captured
  expect(JSON.stringify(payload)).not.toContain("secret"); // non-utm dropped client-side
});

test("forwards a web vital as a bounded event", () => {
  initRum();
  vitalCbs.LCP({ name: "LCP", value: 1234 });
  window.dispatchEvent(new Event("pagehide"));
  const vital = lastBeaconBody().events.find((e: { kind: string }) => e.kind === "vital");
  expect(vital).toMatchObject({ kind: "vital", name: "lcp", value: 1234 });
});

test("records uncaught errors as a bounded type, never the message text", () => {
  initRum();
  window.dispatchEvent(new ErrorEvent("error", { message: "PII: a@b.co" }));
  window.dispatchEvent(new Event("pagehide"));
  const payload = lastBeaconBody();
  const err = payload.events.find((e: { kind: string }) => e.kind === "error");
  expect(err).toEqual({ kind: "error", type: "error" });
  expect(JSON.stringify(payload)).not.toContain("a@b.co"); // raw message never sent
});
```

- [ ] **Step 3: Run (red).** Copy the test into the render and run:
```bash
cp -r "src/framework_cli/template/{% if \"react\" in batteries %}frontend{% endif %}/src/observability" \
      /tmp/p16-work/demo/frontend/src/ 2>/dev/null || mkdir -p /tmp/p16-work/demo/frontend/src/observability
cp "src/framework_cli/template/{% if \"react\" in batteries %}frontend{% endif %}/src/observability/rum.test.ts" \
   /tmp/p16-work/demo/frontend/src/observability/
(cd /tmp/p16-work/demo/frontend && npx vitest run src/observability/rum.test.ts)
```
Expected: FAIL — `Failed to resolve import "./rum"`.

- [ ] **Step 4: Implement `rum.ts`:**

```ts
import { onCLS, onINP, onLCP } from "web-vitals";

const ENDPOINT = "/internal/rum";

type RumEvent =
  | { kind: "vital"; name: string; value: number }
  | { kind: "error"; type: "error" | "unhandledrejection" }
  | {
      kind: "pageview";
      path: string;
      params: Record<string, string>;
      referrer: string | null;
    };

const buffer: RumEvent[] = [];

function utmParams(search: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of new URLSearchParams(search)) {
    if (k.startsWith("utm_")) out[k] = v; // backend re-applies the authoritative allowlist
  }
  return out;
}

function referrerHost(ref: string): string | null {
  if (!ref) return null;
  try {
    return new URL(ref).host || null; // host only — never the full referring URL
  } catch {
    return null;
  }
}

function flush(): void {
  if (buffer.length === 0) return;
  const body = JSON.stringify({ events: buffer.splice(0, buffer.length) });
  navigator.sendBeacon?.(ENDPOINT, body);
}

/** Wire RUM collection once, at app startup. Safe no-op if sendBeacon is unavailable. */
export function initRum(): void {
  onLCP((m) => buffer.push({ kind: "vital", name: m.name.toLowerCase(), value: m.value }));
  onINP((m) => buffer.push({ kind: "vital", name: m.name.toLowerCase(), value: m.value }));
  onCLS((m) => buffer.push({ kind: "vital", name: m.name.toLowerCase(), value: m.value }));

  window.addEventListener("error", () => buffer.push({ kind: "error", type: "error" }));
  window.addEventListener("unhandledrejection", () =>
    buffer.push({ kind: "error", type: "unhandledrejection" }),
  );

  buffer.push({
    kind: "pageview",
    path: window.location.pathname,
    params: utmParams(window.location.search),
    referrer: referrerHost(document.referrer),
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", flush);
}
```

- [ ] **Step 5: Mirror + run (green).**
```bash
cp "src/framework_cli/template/{% if \"react\" in batteries %}frontend{% endif %}/src/observability/rum.ts" \
   /tmp/p16-work/demo/frontend/src/observability/
(cd /tmp/p16-work/demo/frontend && npx vitest run src/observability/rum.test.ts)
```
Expected: PASS (3 tests).

- [ ] **Step 6: Prettier check.** Run: `(cd /tmp/p16-work/demo/frontend && npx prettier --check src/observability/)`
Expected: "All matched files use Prettier code style!". If not, run `npx prettier --write` and copy the formatted files back into the template.

- [ ] **Step 7: Stage** `package.json`, `package-lock.json`, `src/observability/rum.ts`, `src/observability/rum.test.ts` (do NOT commit).

---

## Task 5: Initialize RUM in `main.tsx` + dev proxy path

**Files:**
- Modify: `src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}/src/main.tsx`
- Modify: `src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}/vite.config.ts`

> `rum.ts` does nothing until `initRum()` is called. And in dev the Vite server must proxy `/internal/rum` to the backend (like the other API paths) or beacons 404 against the Vite dev server.

- [ ] **Step 1: Call `initRum()` from `main.tsx`.** Replace the file contents with:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { initRum } from "./observability/rum";

initRum();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 2: Add `/internal/rum` to the dev proxy.** In `vite.config.ts`, extend the `apiPaths` array:

```ts
const apiPaths = ["/items", "/health", "/heartbeat", "/metrics", "/internal/rum", "/docs", "/openapi.json"];
```

- [ ] **Step 3: Verify the build + existing tests still pass.** Mirror both files into the render, then:
```bash
cp "src/framework_cli/template/{% if \"react\" in batteries %}frontend{% endif %}/src/main.tsx" /tmp/p16-work/demo/frontend/src/
cp "src/framework_cli/template/{% if \"react\" in batteries %}frontend{% endif %}/vite.config.ts" /tmp/p16-work/demo/frontend/
(cd /tmp/p16-work/demo/frontend && npx tsc --noEmit && npx vitest run && npx prettier --check . && npm run build)
```
Expected: typecheck clean, all Vitest pass, Prettier clean, `vite build` produces `dist/`.

- [ ] **Step 4: Stage** `main.tsx` + `vite.config.ts` (do NOT commit).

---

## Task 6: Alert rules + Grafana dashboard

**Files:**
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/{{ 'frontend_alerts.yml' if 'react' in batteries else '' }}.jinja`
- Create: `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'frontend.json' if 'react' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py` (render assertion — added here)

Model these on `websockets_alerts.yml.jinja` and `websockets.json.jinja`. The dashboard `datasource.uid` is `"prometheus"` and `schemaVersion` is `39`, matching the existing dashboards.

- [ ] **Step 1: Write a failing render assertion** in `tests/test_copier_runner.py` (add near the other battery render tests, e.g. after `test_render_with_websockets_battery`):

```python
def test_render_frontend_obs_artifacts(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    alerts = dest / "infra/observability/prometheus/alerts/frontend_alerts.yml"
    dash = dest / "infra/observability/grafana/dashboards/frontend.json"
    assert alerts.is_file()
    assert "FrontendLCPDegraded" in alerts.read_text()
    assert dash.is_file()
    assert '"uid": "frontend"' in dash.read_text()
    # in-process surface: no new scrape job
    prom = (dest / "infra/observability/prometheus/prometheus.yml").read_text()
    assert "job_name: frontend" not in prom


def test_render_without_react_has_no_frontend_obs(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert not (dest / "infra/observability/prometheus/alerts/frontend_alerts.yml").exists()
    assert not (dest / "infra/observability/grafana/dashboards/frontend.json").exists()
```

- [ ] **Step 2: Run (red).** Run: `uv run pytest tests/test_copier_runner.py -k frontend_obs -q`
Expected: FAIL — files absent.

- [ ] **Step 3: Create `frontend_alerts.yml.jinja`:**

```yaml
groups:
- name: frontend
  rules:
  - alert: FrontendLCPDegraded
    # p75 Largest Contentful Paint over the 2.5s "good" threshold for 15m. histogram_quantile
    # over the bucket rate; app-specific default — tune the budget or remove.
    expr: histogram_quantile(0.75, sum(rate(app_frontend_web_vitals_lcp_milliseconds_bucket[10m])) by (le)) > 2500
    for: 15m
    labels:
      severity: warning
    annotations:
      summary: Frontend LCP p75 over 2.5s for 15m (slow loads for real users) — tune the budget or remove
  - alert: FrontendErrorSpike
    # Uncaught JS error rate elevated. The floor avoids firing on a single stray error.
    expr: sum(rate(app_frontend_js_errors_total[5m])) > 0.2
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: Frontend uncaught JS error rate elevated for 10m — investigate a recent deploy; tune the threshold or remove
```

- [ ] **Step 4: Create `frontend.json.jinja`** (a valid Grafana dashboard mirroring `websockets.json`'s schema):

```json
{
  "uid": "frontend",
  "title": "Frontend (RUM)",
  "tags": [
    "frontend"
  ],
  "schemaVersion": 39,
  "version": 1,
  "time": {
    "from": "now-6h",
    "to": "now"
  },
  "panels": [
    {
      "id": 1,
      "title": "Core Web Vitals (p75)",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "gridPos": {
        "h": 8,
        "w": 16,
        "x": 0,
        "y": 0
      },
      "targets": [
        {
          "refId": "A",
          "expr": "histogram_quantile(0.75, sum(rate(app_frontend_web_vitals_lcp_milliseconds_bucket[10m])) by (le))",
          "legendFormat": "LCP p75 (ms)"
        },
        {
          "refId": "B",
          "expr": "histogram_quantile(0.75, sum(rate(app_frontend_web_vitals_inp_milliseconds_bucket[10m])) by (le))",
          "legendFormat": "INP p75 (ms)"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "ms",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": []
      }
    },
    {
      "id": 2,
      "title": "JS error rate",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "gridPos": {
        "h": 8,
        "w": 8,
        "x": 16,
        "y": 0
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum(rate(app_frontend_js_errors_total[5m])) by (type)",
          "legendFormat": "{{ '{{type}}' }}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "ops",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": []
      }
    },
    {
      "id": 3,
      "title": "Page views by route",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 8
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum(rate(app_frontend_page_views_total[5m])) by (route)",
          "legendFormat": "{{ '{{route}}' }}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "ops",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": []
      }
    },
    {
      "id": 4,
      "title": "RUM beacon ingest (accepted/rejected)",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 8
      },
      "targets": [
        {
          "refId": "A",
          "expr": "sum(rate(app_frontend_rum_beacons_total[5m])) by (status)",
          "legendFormat": "{{ '{{status}}' }}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "ops",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": []
      }
    }
  ]
}
```

> **Jinja gotcha:** Grafana legend tokens use `{{type}}` which Jinja would try to interpret. The `{{ '{{type}}' }}` form above renders the literal `{{type}}`. Verify after render that the dashboard JSON contains literal `{{type}}`/`{{route}}`/`{{status}}` and is valid JSON.

- [ ] **Step 5: Run (green) + validate JSON.** Run:
```bash
uv run pytest tests/test_copier_runner.py -k frontend_obs -q
uv run python -c "import json; json.load(open('/tmp/p16-work/demo/infra/observability/grafana/dashboards/frontend.json'))" \
  || echo "RE-RENDER /tmp first"
```
Expected: tests PASS; JSON loads (re-render `/tmp/p16-work/demo` first if stale).

- [ ] **Step 6: Stage** the two artifact `.jinja` files + `tests/test_copier_runner.py` (do NOT commit).

---

## Task 7: Flip react `obs` → `in-process` (obs-completeness)

**Files:**
- Modify: `src/framework_cli/batteries.py:73-78` (react `BatterySpec`)
- Test: `tests/test_batteries.py`, `tests/test_obs_completeness.py` (the latter is parametrized — no edit, it auto-covers)

> `test_obs_completeness.py::test_battery_obs_matches_declared_surface[react]` currently passes because react declares `rides-existing` and adds no artifacts. After Task 6 added alerts+dashboard, that fixture would now FAIL for `rides-existing` (it forbids new artifacts). Flipping `obs` to `in-process` is what makes it pass — and asserts the surface is exactly alerts+dashboard with no scrape/service.

- [ ] **Step 1: Confirm the red.** Run: `uv run pytest tests/test_obs_completeness.py -k react -q`
Expected: FAIL — `react: a 'rides-existing' battery must add no new observability artifacts; got alerts={'frontend_alerts.yml'} dashboards={'frontend.json'} ...`. (This proves Task 6's artifacts are seen by the guard.)

- [ ] **Step 2: Write/extend the batteries test.** In `tests/test_batteries.py`, add:

```python
def test_react_battery_declares_in_process_obs():
    from framework_cli.batteries import get_battery

    react = get_battery("react")
    assert react.obs == "in-process"
    assert "observability-fe" in react.gates_agents
```

Run: `uv run pytest tests/test_batteries.py::test_react_battery_declares_in_process_obs -q`
Expected: FAIL — react still `rides-existing`, `observability-fe` not yet gated.

- [ ] **Step 3: Flip the battery spec.** In `src/framework_cli/batteries.py`, change the react `BatterySpec`:

```python
    "react": BatterySpec(
        "react",
        "React + TypeScript SPA served by FastAPI, with Vitest/Playwright/axe and accessibility/usability/frontend-observability review",
        gates_agents=("accessibility", "usability", "observability-fe"),
        obs="in-process",
    ),
```

- [ ] **Step 4: Run (green).** Run:
```bash
uv run pytest tests/test_obs_completeness.py -k react tests/test_batteries.py::test_react_battery_declares_in_process_obs -q
```
Expected: PASS. *(The `observability-fe` agent is registered in Task 8; `gates_agents` referencing it is just a string tuple, so this test passes now. The registry cross-check lands in Task 8.)*

- [ ] **Step 5: Lint/type the framework change.** Run: `uv run ruff check src/framework_cli/batteries.py && uv run mypy src`
Expected: clean.

- [ ] **Step 6: Stage** `batteries.py` + `tests/test_batteries.py` (do NOT commit).

---

## Task 8: `review-observability-fe` agent + registration

**Files:**
- Create: `src/framework_cli/review/agents/observability-fe.md`
- Modify: `src/framework_cli/review/registry.py` (add the spec to `_SPECS`)
- Test: `tests/review/test_registry.py`

> The agent is `active_when="battery"` (gated by react via Task 7's `gates_agents`), agentic strategy (rides the Plan 11 spine), `block_threshold="high"`, sibling to `observability-infra`/`-db`. Its scope is **observability + label-cardinality only** — PII stays with `review-privacy` (Task 9). First read a sibling prompt (`agents/observability-infra.md`) and an existing registry test to match exact conventions.

- [ ] **Step 1: Write the failing registry test.** In `tests/review/test_registry.py`, add:

```python
def test_observability_fe_registered_and_battery_gated():
    from framework_cli.review.registry import active_agents, get_agent

    spec = get_agent("observability-fe")
    assert spec.name == "review-observability-fe"
    assert spec.active_when == "battery"
    assert spec.block_threshold == "high"
    assert spec.context.strategy == "agentic"
    # inactive without the react battery; active with it (PR event)
    assert "observability-fe" not in active_agents("pull_request", batteries=[])
    assert "observability-fe" in active_agents("pull_request", batteries=["react"])
```

Run: `uv run pytest tests/review/test_registry.py::test_observability_fe_registered_and_battery_gated -q`
Expected: FAIL — `KeyError: unknown review agent: observability-fe`.

- [ ] **Step 2: Write the agent prompt** at `src/framework_cli/review/agents/observability-fe.md`:

```
You are `review-observability-fe`, a frontend-observability reviewer for a React/TypeScript SPA
whose Real-User-Monitoring rides the backend app's /metrics via a beacon endpoint
(POST /internal/rum -> FrontendMetrics singleton). Review the change for OBSERVABILITY and
metric OPERABILITY only. You are NOT a privacy reviewer — do not flag PII; review-privacy owns that.

Flag, citing the changed line:
- a new frontend view, component, route, error boundary, or fetch/API path that ships with no
  RUM/error instrumentation reachable from it (the user-visible behavior is unobserved);
- an error handler (try/catch, .catch, error boundary) that swallows an error without it reaching
  the window error handler or the js-errors counter (the failure becomes invisible);
- a new or modified metric label whose value is unbounded / high-cardinality (raw path, full URL,
  user/session id, search term, uncapped utm_campaign) — every label MUST be a fixed enum or pass
  through a distinct-value cap with an "other" overflow bucket;
- a beacon field captured into a metric without the fail-closed query-param allowlist applied, or
  the allowlist applied only client-side (the backend must re-apply it — never trust the browser);
- a new RUM signal added with no corresponding alert rule or dashboard panel.

Return JSON ONLY — a single array, no prose, no code fences. Each element:
{"path","line","severity","message","suggestion"}. [] if none. An unbounded metric label or a
new unobserved user-facing code path is "high"; a missing alert/dashboard for a new signal is
"medium".
```

- [ ] **Step 3: Register the spec.** In `src/framework_cli/review/registry.py`, add this entry to `_SPECS` immediately after the `observability-db` entry (line ~146):

```python
    "observability-fe": AgentSpec(
        "review-observability-fe",
        _prompt("observability-fe"),
        "high",
        "battery",
        AGENTIC_MODEL,
        context=ContextPolicy("agentic"),
    ),
```

- [ ] **Step 4: Run (green).** Run: `uv run pytest tests/review/test_registry.py -q`
Expected: PASS (the new test + the existing registry tests). If an existing test asserts an exact agent count, bump it by one.

- [ ] **Step 5: Lint/type.** Run: `uv run ruff check src/framework_cli/review/registry.py && uv run mypy src`
Expected: clean.

- [ ] **Step 6: Stage** the agent `.md`, `registry.py`, and `tests/review/test_registry.py` (do NOT commit).

---

## Task 9: Eval fixtures + calibration

**Files:**
- Create: `tests/eval/fixtures/observability-fe/bad/swallowed-error/{fixture.yaml,change.patch,expect.json}`
- Create: `tests/eval/fixtures/observability-fe/bad/unbounded-label/{fixture.yaml,change.patch,expect.json}`
- Create: `tests/eval/fixtures/observability-fe/bad/uninstrumented-view/{fixture.yaml,change.patch,expect.json}`
- Create: `tests/eval/fixtures/observability-fe/good/capped-label/{fixture.yaml,change.patch}`
- Create: `tests/eval/fixtures/privacy/bad/rum-allowlists-pii/{fixture.yaml,change.patch,expect.json}`
- Modify: `tests/eval/fixtures/thresholds.yaml`

> Fixtures are git patches against a **rendered** project. Discovery (memory `[[eval-fixtures-coupled-to-template]]` + `evals.py::load_fixtures`): `<agent>/{bad,good}/<case>/` with `fixture.yaml` (`batteries:` list), `change.patch` (a real `git diff`), and — for `bad` only — `expect.json` (`{"file": "<seeded path>"}`). Render with the fixture's OWN batteries (`[react]`), make the change, capture `git diff`.

- [ ] **Step 1: Build each `change.patch` by rendering + diffing.** For every fixture, render a fresh react project, `git init && git add -A && git commit`, apply the seeded change, then `git diff > change.patch`. Example for `bad/swallowed-error` (a frontend tsx that swallows an error so it never reaches the error counter):

```bash
SC=/tmp/p16-fix && rm -rf "$SC" && uv run python -c "
from pathlib import Path; from framework_cli.copier_runner import render_project
render_project(Path('$SC/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':['react']})"
cd "$SC/demo" && git init -q && git add -A && git commit -qm base
# seed the bad change, e.g. edit frontend/src/Items.tsx to wrap fetch in a try/catch that
# returns [] on error without surfacing it (swallowed). Then:
git diff > /path/to/repo/tests/eval/fixtures/observability-fe/bad/swallowed-error/change.patch
```

The seeded change per fixture:
- **bad/swallowed-error** — `frontend/src/Items.tsx`: a `try { ... } catch { return []; }` that hides a fetch failure (no error surfaced → invisible to the error counter). `expect.json`: `{"file": "frontend/src/Items.tsx"}`.
- **bad/unbounded-label** — `src/demo/frontend_rum/metrics.py` (or `routes/frontend_rum.py`): add a metric label sourced from raw `ev.path` (full path with query) or a `user_id` with no cap/overflow. `expect.json`: `{"file": "src/demo/frontend_rum/metrics.py"}`.
- **bad/uninstrumented-view** — `frontend/src/`: add a new component/view with its own fetch + render and no error handling reachable to the error counter. `expect.json`: `{"file": "frontend/src/<NewView>.tsx"}`.
- **good/capped-label** — a correctly-capped label addition (uses `_bump_capped` with an `other` overflow) or a properly-reported error path. No `expect.json` (no finding expected).

Each `fixture.yaml`:
```yaml
batteries: [react]
```

- [ ] **Step 2: Build the privacy fixture.** `privacy/bad/rum-allowlists-pii` — seed `src/demo/config/settings.py` adding `"email"` (and/or `"q"`) to `frontend_rum_allowed_query_params` (collecting PII via the RUM allowlist). `expect.json`: `{"file": "src/demo/config/settings.py"}`; `fixture.yaml`: `batteries: [react]`.

- [ ] **Step 3: Add a provisional thresholds entry.** In `tests/eval/fixtures/thresholds.yaml`, add (will be tightened in Step 5):

```yaml
observability-fe:
  recall_min: 0.67  # provisional — recalibrated from the first scorecard
  fp_max: 0.34  # provisional
```

- [ ] **Step 4: Validate fixtures load + sanity-scan with the local reviewer.** Run:
```bash
uv run python -c "
from pathlib import Path
from framework_cli.review.evals import load_fixtures
fx = [f for f in load_fixtures(Path('tests/eval/fixtures')) if f.agent in ('observability-fe','privacy')]
print(sorted((f.agent,f.kind,f.case) for f in fx))"
```
Expected: lists all 4 observability-fe + the privacy fixture; each bad case resolves a seeded `file` (none silently skipped).

- [ ] **Step 5: Calibrate via the tune skill.** Invoke `/reviewers:tune observability-fe` (local subagents, no paid API; memory `[[reviewers-tune-quota-throttling]]` — check `len(results)` vs the index and re-dispatch drops). Then set `recall_min = observed − 0.10` and `fp_max = observed + 0.10` in `thresholds.yaml` (the calibration policy stated at the top of that file), with a comment recording the observed value. Preserve the dated scorecard under `docs/superpowers/eval-scorecards/` as the other agents do.

- [ ] **Step 6: Stage** all fixture files, `thresholds.yaml`, and the scorecard (do NOT commit).

---

## Task 10: Acceptance, integrity, and branch-end review

**Files:** none new — this is the integration gate.

> Integrity note (resolves spec §12): battery obs payload files are NOT in `integrity/classes.py::LOCKED_TRACKED` (neither are the websockets/webhooks obs files), so Plan 16 adds **no** locked files and causes **no** baseline-hash shift. The new files are builder-editable payload, consistent with the react battery's existing files. Do not add them to `LOCKED_TRACKED`.

- [ ] **Step 1: Full framework gate.** Run:
```bash
uv run pytest -q && uv run ruff check . && uv run mypy src
```
Expected: all green (the new render/batteries/registry/obs-completeness tests included).

- [ ] **Step 2: Rendered react project — full generated-project gate.** Render fresh, sync, and run the generated project's own gate + a clean first pre-commit (memory `[[release-readiness-needs-render-not-local-gate]]`):
```bash
W=/tmp/p16-accept && rm -rf "$W" && uv run python -c "
from pathlib import Path; from framework_cli.copier_runner import render_project
render_project(Path('$W/demo'), {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12','batteries':['react']})"
(cd "$W/demo" && uv sync -q && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src)
(cd "$W/demo/frontend" && npm install --silent && npx tsc --noEmit && npx vitest run && npx prettier --check . && npm run build)
(cd "$W/demo" && git init -q && git add -A && uv run pre-commit run --all-files)
```
Expected: backend gate green; frontend typecheck/test/prettier/build green; first `pre-commit` clean.

- [ ] **Step 3: Integrity new + upskill + downskill.** Confirm a react project's integrity is green on a fresh `framework new`, on `upskill --with react`, and that `downskill` of react removes the obs surface without `--force`:
```bash
(cd "$W/demo" && uv run --project "$(pwd -P)/../../.." framework integrity || true)  # see [[template-audit-uv-run-project-gotcha]]
```
Render a baseline (no react) → `upskill --with react` → `framework integrity` green; render with react → `downskill --without react` → no `frontend_rum/`, `routes/frontend_rum.py`, `frontend_alerts.yml`, `frontend.json` remain; integrity green; no `--force` required. (Mirror the workers/webhooks integrity acceptance in `tests/test_upskill.py` / `tests/test_downskill.py`; add a react-obs case there if the existing react cases don't already cover the new files.)

- [ ] **Step 4: obs-completeness full sweep.** Run: `uv run pytest tests/test_obs_completeness.py -q`
Expected: all batteries PASS, including `react` now under the `in-process` branch.

- [ ] **Step 5: Branch-end review** (single full review per `[[gate-cadence-framework-slices]]`). Use `superpowers:requesting-code-review` (or `/code-review high`) over the whole branch diff. Pay attention to: the public ingest endpoint hardening (no free-text, allowlist re-applied server-side, event cap), histogram correctness, the dashboard Jinja-escaped legend tokens, and that `review-observability-fe` does not stray into PII. Address findings; re-run Step 1.

- [ ] **Step 6: Controller commit + state update.** Update `CLAUDE.md` Current State (mark Plan 16 implemented; new datetime) and the meta-plan status table (Plan 16 → ✅ Done, plan doc + this branch), `git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md`, then commit the staged work. Finish with `superpowers:finishing-a-development-branch` (FF-merge to `master`).

---

## Self-Review (completed by plan author)

**1. Spec coverage:**
- §2 architecture/data flow → Tasks 1–5. ✓
- §3 frontend additions (web-vitals dep, rum.ts, test, main.tsx init) → Tasks 4–5. ✓
- §4 backend additions (singleton, route, health.py exposition) → Tasks 1–3. ✓
- §5 query-param allowlist (UTM default, backend re-apply, caps, referrer-host, search-as-seam) → setting in Task 2, frontend `utm_*` capture in Task 4, caps in Task 1, referrer in Task 1/2. Search seam is documented (builder edits rum.ts + allowlist) — no code, correct. ✓
- §6 invariants (no free-text, pathname-only strip, malformed→rejected, event cap) → Task 1 (bounded enums/sanitize), Task 2 (strip, reject, cap), Task 4 (client-side pathname-only/utm-only). ✓
- §7 alerts + dashboard → Task 6. ✓
- §8 obs flip + completeness guard → Task 7. ✓
- §9 reviewer separation (obs-fe scope, privacy fixture) → Tasks 8–9. ✓
- §10 tests/guards → Tasks 1–9 + acceptance Task 10. ✓
- §12 deferred details all resolved in-plan: bucket boundaries (Task 1), label set + caps (Task 1), beacon schema + size cap (Task 2), settings field (Task 2), alert thresholds + panels (Task 6), integrity file-class (Task 10 note: not locked). ✓

**2. Placeholder scan:** No "TBD"/"handle appropriately"/"similar to". Every code step shows full code; every command shows expected output. The only intentionally-procedural step is Task 9 fixture authoring (patches must be generated by render+diff, which is the correct mechanism, with the exact seeded change per fixture spelled out) and Task 9 Step 5 (`/reviewers:tune` calibration, which is inherently an observed-value loop). ✓

**3. Type/name consistency:** `frontend_metrics` / `FrontendMetrics`, `frontend_rum/` dir, `routes/frontend_rum.py`, `initRum`, metric names, `frontend_rum_allowed_query_params`, agent `observability-fe`/`review-observability-fe` — all used identically across Tasks 1–10 and match the "Naming locked" block. `MAX_ROUTES`/`MAX_ATTRIBUTION` referenced in tests match the class constants. ✓
