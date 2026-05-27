# 8f Slice 2b — `redis` DB-Paradigm Battery (redis as a datastore)

**Date:** 2026-05-27
**Status:** Design approved — ready for implementation plan
**Plan 8 slice:** 8f slice 2b (db-paradigm fan-out, final atomic battery)
**Predecessors:** 8c (workers battery — already runs a redis broker), 8f slice 1 (mongodb separate-service archetype), 8f slice 2 (timescaledb/age extension archetypes), OBS-PROD (`observability.yml` overlay), SVC-PROD (`services.yml` overlay)

---

## 1. Summary & Motivation

Adds the `redis` database-paradigm battery: **redis as an application-level datastore** (key/value cache, sessions, ephemeral state). This completes the db-paradigm fan-out (pgvector, mongodb, timescaledb, age, redis); only the `8f-w` configurable wizard remains as a Plan-8 db item.

The defining constraint is the **overlap with the `workers` battery**, which already provisions a `redis:7-alpine` service (Celery broker + result backend) in `dev.yml`/`services.yml`, a `redis_url` setting, and a `/health` liveness probe. A naive redis battery would (a) define the `redis` service twice (a compose error for `--with workers,redis`) and (b) declare a second `redis_url` settings field (a Python error). The resolution: **share one redis service and hoist `redis_url` to a battery-shared gate.**

A secondary finding: the redis *server* is currently **unmonitored** even under `workers` (there is a `celery-exporter` for Celery metrics, but no redis-exporter). This battery adds a redis-exporter gated so the service is monitored **whenever it exists** (`workers OR redis`), closing that gap.

### Scope

**In scope:** the `cache/` datastore package (client + KV repo), the shared-service/shared-`redis_url` overlap fix, redis observability (exporter + scrape + alert + dashboard) gated `workers OR redis`, a `/health` ping, conditional deps, registration, integrity + downskill + acceptance tests.

**Out of scope / deferred:**
- The `8f-w` unified configurable wizard (db-paradigm + alert-channel selection) — last Plan-8 db item.
- No new Postgres-image involvement (redis is its own service, unrelated to the multi-extension Postgres image).
- No migration (redis is schemaless — `MIGRATION_ORDER` is untouched).

---

## 2. Archetype

A **separate-service** battery (like mongodb), `requires=()`, but one that **shares** the redis service rather than adding a second one. It is the first battery to *co-own* a service with another battery (`workers`), which drives the gating design below.

---

## 3. Shared Service + Settings (the overlap fix)

### 3.1 Service (shared, gated `workers OR redis`)

In `infra/compose/dev.yml.jinja` and `infra/compose/services.yml.jinja`, broaden the existing `{% if "workers" in batteries %}` gate around the `redis` service (and the `redisdata` volume) to `{% if "workers" in batteries or "redis" in batteries %}`. The service block itself is unchanged (`redis:7-alpine`, `redis-cli ping` healthcheck, `redisdata` volume, dev published port). Defined **once** regardless of which/both batteries are present.

- **dev.yml**: the `redis` service stanza + the `redisdata: {}` volume entry.
- **services.yml** (prod/staging overlay): the `redis` service stanza + the `redisdata: {}` volume entry. (The worker/beat services stay `{% if "workers" %}` — they are Celery-specific.)

### 3.2 Settings (`redis_url` hoisted)

In `config/settings.py.jinja`, move the `redis_url` field out of the workers-only block into a block gated `{% if "workers" in batteries or "redis" in batteries %}` (default `redis://redis:6379/0`). The Celery-specific fields (`celery_broker_url`, `celery_result_backend`) **stay** in the workers-only block. Result: `redis_url` is declared exactly once whether one or both batteries are active.

### 3.3 Dedicated logical DB for the cache keyspace

The datastore client connects via `redis_url` but selects a **dedicated logical DB (`3`)** so its keys never collide with Celery's broker (`/0`) and result backend (`/1`). Implementation note: `redis-py`'s `Redis.from_url(url, db=3)` does **not** override a DB already present in the URL path — so the client must construct the connection so the dedicated DB is actually used (parse `redis_url` and substitute the DB, or build `Redis(...)` from the parsed host/port with `db=3`). The plan pins the exact mechanism after verifying `redis-py` behavior. The cache keyspace is therefore isolated even when sharing the same redis server with Celery.

---

## 4. Application Package (`cache/`)

A gated package `src/{{package_name}}/{% if "redis" in batteries %}cache{% endif %}/`:

- `__init__.py` (empty).
- `client.py`: `get_redis()` — an `lru_cache`d `redis.Redis` bound to `redis_url` on logical DB `3`, `decode_responses=True` (so values round-trip as `str`).
- `repository.py`: a small KV datastore seam —
  - `cache_set(key: str, value: str, ttl_seconds: int | None = None) -> None` (sets with optional TTL via `ex=`),
  - `cache_get(key: str) -> str | None`,
  - `cache_delete(key: str) -> None`.

This is the redis-as-datastore example a builder extends (caching, sessions, rate-limit counters, etc.).

---

## 5. Observability (gated `workers OR redis`)

Redis server metrics, active whenever the service exists:

- **`redis-exporter`** (`oliver006/redis_exporter`, a pinned tag) in `observability.yml`, gated `{% if "workers" in batteries or "redis" in batteries %}`, `depends_on` the `redis` service (resolves via `dev.yml` in dev, `services.yml` in prod). Connects to `redis://redis:6379`.
- **`redis` scrape job** in `prometheus.yml` (LOCKED), same gate — targets `redis-exporter:9121` (the exporter's default metrics port; the plan confirms the pin).
- **`redis_alerts.yml`** (conditional payload, gated filename): `RedisExporterDown` (`up{job="redis"} == 0`, `for: 5m`, warning) + a high-memory alert (`redis_memory_used_bytes / redis_memory_max_bytes > 0.9` with a `maxmemory>0` guard, or an equivalent the plan finalizes against the exporter's metric names).
- **`redis.json`** Grafana dashboard (conditional payload, gated filename): panels for memory used, keyspace hits/misses ratio, connected clients, and commands/sec — mirroring the structural envelope of an existing battery dashboard (e.g. `mongodb.json`).

This closes the pre-existing "workers' redis broker is unmonitored" gap as a deliberate, beneficial side effect.

---

## 6. `/health`

In `routes/health.py.jinja`, add a `redis` connectivity block gated `{% if "redis" in batteries %}`: ping `get_redis().ping()` inside try/except, set `report["redis"] = {"alive": True|False}`, never 500 the probe (mirrors the mongo/neo4j-era graceful-degrade pattern). Workers' existing redis liveness (`report["workers"]`) is unchanged — when both batteries are present the two probes hit the same server (a negligible redundancy; each battery owns its own signal).

---

## 7. Dependencies

- **`redis>=5`** (Python) — conditional in `pyproject.toml.jinja`, gated on the redis battery. When `workers` is present it is already pulled transitively by `celery[redis]`; the gating must not produce a duplicate or conflicting dependency line (the plan handles the both-present case cleanly — e.g. gate the explicit `redis` dep on the redis battery only; `uv` resolves the overlap with `celery[redis]`).
- **`testcontainers[redis]`** — conditional test dependency, gated like `testcontainers[mongodb]`, for the functional test's `RedisContainer`.

No new framework dependency (these are template-only).

---

## 8. Registration, Integrity & Downskill

- **`batteries.py`**: register `redis` (`BatterySpec("redis", "Redis key/value datastore (cache/sessions) — shares the workers redis service when both are active", requires=())`).
- **No `MIGRATION_ORDER` change** (schemaless).
- **No new `LOCKED_TRACKED` entries.** The edited LOCKED files (`dev.yml`, `services.yml`, `observability.yml`, `prometheus.yml`) stay **byte-identical for a render where neither `workers` nor `redis` is present** → **no baseline manifest shift.** Renders that include `workers` and/or `redis` shift once (the accepted cost of the `workers OR redis` obs gate — workers-only projects gain the redis-exporter/scrape on `framework upskill`).
- **Conditional payload** (gated filenames, not LOCKED): the `cache/` package, the functional test, `redis_alerts.yml`, `redis.json`.
- **Integrity** must be green across: `[]`, `[redis]`, `[workers]`, `[workers,redis]`, and a representative larger combo (e.g. `[workers,redis,mongodb,pgvector]`).
- **downskill `redis`** must need no `--force`: the `cache/` package + payload are owned files (deleted); the shared `redis` service / `redis_url` / redis-exporter **persist when `workers` remains** (still gated `workers OR ...`), and revert only when neither battery is left — the two-render owned-files diff + the 8b-1 byte-identity exclusion for gated shared files handle this. (Removing `redis` from `[workers,redis]` must leave the redis service, `redis_url`, and the redis-exporter intact, because `workers` still gates them.)

---

## 9. Testing

- **Render/unit (`tests/test_copier_runner.py`):**
  - `[redis]`: `cache/` package + `test_cache.py` render; `redis_url` present in settings; the redis service present in dev.yml/services.yml; redis-exporter in observability.yml; `job_name: redis` in prometheus.yml; `redis_alerts.yml` + `redis.json` present; `/health` has a redis block.
  - `[workers,redis]`: the redis service is defined **exactly once** in each compose file; `redis_url` appears **exactly once** in settings; redis-exporter present once.
  - `[workers]`: redis service present; redis-exporter present (the obs-gap closure); but **no** `cache/` package, no redis `/health` block (those are `redis`-only).
  - `[]`: byte-identical baseline (no redis service, no redis_url, no exporter — confirming no manifest shift).
- **Integrity** parametrized across the combos in §8 (`check(dest, ci=True) == []`).
- **downskill** `redis` from `[redis]` and from `[workers,redis]` (force=False) — owned files gone, shared infra retained when workers remains, integrity green.
- **Live acceptance (`tests/acceptance/test_rendered_project.py`):** `--with redis` → `uv sync` → `scripts/coverage.sh 70 unit functional`; the functional test runs a `RedisContainer` round-trip (`cache_set` with TTL → `cache_get` → `cache_delete`), and `cache/repository.py` reaches 100% (proves the round-trip ran). (Mind the `/tmp` Docker-acceptance hygiene caveat — run sparingly, clean up.)
- **`docker compose config` merge-validations** (safe, no containers): `[redis]` dev stack has one redis service; `[workers,redis]` dev + prod (`-f services.yml -f observability.yml`) have exactly one redis service and the redis-exporter with `depends_on` resolving.

---

## 10. Components & File Map

**Framework CLI (`src/framework_cli/`):**
- `batteries.py` — register `redis`.
- (No `migrations.py` change — redis adds no migration.)
- No `LOCKED_TRACKED` change.

**Template payload (`src/framework_cli/template/`):**
- Create: `src/{{package_name}}/{% if "redis" in batteries %}cache{% endif %}/{__init__.py,client.py,repository.py}`.
- Create: `tests/functional/{{ 'test_cache.py' if 'redis' in batteries else '' }}.jinja`.
- Create: `infra/observability/prometheus/alerts/{{ 'redis_alerts.yml' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja` *(gate the filename on `workers OR redis` so the alert ships whenever the exporter does)*.
- Create: `infra/observability/grafana/dashboards/{{ 'redis.json' if ('redis' in batteries or 'workers' in batteries) else '' }}.jinja` *(same gate)*.
- Modify: `infra/compose/dev.yml.jinja`, `infra/compose/services.yml.jinja` (broaden the redis service + `redisdata` volume gate to `workers OR redis`); `infra/compose/observability.yml.jinja` (add `redis-exporter`, `workers OR redis`); `infra/observability/prometheus/prometheus.yml.jinja` (add the `redis` scrape, `workers OR redis`); `config/settings.py.jinja` (hoist `redis_url` to `workers OR redis`); `routes/health.py.jinja` (redis ping, `redis` only); `pyproject.toml.jinja` (conditional `redis` + `testcontainers[redis]`).

**Framework docs:** `CLAUDE.md` Current State + meta-plan 8f row.

---

## 11. Risks & Mitigations

- **Dedicated-DB mechanism** (`redis-py` `from_url` ignoring the `db` kwarg when the URL has a path-DB). *Mitigation:* the plan verifies the exact `redis-py` call and constructs the client so DB `3` is actually used; the functional test (round-trip against a real `RedisContainer`) is the proof.
- **Both-present dependency duplication** (`redis` explicit dep + `celery[redis]`). *Mitigation:* gate the explicit `redis` dep so the combined render produces a valid, non-duplicated `pyproject.toml`; verified by the `[workers,redis]` render + `uv sync` in acceptance.
- **Byte-identity of the broadened LOCKED-file gates** (the `{% if "workers" %}` → `{% if "workers" or "redis" %}` edits). *Mitigation:* the `[]` baseline must render byte-identical (Task-style integrity assertion); Jinja whitespace control; the `[workers]` render must remain valid (only gaining the redis-exporter/scrape — the intended shift).
- **downskill leaving shared infra when workers remains.** *Mitigation:* explicit downskill test removing `redis` from `[workers,redis]` and asserting the redis service / `redis_url` / exporter persist.

---

## 12. Out of Scope / Follow-ups

- **`8f-w` wizard** — unified configurable `framework new` (db-paradigm + alert-channel selection); last Plan-8 db item.
- **obs-completeness review check** (existing Known follow-up) — this battery's "monitor the service whenever it exists" gate is another data point: the check should flag a battery that adds/uses a service without a scrape target + alert + dashboard.
