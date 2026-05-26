# Battery Services in Staging/Prod (SVC-PROD) — Design Spec

**Date:** 2026-05-26
**Status:** Approved (brainstorm) — not yet planned/implemented
**Plan:** SVC-PROD (a prod-correctness defect fix; sibling of OBS-PROD — the same dev-only-not-prod class, but for *functional* battery runtime rather than observability).
**Builds on:** OBS-PROD (the `observability.yml` overlay pattern + the `strategy.sh` deploy-merge guidance + the exporters it left dev-only), Plan 8c (workers — the celery worker/beat + `entrypoint.sh` `APP_RUN_MIGRATIONS` gate), Plan 8f-1 (mongodb — the mongo service + `mongodb-exporter`).

---

## 1. Purpose & scope

`prod.yml`/`staging.yml` define only `app` + `postgres`. The battery services and processes — `mongo`, `redis` (data stores), `worker`, `beat` (celery processes), and the `mongodb-exporter`/`celery-exporter` — live **only in `dev.yml`** (`profiles: ["dev"]`/`["dev","lite"]`). So a project using the **`mongodb`** or **`workers`** battery, deployed to staging/prod, is missing them: **no worker/beat → background tasks never run and the beat schedule never fires; no mongo/redis → the app can't reach its document store / broker.** This is a *functional* prod gap (the app is broken/incomplete in prod), arguably more severe than the OBS-PROD observability gap.

SVC-PROD gets the battery services + processes into staging/prod, **self-hosted by default** (containers in a prod/staging overlay — consistent with the not-BYO stance and OBS-PROD), with the env-overridable URLs as the **documented managed-instance escape hatch**. It also **closes OBS-PROD's loop**: with the data stores now present in prod, the `mongodb-exporter`/`celery-exporter` move into the `observability.yml` overlay and finally run in all obs environments.

**In scope:**
- A new `infra/compose/services.yml.jinja` overlay (prod/staging) defining gated `mongo`/`redis` (persistent) + `worker`/`beat` (`image:${APP_IMAGE}` + celery command + `APP_RUN_MIGRATIONS:false`).
- Merge into staging/prod via `strategy.sh`/README guidance (`-f $DEPLOY_ENV.yml -f services.yml -f observability.yml`).
- Move `mongodb-exporter`/`celery-exporter` from `dev.yml` into `observability.yml` (gated) so they run wherever obs runs.
- Documented managed-instance escape hatch.
- `services.yml` → `LOCKED_TRACKED`; tests (render + `docker compose config` merge-validation + an image-drift guard).

**Out of scope (deferred / recorded):**
- **HA/clustering/replication** of the self-hosted stores (single-host compose; the builder owns backups — the same posture as the already-self-hosted prod postgres).
- **The unified `8f-w` wizard** (db-paradigm + alert-channel selection).
- **Restructuring `dev.yml`** (the dev battery blocks stay; see §7).
- **Non-compose prod hosting** (k8s, etc.).

## 2. Architecture — a prod/staging-only `services.yml` overlay

The framework already splits the **app** by environment: `base.yml` defines it as `build:` (dev), and `prod.yml`/`staging.yml` redefine it as `image:${APP_IMAGE}` (the promoted image). Battery services follow the **same intentional dev/prod split** rather than a shared overlay:

- **`infra/compose/services.yml.jinja`** (NEW, LOCKED) — the **prod/staging** definition of battery services. Gated blocks, **no compose profiles** (they run whenever the overlay is merged). Merged into staging/prod by the deploy (`strategy.sh` guidance), NOT into dev.
- **`dev.yml` is unchanged** — it keeps the dev-oriented battery blocks (`mongo`/`redis` at `profiles:["dev","lite"]`; `worker`/`beat` `build:` at `profiles:["dev"]`). So **`task dev` and `task dev:lite` are untouched** — no regression, no change to the `dev:lite` "app + DB + Redis" semantics.

This deliberately accepts **parallel battery-service definitions** (`dev.yml` for dev/lite, `services.yml` for prod/staging) — the same kind of dev/prod duplication the app already has (`base.yml`+`dev.yml` vs `prod.yml`/`staging.yml`). It's the lower-risk choice: moving the battery blocks into a single shared overlay (the OBS-PROD approach) breaks down here because the **data stores are app dependencies needed in `dev:lite`** (which opts out of overlays) and **worker/beat are `build:` in dev vs `image:` in prod**. A render test guards image drift between the two definitions (§9).

(Rejected alternatives: a single shared overlay merged everywhere — fails the `dev:lite`-needs-data-stores + build-vs-image constraints; inline battery blocks in `prod.yml`/`staging.yml` — works but bloats those LOCKED files and forks staging/prod copies.)

## 3. `services.yml` contents

Gated by battery, no profiles, `image:${APP_IMAGE}` for the processes. Mirrors the dev blocks but prod-shaped (image not build; persistence; no dev-only port exposure unless useful):

```yaml
# Battery-service overlay for staging/prod — merged by the deploy (strategy.sh) alongside
# observability.yml. Defines the battery data stores + worker/beat for prod/staging; dev keeps
# its own (build-based, profiled) copies in dev.yml. (Managed alternative: set APP_MONGO_URL /
# APP_REDIS_URL / APP_CELERY_* to a managed instance and omit the data-store services here.)
services:
{% if "mongodb" in batteries %}
  mongo:
    image: mongo:7
    restart: unless-stopped
    healthcheck: {test: ["CMD-SHELL", "mongosh --quiet --eval \"db.adminCommand('ping').ok\" | grep -q 1"], interval: 5s, timeout: 3s, retries: 10, start_period: 10s}
    volumes:
      - "mongodata:/data/db"
{% endif %}
{% if "workers" in batteries %}
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck: {test: ["CMD", "redis-cli", "ping"], interval: 5s, timeout: 3s, retries: 10}
    volumes:
      - "redisdata:/data"

  worker:
    image: ${APP_IMAGE:?set APP_IMAGE to the promoted registry tag}
    restart: unless-stopped
    command: ["celery", "-A", "{{ package_name }}.tasks.app", "worker", "--loglevel=info"]
    environment:
      APP_RUN_MIGRATIONS: "false"   # the app (or the pre-roll) migrates once; workers must not race
      APP_DATABASE_URL: "postgresql+psycopg://app:${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}@postgres:5432/app"
      APP_REDIS_URL: "redis://redis:6379/0"
      APP_CELERY_BROKER_URL: "redis://redis:6379/0"
      APP_CELERY_RESULT_BACKEND: "redis://redis:6379/1"
    healthcheck: {test: ["CMD", "celery", "-A", "{{ package_name }}.tasks.app", "inspect", "ping"], interval: 15s, timeout: 10s, retries: 5, start_period: 20s}
    depends_on:
      redis: {condition: service_healthy}
      postgres: {condition: service_healthy}

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
      redis: {condition: service_healthy}
{% endif %}

volumes:
{% if "mongodb" in batteries %}  mongodata: {}
{% endif %}{% if "workers" in batteries %}  redisdata: {}
{% endif %}
```
(The implementer pins exact formatting/whitespace control so the file is valid YAML for every battery combo, including **neither battery present** — then `services.yml` renders to a near-empty `services: {}`/no-op that still merges cleanly. Inline-map healthchecks shown for brevity; the implementer may expand to block style to match `dev.yml`.)

Notes:
- `restart: unless-stopped` (prod posture, matching `prod.yml`'s app/postgres) — unlike dev.
- `worker`/`beat` = `image:${APP_IMAGE}` (the promoted image; the same `:?` validation `prod.yml` uses), command overrides the entrypoint's uvicorn with celery, `APP_RUN_MIGRATIONS:false`.
- No published `ports` (in-network only; the dev blocks publish ports for host tooling — prod doesn't need to).
- `depends_on: postgres`/`redis` resolve against `prod.yml`'s postgres + this overlay's redis in the merged project.

## 4. Exporters move to `observability.yml` (closes OBS-PROD's loop)

Move the `mongodb-exporter` + `celery-exporter` blocks **out of `dev.yml`** and **into `observability.yml.jinja`** (gated `{% if "mongodb" %}`/`{% if "workers" %}`, no profiles). Because `observability.yml` is merged into dev-full/staging/prod (not `dev:lite`), and the exporters' `depends_on` services (mongo/redis) are present wherever obs runs (`dev.yml` in dev, `services.yml` in prod/staging), they now run in **all obs environments** — delivering the battery metrics in prod that OBS-PROD deferred. `dev:lite` keeps no exporters (no obs overlay), as today. The Prometheus scrape jobs for `celery`/`mongodb` already exist (gated in `prometheus.yml`); no scrape change needed.

## 5. Migration discipline

`worker`/`beat` run the app image but set `APP_RUN_MIGRATIONS: "false"` (the `entrypoint.sh` gate), so they never run `alembic upgrade head` — only the app (single-host) or the deploy's once-before-roll step migrates. This is the existing multi-instance discipline (already documented in `infra/deploy/README.md`); SVC-PROD just applies it to the prod worker/beat, exactly as `dev.yml` does for the dev ones.

## 6. Managed-instance escape hatch (documented)

`infra/deploy/README.md` gains a short note: a team preferring a managed data store points `APP_MONGO_URL` / `APP_REDIS_URL` / `APP_CELERY_BROKER_URL` / `APP_CELERY_RESULT_BACKEND` at the managed endpoint (target secrets) and **omits the data-store services** from the deploy merge (e.g. a trimmed overlay, or just doesn't run them) — `worker`/`beat` stay self-hosted (they're the app image) and connect to the managed broker. Self-host is the default; managed is the opt-out.

## 7. `dev.yml`/`dev:lite` unchanged + the drift guard

`dev.yml`'s battery blocks (mongo/redis profiles `[dev,lite]`; worker/beat `build:` profiles `[dev]`) stay exactly as-is — `task dev`/`dev:lite` are untouched (no regression, the `dev:lite` data-store semantics preserved). The **exporters** are the only `dev.yml` removal (they relocate to `observability.yml`, §4) — dev still gets them via the obs overlay it already merges. The cost of the parallel dev/prod definitions (drift between `dev.yml`'s `mongo:7`/`redis:7-alpine` and `services.yml`'s) is guarded by a render test asserting the images match across the two files (§9).

## 8. Integrity & consistency

`services.yml.jinja` is a new `LOCKED_TRACKED` file. `dev.yml` changes (exporters removed) and `observability.yml` changes (exporters added) — both LOCKED, both battery-conditional (byte-identical without the relevant battery; the workers/8c precedent). `prod.yml`/`staging.yml` are **untouched** (the overlay merges at deploy). `strategy.sh`/`README` guidance updated (LOCKED). Net: a **one-time baseline manifest shift** for all projects (same class as OBS-PROD) — fresh `framework new` includes it; existing projects get it on `framework upskill`.

## 9. Testing

- **Render (`tests/test_copier_runner.py`):** with `["workers"]` → `services.yml` has `redis`/`worker`/`beat` with `image:${APP_IMAGE}` + `APP_RUN_MIGRATIONS:false`; with `["mongodb"]` → `services.yml` has `mongo` + the volume; with neither → `services.yml` renders as a valid no-op (no battery services). Exporters now in `observability.yml` (gated), gone from `dev.yml`. `dev.yml`'s dev battery blocks unchanged. **Image-drift guard:** assert `dev.yml` and `services.yml` reference the same `mongo:`/`redis:` image tags.
- **Merge-validation (`docker compose config`, docker available):** `-f prod.yml -f services.yml -f observability.yml` with `["workers","mongodb"]` → exit 0; merged config includes `worker`, `beat`, `redis`, `mongo`, `app`, `postgres`, `mongodb-exporter`, `celery-exporter`; `worker`/`beat` use `${APP_IMAGE}` + `APP_RUN_MIGRATIONS=false`. `-f base.yml -f dev.yml --profile lite config` (no overlays) → still has the data stores, no worker/beat/exporters (dev:lite unchanged).
- **Integrity:** `framework integrity --ci` green on baseline + `--with workers,mongodb` renders; `LOCKED_TRACKED` includes `services.yml`.
- **No live-stack test for prod** (can't stand up real prod in CI) — `docker compose config` is the honest wiring proof, consistent with OBS-PROD. The dev live-stack acceptance tests (workers/mongodb) already exercise the dev worker/beat path.

## 10. Self-review

- **Placeholders:** none material — the overlay contents (with `image:${APP_IMAGE}`, the celery commands, `APP_RUN_MIGRATIONS:false`, persistence), the exporter relocation, the migration discipline, the managed escape hatch, the integrity changes, and the test tiers are specified. The exact YAML whitespace/healthcheck style + the neither-battery no-op render are the implementer-pinned details (§3).
- **Internal consistency:** prod/staging-only overlay mirrors the app's existing dev/prod definition split (not a new pattern); `dev.yml` untouched preserves `dev:lite`; exporters relocate to where their services are guaranteed present (obs envs); worker/beat `APP_RUN_MIGRATIONS:false` matches `entrypoint.sh` + the dev blocks; the managed escape hatch uses the already-env-overridable URLs.
- **Scope:** one cohesive fix — battery services/processes in prod/staging + the exporter loop-closure. HA, the wizard, and `dev.yml` restructuring are deferred.
- **Ambiguity:** "self-host" pinned to containers in `services.yml` (managed = the documented URL opt-out); "in prod" pinned to the deploy-time `-f prod.yml -f services.yml -f observability.yml` merge (the builder's place-image hook, guided — like OBS-PROD); the parallel-definition tradeoff pinned (accepted, drift-guarded) over a `dev.yml` restructure.

---

*End of design. Next step: `superpowers:writing-plans` for SVC-PROD.*
