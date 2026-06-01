# Obs-infra Self-Monitoring + Completeness Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the generated obs stack monitor its own base components (otel-collector, prometheus) — scrape + alert + dashboard — and add a framework guard test that fails if any exporter/infra Prometheus job lacks the full trio.

**Architecture:** Write the completeness-guard test first (it renders an all-batteries project and asserts (A) every monitored compose service is a scrape target and (B) every scrape job except `app` has an alert + dashboard referencing its `job="…"`). It goes red on the two known gaps; then add otel-collector self-metrics + scrape + alert + dashboard, and prometheus alert + dashboard, to turn it green.

**Tech Stack:** OpenTelemetry Collector 0.111, Prometheus, Grafana (dashboard JSON), Copier (Jinja) template, pytest + PyYAML, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-01-obs-infra-self-monitoring-design.md`

---

## Conventions (read first)

- `FW` = framework repo root (`/home/chris/Claude Code/Projects/framework/swiftwater-framework`). Run `uv` from there. You are on branch `obs-infra-selfmon-2026-06-01` — do NOT switch branches.
- **This slice is config-only on the template side** (YAML + Grafana JSON) plus one **framework test**. The guard test runs in the FRAMEWORK venv (`uv run pytest tests/test_obs_completeness.py`) — it renders a project with `framework_cli.copier_runner.render_project` and parses files. **No rendered-project `uv sync` loop is needed.**
- **Template payload vs framework source:** files under `src/framework_cli/template/` are rendered into generated projects. `otel-collector.yml` and the dashboard `.json` files are plain (no Jinja); `prometheus.yml.jinja` and the battery alert/dashboard files use Jinja. The two NEW alert files and two NEW dashboards are unconditional (base obs) — plain `.yml`/`.json`, no Jinja.
- **COMMIT-GATE HOOK:** a PreToolUse hook blocks `git commit` unless `CLAUDE.md` is staged. For each commit: (1) add a BRIEF note to the **Current State** pointer at the top of `CLAUDE.md` + bump **Last updated**; (2) `git add CLAUDE.md <files>` as a SEPARATE command; (3) `git commit` as its own command (don't chain `add && commit`; keep "commit" out of Bash command *descriptions*). End bodies with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. NOTE: in a subagent session the gate may BLOCK the commit (it needs the `Workflow` tool, which subagents lack) — if so, report DONE with everything staged and the controller will commit.
- **Do NOT run the Docker acceptance tier** (it can wedge `/tmp`). The guard test + render/parse checks here are sufficient; Grafana/collector runtime validity is covered by CI's acceptance tier.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tests/test_obs_completeness.py` (framework) | guard: monitored services scraped + every infra job has alert+dashboard | 1 |
| `src/framework_cli/template/infra/observability/otel/otel-collector.yml` | expose `:8888` self-metrics | 2 |
| `src/framework_cli/template/infra/observability/prometheus/prometheus.yml.jinja` | `otel-collector` scrape job | 2 |
| `src/framework_cli/template/infra/observability/prometheus/alerts/otel_collector_alerts.yml` | new — OtelCollectorDown | 2 |
| `src/framework_cli/template/infra/observability/grafana/dashboards/otel-collector.json` | new — collector up-stat | 2 |
| `src/framework_cli/template/infra/observability/prometheus/alerts/prometheus_alerts.yml` | new — PrometheusDown + ConfigReloadFailed | 3 |
| `src/framework_cli/template/infra/observability/grafana/dashboards/prometheus.json` | new — prometheus up-stat | 3 |

---

## Task 1: Completeness-guard test (red)

**Files:**
- Create: `tests/test_obs_completeness.py`

- [ ] **Step 1: Write the guard test**

Create `tests/test_obs_completeness.py`:

```python
"""Obs-completeness guard (framework-authoring invariant).

Renders an all-batteries project and asserts two things about the obs stack:
  A. every monitored compose service (a `*-exporter`, or the otel-collector) is a
     Prometheus scrape target — catches a deployed service with no scrape target;
  B. every Prometheus scrape job EXCEPT `app` has an alert rule and a dashboard
     referencing its `job="<name>"` — catches a scraped surface with no alert/dashboard.

The `app` job is the application's own /metrics (SLO dashboards/alerts on latency &
error-rate, not an `up{job=...}` exporter surface) — excluded by design.
"""

import re
from pathlib import Path

import yaml

from framework_cli.copier_runner import render_project

_EXCLUDED_JOBS = {"app"}


def _render(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    render_project(
        root,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
            "batteries": ["workers", "mongodb", "redis", "pgvector", "graphql"],
        },
    )
    return root


def _job_ref(text: str, job: str) -> bool:
    # Matches job="x" (YAML/plain) and job=\"x\" (escaped inside dashboard JSON).
    return re.search(rf'job=\\?"{re.escape(job)}\\?"', text) is not None


def test_monitored_services_are_scraped(tmp_path: Path):
    root = _render(tmp_path)
    obs = yaml.safe_load(
        (root / "infra/compose/observability.yml").read_text()
    )["services"]
    monitored = {
        name for name in obs if name.endswith("-exporter")
    } | {"otel-collector"}

    prom = yaml.safe_load(
        (root / "infra/observability/prometheus/prometheus.yml").read_text()
    )
    target_hosts = {
        t.split(":")[0]
        for job in prom["scrape_configs"]
        for sc in job.get("static_configs", [])
        for t in sc.get("targets", [])
    }

    missing = monitored - target_hosts
    assert not missing, f"monitored services with no Prometheus scrape target: {sorted(missing)}"


def test_every_infra_job_has_alert_and_dashboard(tmp_path: Path):
    root = _render(tmp_path)
    prom = yaml.safe_load(
        (root / "infra/observability/prometheus/prometheus.yml").read_text()
    )
    jobs = [j["job_name"] for j in prom["scrape_configs"] if j["job_name"] not in _EXCLUDED_JOBS]

    alert_text = "\n".join(
        p.read_text()
        for p in (root / "infra/observability/prometheus/alerts").glob("*.yml")
    )
    dash_text = "\n".join(
        p.read_text()
        for p in (root / "infra/observability/grafana/dashboards").glob("*.json")
    )

    for job in jobs:
        assert _job_ref(alert_text, job), f"job {job!r} is scraped but no alert references job=\"{job}\""
        assert _job_ref(dash_text, job), f"job {job!r} is scraped but no dashboard references job=\"{job}\""
```

- [ ] **Step 2: Run the test to verify it fails (the two gaps)**

Run: `uv run pytest tests/test_obs_completeness.py -q`
Expected: FAIL — `test_monitored_services_are_scraped` fails with `monitored services with no Prometheus scrape target: ['otel-collector']`, and `test_every_infra_job_has_alert_and_dashboard` fails with `job 'prometheus' is scraped but no alert references job="prometheus"`. (postgres/celery/mongodb/redis already pass both.)

- [ ] **Step 3: Commit (red guard is intentional — the next tasks turn it green)**

Update the CLAUDE.md pointer (brief), then:
```bash
git add CLAUDE.md tests/test_obs_completeness.py
git commit -m "test(obs): completeness guard — monitored services scraped + jobs have alert+dashboard"
```
(Committing a known-red guard is acceptable here ONLY because Tasks 2-3 in this same plan turn it green and the final gate (Task 4) blocks on it. If you prefer, hold this commit and bundle it with Task 2 — either is fine; do NOT push a red guard to master, which Task 4 + the finishing step prevent.)

> Implementer note: if you'd rather not commit a red test, skip the commit here and stage `tests/test_obs_completeness.py` along with Task 2's files, committing once Task 2 makes `test_monitored_services_are_scraped` pass. The controller will confirm the guard is green before merge regardless.

---

## Task 2: otel-collector self-monitoring

**Files:**
- Modify: `src/framework_cli/template/infra/observability/otel/otel-collector.yml`
- Modify: `src/framework_cli/template/infra/observability/prometheus/prometheus.yml.jinja`
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/otel_collector_alerts.yml`
- Create: `src/framework_cli/template/infra/observability/grafana/dashboards/otel-collector.json`

- [ ] **Step 1: Expose the collector's self-metrics**

In `src/framework_cli/template/infra/observability/otel/otel-collector.yml`, change the `service:` block from:
```yaml
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/tempo]
```
to:
```yaml
service:
  telemetry:
    metrics:
      address: "0.0.0.0:8888"
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/tempo]
```

- [ ] **Step 2: Add the scrape job**

In `src/framework_cli/template/infra/observability/prometheus/prometheus.yml.jinja`, the top of `scrape_configs` is:
```yaml
  - job_name: app
    metrics_path: /metrics
    static_configs:
      - targets: ["app:8000"]
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]
  - job_name: postgres
    static_configs:
      - targets: ["postgres-exporter:9187"]
```
Insert the `otel-collector` job between `prometheus` and `postgres`:
```yaml
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]
  - job_name: otel-collector
    static_configs:
      - targets: ["otel-collector:8888"]
  - job_name: postgres
    static_configs:
      - targets: ["postgres-exporter:9187"]
```

- [ ] **Step 3: Add the alert file**

Create `src/framework_cli/template/infra/observability/prometheus/alerts/otel_collector_alerts.yml` (mirror the existing `postgres_alerts.yml` shape):
```yaml
groups:
- name: otel-collector
  rules:
  - alert: OtelCollectorDown
    expr: up{job="otel-collector"} == 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: otel-collector scrape target is down (traces may be dropped) — app-specific default; tune or remove
```

- [ ] **Step 4: Add the dashboard**

Create `src/framework_cli/template/infra/observability/grafana/dashboards/otel-collector.json` (mirror the minimal exporter-dashboard shape):
```json
{
  "uid": "otel-collector",
  "title": "OTel Collector",
  "tags": ["otel-collector"],
  "schemaVersion": 39,
  "version": 1,
  "time": {"from": "now-1h", "to": "now"},
  "panels": [
    {
      "id": 1,
      "title": "Collector Up",
      "type": "stat",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
      "targets": [{"refId": "A", "expr": "up{job=\"otel-collector\"}"}]
    }
  ]
}
```

- [ ] **Step 5: Run the guard (collector half now passes)**

Run: `uv run pytest tests/test_obs_completeness.py -q`
Expected: `test_monitored_services_are_scraped` PASSES (otel-collector is now scraped). `test_every_infra_job_has_alert_and_dashboard` still FAILS, now only on `job 'prometheus'` (otel-collector now has its alert + dashboard).

- [ ] **Step 6: Sanity — rendered files parse**

Run:
```bash
rm -rf /tmp/oi && uv run framework template-render --out /tmp/oi >/dev/null
python3 -c "import yaml,json; yaml.safe_load(open('/tmp/oi/infra/observability/otel/otel-collector.yml')); yaml.safe_load(open('/tmp/oi/infra/observability/prometheus/prometheus.yml')); yaml.safe_load(open('/tmp/oi/infra/observability/prometheus/alerts/otel_collector_alerts.yml')); json.load(open('/tmp/oi/infra/observability/grafana/dashboards/otel-collector.json')); print('parse ok')"
rm -rf /tmp/oi
```
Expected: `parse ok`.

- [ ] **Step 7: Commit**

Update the CLAUDE.md pointer (brief), then:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/infra/observability/otel/otel-collector.yml" \
  "src/framework_cli/template/infra/observability/prometheus/prometheus.yml.jinja" \
  "src/framework_cli/template/infra/observability/prometheus/alerts/otel_collector_alerts.yml" \
  "src/framework_cli/template/infra/observability/grafana/dashboards/otel-collector.json"
# (also `git add tests/test_obs_completeness.py` here if you held the Task 1 commit)
git commit -m "feat(template): monitor otel-collector (self-metrics + scrape + alert + dashboard)"
```

---

## Task 3: prometheus self-monitoring

**Files:**
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/prometheus_alerts.yml`
- Create: `src/framework_cli/template/infra/observability/grafana/dashboards/prometheus.json`

- [ ] **Step 1: Add the alert file**

Create `src/framework_cli/template/infra/observability/prometheus/alerts/prometheus_alerts.yml`:
```yaml
groups:
- name: prometheus
  rules:
  - alert: PrometheusDown
    expr: up{job="prometheus"} == 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Prometheus self-scrape is down — app-specific default; tune or remove
  - alert: PrometheusConfigReloadFailed
    expr: prometheus_config_last_reload_successful == 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Prometheus config reload failed — alerting/scrape config may be stale
```

- [ ] **Step 2: Add the dashboard**

Create `src/framework_cli/template/infra/observability/grafana/dashboards/prometheus.json`:
```json
{
  "uid": "prometheus",
  "title": "Prometheus",
  "tags": ["prometheus"],
  "schemaVersion": 39,
  "version": 1,
  "time": {"from": "now-1h", "to": "now"},
  "panels": [
    {
      "id": 1,
      "title": "Prometheus Up",
      "type": "stat",
      "datasource": {"type": "prometheus", "uid": "prometheus"},
      "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
      "targets": [{"refId": "A", "expr": "up{job=\"prometheus\"}"}]
    }
  ]
}
```

- [ ] **Step 3: Run the guard (now fully green)**

Run: `uv run pytest tests/test_obs_completeness.py -q`
Expected: PASS (2 passed) — both monitored-services-scraped and every-job-has-alert+dashboard hold.

- [ ] **Step 4: Sanity — rendered files parse**

Run:
```bash
rm -rf /tmp/oi && uv run framework template-render --out /tmp/oi >/dev/null
python3 -c "import yaml,json; yaml.safe_load(open('/tmp/oi/infra/observability/prometheus/alerts/prometheus_alerts.yml')); json.load(open('/tmp/oi/infra/observability/grafana/dashboards/prometheus.json')); print('parse ok')"
rm -rf /tmp/oi
```
Expected: `parse ok`.

- [ ] **Step 5: Commit**

Update the CLAUDE.md pointer (brief), then:
```bash
git add CLAUDE.md \
  "src/framework_cli/template/infra/observability/prometheus/alerts/prometheus_alerts.yml" \
  "src/framework_cli/template/infra/observability/grafana/dashboards/prometheus.json"
git commit -m "feat(template): monitor prometheus self (alerts + dashboard)"
```

---

## Task 4: Whole-slice verification

**Files:** none (verification only).

- [ ] **Step 1: Guard green + a non-data-store render still passes**

```bash
uv run pytest tests/test_obs_completeness.py -q
```
Expected: 2 passed. (The render inside the test uses an all-batteries-ish set; otel-collector/prometheus are base, so the guard holds for any combo.)

- [ ] **Step 2: Eval-fixture safety scan (expect broken: 0)**

```bash
python3 - <<'PY'
import subprocess, tempfile, yaml, shutil
from pathlib import Path
cache={}
def render(b):
    k=",".join(sorted(b)) or "_none_"
    if k in cache: return cache[k]
    d=tempfile.mkdtemp(prefix="fx-"); subprocess.run(["uv","run","framework","template-render","--out",d,"--batteries",",".join(b)],capture_output=True,text=True); cache[k]=d; return d
bad=0
for p in sorted(Path("tests/eval/fixtures").glob("*/*/*/change.patch")):
    b=(yaml.safe_load((p.parent/"fixture.yaml").read_text()) or {}).get("batteries",[])
    if subprocess.run(["git","apply","--check","-p1",str(p.resolve())],cwd=render(b),capture_output=True,text=True).returncode!=0:
        bad+=1; print("BROKEN",p.parent)
print("broken:",bad)
for d in cache.values(): shutil.rmtree(d,ignore_errors=True)
PY
```
Expected: `broken: 0`.

- [ ] **Step 3: Full framework gate**

```bash
uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run mypy src
```
Expected: all pass (incl. the new `tests/test_obs_completeness.py`), ruff clean, mypy clean.

- [ ] **Step 4: Clean up**

```bash
rm -rf /tmp/oi 2>/dev/null
rm -rf /tmp/pytest-of-chris/* 2>/dev/null
```

---

## Notes for the implementer

- **The guard is the spec's centerpiece** — write it first (Task 1) and let it drive Tasks 2-3. It encodes the framework-authoring invariant (scrape + alert + dashboard per infra/exporter surface) so a future exporter-adding battery that forgets a piece fails CI.
- **`app` is excluded** from Part B by design — it's the application's own /metrics with SLO-style dashboards/alerts, not an `up{job=...}` exporter surface. Don't try to give it an `up{job="app"}` alert.
- **Dashboards are minimal** (a single `up{job=...}` stat panel) — they exist for parity + the guard, not as rich dashboards. The `job=\"…\"` string inside the JSON is what the guard matches.
- The `service.telemetry.metrics.address: "0.0.0.0:8888"` form is correct for the pinned collector (`otel/opentelemetry-collector:0.111.0`); the runtime (collector actually starting + Prometheus scraping it) is validated by CI's acceptance tier, not in-session.
