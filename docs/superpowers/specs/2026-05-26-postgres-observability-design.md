# Baseline Postgres Observability Backfill (Plan 8i) — Design Spec

**Date:** 2026-05-26
**Status:** Approved (brainstorm) — not yet planned/implemented
**Plan:** 8i (a baseline-observability backfill; sibling of 8b-1/8e-1 but **unconditional/baseline**, not battery-gated)
**Builds on:** Plan 4/6 (the baseline observability stack — `prometheus`/`grafana`/`alertmanager` in `dev.yml`, the always-on `slo_alerts.yml` + `slo.json`, the integrity `LOCKED_TRACKED` set), Plan 8c (the §5 battery-observability contract; the workers `celery-exporter` scrape pattern), Plan 8f-1 (the mongodb `mongodb-exporter` — the exporter-as-scrape-source sibling, and the thing that surfaced this gap).

---

## 1. Purpose & scope

The always-on PostgreSQL store — the framework's **primary** datastore — currently has **no dedicated observability**: no exporter, no Prometheus scrape target, no alert rule, no dashboard. The app's `/metrics` exposes only HTTP/SLO metrics; postgres health is implicit (compose `depends_on: service_healthy` + the app's readiness). This gap became visible when Plan 8f-1 gave the **optional** `mongodb` battery *full* §5 observability (a `mongodb-exporter` + scrape + alert + dashboard) — leaving the primary store less observable than an opt-in one.

8i closes the gap by giving postgres the same dev-stack observability mongodb got, but as **baseline** (always rendered), mirroring the existing always-on `slo_alerts.yml`/`slo.json`. **No app code, no battery, no migration** — four config edits + two new always-on files.

**In scope:**
- An always-on `postgres-exporter` service in `dev.yml` (the `dev` profile, like `prometheus`/`grafana`/`mongodb-exporter`).
- An always-on `postgres` scrape job in `prometheus.yml`.
- A new always-on `postgres_alerts.yml` (one robust `PostgresDown` rule) + a `postgres.json` Grafana dashboard, both added to the integrity `LOCKED_TRACKED` set (like `slo_alerts.yml`/`slo.json`).
- The one notable consequence: a **one-time baseline integrity-manifest shift** for all projects (the LOCKED `dev.yml`/`prometheus.yml` gain unconditional lines).

**Out of scope (deferred):**
- **Prod postgres monitoring.** The entire dev monitoring stack — `prometheus`/`grafana`/all exporters — is `profiles: ["dev"]`; prod observability is external/managed. 8i matches `mongodb-exporter`'s dev-only scope. A prod observability story is a separate, larger concern.
- **Richer alerts** (connection saturation `pg_stat_activity_count / pg_settings_max_connections`, high rollback rate) — deferred tunable add-ons; the framework's stance is minimal + tunable defaults.
- **App-process postgres metrics** (a connection-pool gauge on `/metrics`) — the exporter owns DB-level metrics; no in-process `/metrics` change (mirrors how workers/mongodb use an exporter as the scrape source, not the app).

## 2. The exporter service (`infra/compose/dev.yml`, LOCKED)

An **unconditional** service (no `{% if %}`) in the `dev` profile, mirroring the `mongodb-exporter`/`celery-exporter` blocks:
```yaml
  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:v0.16.0
    profiles: ["dev"]
    environment:
      DATA_SOURCE_NAME: "postgresql://app:app@postgres:5432/app?sslmode=disable"
    ports:
      - "9187:9187"
    depends_on:
      postgres:
        condition: service_healthy
```
The DSN uses the dev credentials already present in `dev.yml` (`POSTGRES_USER/PASSWORD/DB = app`), so there is **no secret handling** — these are dev-only, the same posture as the existing exporters. Port `9187` is the postgres_exporter default. Placed alongside the other always-on dev-stack services (after `grafana`, before the gated battery exporters). **`prometheuscommunity/postgres-exporter:v0.16.0`** is the standard maintained exporter (the implementer pins/confirms the exact current stable tag).

## 3. The scrape target (`infra/observability/prometheus/prometheus.yml`, LOCKED)

An **unconditional** `postgres` job, placed after the always-on `prometheus` self-scrape job and **before** the gated `{%- if "workers" %}`/`{%- if "mongodb" %}` blocks (so the always-on jobs stay grouped):
```yaml
  - job_name: postgres
    static_configs:
      - targets: ["postgres-exporter:9187"]
```
The job name `postgres` is what the alert's `up{job="postgres"}` selector keys on (§4) — they must match.

## 4. Alert + dashboard (new always-on, LOCKED-tracked)

Both are **plain** files (no Jinja, always rendered), exactly like `slo_alerts.yml`/`slo.json` — NOT brace-templated battery payload.

- **`infra/observability/prometheus/alerts/postgres_alerts.yml`** — one robust rule mirroring `MongoDBExporterDown` (no exporter-metric-name coupling, no threshold guessing):
  ```yaml
  groups:
  - name: postgres
    rules:
    - alert: PostgresDown
      expr: up{job="postgres"} == 0
      for: 5m
      labels:
        severity: warning
      annotations:
        summary: Postgres exporter target is down (postgres unreachable or exporter crashed) — app-specific default; tune or remove
  ```
- **`infra/observability/grafana/dashboards/postgres.json`** — a "Postgres" dashboard (`uid: "postgres"`), modeled on `slo.json`/`mongodb.json` (same `schemaVersion`/`datasource`/`gridPos` shape), with standard `postgres_exporter` panels: target up (`up{job="postgres"}`), active connections (`pg_stat_database_numbackends` / `pg_stat_activity_count`), commit & rollback rate (`rate(pg_stat_database_xact_commit[5m])` / `rate(pg_stat_database_xact_rollback[5m])`), and cache-hit ratio (`pg_stat_database_blks_hit / clamp_min(pg_stat_database_blks_hit + pg_stat_database_blks_read, 1)`). Plain/`__auto` legends (no `{{...}}`), valid JSON. Auto-provisioned by the existing Grafana file provider (it scans `dashboards/*.json`).

## 5. Integrity — the deliberate baseline-manifest shift

The new `postgres_alerts.yml` + `postgres.json` are added to the **`LOCKED_TRACKED`** tuple in `src/framework_cli/integrity/classes.py` (joining `slo_alerts.yml`/`slo.json`). Because the exporter service + scrape job are **unconditional**, the LOCKED `dev.yml`/`prometheus.yml` now render with the new lines in **every** project — so the integrity **baseline manifest changes for all battery combinations** (not just byte-identical-with-a-battery, the way conditional battery edits are). This is the intended, one-time framework-version effect, the same kind of change `slo` itself was:
- A fresh `framework new` includes the postgres exporter/alerts/dashboard and a manifest that checksums them.
- An existing project picks them up on **`framework upskill`** (Copier update renders the new LOCKED lines + new files; `upskill_project` regenerates the manifest) — closing the gap everywhere, which is the point.

This differs from the conditional battery-obs backfills (8b-1/8e-1: no LOCKED change at all) and from the LOCKED-conditional battery edits (workers/mongodb: byte-identical without the battery). 8i is a **baseline** change — it shifts the floor for everyone.

## 6. Testing

- **Render (`tests/test_copier_runner.py`):** in a **baseline** render (no batteries) — assert the `postgres-exporter` service in `dev.yml`, the `postgres` scrape job in `prometheus.yml`, and `postgres_alerts.yml` (group `postgres`, alert `PostgresDown`) + `postgres.json` (`uid: "postgres"`) all present and valid (YAML/JSON parse). Assert they're present **regardless of battery set** (e.g. also with `["mongodb"]`) — they're baseline, not gated. A baseline ruff-format-clean guard already covers the rendered project; the new files are config (not ruff targets).
- **Integrity (`tests/`):** `framework integrity --ci` on a baseline render is green (the regenerated manifest includes the two new LOCKED files + the changed LOCKED `dev.yml`/`prometheus.yml`). Confirm the integrity-tracked-files test (if one enumerates `LOCKED_TRACKED`) accounts for the two additions.
- **No Docker stack test.** The exporter — like `mongodb-exporter`/`celery-exporter` — is exercised manually via `task dev`; it is not unit-testable, and the acceptance suite runs `pytest` (the app's own tests), not the dev monitoring stack. Validation is: the render tests + integrity + a manual `task dev` + `curl postgres-exporter:9187/metrics` (documented, not automated). This matches how the framework already (does not) automatically test the existing exporters.
- **Existing-suite impact:** because the LOCKED baseline shifts, any test that pins a baseline `dev.yml`/`prometheus.yml` checksum or content must be updated to the new baseline (expected, part of the change).

## 7. Follow-up recorded (not part of 8i)

This gap was caught by a **human during brainstorming, not by a review agent** — the existing `review-observability` agent is diff/code-level (untraced paths, unlogged errors) and does not enforce the §5 *completeness* contract (a new service/store added without metrics+scrape+alert+dashboard+health). Recorded in CLAUDE.md **Known follow-ups**: we want either a new `review-observability-completeness` agent or a framework-side test invariant (every service-adding battery ships an alert+dashboard) to catch this class automatically — partly a framework-authoring check, distinct from the generated-project diff review. Form + scheduling TBD (candidate: alongside Plan 9 dogfooding).

## 8. Self-review

- **Placeholders:** none — the exporter service (image/DSN/port/profile/depends_on), the scrape job, the exact alert rule, the dashboard panel queries, the `LOCKED_TRACKED` additions, the manifest-shift consequence, and the test tiers are all specified. The exact exporter image tag (`v0.16.0`) is the one item the implementer confirms against the current stable release — bounded.
- **Internal consistency:** the alert `up{job="postgres"}` matches the scrape `job_name: postgres`; the exporter port `9187` matches the scrape target and the service `ports`; always-on files mirror `slo`'s plain-file + LOCKED treatment exactly; dev-only scope matches `mongodb-exporter` (no prod claim).
- **Scope:** one cohesive baseline backfill (exporter + scrape + alert + dashboard + the LOCKED additions); prod monitoring, richer alerts, and the observability-completeness review agent are explicitly deferred/recorded.
- **Ambiguity:** "baseline" pinned to *unconditional/always-rendered + LOCKED-tracked* (not battery-gated, not opt-in); "minimal alerting" pinned to a single `PostgresDown` (= mongodb parity); the manifest shift pinned as the intended one-time framework-version effect (vs the no-impact 8b-1/8e-1 backfills).

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8i.*
