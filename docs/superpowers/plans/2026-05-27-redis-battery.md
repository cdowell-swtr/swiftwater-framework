# 8f Slice 2b — `redis` DB-Paradigm Battery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `redis` database-paradigm battery (redis as an app-level KV datastore) that shares the workers battery's redis service and monitors it whenever it exists.

**Architecture:** Restructure the workers compose blocks so the `redis` service (and `redis_url` setting + `redisdata` volume) is gated `workers OR redis` (defined once), while `worker`/`beat` stay `workers`-only. Add a `cache/` package (a `redis.Redis` client on a dedicated logical DB `/3` + a KV repo), a `/health` ping, and a redis-exporter + scrape + alert + dashboard gated `workers OR redis`. No migration (redis is schemaless).

**Tech Stack:** Copier/Jinja templates, Docker/Compose, Redis 7, `redis` Python client, Prometheus/Grafana (`oliver006/redis_exporter`), testcontainers, pytest.

**Spec:** `docs/superpowers/specs/2026-05-27-redis-battery-design.md`

**Conventions (read before starting):**
- `src/framework_cli/template/` is **template payload**, not framework source — don't lint/type-check it as framework code. Validated by rendering (`tests/test_copier_runner.py`) + exercising the rendered project (`tests/acceptance/test_rendered_project.py`).
- Framework fast gate (green before each commit): `uv run --frozen pytest -q --ignore=tests/acceptance && uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen mypy src`.
- **⚠ /tmp HAZARD:** the Docker `tests/acceptance` tier renders into `/tmp` as root and can fill it, wedging the sandbox. Do NOT run the full acceptance suite; run AT MOST the one named acceptance test per task and `rm -rf /tmp/pytest-of-chris/* 2>/dev/null` + `df -h /tmp` after. `docker compose config` (no containers) is the safe merge-validation.
- **COMMIT-GATE HOOK:** `git commit` is blocked unless `CLAUDE.md` is staged. The hook greps the **entire tool-input JSON including your Bash `description`** — so NEVER put the literal word c-o-m-m-i-t in a description or anywhere in a git command except the actual `git commit`. Use SEPARATE `git add` then `git commit` Bash calls (combining them trips the hook because it fires before `add` runs). For each task's commit: edit the `CLAUDE.md` `- **Last updated:**` line's marker (e.g. to `[redis Tn]`) and stage it with your changes.
- `render_project(dest, {**DATA, "batteries": [...]})` where `DATA = {"project_name":"Demo","project_slug":"demo","package_name":"demo","python_version":"3.12"}` (top of `tests/test_copier_runner.py`).
- Integrity test shape (match existing `test_integrity_*`): `from framework_cli.integrity.checker import check`; `from framework_cli.integrity.manifest import write_manifest`; `from framework_cli.source import installed_framework_version`; render → `write_manifest(dest, installed_framework_version())` → `check(dest, ci=True) == []`.

---

## File Structure

**Framework CLI (`src/framework_cli/`):**
- `batteries.py` — register `redis` (`requires=()`). No `migrations.py` change (schemaless). No `LOCKED_TRACKED` change.

**Template payload (`src/framework_cli/template/`):**
- Modify: `infra/compose/dev.yml.jinja`, `infra/compose/services.yml.jinja` — split the redis service to `workers OR redis`; broaden the `redisdata` volume gate; (services.yml) broaden the outer gate.
- Modify: `config/settings.py.jinja` — hoist `redis_url` to `workers OR redis`.
- Modify: `infra/compose/observability.yml.jinja` — add `redis-exporter` (`workers OR redis`).
- Modify: `infra/observability/prometheus/prometheus.yml.jinja` — add the `redis` scrape (`workers OR redis`).
- Modify: `routes/health.py.jinja` — add a redis ping (`redis`-only).
- Modify: `pyproject.toml.jinja` — conditional `redis` + `testcontainers[redis]`.
- Create: `src/{{package_name}}/{% if "redis" in batteries %}cache{% endif %}/{__init__.py,client.py,repository.py}`.
- Create: `tests/functional/{{ 'test_cache.py' if 'redis' in batteries else '' }}.jinja`.
- Create: `infra/observability/prometheus/alerts/{{ 'redis_alerts.yml' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja`.
- Create: `infra/observability/grafana/dashboards/{{ 'redis.json' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja`.

**Framework tests:** `tests/test_copier_runner.py`, `tests/test_batteries.py`, `tests/acceptance/test_rendered_project.py`.

---

## Task 1: Shared redis service + hoisted `redis_url` + registration (the overlap fix)

**Files:**
- Modify: `src/framework_cli/template/infra/compose/dev.yml.jinja` (lines 91–157)
- Modify: `src/framework_cli/template/infra/compose/services.yml.jinja` (lines 6, 21–67, 73)
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja` (the workers block, ~lines 35–41)
- Modify: `src/framework_cli/batteries.py`
- Test: `tests/test_copier_runner.py`, `tests/test_batteries.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_copier_runner.py`:
```python
def test_redis_service_shared_by_workers_or_redis(tmp_path):
    # redis service is defined exactly once whether workers, redis, or both — and worker/beat
    # only appear for workers.
    for bats, want_redis, want_worker in [
        ([], False, False),
        (["redis"], True, False),
        (["workers"], True, True),
        (["workers", "redis"], True, True),
    ]:
        d = tmp_path / ("_".join(bats) or "base")
        render_project(d, {**DATA, "batteries": bats})
        dev = (d / "infra" / "compose" / "dev.yml").read_text()
        assert dev.count("\n  redis:\n") == (1 if want_redis else 0), (bats, "redis svc count")
        assert ("\n  worker:\n" in dev) == want_worker, (bats, "worker presence")
        settings = (d / "src" / "demo" / "config" / "settings.py").read_text()
        assert settings.count("redis_url:") == (1 if want_redis else 0), (bats, "redis_url count")


def test_redis_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "redis" in battery_names()
    assert get_battery("redis").requires == ()
    assert resolve(["redis"]) == ["redis"]
```
(`test_redis_battery_registered` also belongs in `tests/test_batteries.py` — add it there too, matching the existing `test_<battery>_battery_registered` style.)

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_redis_service_shared_by_workers_or_redis tests/test_copier_runner.py::test_redis_battery_registered -q`
Expected: FAIL (`redis` unknown → `resolve` raises; redis service only renders for workers).

- [ ] **Step 3: Register the battery**

In `src/framework_cli/batteries.py`, add to `_BATTERIES` (after `mongodb`/`timescaledb`/`age`):
```python
    "redis": BatterySpec(
        "redis",
        "Redis key/value datastore (cache/sessions) — shares the workers redis service when both are active",
    ),
```

- [ ] **Step 4: Split the redis service in `dev.yml.jinja`**

Replace lines 91–151 (the single `{%- if "workers" in batteries %}` block wrapping redis + worker + beat) so redis is gated `workers OR redis` and worker/beat stay `workers`:
```jinja
{%- if "workers" in batteries or "redis" in batteries %}

  redis:
    image: redis:7-alpine
    profiles: ["dev", "lite"]
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - "redisdata:/data"
{%- endif %}
{%- if "workers" in batteries %}

  worker:
    build:
      context: ../..
      dockerfile: infra/docker/Dockerfile
    profiles: ["dev"]
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "worker", "--loglevel=info"]
    environment:
      # Only the app/migrate step runs migrations — workers share entrypoint.sh, so disable
      # its alembic-upgrade to avoid concurrent `upgrade head` racing the app on startup.
      APP_RUN_MIGRATIONS: "false"
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
      APP_DATABASE_URL: "postgresql+psycopg://app:app@postgres:5432/app"
    volumes:
      - ../../src:/app/src
    healthcheck:
      test: ["CMD", "celery", "-A", "{{ package_name }}.tasks.app", "inspect", "ping"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 20s
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy

  beat:
    build:
      context: ../..
      dockerfile: infra/docker/Dockerfile
    profiles: ["dev"]
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "beat", "--loglevel=info"]
    environment:
      APP_RUN_MIGRATIONS: "false"  # shares entrypoint.sh; don't let beat run migrations
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
    volumes:
      - ../../src:/app/src
    depends_on:
      redis:
        condition: service_healthy

{%- endif %}
```
Then broaden the `redisdata` volume line (currently line 156): change `{% endif %}{% if "workers" in batteries %}  redisdata: {}` to `{% endif %}{% if "workers" in batteries or "redis" in batteries %}  redisdata: {}`.

- [ ] **Step 5: Split the redis service in `services.yml.jinja`**

Broaden the outer gate (line 6) to include redis:
```jinja
{%- if "mongodb" in batteries or "workers" in batteries or "redis" in batteries %}
```
Replace the `{%- if "workers" in batteries %}` block (lines 21–67, wrapping redis + worker + beat) so redis is `workers OR redis`, worker/beat stay `workers`:
```jinja
{%- if "workers" in batteries or "redis" in batteries %}
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - "redisdata:/data"
{%- endif %}
{%- if "workers" in batteries %}

  worker:
    image: ${APP_IMAGE:?set APP_IMAGE to the promoted registry tag}
    restart: unless-stopped
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "worker", "--loglevel=info"]
    environment:
      APP_RUN_MIGRATIONS: "false"
      APP_DATABASE_URL: "postgresql+psycopg://app:${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}@postgres:5432/app"
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
    healthcheck:
      test: ["CMD", "celery", "-A", "{{ package_name }}.tasks.app", "inspect", "ping"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 20s
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy

  beat:
    image: ${APP_IMAGE:?set APP_IMAGE to the promoted registry tag}
    restart: unless-stopped
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "beat", "--loglevel=info"]
    environment:
      APP_RUN_MIGRATIONS: "false"
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
    depends_on:
      redis:
        condition: service_healthy
{%- endif %}
```
Broaden the `redisdata` volume gate (lines 73–75): `{%- if "workers" in batteries %}` → `{%- if "workers" in batteries or "redis" in batteries %}`.

- [ ] **Step 6: Hoist `redis_url` in `settings.py.jinja`**

The workers block is currently:
```jinja
{%- if "workers" in batteries %}

    # Celery workers (Redis broker + result backend).
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
{%- endif %}
```
Replace it with a shared `redis_url` block + a workers-only celery block:
```jinja
{%- if "workers" in batteries or "redis" in batteries %}

    # Redis connection (shared by the workers broker and the redis datastore battery).
    redis_url: str = "redis://redis:6379/0"
{%- endif %}
{%- if "workers" in batteries %}

    # Celery workers (broker + result backend).
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/1"
{%- endif %}
```

- [ ] **Step 7: Run the tests → PASS**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_redis_service_shared_by_workers_or_redis tests/test_copier_runner.py::test_redis_battery_registered tests/test_batteries.py -q`
Then render `[workers]`, `[redis]`, `[workers,redis]`, `[]` and confirm each `dev.yml`/`services.yml` is valid YAML (`docker compose -f infra/compose/dev.yml --profile dev config` exit 0, or `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))"`), and that `[]` renders byte-identical (no redis).

- [ ] **Step 8: Fast gate + commit**

Run the fast gate. Stage the 4 changed files + tests + a `CLAUDE.md` `[redis T1]` marker edit; `git commit -m "feat(db): share the redis service (workers OR redis) + hoist redis_url + register redis battery"`.

---

## Task 2: `cache/` package + `/health` ping + deps

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "redis" in batteries %}cache{% endif %}/{__init__.py,client.py,repository.py}`
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja` (after the mongodb block, ~line 46)
- Modify: `src/framework_cli/template/pyproject.toml.jinja` (deps + dev-deps)
- Create: `src/framework_cli/template/tests/functional/{{ 'test_cache.py' if 'redis' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:
```python
def test_render_redis_cache_package(tmp_path):
    dest = tmp_path / "r"
    render_project(dest, {**DATA, "batteries": ["redis"]})
    assert (dest / "src" / "demo" / "cache" / "client.py").exists()
    repo = (dest / "src" / "demo" / "cache" / "repository.py").read_text()
    assert "cache_set" in repo and "cache_get" in repo and "cache_delete" in repo
    health = (dest / "src" / "demo" / "routes" / "health.py").read_text()
    assert "redis" in health and "ping" in health
    pyproject = (dest / "pyproject.toml").read_text()
    assert "redis>=5" in pyproject and "testcontainers[redis]" in pyproject
    assert (dest / "tests" / "functional" / "test_cache.py").exists()
    # baseline omits all of it
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert not (base / "src" / "demo" / "cache").exists()
```

- [ ] **Step 2: Run it → FAIL**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_render_redis_cache_package -q`

- [ ] **Step 3: Create the cache package**

`.../cache/__init__.py` (empty).

`.../cache/client.py`:
```python
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from redis import Redis

from ..config.settings import get_settings

# Dedicated logical DB for the app cache keyspace — kept separate from Celery's broker (/0)
# and result backend (/1) so a cache flush never touches Celery state.
_CACHE_DB = 3


@lru_cache
def get_redis() -> Redis:
    # redis-py honors the DB in the URL path over a db= kwarg, so substitute the path
    # explicitly to land on the dedicated cache DB regardless of how redis_url is written.
    parts = urlparse(get_settings().redis_url)
    url = urlunparse(parts._replace(path=f"/{_CACHE_DB}"))
    return Redis.from_url(url, decode_responses=True)
```

`.../cache/repository.py` (the repo takes the client as a param — mirrors `mongo/repository.py` taking the `db`, so the functional test can inject a testcontainer-backed client):
```python
from redis import Redis


def cache_set(client: Redis, key: str, value: str, ttl_seconds: int | None = None) -> None:
    client.set(key, value, ex=ttl_seconds)


def cache_get(client: Redis, key: str) -> str | None:
    return client.get(key)


def cache_delete(client: Redis, key: str) -> None:
    client.delete(key)
```

- [ ] **Step 4: Add the `/health` ping**

In `health.py.jinja`, after the mongodb block (after ~line 46), add:
```jinja
{% if "redis" in batteries %}
    from {{ package_name }}.cache.client import get_redis as _redis

    try:
        _redis().ping()
        report["redis"] = {"alive": True}
    except Exception:  # redis unreachable — degrade, never 500 the probe
        report["redis"] = {"alive": False}
{% endif %}
```

- [ ] **Step 5: Add the dependencies**

In `pyproject.toml.jinja`, in the `dependencies` array (after the mongodb line, before the closing `{% endif %}]`):
```jinja
{% if "redis" in batteries %}    "redis>=5",
{% endif %}
```
(When `workers` is also present, `celery[redis]` already pulls redis-py; an explicit `redis>=5` line alongside it is valid and `uv` resolves the overlap — verify with `uv sync` in the `[workers,redis]` acceptance check in Task 4.)
In the `dev` dependency-group (after the `testcontainers[mongodb]` line):
```jinja
{% if "redis" in batteries %}    "testcontainers[redis]>=4.8",
{% endif %}
```

- [ ] **Step 6: Create the functional test**

`tests/functional/{{ 'test_cache.py' if 'redis' in batteries else '' }}.jinja`:
```python
import pytest


@pytest.fixture(scope="module")
def redis_client():
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        from redis import Redis

        client = Redis(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(6379)),
            db=3,
            decode_responses=True,
        )
        yield client


def test_set_get_delete_with_ttl(redis_client):
    from {{ package_name }}.cache.repository import cache_delete, cache_get, cache_set

    cache_set(redis_client, "k", "v", ttl_seconds=60)
    assert cache_get(redis_client, "k") == "v"
    assert redis_client.ttl("k") > 0  # TTL applied
    cache_delete(redis_client, "k")
    assert cache_get(redis_client, "k") is None
```
(Verify the `testcontainers.redis.RedisContainer` API in the installed testcontainers version: `RedisContainer("redis:7-alpine")`, `get_container_host_ip()`, `get_exposed_port(6379)`. Adjust if the accessors differ.)

- [ ] **Step 7: Run the render test → PASS**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_render_redis_cache_package -q`

- [ ] **Step 8: Fast gate + commit**

Fast gate. Stage cache package + health/pyproject + functional test + `CLAUDE.md` `[redis T2]` marker; `git commit -m "feat(db): redis cache package (KV repo on a dedicated DB) + /health ping + deps"`.

---

## Task 3: Redis observability (exporter + scrape + alert + dashboard, `workers OR redis`)

**Files:**
- Modify: `src/framework_cli/template/infra/compose/observability.yml.jinja` (after the celery-exporter block)
- Modify: `src/framework_cli/template/infra/observability/prometheus/prometheus.yml.jinja` (after the mongodb scrape)
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/{{ 'redis_alerts.yml' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja`
- Create: `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'redis.json' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_copier_runner.py`:
```python
def test_render_redis_observability(tmp_path):
    for bats in (["redis"], ["workers"], ["workers", "redis"]):
        d = tmp_path / "_".join(bats)
        render_project(d, {**DATA, "batteries": bats})
        obs = (d / "infra" / "compose" / "observability.yml").read_text()
        assert obs.count("\n  redis-exporter:\n") == 1, (bats, "one redis-exporter")
        prom = (d / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
        assert "job_name: redis" in prom
        assert (d / "infra" / "observability" / "prometheus" / "alerts" / "redis_alerts.yml").exists()
        assert (d / "infra" / "observability" / "grafana" / "dashboards" / "redis.json").exists()
    # baseline omits redis obs
    base = tmp_path / "base"
    render_project(base, {**DATA, "batteries": []})
    assert "redis-exporter" not in (base / "infra" / "compose" / "observability.yml").read_text()
    assert "job_name: redis" not in (base / "infra" / "observability" / "prometheus" / "prometheus.yml").read_text()
```

- [ ] **Step 2: Run it → FAIL**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_render_redis_observability -q`

- [ ] **Step 3: Add the exporter**

In `observability.yml.jinja`, after the celery-exporter block (the `{%- if "workers" in batteries %}celery-exporter…{%- endif %}` block), add:
```jinja
{%- if "redis" in batteries or "workers" in batteries %}

  redis-exporter:
    image: oliver006/redis_exporter:v1.62.0
    command: ["--redis.addr=redis://redis:6379"]
    ports:
      - "9121:9121"
    depends_on:
      redis:
        condition: service_healthy
{%- endif %}
```
(Pin: confirm `oliver006/redis_exporter:v1.62.0` exists / pull-able and exposes `/metrics` on `9121` during Step 7; adjust the tag if needed.)

- [ ] **Step 4: Add the scrape job**

In `prometheus.yml.jinja`, after the mongodb scrape block, add:
```jinja
{%- if "redis" in batteries or "workers" in batteries %}
  - job_name: redis
    static_configs:
      - targets: ["redis-exporter:9121"]
{%- endif %}
```

- [ ] **Step 5: Create the alert rules**

`.../alerts/{{ 'redis_alerts.yml' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja`:
```yaml
groups:
- name: redis
  rules:
  - alert: RedisExporterDown
    expr: up{job="redis"} == 0
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: Redis exporter target is down (redis unreachable or exporter crashed) — app-specific default; tune or remove
  - alert: RedisHighMemory
    expr: redis_memory_max_bytes > 0 and (redis_memory_used_bytes / redis_memory_max_bytes) > 0.9
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: Redis memory usage above 90% of maxmemory — app-specific default; tune the threshold or set maxmemory
```
(The `redis_memory_max_bytes > 0` guard avoids a divide-by-zero when `maxmemory` is unset/0 = unlimited. Confirm the metric names against the exporter output in Step 7.)

- [ ] **Step 6: Create the dashboard**

`.../dashboards/{{ 'redis.json' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja` — mirror the `mongodb.json` envelope (uid/title/tags/schemaVersion 39/version/time/panels with the same datasource shape):
```json
{
  "uid": "redis",
  "title": "Redis",
  "tags": [
    "redis"
  ],
  "schemaVersion": 39,
  "version": 1,
  "time": {
    "from": "now-1h",
    "to": "now"
  },
  "panels": [
    {
      "id": 1,
      "title": "Redis exporter up",
      "type": "stat",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 0,
        "y": 0
      },
      "targets": [
        {
          "refId": "A",
          "expr": "up{job=\"redis\"}",
          "legendFormat": "up"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "red",
                "value": null
              },
              {
                "color": "green",
                "value": 1
              }
            ]
          }
        },
        "overrides": []
      }
    },
    {
      "id": 2,
      "title": "Memory used",
      "type": "timeseries",
      "datasource": {
        "type": "prometheus",
        "uid": "prometheus"
      },
      "gridPos": {
        "h": 8,
        "w": 18,
        "x": 6,
        "y": 0
      },
      "targets": [
        {
          "refId": "A",
          "expr": "redis_memory_used_bytes",
          "legendFormat": "used"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "bytes"
        },
        "overrides": []
      }
    },
    {
      "id": 3,
      "title": "Connected clients",
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
          "expr": "redis_connected_clients",
          "legendFormat": "clients"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short"
        },
        "overrides": []
      }
    }
  ]
}
```

- [ ] **Step 7: Render test → PASS + `docker compose config` + verify exporter**

Run: `uv run --frozen pytest tests/test_copier_runner.py::test_render_redis_observability -q`
Render `[redis]` and `[workers,redis]`; from each root:
```bash
docker compose -f infra/compose/dev.yml --profile dev config        # one redis service + redis-exporter, depends_on resolves
APP_IMAGE=demo:ci POSTGRES_PASSWORD=x docker compose -f infra/compose/services.yml -f infra/compose/observability.yml config  # redis + redis-exporter present once
```
Both exit 0. Verify the exporter image: `docker run --rm -d --name rexp oliver006/redis_exporter:v1.62.0; sleep 3; curl -s localhost:9121/metrics | grep -E "redis_up|redis_memory_used_bytes" | head; docker rm -f rexp` — confirm it serves Prometheus metrics on 9121 and the metric names in the alert exist. Pin the tag from this. (If the image won't pull in this sandbox, note it and rely on the compose-config + the alert keying on the robust `up{job="redis"}`.)

- [ ] **Step 8: Fast gate + commit**

Fast gate. Stage obs/prometheus/alert/dashboard + test + `CLAUDE.md` `[redis T3]` marker; `git commit -m "feat(db): redis observability — exporter + scrape + alert + dashboard (workers OR redis)"`.

---

## Task 4: Integrity, downskill, and live acceptance

**Files:**
- Test: `tests/test_copier_runner.py`, `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Integrity across combos**

Add to `tests/test_copier_runner.py` (match the existing `test_integrity_*` imports/shape):
```python
import pytest


@pytest.mark.parametrize("batteries", [
    [], ["redis"], ["workers"], ["workers", "redis"],
    ["workers", "redis", "mongodb", "pgvector"],
])
def test_integrity_green_for_redis_combos(tmp_path, batteries):
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": batteries})
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []
```
Run it. `[]` MUST be green (no baseline manifest shift). If a combo fails, it's a stray-newline whitespace issue in the broadened-gate LOCKED files (`dev.yml`/`services.yml`/`observability.yml`/`prometheus.yml`) — fix with Jinja whitespace control until baseline + every combo is green.

- [ ] **Step 2: Downskill (force=False), incl. the shared-infra-retained case**

Add (mirror the existing downskill test's git-init helper + `remove_battery` shape — grep `tests/test_copier_runner.py` for the helper used by the other `test_downskill_*` tests and reuse it verbatim):
```python
def test_downskill_redis_alone_no_force(tmp_path):
    from framework_cli.downskill import remove_battery
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["redis"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "redis", force=False)
    assert not (dest / "src" / "demo" / "cache").exists()
    # redis-only project: removing redis removes the service + redis_url + exporter
    assert "\n  redis:\n" not in (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "redis_url:" not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert check(dest, ci=True) == []


def test_downskill_redis_keeps_shared_infra_when_workers_remains(tmp_path):
    from framework_cli.downskill import remove_battery
    dest = tmp_path / "p"
    render_project(dest, {**DATA, "batteries": ["workers", "redis"]})
    write_manifest(dest, installed_framework_version())
    _git_init_commit(dest)
    remove_battery(dest, "redis", force=False)
    assert not (dest / "src" / "demo" / "cache").exists()       # cache package gone
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "\n  redis:\n" in dev                                 # redis service STAYS (workers needs it)
    assert "redis_url:" in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "redis-exporter" in (dest / "infra" / "compose" / "observability.yml").read_text()
    assert check(dest, ci=True) == []
```
Run them. If `remove_battery` demands `--force`, confirm the 8b-1 byte-identity exclusion covers the broadened-gate shared files; report rather than forcing if a genuine builder-shared file trips it.

- [ ] **Step 3: Run the fast-tier tests → green**

Run: `uv run --frozen pytest tests/test_copier_runner.py -k "integrity_green_for_redis or downskill_redis" -q`

- [ ] **Step 4: Live acceptance test**

Add to `tests/acceptance/test_rendered_project.py` (mirror `test_rendered_project_with_mongodb_battery_passes`):
```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: real Redis + Postgres",
)
def test_rendered_redis_battery_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["redis"]})
    assert (dest / "src" / "demo" / "cache" / "repository.py").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the redis battery project:\n"
        + result.stdout + result.stderr
    )
    cov = result.stdout + result.stderr
    line = next((ln for ln in cov.splitlines() if "cache/repository.py" in ln), "")
    assert "100%" in line, (
        f"cache repo not fully exercised; coverage line: {line!r}\n"
        "Expected 100% of cache/repository.py — did test_cache.py run?\n" + cov
    )
```

- [ ] **Step 5: Run it, then CLEAN /tmp**

Run: `uv run --frozen pytest "tests/acceptance/test_rendered_project.py::test_rendered_redis_battery_passes" -q`
Then: `rm -rf /tmp/pytest-of-chris/* 2>/dev/null; df -h /tmp`
Expected: PASS (the `RedisContainer` set/get/ttl/delete round-trip; `cache/repository.py` 100%).

- [ ] **Step 6: Fast gate + commit**

Run the full fast gate. Stage tests + `CLAUDE.md` `[redis T4]` marker; `git commit -m "test(db): redis integrity combos + downskill (shared-infra retained) + live acceptance"`.

---

## Final Review (controller, after all tasks)

Dispatch an opus whole-branch reviewer that RUNS the tooling (see prior slices' final-review pattern). It must:
- Fast gate (`pytest -q --ignore=tests/acceptance`, ruff check, ruff format --check, mypy src) with counts.
- `uv lock --check` (no new FRAMEWORK dep — `redis`/`testcontainers[redis]` are template-only) + `uv build`.
- Empirically: the redis service is defined **exactly once** for `[redis]`/`[workers]`/`[workers,redis]` in dev.yml + services.yml; `redis_url` once in settings; `redis-exporter` once; `worker`/`beat` only for workers; `[]` baseline byte-identical (integrity `[]` green = no manifest shift).
- Integrity green across the Task-1 combos (new + downskill), incl. the shared-infra-retained downskill case.
- Run ONLY the one `test_rendered_redis_battery_passes` acceptance test (clean /tmp after) — confirm the RedisContainer round-trip + `cache/repository.py` 100%.
- `docker compose config` for `[workers,redis]` dev + prod overlays: one redis service, redis-exporter present, `depends_on` resolves.
- **OBS/SVC live-stack gap class:** confirm the broadened gates don't break the baseline live-stack acceptance tests (baseline renders no batteries → no redis → unaffected; read, don't run).
- Verdict: READY TO MERGE or NOT READY + severity-tagged blockers + fix.

Then proceed to `superpowers:finishing-a-development-branch`.

---

## Notes & Risks
- **Dedicated-DB mechanism:** `urlparse`/`urlunparse` path-swap to land on DB `3` regardless of how `redis_url` is written (the `redis-py` `from_url` `db=`-ignored wrinkle). Proven by the functional round-trip.
- **Both-present deps:** explicit `redis>=5` + `celery[redis]` coexist; verified by `uv sync` in the `[workers,redis]` path (acceptance/compose).
- **Exporter image pin:** `oliver006/redis_exporter` is the standard; confirm tag/port/metric-names in Task 3 Step 7.
- **Whitespace control** on the broadened-gate LOCKED files is the #1 regression risk (the 8c class) — baseline `[]` must stay byte-identical; Task 4 integrity is the guard.
- **downskill retains shared infra** when workers remains — explicitly tested (Task 4 Step 2).
