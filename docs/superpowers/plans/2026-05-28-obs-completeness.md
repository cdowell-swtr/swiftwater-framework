# Observability-completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce the §5 battery-observability contract with a deterministic framework-authoring invariant, and split `review-observability` into app/infra/db domain reviewers.

**Architecture:** Facet 1 adds a required `obs` declaration to `BatterySpec` and a parametrized render-diff test (`tests/test_obs_completeness.py`) that asserts each battery's rendered observability artifacts match its declaration. Facet 2 adds two new file-triggered review agents (`review-observability-infra`, `review-observability-db`) alongside the unchanged app agent, each with a prompt + eval fixtures + registry wiring. No template payload changes → no baseline manifest shift.

**Tech Stack:** Python 3.12, dataclasses (`kw_only` field), Copier render (`render_project`), pytest (parametrize, module fixtures), PyYAML, the existing `framework_cli.review` registry + eval-fixture harness.

**Spec:** `docs/superpowers/specs/2026-05-28-obs-completeness-design.md`

---

## File Structure

- `src/framework_cli/batteries.py` — **modify**: add `ObsSurface` Literal + required kw-only `obs` field on `BatterySpec`; backfill all 11 batteries.
- `tests/test_batteries.py` — **modify**: tests for the required field + per-battery obs values; fix the synthetic `_child` construction.
- `tests/test_obs_completeness.py` — **create**: the parametrized render-diff invariant.
- `src/framework_cli/review/agents/observability-infra.md` — **create**: infra reviewer prompt.
- `src/framework_cli/review/agents/observability-db.md` — **create**: db reviewer prompt.
- `src/framework_cli/review/registry.py` — **modify**: register the two new agents.
- `tests/review/test_registry.py` — **modify**: update `_EXPECTED_PR`; add split-specific assertions; fix synthetic `BatterySpec` constructions.
- `tests/eval/fixtures/observability-infra/{bad,good}/…` — **create**: 3 bad + 1 good fixtures.
- `tests/eval/fixtures/observability-db/{bad,good}/…` — **create**: 3 bad + 1 good fixtures.
- `CLAUDE.md` + `docs/superpowers/plans/2026-05-20-meta-plan.md` — **modify** (Task 5): state + roadmap.

---

## Task 1: Required `obs` declaration on `BatterySpec`

**Files:**
- Modify: `src/framework_cli/batteries.py`
- Modify: `tests/test_batteries.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_batteries.py`:

```python
def test_batteryspec_requires_obs():
    from framework_cli.batteries import BatterySpec

    with pytest.raises(TypeError):
        BatterySpec("x", "y")  # obs is a required keyword-only field


def test_every_battery_declares_a_valid_obs_surface():
    from framework_cli.batteries import battery_names, get_battery

    valid = {"service", "in-process", "rides-existing"}
    for name in battery_names():
        assert get_battery(name).obs in valid, name


@pytest.mark.parametrize(
    "name,expected",
    [
        ("mongodb", "service"),
        ("workers", "service"),
        ("redis", "service"),
        ("webhooks", "in-process"),
        ("websockets", "in-process"),
        ("graphql", "in-process"),
        ("pgvector", "rides-existing"),
        ("timescaledb", "rides-existing"),
        ("age", "rides-existing"),
        ("react", "rides-existing"),
        ("consumers", "rides-existing"),
    ],
)
def test_battery_obs_surface(name, expected):
    from framework_cli.batteries import get_battery

    assert get_battery(name).obs == expected
```

`tests/test_batteries.py` already imports `pytest`; confirm it does (it uses `pytest.raises` elsewhere) — if not, add `import pytest`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_batteries.py -q`
Expected: FAIL — `BatterySpec` has no `obs` field (`TypeError`/`AttributeError`), per-value tests error.

- [ ] **Step 3: Add the field + backfill**

In `src/framework_cli/batteries.py`, change the imports and dataclass:

```python
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

ObsSurface = Literal["service", "in-process", "rides-existing"]


@dataclass(frozen=True)
class BatterySpec:
    name: str  # token used in templates + `--with`
    summary: str  # one line, for --help / error messages
    requires: tuple[str, ...] = ()  # batteries this one implies (e.g. pgvector -> postgres)
    gates_agents: tuple[str, ...] = ()  # review agents activated when present (8d/8g)
    # §5 observability surface — REQUIRED, keyword-only. Forces every battery author to
    # declare obs intent; verified against the rendered template by tests/test_obs_completeness.py.
    #   "service"        -> a separate process/exporter: owes scrape + alert + dashboard + prod-wiring
    #   "in-process"     -> metrics on the app's own /metrics: owes alert + dashboard
    #   "rides-existing" -> no new §5 surface (postgres-extension, frontend-deferred, test harness)
    obs: ObsSurface = field(kw_only=True)
```

Then add `obs=...` to **every** battery in `_BATTERIES`:

```python
_BATTERIES: dict[str, BatterySpec] = {
    "webhooks": BatterySpec(
        "webhooks",
        "Signed inbound webhook ingress (HMAC) with an idempotent inbox",
        obs="in-process",
    ),
    "websockets": BatterySpec(
        "websockets",
        "FastAPI WebSocket routes + a connection manager",
        obs="in-process",
    ),
    "workers": BatterySpec(
        "workers",
        "Celery + Redis async task workers with a DB-backed dead-letter queue and beat scheduler",
        obs="service",
    ),
    "graphql": BatterySpec(
        "graphql",
        "Strawberry code-first GraphQL endpoint at /graphql over the demo Item model",
        gates_agents=("api-design",),
        obs="in-process",
    ),
    "pgvector": BatterySpec(
        "pgvector",
        "PostgreSQL pgvector extension + an embeddings table for vector similarity search",
        obs="rides-existing",
    ),
    "mongodb": BatterySpec(
        "mongodb",
        "MongoDB document store (pymongo) with a documents collection + full observability",
        obs="service",
    ),
    "timescaledb": BatterySpec(
        "timescaledb",
        "PostgreSQL TimescaleDB extension + a readings hypertable for time-series data",
        obs="rides-existing",
    ),
    "age": BatterySpec(
        "age",
        "Apache AGE openCypher graph queries on Postgres (no new service)",
        obs="rides-existing",
    ),
    "redis": BatterySpec(
        "redis",
        "Redis key/value datastore (cache/sessions) — shares the workers redis service when both are active",
        obs="service",
    ),
    "react": BatterySpec(
        "react",
        "React + TypeScript SPA served by FastAPI, with Vitest/Playwright/axe and accessibility/usability review",
        gates_agents=("accessibility", "usability"),
        obs="rides-existing",
    ),
    "consumers": BatterySpec(
        "consumers",
        "Pact consumer-driven contract testing (consumer + provider verification) for inter-service contracts",
        gates_agents=("contracts",),
        obs="rides-existing",
    ),
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_batteries.py -q && uv run mypy src`
Expected: PASS; mypy clean (mypy now enforces `obs=` at every `BatterySpec(...)` call site).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/batteries.py tests/test_batteries.py
git commit -m "feat(obs): required obs-surface declaration on BatterySpec"
```

(Commit-gate hook: stage `CLAUDE.md` only at Task 5 when state changes; this task touches no state pointer, so the hook does not fire on a non-`master` branch. If it does, stage `CLAUDE.md` separately.)

---

## Task 2: The render-diff obs-completeness invariant

**Files:**
- Create: `tests/test_obs_completeness.py`

- [ ] **Step 1: Write the invariant test**

Create `tests/test_obs_completeness.py`:

```python
import re
from pathlib import Path

import pytest
import yaml

from framework_cli.batteries import battery_names, get_battery
from framework_cli.copier_runner import render_project

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}

_ALERTS_DIR = Path("infra/observability/prometheus/alerts")
_DASHBOARDS_DIR = Path("infra/observability/grafana/dashboards")
_PROMETHEUS = Path("infra/observability/prometheus/prometheus.yml")
_SERVICES = Path("infra/compose/services.yml")
_OBSERVABILITY = Path("infra/compose/observability.yml")


def _alert_files(root: Path) -> set[str]:
    d = root / _ALERTS_DIR
    return {p.name for p in d.glob("*.yml")} if d.is_dir() else set()


def _dashboards(root: Path) -> set[str]:
    d = root / _DASHBOARDS_DIR
    return {p.name for p in d.glob("*.json")} if d.is_dir() else set()


def _scrape_jobs(root: Path) -> set[str]:
    text = (root / _PROMETHEUS).read_text()
    return set(re.findall(r"job_name:\s*(\S+)", text))


def _compose_services(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data = yaml.safe_load(path.read_text()) or {}
    return set((data.get("services") or {}).keys())


@pytest.fixture(scope="module")
def baseline(tmp_path_factory) -> Path:
    dest = tmp_path_factory.mktemp("obs-base") / "demo"
    render_project(dest, {**_BASE, "batteries": []})
    return dest


@pytest.mark.parametrize("name", battery_names())
def test_battery_obs_matches_declared_surface(
    name: str, baseline: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "demo"
    render_project(dest, {**_BASE, "batteries": [name]})

    new_alerts = _alert_files(dest) - _alert_files(baseline)
    new_dashboards = _dashboards(dest) - _dashboards(baseline)
    new_scrapes = _scrape_jobs(dest) - _scrape_jobs(baseline)
    new_prod_services = _compose_services(dest / _SERVICES) - _compose_services(
        baseline / _SERVICES
    )
    new_prod_exporters = _compose_services(dest / _OBSERVABILITY) - _compose_services(
        baseline / _OBSERVABILITY
    )

    obs = get_battery(name).obs
    if obs == "service":
        assert new_scrapes, f"{name}: a 'service' battery must add a Prometheus scrape job"
        assert new_alerts, f"{name}: a 'service' battery must add an alert-rule file"
        assert new_dashboards, f"{name}: a 'service' battery must add a Grafana dashboard"
        assert new_prod_services, (
            f"{name}: a 'service' battery must add its service to services.yml (prod-wiring)"
        )
        assert new_prod_exporters, (
            f"{name}: a 'service' battery must add its exporter to observability.yml (prod-wiring)"
        )
    elif obs == "in-process":
        assert new_alerts, f"{name}: an 'in-process' battery must add an alert-rule file"
        assert new_dashboards, f"{name}: an 'in-process' battery must add a Grafana dashboard"
        assert not new_scrapes, f"{name}: an 'in-process' battery must not add a scrape job"
        assert not new_prod_services, (
            f"{name}: an 'in-process' battery must not add a prod service"
        )
        assert not new_prod_exporters, (
            f"{name}: an 'in-process' battery must not add a prod exporter"
        )
    else:  # rides-existing
        assert not (
            new_alerts
            or new_dashboards
            or new_scrapes
            or new_prod_services
            or new_prod_exporters
        ), (
            f"{name}: a 'rides-existing' battery must add no new observability artifacts; got "
            f"alerts={new_alerts} dashboards={new_dashboards} scrapes={new_scrapes} "
            f"services={new_prod_services} exporters={new_prod_exporters}"
        )
```

- [ ] **Step 2: Run the test to verify it passes (the contract is already honored)**

Run: `uv run pytest tests/test_obs_completeness.py -q`
Expected: PASS — all 11 batteries' rendered obs match their declarations.

- [ ] **Step 3: Prove the test is not vacuous (mutation check, NOT committed)**

Temporarily edit `src/framework_cli/batteries.py` to mis-declare `mongodb` as `obs="rides-existing"`, then run:

Run: `uv run pytest tests/test_obs_completeness.py -q -k mongodb`
Expected: FAIL — "a 'rides-existing' battery must add no new observability artifacts; got … services={'mongo'} …".

Then **revert** the edit:

Run: `git checkout src/framework_cli/batteries.py`
Run: `uv run pytest tests/test_obs_completeness.py -q -k mongodb`
Expected: PASS again.

- [ ] **Step 4: Commit**

```bash
git add tests/test_obs_completeness.py
git commit -m "test(obs): render-diff invariant enforces declared obs surface per battery"
```

---

## Task 3: `review-observability-infra` agent

**Files:**
- Create: `src/framework_cli/review/agents/observability-infra.md`
- Modify: `src/framework_cli/review/registry.py`
- Modify: `tests/review/test_registry.py`
- Create: `tests/eval/fixtures/observability-infra/bad/{new-service-no-scrape,scrape-without-alert,exporter-dev-only}.{diff,expect.json}`
- Create: `tests/eval/fixtures/observability-infra/good/tune-existing-alert.diff`

- [ ] **Step 1: Write the failing registry tests**

In `tests/review/test_registry.py`, add **only** `observability-infra` to `_EXPECTED_PR` (file-trigger agents are in the PR base set); `observability-db` is added in Task 4 when it is registered — add them incrementally so `test_full_active_sets` stays green per task. Replace the `_EXPECTED_PR` list:

```python
_EXPECTED_PR = sorted(
    [
        "security",
        "data-integrity",
        "data-lineage",
        "application-logic",
        "observability",
        "observability-infra",
        "test-quality",
        "architecture",
        "performance",
        "compliance",
        "privacy",
        "documentation",
        "dependency",
    ]
)
```

Add this test:

```python
def test_observability_split_infra():
    from framework_cli.review.registry import active_agents, get_agent

    spec = get_agent("observability-infra")
    assert spec.name == "review-observability-infra"
    assert spec.block_threshold == "high"
    assert spec.active_when == "file-trigger"
    assert spec.trigger_globs and "infra/*" in spec.trigger_globs
    # file-trigger agents are PR candidates; gated at runtime by the diff's changed files.
    assert "observability-infra" in active_agents("pull_request")
    # not on push (file-trigger, on_push defaults False) — keeps the curated push subset.
    assert "observability-infra" not in active_agents("push")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/review/test_registry.py -q`
Expected: FAIL — `get_agent("observability-infra")` raises `KeyError`; `_EXPECTED_PR` mismatch; `test_every_registered_agent_has_fixtures` (in `tests/review/test_evals.py`) not yet failing because the agent isn't registered.

- [ ] **Step 3: Write the prompt**

Create `src/framework_cli/review/agents/observability-infra.md`:

```markdown
You are `review-observability-infra`. Review ONLY the unified diff of infrastructure files
(Docker Compose, Prometheus, Grafana, Alertmanager). Flag: a new Compose service or Prometheus
scrape job with no matching alert rule and dashboard; an alert rule with no dashboard panel (or a
panel with no alert) for the same surface; observability defined only for dev (e.g. added to
`dev.yml`) that never reaches prod (`services.yml` / `observability.yml`); a scrape target with no
corresponding exporter; a missing or unroutable Alertmanager receiver. Also flag a co-located
single-host obs stack that is clearly outgrowing one host (note it, do not block). Cite the changed
line. Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none.
A new prod runtime surface with no observability is "high".
```

- [ ] **Step 4: Register the agent**

In `src/framework_cli/review/registry.py`, add to `_SPECS` (after the `observability` entry):

```python
    "observability-infra": AgentSpec(
        "review-observability-infra",
        _prompt("observability-infra"),
        "high",
        "file-trigger",
        DEFAULT_MODEL,
        trigger_globs=("infra/*",),
    ),
```

(`fnmatch`'s `*` spans `/`, so `infra/*` matches every Compose/Prometheus/Grafana/Alertmanager file under `infra/` in a rendered project's diff.)

- [ ] **Step 5: Add eval fixtures**

Create `tests/eval/fixtures/observability-infra/bad/new-service-no-scrape.diff`:

```diff
--- a/infra/compose/services.yml
+++ b/infra/compose/services.yml
@@ -20,3 +20,9 @@ services:
   redis:
     image: redis:7
     restart: unless-stopped
+  search:
+    image: opensearchproject/opensearch:2
+    restart: unless-stopped
+    environment:
+      - discovery.type=single-node
+    volumes:
+      - searchdata:/usr/share/opensearch/data
```

Create `tests/eval/fixtures/observability-infra/bad/new-service-no-scrape.expect.json`:

```json
{"file": "infra/compose/services.yml"}
```

Create `tests/eval/fixtures/observability-infra/bad/scrape-without-alert.diff`:

```diff
--- a/infra/observability/prometheus/prometheus.yml
+++ b/infra/observability/prometheus/prometheus.yml
@@ -30,3 +30,6 @@ scrape_configs:
   - job_name: redis
     static_configs:
       - targets: ["redis-exporter:9121"]
+  - job_name: search
+    static_configs:
+      - targets: ["search-exporter:9114"]
```

Create `tests/eval/fixtures/observability-infra/bad/scrape-without-alert.expect.json`:

```json
{"file": "infra/observability/prometheus/prometheus.yml"}
```

Create `tests/eval/fixtures/observability-infra/bad/exporter-dev-only.diff`:

```diff
--- a/infra/compose/dev.yml
+++ b/infra/compose/dev.yml
@@ -40,3 +40,7 @@ services:
   redis:
     image: redis:7
+  search-exporter:
+    image: prometheuscommunity/opensearch-exporter:latest
+    command: ["--es.uri=http://search:9200"]
+    restart: unless-stopped
```

Create `tests/eval/fixtures/observability-infra/bad/exporter-dev-only.expect.json`:

```json
{"file": "infra/compose/dev.yml"}
```

Create `tests/eval/fixtures/observability-infra/good/tune-existing-alert.diff`:

```diff
--- a/infra/observability/prometheus/alerts/postgres_alerts.yml
+++ b/infra/observability/prometheus/alerts/postgres_alerts.yml
@@ -5,6 +5,6 @@ groups:
       - alert: PostgresDown
         expr: up{job="postgres"} == 0
-        for: 1m
+        for: 2m
         labels:
           severity: critical
```

(Good fixtures have no `.expect.json` sidecar — a benign threshold tune with no obs gap; the agent should return `[]`.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/review/test_registry.py tests/review/test_evals.py -q`
Expected: PASS — registry tests green; `test_every_registered_agent_has_fixtures` satisfied for `observability-infra` (3 bad ≥ 2, 1 good ≥ 1); `test_fixtures_are_wellformed` green (each bad fixture's `seeded_file` is among its diff's changed paths).

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/review/agents/observability-infra.md src/framework_cli/review/registry.py tests/review/test_registry.py tests/eval/fixtures/observability-infra
git commit -m "feat(review): review-observability-infra agent (file-trigger on infra/, blocking-high)"
```

---

## Task 4: `review-observability-db` agent

**Files:**
- Create: `src/framework_cli/review/agents/observability-db.md`
- Modify: `src/framework_cli/review/registry.py`
- Modify: `tests/review/test_registry.py`
- Create: `tests/eval/fixtures/observability-db/bad/{query-no-metric,mongo-find-no-metric,cache-client-no-health}.{diff,expect.json}`
- Create: `tests/eval/fixtures/observability-db/good/query-with-span.diff`

- [ ] **Step 1: Write the failing registry test**

In `tests/review/test_registry.py`, add `"observability-db"` to the `_EXPECTED_PR` list (it becomes registered in this task), keeping the list sorted via the `sorted(...)` wrapper. Then add:

```python
def test_observability_split_db():
    from framework_cli.review.registry import active_agents, get_agent

    spec = get_agent("observability-db")
    assert spec.name == "review-observability-db"
    assert spec.block_threshold == "high"
    assert spec.active_when == "file-trigger"
    # data-layer globs, NOT battery-gated (baseline always ships postgres).
    assert spec.trigger_globs and "*/db/*" in spec.trigger_globs
    assert "observability-db" in active_agents("pull_request")
    assert "observability-db" not in active_agents("push")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/review/test_registry.py::test_observability_split_db -q`
Expected: FAIL — `get_agent("observability-db")` raises `KeyError`.

- [ ] **Step 3: Write the prompt**

Create `src/framework_cli/review/agents/observability-db.md`:

```markdown
You are `review-observability-db`. Review ONLY the unified diff of data-access code (repositories,
models, migrations, query paths, datastore clients in `db/`, `vectors/`, `mongo/`, `cache/`,
`timeseries/`, `graph/`). Flag: a new data-store query or write path with no metric or span around
it; an unbounded query (no limit/pagination) with no latency or row-count metric; a datastore
client or connection with no `/health` signal; a new store whose errors are not logged with the
correlation id. Cite the changed line. Return JSON ONLY — an array of
{"path","line","severity","message","suggestion"}; [] if none. A new datastore access path with no
observability is "high".
```

- [ ] **Step 4: Register the agent**

In `src/framework_cli/review/registry.py`, add to `_SPECS` (after the `observability-infra` entry):

```python
    "observability-db": AgentSpec(
        "review-observability-db",
        _prompt("observability-db"),
        "high",
        "file-trigger",
        DEFAULT_MODEL,
        trigger_globs=(
            "*/db/*",
            "*/vectors/*",
            "*/mongo/*",
            "*/cache/*",
            "*/timeseries/*",
            "*/graph/*",
            "migrations/*",
        ),
    ),
```

- [ ] **Step 5: Add eval fixtures**

Create `tests/eval/fixtures/observability-db/bad/query-no-metric.diff`:

```diff
--- a/src/myapp/db/repository.py
+++ b/src/myapp/db/repository.py
@@ -10,3 +10,7 @@ def list_items(session: Session) -> list[Item]:
     return list(session.scalars(select(Item)).all())
+
+
+def search_items(session: Session, term: str) -> list[Item]:
+    stmt = select(Item).where(Item.name.ilike(f"%{term}%"))
+    return list(session.scalars(stmt).all())
```

Create `tests/eval/fixtures/observability-db/bad/query-no-metric.expect.json`:

```json
{"file": "src/myapp/db/repository.py"}
```

Create `tests/eval/fixtures/observability-db/bad/mongo-find-no-metric.diff`:

```diff
--- a/src/myapp/mongo/repository.py
+++ b/src/myapp/mongo/repository.py
@@ -8,3 +8,6 @@ def insert_document(db, doc: dict) -> str:
     return str(db.documents.insert_one(doc).inserted_id)
+
+
+def find_documents(db, query: dict) -> list[dict]:
+    return list(db.documents.find(query))
```

Create `tests/eval/fixtures/observability-db/bad/mongo-find-no-metric.expect.json`:

```json
{"file": "src/myapp/mongo/repository.py"}
```

Create `tests/eval/fixtures/observability-db/bad/cache-client-no-health.diff`:

```diff
--- a/src/myapp/cache/client.py
+++ b/src/myapp/cache/client.py
@@ -3,3 +3,8 @@ import redis
 
 def get_redis(url: str) -> redis.Redis:
     return redis.Redis.from_url(url)
+
+
+def get_session_store(url: str) -> redis.Redis:
+    # second logical DB for sessions; no health probe or metric wired
+    return redis.Redis.from_url(url, db=4)
```

Create `tests/eval/fixtures/observability-db/bad/cache-client-no-health.expect.json`:

```json
{"file": "src/myapp/cache/client.py"}
```

Create `tests/eval/fixtures/observability-db/good/query-with-span.diff`:

```diff
--- a/src/myapp/db/repository.py
+++ b/src/myapp/db/repository.py
@@ -10,3 +10,9 @@ def list_items(session: Session) -> list[Item]:
     return list(session.scalars(select(Item)).all())
+
+
+def count_items(session: Session) -> int:
+    with tracer.start_as_current_span("db.count_items"):
+        return session.scalar(select(func.count()).select_from(Item)) or 0
```

(Good fixture: a new query path that IS instrumented with a span — no obs gap; the agent should return `[]`. No `.expect.json` sidecar.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/review/test_registry.py tests/review/test_evals.py -q`
Expected: PASS — both new agents registered, `_EXPECTED_PR` matches, fixture-coverage + well-formedness gates green.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/review/agents/observability-db.md src/framework_cli/review/registry.py tests/review/test_registry.py tests/eval/fixtures/observability-db
git commit -m "feat(review): review-observability-db agent (file-trigger on data layer, blocking-high)"
```

---

## Task 5: Synthetic-fixture fixups, full gate, and state

**Files:**
- Modify: `tests/review/test_registry.py` (synthetic `BatterySpec` constructions)
- Modify: `tests/test_batteries.py` (synthetic `_child` construction, if not already fixed)
- Modify: `CLAUDE.md`, `docs/superpowers/plans/2026-05-20-meta-plan.md`

- [ ] **Step 1: Fix synthetic `BatterySpec` constructions**

The required `obs` field breaks any in-test `BatterySpec(...)` that omits it. Add `obs="rides-existing"` to each. In `tests/review/test_registry.py`:

- `test_active_agents_adds_gated_agent_when_battery_present`: the two `bat.BatterySpec("_demo", "x", gates_agents=...)` / `("_demo2", "x", gates_agents=...)` calls → add `, obs="rides-existing"`.
- `test_active_agents_battery_can_gate_multiple`: the `bat.BatterySpec("_multi", "x", gates_agents=(...))` call → add `, obs="rides-existing"`.

In `tests/test_batteries.py`:

- `test_resolve_includes_dependency_closure`: the `batteries.BatterySpec("_child", ...)` call → add `, obs="rides-existing"`.

(Grep to be sure none are missed: `rg 'BatterySpec\(' tests/` — every hit must pass `obs=`.)

- [ ] **Step 2: Run the targeted suites to verify green**

Run: `uv run pytest tests/test_batteries.py tests/review -q`
Expected: PASS.

- [ ] **Step 3: Run the full framework gate**

Run:
```bash
uv run pytest -q --ignore=tests/acceptance
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run framework integrity --ci || true   # confirm no baseline manifest shift expectation
```
Expected: all green. (The `obs` field + new agents are framework-side only — no template payload changed — so the integrity manifest is unchanged. If `framework integrity --ci` is not the exact invocation, use the project's documented integrity check; the point is to confirm **no baseline manifest shift**.)

Confirm no manifest shift explicitly:

Run: `git status --porcelain` (after a render-integrity check) — Expected: no changes to `manifest`/`LOCKED` baseline files.

- [ ] **Step 4: Update state + roadmap**

In `docs/superpowers/plans/2026-05-20-meta-plan.md`, add a status row for the obs-completeness slice (between Plan 8 and Plan 9 chronologically, or as a sub-slice — match the surrounding table format), marked `✅ Done` with this plan's path and the merge SHA (filled at merge).

In `CLAUDE.md`, update the **Current State** pointer: the obs-completeness slice is now **implemented + merged** (Facet 1 invariant live, Facet 2 infra+db reviewers authored, real-key scoring still pending Plan 11), and update **Last updated** to a datetime with timezone.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-05-20-meta-plan.md tests/review/test_registry.py tests/test_batteries.py
git commit -m "test(obs): fix synthetic BatterySpec constructions; state + roadmap"
```

(Stage `CLAUDE.md` as its own `git add` before the commit per the commit-gate hook; keep "commit" out of any Bash description.)

---

## Notes for the implementer

- **No real Anthropic key is used or needed.** The two new agents are authored only — their thresholds default (no `thresholds.yaml` entry) and real-key scoring is **deferred to Plan 11** (identical to `review-contracts`). Do not attempt to score them.
- **`fe` is intentionally skipped** — there is no frontend-obs surface yet (React ships zero telemetry). Do not add a `review-observability-fe` agent.
- **Facet 3 (obs-infra-scaling) is out of scope** — deferred to the Plan 12 docs pack. The infra prompt carries a soft, non-blocking note about it; that is the extent of it here.
- The acceptance tier (`tests/acceptance`) is **not** required for this slice (no Docker behavior changes); keep `--ignore=tests/acceptance` to avoid the `/tmp` wedge. The Plan 9 host-UID hygiene fix is in place but still avoid the full tier in-session.
```
