# Database Paradigm Batteries — Slice 1 (`pgvector` + `mongodb`) — Design Spec

**Date:** 2026-05-25
**Status:** Approved (brainstorm) — not yet planned/implemented
**Plan:** 8f (slice 1 of the database-paradigm batteries; the `8f-w` wizard and the remaining paradigms are deferred — see §8)
**Builds on:** Plan 8a-1 (battery registry + `resolve()` + conditional rendering + router/model autodiscovery), 8a-2 (`downskill` — owned-files two-render diff, migration preservation, reverse-dep + usage guards), 8b/8c (managed-section injection; LOCKED-conditional rendering of `dev.yml`/`prometheus.yml`; the §5 battery-observability contract; the workers service-injection + `/health` liveness pattern; the workers `0003` templated `down_revision`), 8b-1 (downskill `usage_references` byte-identity exclusion).

---

## 1. Purpose & scope

Add the first two **database-paradigm atomic batteries**, one per archetype, to prove both patterns and build the mechanics the rest of 8f reuses:

- **`pgvector`** — the **postgres-extension archetype**. Postgres is always-on (not a battery), so this adds *no new service*: it enables the `vector` extension on the existing postgres, adds an `embeddings` table + repository, and is the vehicle for the **N>2 migration-ordering generalization**.
- **`mongodb`** — the **separate-service archetype**. A new `mongo` container + a `pymongo` client + a documents demo + **full §5 observability** (exporter scrape target, alerts, dashboard, `/health` connection check).

Both have `requires=()`, compose with each other and with every existing battery, and are independently add/removable.

**Two documented premises are corrected here (and the meta-plan updated):**

- **The reverse-dependency guard does NOT "go live" in 8f.** `BatterySpec.requires` names *batteries*; postgres is always-on, not a battery, so `pgvector.requires=()` (a `CREATE EXTENSION` on the ever-present postgres). No battery in this slice requires another battery, so `downskill`'s `blocking_dependents` guard stays **inert** — still proven by its synthetic `_pgvector→_postgres` unit test, but not exercised by a real battery until some future battery genuinely requires another. The "pgvector⇒postgres reverse-dep" framing was a category error (battery vs always-on service).
- **The always-on postgres store has no dedicated exporter/dashboard.** Giving `mongodb` full §5 parity (chosen) makes that baseline gap visible. Closing it (a postgres_exporter for the baseline) is **out of scope here** and recorded as a follow-up (§8) — not scope-crept into this slice.

**Out of scope (deferred):** `timescaledb`, `neo4j`, `redis` (fan out later reusing these two patterns; `redis` only after resolving the overlap with the workers battery's redis service), the **`8f-w` database wizard** (end of Plan 8), the **postgres-baseline exporter**, and any **dynamic paradigm-set injection** into the data-review agents (their prompts already flag cross-store/cross-paradigm risks — YAGNI).

## 2. Migration-ordering mechanism (the core new mechanic)

Today each battery migration hard-codes its parent (`workers/0003`: `down_revision = "0002" if webhooks else "0001"`). That ad-hoc ternary doesn't scale past two levels. This slice generalizes it.

**A Python helper, framework-side and unit-tested — not Jinja gymnastics.** A single canonical order of the *migration-adding* batteries is the source of truth:

```python
# framework_cli/migrations.py  (new)
MIGRATION_ORDER = ["webhooks", "workers", "pgvector"]  # timescaledb appended later
REVISIONS = {"webhooks": "0002", "workers": "0003", "pgvector": "0004"}  # fixed per battery

def migration_down_revisions(batteries: Sequence[str]) -> dict[str, str]:
    """For each present migration-adding battery, its down_revision = the nearest PRESENT
    predecessor in canonical order, else '0001' (the baseline)."""
    present = [b for b in MIGRATION_ORDER if b in batteries]
    out: dict[str, str] = {}
    prev = "0001"
    for b in present:
        out[b] = prev
        prev = REVISIONS[b]
    return out
```

**Revision ids stay fixed numeric per battery** (`webhooks=0002`, `workers=0003`, `pgvector=0004`) — so **no renaming of existing migration ids and no `copier update` hazard** for already-generated projects. Alembic treats revision ids as opaque labels; a "gap" like `0001 → 0003` when webhooks is absent is harmless.

`render_project` (and the upskill path) computes `migration_down_revisions(batteries)` and merges the values into the Copier `data` dict as context vars (`down_revision_webhooks`, `down_revision_workers`, `down_revision_pgvector`). Each migration template interpolates `down_revision = "{{ down_revision_<battery> }}"`. **Workers' existing ad-hoc ternary is refactored to the injected value** (identical result for the webhooks/workers cases). `migrations/env.py` conditionally imports the pgvector model (existing pattern). `scripts/check_migrations.py` continues to enforce a non-trivial `downgrade()`.

**Determinism + the incremental-insertion constraint (documented, narrow):** every render/upskill recomputes the chain deterministically, so a fresh render of a given battery set is byte-identical (integrity-clean). The one unsafe case is **adding a battery whose canonical position is *before* an already-present, already-deployed battery's migration** (it would shift the later migration's `down_revision`). This is *pre-existing* (adding `webhooks` after `workers` has the same shape today) and **does not arise in this slice** — `pgvector` is canonical-last among existing migration batteries, so adding it to a webhooks/workers project is a clean append. Mitigation, documented for when `timescaledb` lands: recompute is safe before a migration is deployed; a post-deploy mid-insertion is resolved with a manual contract/merge migration. Fully general branch/merge ordering is explicitly deferred (YAGNI for two migration-batteries).

## 3. `pgvector` battery (extension archetype)

- **Registration:** `BatterySpec("pgvector", "PostgreSQL pgvector extension + an embeddings table for vector similarity search", requires=())`.
- **Dependency:** conditional `pgvector>=0.3` (the Python package providing the SQLAlchemy `Vector` type) in `pyproject.toml.jinja` (the `celery[redis]` gating pattern; ships `py.typed`, so no mypy override).
- **Migration `0004` (gated path):** `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`, then create `embeddings` (`id` PK, `item_id` FK → `items.id`, `embedding` `Vector(1536)`). `revision = "0004"`, `down_revision = "{{ down_revision_pgvector }}"`. `downgrade()` drops the `embeddings` table (the extension is left in place — dropping a shared extension is destructive; documented).
- **Model + repository** (gated package, e.g. `vectors/` or added to `db/`): an `Embedding` model; `add_embedding(session, item_id, embedding)` and `nearest(session, query, k)` (cosine distance `embedding.cosine_distance(query)` ordered ascending, `.limit(k)`). Reuses the baseline sync `Session`.
- **Observability:** **none new.** pgvector adds no service/process — only a table + extension, covered by the app's existing request/DB metrics (consistent with the baseline `items` table, which has no dedicated metric). The §5 contract targets service/process surfaces; pgvector is neither.
- **`migrations/env.py`:** gated import of the `Embedding` model so alembic autogenerate/metadata sees it only when present.
- **Tests:** a functional test against a real Postgres-with-pgvector (testcontainers image `pgvector/pgvector:pg17` or `CREATE EXTENSION` on the base image) inserting a few embeddings and asserting `nearest` returns them in similarity order; render tests (with/without) + a pgvector-only ruff-format-clean guard.

## 4. `mongodb` battery (separate-service archetype, full §5)

- **Registration:** `BatterySpec("mongodb", "MongoDB document store (pymongo) with a documents collection + full observability", requires=())`.
- **Dependency:** conditional `pymongo>=4.9` in `pyproject.toml.jinja`. **Sync** client (matches the sync app/SQLAlchemy style — no async split).
- **Client + demo:** a gated `mongo/` package — a client accessor (`get_client()`/`get_db()` reading `settings.mongo_url`, a module-level lazily-built client mirroring `db/engine.py`) + a thin repository (`insert_document(db, doc)`, `find_documents(db, filter)`) over a `documents` collection. Minimal — enough to exercise insert/find end-to-end.
- **Settings:** a gated `mongo_url: str = "mongodb://mongo:27017/app"` field in `settings.py.jinja`.
- **Service (LOCKED-conditional `dev.yml`, the workers precedent):** a `mongo:7` service (healthcheck `mongosh --eval "db.adminCommand('ping')"`, published port, volume) + a `mongodb-exporter` service (e.g. `percona/mongodb_exporter`, pointed at the mongo URI, port 9216).
- **Scrape target (LOCKED-conditional `prometheus.yml`):** a gated `mongodb` job targeting `mongodb-exporter:9216`.
- **Managed-section injection (HYBRID):** `APP_MONGO_URL=mongodb://mongo:27017/app` in the `.env.example` `FRAMEWORK:BEGIN/END` section + a Taskfile entry (e.g. `mongo:shell`) — the workers two-hybrid-section precedent. (Battery-dependent checksum → handled by the existing battery-aware restore/manifest-regen.)
- **Observability (full §5):**
  - **`/health`** gains a gated mongo connection check (a `ping`; graceful try/except → `{"mongo": {"alive": false}}` on failure, never 500s the probe; closes the client — the workers redis-liveness precedent).
  - **`mongodb_alerts.yml`** (new untracked payload): a tunable warning rule — e.g. `mongodb-exporter` target down, or `mongodb_connections{state="current"}` above a floor — annotated "app-specific default; tune or remove". (Exact metric names pinned in the plan against the chosen exporter.)
  - **`mongodb.json`** Grafana dashboard (new untracked payload; `uid: "mongodb"`): connections + op-rate panels, plain/`__auto` legends, valid JSON.
  - The app process exposes no mongo-specific in-process metric (the exporter owns DB-level metrics); `/metrics` is unchanged for mongodb (unlike the in-process webhooks/websockets/graphql batteries) — the exporter is the scrape source, mirroring workers' celery-exporter.
- **Tests:** a functional test against a real mongo (testcontainers) — insert + find round-trip + `/health` shows mongo alive; render tests (with/without) + a mongodb-only ruff-format-clean guard.

## 5. Composition, integrity, downskill

- **Composition:** `pgvector` and `mongodb` are independent of each other and of webhooks/workers/websockets/graphql; every combo composes. The migration helper handles `pgvector` stacking after webhooks/workers (`--with webhooks,workers,pgvector` → `0001→0002→0003→0004`).
- **Integrity:** `dev.yml`/`prometheus.yml` are **LOCKED** — the gated mongodb edits render byte-identical without the battery (`{%- if %}` control; the workers/`dev.yml` precedent; the battery-aware manifest keeps `integrity --ci` green with the battery). `.env.example`/`Taskfile.yml` are **HYBRID** — mongodb's managed sections inject/splice via the existing section machinery. `pgvector` touches **no LOCKED/HYBRID file** (just `pyproject`, a migration, a model/repo — its only shared edit is the gated `env.py` import + `pyproject` dep, both byte-identical without it). `mongodb_alerts.yml`/`mongodb.json` are new untracked payload (no manifest impact).
- **Downskill:** both remove with **no `--force`** (the 8b-1 byte-identity exclusion covers the gated `env.py`/`settings.py`/`health.py`/`pyproject` references). `pgvector`'s `0004` migration is **preserved + warned** (the 8a-2 rule — a DB may be at that revision; drop via a contract down-migration). `mongodb`'s HYBRID sections are spliced out; its service/scrape/alert/dashboard files (owned) are deleted. `record_batteries` + `write_manifest` keep integrity/restore green.

## 6. Testing

- **Unit (hermetic, framework-side):** `migration_down_revisions` — `[]`→`{}`; `["pgvector"]`→`{pgvector:"0001"}`; `["webhooks","pgvector"]`→`{webhooks:"0001", pgvector:"0002"}`; `["webhooks","workers","pgvector"]`→`{...workers:"0002", pgvector:"0003"}`; order-insensitive input (sorted by canonical order, not input order). This is the key new logic.
- **Render (`tests/test_copier_runner.py`):** with `["pgvector"]` → the migration (`down_revision` correct), model/repo, dep render; with `["mongodb"]` → the `mongo/` package, settings field, `dev.yml` mongo + exporter services, `prometheus.yml` job, `.env.example`/`Taskfile` sections, `mongodb_alerts.yml` + `mongodb.json`, `/health` mongo check render; without either → none render and the LOCKED/HYBRID files are clean. Per-battery ruff-format-clean guards (the 8c regression class).
- **Acceptance (Docker):** `--with pgvector` (real Postgres + extension → `nearest` similarity search green, migration applies), `--with mongodb` (real mongo → insert/find round-trip + `/health` mongo alive), and `--with webhooks,workers,pgvector` (proves the `0001→0002→0003→0004` chain applies end-to-end).
- **Integrity:** rendered baseline + each battery variant pass `framework integrity --ci`; the LOCKED `dev.yml`/`prometheus.yml` are byte-identical without the batteries.

## 7. Integrity & consistency summary

`pgvector` is the cleanest archetype (a dep + a migration + a model/repo; no service, no observability, no LOCKED/HYBRID edit beyond the gated `env.py` import). `mongodb` is the first **data-store** battery with full §5 parity — and the first to expose that the always-on postgres store lacks an exporter (recorded follow-up, §8). The migration helper is the reusable spine for every future migration-adding paradigm.

## 8. Follow-ups (recorded, not in this slice)

- **`timescaledb`** battery (extension archetype; appends to `MIGRATION_ORDER` as `0005` — the first real exercise of multi-level chain growth; the incremental-insertion constraint of §2 becomes live).
- **`neo4j`** battery (service archetype; reuses the mongodb pattern).
- **`redis` paradigm** battery (service archetype; must first resolve the overlap with the workers battery's redis service — shared service vs separate instance).
- **`8f-w` database wizard** — the guided `--with database` front-end that interviews and resolves to these atomic batteries; **last in Plan 8**, once all paradigms exist.
- **postgres-baseline exporter** — a postgres_exporter + dashboard for the always-on store, to match the monitorability the service-batteries get (a baseline-observability backfill; separate plan).
- **Reverse-dependency guard activation** — remains inert until a battery genuinely requires another battery; the synthetic unit test stays as the proof.

## 9. Self-review

- **Placeholders:** none — the migration helper (with the exact algorithm + fixed-revision-id decision), both batteries' deps/migrations/models/services/settings/observability, the LOCKED/HYBRID handling, downskill, and the test tiers are specified. Exact mongodb_exporter metric names for the alert are deferred to the plan (pinned against the chosen exporter image) — a bounded, intentional defer.
- **Internal consistency:** `requires=()` for both (postgres always-on) → the reverse-dep guard stays inert, consistent with the corrected premise; fixed numeric revision ids → no rename/upgrade hazard, consistent with "deterministic recompute"; pgvector adds no service → no observability, while mongodb adds a service → full §5, a deliberate archetype asymmetry justified by the postgres-baseline precedent.
- **Scope:** two batteries + one reusable mechanism (the migration helper), focused enough for one plan; the other paradigms + wizard + postgres-exporter are explicitly deferred.
- **Ambiguity:** "N>2 migration ordering" pinned to a canonical-order Python helper with fixed revision ids + context injection (not Jinja macros, not renaming); the incremental-insertion edge pinned as a documented narrow constraint (not arising in this slice); mongodb client pinned to sync `pymongo`; mongodb observability pinned to full §5 via an exporter (no in-process `/metrics` change).

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8f (slice 1).*
