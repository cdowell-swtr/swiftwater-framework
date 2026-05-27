# 8f Slice 2 — DB Paradigm Fan-out (timescaledb + neo4j) + Multi-Extension Postgres Image

**Date:** 2026-05-26
**Status:** Design approved — ready for implementation plan
**Plan 8 slice:** 8f slice 2 (db-paradigm fan-out)
**Predecessors:** 8f slice 1 (pgvector + mongodb), `framework_cli/migrations.py` (N>2 ordering helper), OBS-PROD (`observability.yml` overlay), SVC-PROD (`services.yml` overlay)

---

## 1. Summary & Motivation

Slice 1 established two database-paradigm battery archetypes:

- **postgres-extension** (`pgvector`): rides the always-on Postgres, a migration runs `CREATE EXTENSION`, no new service.
- **separate-service** (`mongodb`): a new compose service with full §5 observability.

Slice 2 advances **both** archetypes and, in doing so, fixes a latent defect the design spike uncovered:

1. **Foundation — a custom multi-extension Postgres image.** Today the `pgvector` battery only switches the **testcontainers** image (`conftest.py` → `pgvector/pgvector:pg17`); the dev/test/prod **compose** Postgres stays plain `postgres:17`, which does **not** ship the `vector` extension binary. A live `task dev` / deployed stack with pgvector would therefore fail the `0004` migration's `CREATE EXTENSION vector`. This is the same **dev-only-not-prod defect class** as OBS-PROD and SVC-PROD — it works in the tested path (testcontainers) and breaks in the deploy path. It was never caught because the pgvector acceptance test runs against a testcontainer, never a live compose stack. A second extension battery makes this acute: `pgvector/pgvector:pg17`, `timescale/timescaledb:…-pg17`, and `apache/age:…` are **mutually exclusive prebuilt images** — two extensions cannot share one base image. The fix is a **custom-built Postgres image** that installs each *present* extension, used by dev/test/prod compose **and** testcontainers.

2. **timescaledb battery (extension archetype, second member).** A hypertable example over a time-series table; appends `0005` to the canonical migration order — the first migration chain ≥3 deep, exercising the N>2 ordering helper for real.

3. **neo4j battery (service archetype, fan-out).** A graph database as its own compose service, reusing mongodb's pattern end-to-end — including the SVC-PROD `services.yml` prod presence and an `observability.yml` exporter.

### Graph paradigm: Apache AGE (Postgres extension) — REVERSED from neo4j mid-build

> **Amendment (2026-05-27):** the original design chose **neo4j (separate service)** over Apache AGE, reasoning that AGE's lack of an apt package made it hard to compose into the shared custom Postgres image, while neo4j's "one more service" cost was now well-patterned. **That reversed during implementation.** Building neo4j's observability hit a wall: **Neo4j Community has no Prometheus exporter that authenticates** — native Prometheus metrics are Enterprise-only, and the only working community exporter (`ghcr.io/petrov-e/neo4j_exporter`) connects without auth, which forced disabling auth in dev and left metrics **broken in prod** (the exporter can't authenticate against prod's `NEO4J_PASSWORD` → the alert fires forever). That is exactly the dev-only-not-prod defect class this whole slice (and OBS-PROD/SVC-PROD) exists to eliminate. So we re-evaluated AGE — and a spike **succeeded**: a multi-stage `COPY` of the prebuilt PG17 extension files (`age.so`, `age--1.6.0.sql`, `age.control`) from `apache/age:release_PG17_1.6.0` into our `FROM postgres:17` image builds cleanly, `CREATE EXTENSION age` loads with `shared_preload_libraries=age`, and a Cypher `CREATE`→`MATCH` round-trip works. **AGE makes graph observability free and prod-correct**: as a Postgres extension it rides the all-env `postgres-exporter`, the authenticated `/health` DB ping, and Postgres backups/HA — exactly like pgvector and timescaledb. No new service, no exporter, no auth wall. The image-composition cost (the original objection) is tractable now that the custom-image machinery exists (T1/T3). The remaining cost — Cypher-embedded-in-SQL ergonomics (`SELECT * FROM cypher('g', $$ … $$) AS (v agtype)`) — is acceptable for a scaffold seam. **Graph = AGE, a third extension battery (`age`, migration `0006`).** neo4j is dropped from this slice (kept as a future option only if a builder specifically wants a dedicated graph service).

### Scope

**In scope:** the custom multi-extension Postgres image (Foundation), the pgvector live-gap fix, the `timescaledb` battery, the **`age` (Apache AGE) graph battery**.

**Deferred (named, not dropped):**
- **`redis` battery → slice 2b.** Its overlap with the workers battery's redis broker (the service cannot be defined twice for `--with workers,redis`) is a distinct design problem that shares nothing with the extension-image work.
- **`neo4j` (dedicated graph service)** — dropped from this slice after the obs wall above; a possible future battery if a builder needs a standalone graph DB (and would need Enterprise for prod Prometheus metrics, or `/health`-only obs).

> **Note:** the **§4 "neo4j Battery" section below is SUPERSEDED** by the AGE design. AGE is an extension battery (no service, no exporter, no settings, no `/health` change, no managed secrets, no `env.py` model import): a Dockerfile multi-stage `COPY` block + `shared_preload_libraries=age` + a `0006` graph migration (`CREATE EXTENSION age` + `create_graph('app_graph')`) + a `graph/` package doing Cypher-in-SQL via SQLAlchemy `text()`. Observability rides the all-env postgres-exporter. The actionable AGE task breakdown lives in the implementation plan (`docs/superpowers/plans/2026-05-26-db-paradigms-slice2.md`, Tasks 4–5, rewritten for AGE).

---

## 2. Foundation — Custom Multi-Extension Postgres Image

### 2.1 The image

A new templated **`infra/docker/postgres.Dockerfile.jinja`**:

- `FROM postgres:17` (the official Debian-based image, which already carries the PGDG apt source used for its own packages).
- Conditionally installs each *present* extension:
  - **pgvector** → `apt-get install -y postgresql-17-pgvector` (PGDG).
  - **timescaledb** → add the TimescaleDB apt repository, `apt-get install -y timescaledb-2-postgresql-17`, and run `timescaledb-tune --quiet --yes` (sets `shared_preload_libraries=timescaledb`, required for the extension to load). The plan pins the exact repo/package mechanics.
- **The Dockerfile is conditional battery payload** — it renders only when `uses_postgres_extension` is true (i.e. at least one extension battery is present), exactly like the `0005` migration and the neo4j dashboards/alerts render only with their batteries. With no extension battery it is **not rendered at all** (and the compose files keep `image: postgres:17`, byte-identical to today — see 2.2). It is therefore **not** in the always-present LOCKED tier (there is no precedent for a conditionally-*existing* LOCKED file; LOCKED batteries only vary the *content* of always-present files). See §6.

### 2.2 Where the image is used

A render-time predicate **`uses_postgres_extension`** = `("pgvector" in batteries or "timescaledb" in batteries)` (or future extension batteries) drives conditional rendering in the compose files:

- **`dev.yml` / `test.yml`**: when `uses_postgres_extension`, the `postgres` / `postgres-test` service uses `build:` (context + the Dockerfile) instead of `image: postgres:17`. When **false**, the service is **byte-identical** to today's plain `image: postgres:17` (integrity stays green; baseline unchanged).
- **`prod.yml` / `staging.yml`** (the standalone deploy topologies, where the `postgres` service lives — `services.yml` is SVC-PROD's *battery data stores* overlay, mongo/redis/neo4j): the `postgres` service references `${POSTGRES_IMAGE:?…}` (the built+pushed tag) when `uses_postgres_extension`; otherwise byte-identical to today.
- **timescaledb config**: when timescaledb is present, the Postgres service command sets `shared_preload_libraries=timescaledb` (via `command:` or the tuned config baked into the image). This applies in dev/test/prod and testcontainers.

### 2.3 testcontainers

`tests/conftest.py.jinja` currently swaps the image string to `pgvector/pgvector:pg17` when pgvector is present. It is replaced so that, when `uses_postgres_extension`, the fixture **builds the same `postgres.Dockerfile`** (via testcontainers' image-build support) and runs the container from it — guaranteeing **test == dev == prod** Postgres. When no extension battery is present, the fixture uses plain `postgres:17` exactly as today.

### 2.4 Prod (self-host) build+push

Consistent with the not-BYO / self-host default:

- The deploy strategy (`infra/deploy/strategy.sh`) builds+pushes the custom Postgres image alongside the app image (reusing the existing builder place-image hook seam — guidance/example, not a literal merge, as established by OBS-PROD/SVC-PROD). `prod.yml`/`services.yml` reference `${POSTGRES_IMAGE}`.
- **Managed escape hatch** (documented in `infra/deploy/README.md`): point `APP_DATABASE_URL` at a managed Postgres that provides the extensions (pgvector/timescaledb are widely offered by RDS / Cloud SQL / Timescale Cloud / Supabase); the built image is then unused.

### 2.5 The pgvector fix

Because pgvector now drives the same build path, a live `task dev` / deployed stack with pgvector has the `vector` extension available — closing the latent gap. This is verified by a new live-stack acceptance test (§7), not just the existing testcontainers test.

---

## 3. timescaledb Battery (extension archetype)

`requires=()` (postgres is always-on). No new service. Mirrors pgvector's structure.

- **Migration `0005`** (`migrations/versions/{{ '0005_readings.py' if 'timescaledb' in batteries else '' }}.jinja`): create a `readings` table — `time TIMESTAMPTZ NOT NULL`, `item_id` FK→`items.id`, `value DOUBLE PRECISION` — then `op.execute("SELECT create_hypertable('readings', 'time')")`. `down_revision = "{{ down_revision_timescaledb }}"` (computed by the helper, §5). Downgrade drops the `readings` table (leaves the extension — dropping a shared extension is destructive, per the pgvector precedent).
- **`timeseries/` package** (gated dir): `models.py` (a `Reading` model on `db.base.Base`) and `repository.py` (`add_reading(...)` + a `bucketed_averages(...)` query using `time_bucket` via SQLAlchemy `text()`). No new Python dependency (timescaledb is SQL-only).
- **`migrations/env.py`** gains a gated `timeseries.models` import (parallel to pgvector/workers).
- **Observability**: rides Postgres — **no new exporter, scrape target, alert, or dashboard** (consistent with pgvector; §5 obs targets service/process surfaces, and timescaledb adds neither). The existing postgres-exporter (all-env, from OBS-PROD) covers it.
- **shared_preload_libraries**: the Foundation image/compose sets `timescaledb` (§2.2) when this battery is present.

---

## 4. neo4j Battery (separate-service archetype)

`requires=()`. Mirrors mongodb end-to-end.

- **Dependency** (template-only, conditional): the `neo4j` Python bolt driver.
- **`graph/` package** (gated dir): `client.py` (`get_driver()` lru_cached from settings; a `get_session` helper) and `repository.py` (an example write — create a node and a relationship — and a read — a bounded traversal query). Bolt sessions are short-lived; the driver is shared and not closed per request.
- **Settings** (`settings.py`, gated fields): `neo4j_url` (e.g. `bolt://neo4j:7687`), `neo4j_user`, `neo4j_password`.
- **`/health`** (`health.py`, gated): a `driver.verify_connectivity()` ping; graceful degrade to `neo4j: false` on failure (shared driver not closed), never 500s.
- **Compose — dev** (`dev.yml`, gated): a `neo4j:5` (Community) service with `NEO4J_AUTH`, a persistence volume (`neo4jdata`), a healthcheck, ports exposed for dev only.
- **Compose — prod/staging** (`services.yml`, gated): the same `neo4j:5` service with persistence + healthcheck, **no published ports** (parallel to mongo/redis in SVC-PROD).
- **Observability** (full §5 parity, mirroring mongodb):
  - A **community neo4j exporter** (Cypher/JMX-based; the plan pins the image, e.g. `comol/neo4jexporter` or equivalent) in **`observability.yml`**, gated on neo4j, `depends_on` the neo4j service (which resolves via `dev.yml` in dev, `services.yml` in prod). Native Prometheus is Enterprise-only and is **out of scope** (documented).
  - A `neo4j` scrape job in **`prometheus.yml`** (byte-identical without the battery — the 8c precedent).
  - `neo4j_alerts.yml` (`Neo4jDown` = exporter `up == 0`) — conditional battery payload.
  - `neo4j.json` Grafana dashboard — conditional battery payload.
- **`.env.example`** (HYBRID managed section): `APP_NEO4J_*` / `NEO4J_AUTH` credentials.
- **`Taskfile.yml`** (HYBRID managed section): a `neo4j:shell` task (cypher-shell into the container).

---

## 5. Migration Ordering (N>2 goes live)

`framework_cli/migrations.py`:

- `MIGRATION_ORDER` appends **`timescaledb` as `0005`** after `pgvector` (`0004`). The **incremental-insertion rule** is now operative and documented: new migration batteries append at the **end** of the canonical order and never renumber existing entries, so existing `down_revision` computations are preserved and alembic gaps remain harmless (the slice-1 fixed-numeric-id design).
- `migration_down_revisions(batteries)` already computes each present migration battery's `down_revision` as the nearest *present* predecessor. timescaledb is the first battery to make the chain ≥3 deep, so combinations like `--with pgvector,timescaledb` (`0001 → 0004 → 0005`) or `--with timescaledb` alone (`0001 → 0005`, pgvector absent) exercise N>2 for the first time.
- `migration_context()` injects `down_revision_timescaledb` into both `render_project` and `upskill_project` (parallel to existing entries).
- The module-load **drift guard** (raises if `MIGRATION_ORDER` / `REVISIONS` diverge) is extended to include timescaledb's revision.

---

## 6. Integrity, LOCKED Files & Manifest Shift

- **Conditional battery payload** (renders only with its battery; not LOCKED, like mongodb's alerts/dashboards): `infra/docker/postgres.Dockerfile`, `neo4j_alerts.yml`, `neo4j.json`, the `timeseries/` and `graph/` packages, the `0005` migration.
- **No new `LOCKED_TRACKED` entries.** The already-LOCKED infra files (`dev.yml`, `test.yml`, `prod.yml`, `staging.yml`, `services.yml`, `observability.yml`, `prometheus.yml`) are conditionally **edited** but stay **byte-identical without the relevant battery** (the 8c/SVC precedent) — so the locked set is unchanged.
- **HYBRID managed-section files**: `.env.example`, `Taskfile.yml` (neo4j section).
- **No baseline manifest shift.** Unlike OBS-PROD/SVC-PROD (which added always-present files), every new artifact here is battery-gated and the edited LOCKED files are byte-identical without their battery — so a **no-battery project renders byte-identical** and its manifest is unchanged. Projects that **already use pgvector** receive the image-build fix on `framework upskill` (their dev/test/prod Postgres switches to the built image; their manifest updates accordingly — the intended fix). Integrity must be green across: baseline (no battery), each battery alone, and combinations (`pgvector,timescaledb`; `timescaledb,neo4j`; `pgvector,timescaledb,neo4j`; with/without workers/mongodb).
- **downskill** must need no `--force` for any of the three (the 8b-1 byte-identity exclusion covers gated shared files); the `0005` migration is preserved + warned on `downskill timescaledb` (the pgvector precedent).

---

## 7. Testing

The acceptance strategy explicitly closes the gap class the spike found.

- **Render / unit tests** (`tests/test_copier_runner.py`): the `postgres.Dockerfile` renders with the right extensions per battery set; compose files switch to `build:`/`${POSTGRES_IMAGE}` when `uses_postgres_extension` and are byte-identical otherwise; the `0005` migration renders with the correct computed `down_revision` across battery combinations; neo4j service/exporter/scrape/alert/dashboard render; `MIGRATION_ORDER` drift guard passes.
- **`docker compose config` merge-validations** (fast, no containers): neo4j present in `dev.yml` (dev) and `services.yml` (prod merge) with its exporter in `observability.yml` and `depends_on` resolving; the Postgres service uses `build:`/`${POSTGRES_IMAGE}` when an extension battery is present.
- **Live-stack acceptance test (the explicit fix)**: bring up a live `docker compose` stack for an extension battery (pgvector and/or timescaledb) and assert the `CREATE EXTENSION` migration succeeds against the **built** image — proving the dev/prod path works, not just testcontainers. (Mind the recorded Docker-acceptance `/tmp` hygiene caveat — run sparingly, clean up.)
- **testcontainers functional tests**: pgvector similarity search and timescaledb `time_bucket` query run against the built image; neo4j graph round-trip (the neo4j functional test uses a neo4j testcontainer or the live service per the mongodb precedent).
- **Integrity invariant**: green across all battery combinations listed in §6, both `new` and `downskill`.
- **Self-CI hygiene**: a freshly rendered project (each battery combo) passes its first `pre-commit` clean (the 8c regression class).

---

## 8. Components & File Map

**Framework CLI (`src/framework_cli/`):**
- `migrations.py` — append `timescaledb`/`0005` to `MIGRATION_ORDER` + `REVISIONS`; extend `migration_context` + drift guard.
- **No `LOCKED_TRACKED` change** (all new files are battery-gated conditional payload; the edited LOCKED files stay byte-identical without their battery).
- (No new top-level module; batteries remain template-driven via the `batteries` answer + autodiscovery.)

**Template payload (`src/framework_cli/template/`):**
- Create: `infra/docker/postgres.Dockerfile.jinja`.
- Create (timescaledb): `migrations/versions/{{ '0005_readings.py' if 'timescaledb' in batteries else '' }}.jinja`; `src/{{package_name}}/{% if "timescaledb" in batteries %}timeseries{% endif %}/{models,repository,__init__}.py`.
- Create (neo4j): `src/{{package_name}}/{% if "neo4j" in batteries %}graph{% endif %}/{client,repository,__init__}.py`; `infra/observability/grafana/dashboards/neo4j.json` (gated); `infra/observability/prometheus/neo4j_alerts.yml` (gated).
- Modify: `infra/compose/{dev,test,prod,staging,services,observability}.yml.jinja`; `infra/observability/prometheus/prometheus.yml.jinja`; `migrations/env.py.jinja`; `src/{{package_name}}/settings.py.jinja`; `src/{{package_name}}/.../health.py.jinja`; `tests/conftest.py.jinja`; `.env.example.jinja`; `Taskfile.yml.jinja`; `pyproject.toml.jinja` (conditional `neo4j` dep); `infra/deploy/strategy.sh` + `infra/deploy/README.md` (build+push the Postgres image + managed escape hatch).

**Framework docs:**
- `CLAUDE.md` Current State + Known follow-ups (mark pgvector live-gap fixed; note AGE/redis deferrals); meta-plan status table.

---

## 9. Risks & Mitigations

- **timescaledb apt on stock `postgres:17`.** Timescale promotes its own images; installing on the official image requires their apt repo + a matching PG17 package + `shared_preload_libraries`. *Mitigation:* the plan validates the exact repo/package/tune steps in an early task; the build is exercised by the live-stack acceptance test.
- **testcontainers building an image** (vs pulling) is slower on first run and needs Docker build access. *Mitigation:* build once per session; the no-Docker path already skips these tests (existing `_docker_available` guard).
- **neo4j Community obs depth.** The community exporter exposes fewer metrics than Enterprise's native endpoint. *Mitigation:* accept a focused metric set (liveness + a few query/store gauges) sufficient for `Neo4jDown` + a basic dashboard; document Enterprise for richer metrics.
- **Prod Postgres image build+push** adds a second image to the deploy pipeline. *Mitigation:* reuse the existing place-image hook seam (guidance, not literal merge); the managed escape hatch avoids it entirely for managed-PG users.
- **Byte-identity of conditionally-edited LOCKED files.** Editing `dev.yml`/`test.yml`/`prod.yml`/`services.yml`/`observability.yml`/`prometheus.yml` for the new batteries risks a stray newline/whitespace leaking into the no-battery render and turning integrity red (the 8c regression class). *Mitigation:* Jinja whitespace control + the integrity-green-on-baseline assertion in the test matrix; this is also what preserves the "no baseline manifest shift" property (§6).

---

## 10. Out of Scope / Follow-ups

- **`redis` battery (slice 2b)** — service archetype + workers-redis dedup design.
- **Apache AGE** — future graph-without-a-new-service option (multi-stage build into the custom image).
- **8f-w wizard** — unified configurable `framework new` (db-paradigm + alert-channel selection); last in Plan 8.
- **obs-completeness review check / obs-infra-scaling / reviewer split** — existing Known follow-ups; this slice's neo4j adds another service-with-obs data point for that check to eventually enforce.
