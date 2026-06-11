# Services

A scaffolded project runs as a set of Docker Compose services. Which services exist depends on the batteries you chose at `framework new`; *how* they run differs between local development and staging/production. This page is the map of those services and how they shift across environments. Your generated project also ships a `SERVICES.md` listing the exact internal/external addresses for your specific battery set.

## How the Compose files layer

The services aren't defined in one big file — they're composed from focused overlays that Compose merges left to right. The base application definition lives in `infra/compose/base.yml`; each environment adds the overlays it needs:

| Environment | Compose merge | Brought up by |
|---|---|---|
| Local full (`dev`) | `base.yml` + `observability.yml` + `dev.yml`, `--profile dev` | `task dev` |
| Local lite (`lite`) | `base.yml` + `dev.yml`, `--profile lite` | `task dev:lite` |
| Staging | `staging.yml` + `services.yml` + `observability.yml` | the deploy strategy |
| Production | `prod.yml` + `services.yml` + `observability.yml` | the deploy strategy |

The dividing line is the **image**. In dev, the app (and worker/beat) services *build* from `infra/docker/Dockerfile` and bind-mount `src/` for hot reload. In staging and prod, every long-running service runs the **same promoted registry image** via `${APP_IMAGE}` — no build, no bind mount, no dev tooling. That single substitution is the core of "dev equals prod": the same definitions, run from a different image.

## The always-present services

Every project, regardless of batteries, has these two:

| Service | Internal address | In dev | In staging/prod |
|---|---|---|---|
| **app** | `app:8000` | builds locally; `--reload`; runs as your host UID/GID so bind-mounted writes aren't root-owned | runs `${APP_IMAGE}`; `restart: unless-stopped`; liveness healthcheck recovers a wedged process |
| **postgres** | `postgres:5432` | `postgres:17`, published on `localhost:5432` for host tooling (`psql`, `task db:migrate`) | `postgres:17` (or a custom image — see below), volume-backed, not published |

The app's health is probed at `/heartbeat` (liveness), with `/health` reporting readiness + SLO state and `/metrics` exposing Prometheus data. In dev, Traefik fronts the app over HTTPS at `https://<project-slug>.localhost`; in staging/prod the app listens on `8000:8000` behind your own load balancer.

A short-lived **`postgres-test`** also exists in the `test` profile — an ephemeral database the test tiers spin up and tear down, isolated from your dev data.

## The observability stack

The full monitoring stack ships in `infra/compose/observability.yml` and runs in **every** environment except `dev:lite`: Prometheus (scrapes `app:8000/metrics`, loads the SLO alert rules), Grafana (the auto-provisioned SLO dashboard), Alertmanager (fires on SLO-breach rules), Loki + Promtail (log store + shipper), and Tempo + the OpenTelemetry Collector (trace store + receiver). Because it's the same overlay everywhere, the SLO dashboard you see locally is the one that runs in production. `dev:lite` is the single mode that opts out — it's the resource-light "just the API" option. See [Observability](observability.md) for what the stack reports.

The one deliberate dev-vs-prod difference is Grafana auth: dev overrides it to anonymous-admin (no login) for convenience; staging and prod require a real password via `GRAFANA_ADMIN_PASSWORD`.

## Battery services

Batteries add data stores and background processing. These appear only if you selected the corresponding battery:

| Service | Battery | Image | Purpose |
|---|---|---|---|
| **mongo** | `mongodb` | `mongo:7` | Document store (`APP_MONGO_URL`) |
| **redis** | `redis` or `workers` | `redis:7-alpine` | Cache / broker (`APP_REDIS_URL`) |
| **worker** | `workers` | `${APP_IMAGE}` (prod) / built (dev) | Celery worker — runs your task code |
| **beat** | `workers` | `${APP_IMAGE}` (prod) / built (dev) | Celery beat — scheduled tasks |
| **frontend** | `react` | `node:22` (dev only) | Vite dev server on `5173` |

In dev, these data stores are profiled into `dev.yml` and publish host ports (Mongo on `27017`, Redis on `6379`) so you can connect from your machine. In staging/prod they're defined in `infra/compose/services.yml` instead, volume-backed and unpublished.

The **worker** and **beat** services are notable: they aren't separate codebases — they run the *same* application image with a different command (`celery ... worker` / `celery ... beat`). In production they run `${APP_IMAGE}` with `APP_RUN_MIGRATIONS=false`, because the app (or a pre-roll migrate step) runs `alembic upgrade head` exactly once — workers must not race it. They reach Postgres and Redis over the Docker network via the in-network `APP_*` URLs.

## Self-host by default, managed by escape hatch

Out of the box the data stores are **self-hosted** containers — nothing external to provision, and dev mirrors prod. But you're not locked in. To use a managed Postgres, MongoDB, or Redis instead, point the relevant `APP_*` URL at the managed endpoint (as a target secret) and **omit that data-store service from the Compose merge**:

| Managed target | Set | Then omit |
|---|---|---|
| Postgres | `APP_DATABASE_URL` | the `postgres` service |
| MongoDB | `APP_MONGO_URL` | the `mongo` service |
| Redis | `APP_REDIS_URL`, `APP_CELERY_BROKER_URL`, `APP_CELERY_RESULT_BACKEND` | the `redis` service |

The application doesn't change — it reads the same env var either way. Worker and beat stay self-hosted (they *are* your app image) and simply connect to the managed broker through those URLs.

### Custom Postgres for extension batteries

If you enabled a Postgres-extension battery (pgvector, TimescaleDB, Apache AGE), the dev/test Postgres builds a custom image from `infra/docker/postgres.Dockerfile` (baking in the extension and, where needed, a `shared_preload_libraries` setting). Staging and prod reference that image via `${POSTGRES_IMAGE}`, which you build and push alongside `APP_IMAGE`. The managed escape hatch still applies where the provider offers the extension (e.g. RDS or Cloud SQL with pgvector, Timescale Cloud); AGE is rarely managed, so self-host the custom image there.

For how these services are placed and validated on a real target, see [Deploy](deploy.md).
