# Workers Battery (Plan 8c) — Design Spec

**Date:** 2026-05-24
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 8a-1 (the battery mechanism: `batteries.py` registry, `--with`, conditional rendering, router/module autodiscovery, the framework-owned `batteries` record), Plan 8b (the `handle_event` dispatch seam designed to compose with workers; the first managed-section injection + the integrity coupling), Plan 8a-2 (battery removal — `downskill` is the inverse of the env injection + manifest regen), Plan 3c (DB layer: models/`Base`/session/Alembic), Plan 4 (recoverability scaffold — retry/circuit-breaker/recoverability metrics; **DLQ was explicitly deferred to here**), Plan 3a/3b (the `/metrics` + `/health` registry pattern and the Prometheus → Alertmanager → Grafana observability stack).

---

## 1. Purpose & scope

The `workers` battery scaffolds **asynchronous background processing**: Celery + Redis, a tasks package the builder extends, a base task with bounded retry that drains exhausted tasks into a **DB-backed dead-letter queue** (the DLQ deferred from Plan 4), a Celery **beat** scheduler whose example periodic task is a **heartbeat**, and — formalized here for the first time — a **battery observability contract** that workers implements end-to-end (metrics on the same Prometheus pipeline, a liveness signal, alert rules, a dashboard).

**`workers` is a standalone battery.** It depends on nothing (`requires=()`), and nothing requires it. Its use cases are independent of webhooks: scheduled jobs, async email/notifications, report generation, image processing, any slow I/O moved off the request path. The webhooks composition (§7) is an **optional, additive enhancement** that only manifests when both batteries happen to be present.

**In scope:**
- A `{{package_name}}/tasks/` package: `app.py` (Celery app), `base.py` (retry + DLQ `on_failure`), `dead_letter.py` (model + repository), `tasks.py` (example task seam + heartbeat), `schedule.py` (beat schedule seam).
- A **DB transactional dead-letter table** (`dead_letter_tasks`) + a conditional Alembic migration, **solving multi-battery migration ordering** via a templated `down_revision`.
- **Celery beat** + a heartbeat task feeding a liveness marker that `/health` reads.
- The **battery observability contract** + workers' full implementation: a `celery-exporter` scrape target, a DB-backed DLQ-depth gauge on `/metrics`, container healthchecks, alert rules, a Grafana panel.
- **Managed-section / settings injection:** `APP_CELERY_*` into `.env.example`'s checksummed section + `settings.py` fields (the **second** managed-section injection after webhooks).
- The **additive webhooks composition** (§7): when both batteries are present, the rendered webhooks handler stub dispatches to a Celery task instead of running inline.
- The **review-architecture heuristic** (§8): the existing always-on agent gains a "heavy work inline → use the workers battery" finding + one golden eval fixture.
- A one-line clarifying comment in the core `/health` route (the per-instance-SLO nuance, §5).

**Out of scope (deferred):**
- **Webhooks observability backfill → Plan 8b-1; websockets observability backfill → Plan 8e-1** (fast-follow slices; both implement the §5 contract). Recorded as explicit meta-plan rows.
- A **3rd migration-shipping battery's** ordering (a total-order helper or `alembic merge`) → revisit at **8f** (db paradigms add more migrations). v1 solves the 2-battery case concretely (§3).
- **Multi-replica prod scrape topology** → a deployment concern; the baseline observability design is already cross-host-correct (§5), so no rework here.
- **DLQ replay tooling** (a CLI/route to re-enqueue dead-lettered tasks) → the repository exposes `list_recent`/`count` now; replay is a later convenience, not v1.
- **Flower** or a task-monitoring UI → `celery-exporter` + Grafana cover observability; a UI is YAGNI for v1.

## 2. Architecture & components

A battery-conditional `{{package_name}}/tasks/` package (the `{% if "workers" in batteries %}tasks{% endif %}/` dir pattern, mirroring `webhooks/`):

- **`app.py`** — the Celery application: `Celery(__name__, broker=settings.celery_broker_url, backend=settings.celery_result_backend)`. Opinionated defaults: `task_acks_late=True` + `task_reject_on_worker_lost=True` (a task re-runs if a worker dies mid-flight), JSON serializer, UTC, `task_default_queue` named for the service. Autodiscovers `tasks.py`.
- **`base.py`** — `class BaseTask(celery.Task)`: bounded `autoretry_for=(Exception,)`, `max_retries`, `retry_backoff=True` + `retry_backoff_max` + `retry_jitter=True`. Its **`on_failure(exc, task_id, args, kwargs, einfo)`** fires only after retries are exhausted (Celery calls it on terminal failure) and writes one `dead_letter_tasks` row via the repository. This is the DLQ's single choke point — every task on `BaseTask` is covered.
- **`dead_letter.py`** — `DeadLetterTask` (SQLAlchemy model on the project `Base`: `id`, `task_name`, `task_id`, `args_json`, `traceback`, `failed_at`) + a small repository: `record_failure(session, *, task_name, task_id, args_json, traceback)`, `count(session)`, `list_recent(session, limit)`. `count` feeds the gauge (§5); `list_recent` is the seam for future replay.
- **`tasks.py`** — the **builder seam**: an example `@app.task(base=BaseTask, bind=True) def process_async(self, payload: dict) -> None` clearly marked "replace with your logic," plus the **`heartbeat`** task (§4). Its module docstring states the discipline: this is where work moved off the request path lives.
- **`schedule.py`** — the **beat schedule** seam: registers `heartbeat` on `app.conf.beat_schedule` at a fixed interval; documented as the place to add periodic jobs.

Each unit has one responsibility and a clear interface: `app` is configuration, `base` is the retry/DLQ policy, `dead_letter` is persistence, `tasks`/`schedule` are the builder seams.

## 3. The DLQ & migration ordering

**The dead-letter table.** `dead_letter_tasks` is created by a conditional migration rendered only when the battery is active. Failed tasks (retries spent) land here durably — queryable, inspectable, replay-able later — composing with Plan 4's recoverability metrics (it is the terminal sink the `retries_exhausted` counter anticipated).

**Migration ordering (solved, not deferred).** Alembic revision ids are arbitrary strings (the `000N` form is convention, not a requirement), so each battery migration keeps a **stable own id** and templates only its `down_revision` to chain off the current head for the active battery set:

| Migration | `revision` | `down_revision` |
|---|---|---|
| core initial | `0001` | `None` |
| webhooks (8b) | `0002_webhook_events` | `0001` (unchanged) |
| workers (8c) | `0003_dead_letter` | `{{ '0002_webhook_events' if 'webhooks' in batteries else '0001' }}` |

So: workers-alone chains off `0001`; workers+webhooks chains off `0002_webhook_events`, giving a single linear history `0001 → 0002 → 0003` with `alembic upgrade head` clean either way.

**The documented convention:** battery migrations form a linear chain in a fixed order (core `0001` → webhooks → workers); each battery templates its `down_revision` from the highest active migration-shipping battery below it. **Known wrinkle (recorded for 8f):** this hand-ordering does not scale past a small fixed set — a 3rd migration-shipping battery needs a defined total order or `alembic merge`. v1 (two such batteries) is solved concretely; 8f revisits the general mechanism when db-paradigm batteries add migrations.

## 4. Beat, heartbeat & healthchecks

- The **example periodic task *is* the heartbeat** (so beat ships a useful, working seam, not a no-op): on each tick it writes a liveness marker — a TTL'd Redis key `{service}:worker:heartbeat` set to the current timestamp.
- The app's **`/health`** reads that marker (only when the battery is present — the health route's worker check is gated `{% if "workers" in batteries %}`): a fresh marker → workers healthy; stale/absent → degraded. This is the liveness signal the contract (§5) requires for a process-bearing battery.
- **Container healthchecks** (dev compose): `redis` (`redis-cli ping`), `worker` (`celery -A {{package_name}}.tasks.app inspect ping`), `beat` (heartbeat-file freshness), `celery-exporter` (HTTP on its metrics port).

## 5. The battery observability contract (formalized) + workers' implementation

**The contract** — every battery that adds a runtime surface ships:
1. **Metrics** on the Prometheus pipeline (either appended to the app's `/metrics` exposition, or a dedicated scrape target).
2. A **liveness signal** wherever it runs a process (surfaced via `/health` or a healthcheck).
3. **Alert rule(s) + dashboard panel(s)** so the signal reaches Alertmanager/Grafana.

This is the standard 8b-1/8e-1 will also satisfy; it closes the gap that 8b/8e shipped without observability.

**Workers' implementation:**
- **Task-level metrics — a `celery-exporter` sidecar** (its own Prometheus scrape target): task sent/received/started/succeeded/failed/retried, runtime histograms, queue length, worker-up. Zero application code; it joins the *same* Prometheus → Alertmanager → Grafana pipeline. This is consistent with the framework's "real infra as dev-compose containers" pattern (Prometheus/Loki/Tempo are already containers).
- **DLQ depth** — `app_dead_letter_tasks` gauge appended to the app's `/metrics` via a DB `count(*)`, following the `recoverability.render_prometheus()` append pattern in `routes/health.py`. Cross-host-correct because the DB is the shared source of truth (any app instance reports the same global count).
- **Alert rules** (extend `infra/observability/prometheus/alerts/slo_alerts.yml`): worker-down, beat-heartbeat-stale, `app_dead_letter_tasks > 0`.
- **Grafana** (`infra/observability/grafana/dashboards/`): a workers panel/row — queue depth, task success/failure rates, DLQ size.

**Observability topology (intentional design, written so it isn't misread):**
- Per-process exposition + **Prometheus as the cross-host aggregator** is the standard model: each process exposes only its own local counters; Prometheus scrapes each target, labels by `instance`/`job`, and aggregation happens at query time in Grafana. The framework's in-process `MetricsRegistry` works exactly like `prometheus_client`. The baseline is already cross-host-capable.
- **Workers/beat/exporter are independent scrape targets**, not funneled through the FastAPI process. The only workers metric on the app's `/metrics` is the DLQ gauge (correct because it reads the shared DB).
- **`/health`'s SLO report is per-instance by design** — `build_health_report` reads the local `app.state.metrics`, so each instance judges itself (correct for a load-balancer liveness/readiness probe). The **global SLO view is Grafana**, not `/health`. With a single dev instance the distinction is invisible; it matters once replicas scale. **A one-line clarifying comment is added to the core `/health` route** (this plan) to prevent mistaking `/health` for a fleet-wide SLO oracle.

## 6. Settings, env injection & integrity

- **`settings.py.jinja`** (builder-extendable, **not** checksummed): `celery_broker_url: str`, `celery_result_backend: str`, `redis_url: str` fields, gated `{% if "workers" in batteries %}`.
- **`.env.example.jinja`** managed section (`FRAMEWORK:BEGIN/END`, checksummed hybrid): inject `APP_CELERY_BROKER_URL=redis://redis:6379/0` and `APP_CELERY_RESULT_BACKEND=redis://redis:6379/1`, gated `{% if "workers" in batteries %}`. This is the **second managed-section injection** (after webhooks) — it exercises, not extends, the mechanism.
- **Integrity coupling — already handled, reused:** `framework new --with workers` checksums the battery-active section; `framework upskill --with workers` regenerates the manifest (8b); `framework downskill workers` (8a-2) is the inverse (re-render the section at the reduced set + regenerate). No new integrity work — workers is the first battery to *reuse* the injection path webhooks built, validating its generality.

## 7. Webhooks composition (additive, opt-in)

Neither battery requires the other (§1). **When both `webhooks` and `workers` are present**, the rendered `webhooks/handler.py` stub demonstrates the worker path:

- **webhooks alone** (8b behavior, byte-identical): `handle_event` logs the event inline.
- **webhooks + workers**: `handle_event` calls `process_async.delay(event)` (enqueue, return fast), with a comment explaining the swap and the fast-return discipline.

The composition lives **entirely in the seam's rendered default** — no route change, no `webhooks/route.py` edit (matching the 8b promise that "workers drops in with no route change"). It is conditional template content keyed on both tokens being in `batteries`. This is the canonical demonstration of the dispatch seam composing; the builder owns it thereafter.

## 8. Review-architecture heuristic + eval

- **Extend the existing always-on `review-architecture` agent** (`src/framework_cli/review/agents/architecture.md`): add a finding for **heavy/blocking synchronous work in a request handler** — external HTTP calls, large/long writes, `time.sleep`, loops over remote I/O — recommending it be moved behind the **workers** battery (`framework upskill --with workers`, dispatch from the seam). If workers is already present, the recommendation is to dispatch rather than run inline. **Keyed on *heavy* work, not *any* inline handler** — the lightweight inline webhook is legitimate and must not be flagged.
- **Add one golden eval fixture** (`tests/eval/fixtures/`): a route doing obvious heavy inline work → expects the finding; the existing lightweight handler → expects no finding (a negative anchor). Add the threshold entry. This is a **minimal** addition to the still-hermetic eval harness (one fixture on an existing agent), keeping Plan 9's validation surface small.

## 9. Docker compose & Taskfile

- **`infra/compose/dev.yml.jinja`** — conditional services gated `{% if "workers" in batteries %}` (profile `["dev"]`): `redis` (`redis:7-alpine`, healthcheck), `worker` (the app image, command `celery -A {{package_name}}.tasks.app worker`, `depends_on: redis`), `beat` (command `celery -A {{package_name}}.tasks.app beat`), `celery-exporter` (scrape target). The `app` service gains `depends_on: redis` when active. A `redisdata` named volume.
- **Prometheus scrape config** — add the `celery-exporter` target (conditional).
- **`Taskfile.yml.jinja`** — `task worker` and `task beat` (run a worker/beat locally) in the builder section (below `FRAMEWORK:END`).

## 10. Testing

- **Unit (hermetic, `task_always_eager=True`):** base task retry config is bounded; `on_failure` writes exactly one `dead_letter_tasks` row with the task name/traceback; the heartbeat task writes the liveness marker; the DLQ repository `count`/`list_recent` behave; `/health` reports degraded when the marker is stale.
- **Render (`tests/test_copier_runner.py`):** `batteries=["workers"]` → the tasks package, the migration (`down_revision="0001"`), the `.env.example` lines (inside the markers), the `settings.py` fields, and the compose services all render; without it → none, and `.env.example`/compose are unchanged. `batteries=["webhooks","workers"]` → the workers migration's `down_revision` is `0002_webhook_events` **and** the webhooks handler stub enqueues (`process_async.delay`).
- **Integrity:** `framework new --with workers` → `framework integrity --ci` green (battery-active section checksum matches); `framework upskill --with workers` (real `run_update`) → the env lines inject AND `integrity --ci` passes (manifest regenerated) — reuse the 8b harness.
- **Acceptance (Docker):** a `--with workers` rendered project against **real Redis + a worker container**: an enqueued task executes; a deliberately-failing task exhausts retries and lands in `dead_letter_tasks` (asserting the gauge increments); the generated suite + coverage gate pass. A `--with webhooks,workers` variant proving (a) the enqueue composition and (b) the migration chain `0001 → 0002_webhook_events → 0003_dead_letter` via `alembic upgrade head`.
- **Eval (hermetic; scored only on a real key in Plan 9):** the new architecture fixture asserts the heavy-inline finding fires and the lightweight handler does not.

## 11. Follow-ups recorded

- **Plan 8b-1** — webhooks observability (event counters by type/outcome, dedup count, alert/dashboard) implementing the §5 contract.
- **Plan 8e-1** — websockets observability (active-connections gauge, message counters, alert/dashboard) implementing the §5 contract.
- **8f** — revisit the general migration-ordering mechanism (total order / `alembic merge`) once db-paradigm batteries add more migrations.
- **Later** — DLQ replay tooling (re-enqueue from `dead_letter_tasks`); the repository already exposes the read side.

## 12. Self-review

- **Placeholders:** none — the package layout, the retry→DLQ choke point, the templated migration ordering (with a concrete table), beat/heartbeat/healthchecks, the observability contract + the `celery-exporter`/DLQ-gauge split, the env injection (reusing 8b), the additive composition, the review heuristic + fixture, and the test tiers are all concrete. Backfills, the N>2 ordering mechanism, replay, and prod scrape topology are explicitly deferred (not hand-waved), each with where it lands.
- **Internal consistency:** `BaseTask.on_failure` is the single DLQ sink the recoverability metrics (Plan 4) anticipated; the migration `down_revision` template is consistent with the webhooks `0002` it chains off; the observability topology section reconciles the per-process registry with Prometheus-as-aggregator and pins the `/health`-is-per-instance nuance; the env-injection reuse confirms the 8b mechanism generalizes; the composition matches 8b's "no route change" promise.
- **Scope:** one cohesive battery (queue + retry + DLQ + beat + observability) plus two tightly-bounded cross-cutting deliverables it is the natural home for (the additive webhooks composition; the review heuristic). Backfills split out so 8c stays focused.
- **Ambiguity:** "DLQ" is pinned to a DB `dead_letter_tasks` table fed by `BaseTask.on_failure`; "metrics" split explicitly between the `celery-exporter` scrape target (task metrics) and the app `/metrics` DB gauge (DLQ depth); "heartbeat" pinned to a TTL'd Redis marker read by a gated `/health` check; the review heuristic pinned to *heavy* inline work with a negative anchor fixture.

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8c.*
