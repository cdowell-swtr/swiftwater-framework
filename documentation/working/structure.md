# Project structure

A scaffolded project has a deliberate, predictable shape. Everything has a home, and the layout is the same in every project the framework generates — so once you know where things live in one project, you know where they live in all of them.

This page is a map of that layout. (Names below use `your_package` for the Python package the framework derives from your project name.)

## The top level

```text
.
├── src/your_package/        # the application
├── tests/                   # the test tiers (unit / functional / e2e / smoke / sniff / non_functional)
├── migrations/              # Alembic migration history (versions/ holds each revision)
├── seeds/                   # seed data loaded by `task db:seed`
├── scripts/                 # operational scripts (coverage, migrations check, entrypoint, …)
├── infra/                   # everything to run and deploy: Docker, Compose, observability, Traefik
├── Taskfile.yml             # the task runner — your day-to-day commands
├── pyproject.toml           # dependencies, build config, test/coverage config
├── alembic.ini              # Alembic configuration
├── .pre-commit-config.yaml  # the local quality gate
├── CLAUDE.md                # Claude Code's guide to working in this project
├── README.md                # project README
├── SECRETS.md               # the secrets your project needs, with your specific values
├── SERVICES.md              # the services your project runs
└── DEPLOY.md                # how to deploy this project
```

The `framework`-managed files (the scaffolding) are kept intact by `framework integrity`; everything else is yours to change.

## Inside the application — `src/your_package/`

The application is organised by responsibility. Each directory owns one concern:

```text
src/your_package/
├── main.py               # builds the FastAPI app (create_app) and the ASGI entry point
├── config/               # settings (typed configuration from the environment)
├── routes/               # HTTP routes (autodiscovered)
├── db/                   # database: ORM models, engine/session, repository, seed
├── middleware/           # cross-cutting request handling (errors, observability)
├── observability/        # metrics, SLOs, tracing, alert/dashboard provisioning
├── resilience/           # retry + circuit-breaker building blocks
└── logging_config.py     # structured logging setup + the request correlation id
```

### `main.py` — the composition root

`create_app()` is where the application is assembled: it loads settings, configures logging, builds the FastAPI app, attaches the observability middleware, registers exception handlers, includes the routes, and configures tracing. There is one place to look to understand how the app is wired.

### `config/` — typed settings

`config/settings.py` defines a Pydantic `Settings` class. Every configuration value — the database URL, log level, SLO thresholds, whether tracing is on — is a typed field read from the environment (all under the `APP_` prefix, e.g. `APP_DATABASE_URL`, `APP_ENVIRONMENT`). Nothing is hardcoded; configuration always comes from the environment or `.env`.

### `routes/` — HTTP endpoints, autodiscovered

Routes are wired automatically. `routes/__init__.py` exposes `include_routers(app)`, which imports every module in the package and includes any `APIRouter` it exposes as `router`, in deterministic (sorted) order. Adding an endpoint is a matter of dropping a `routes/<name>.py` that exposes a `router` — no edit to `main.py`. The project ships `routes/health.py` (the `/heartbeat` liveness ping and the `/health` readiness + SLO report) and an example `routes/items.py`.

### `db/` — the data layer

- `db/base.py` — the SQLAlchemy declarative `Base` all ORM models inherit from.
- `db/models.py` — the ORM models (ships an example `Item` entity to replace with your own).
- `db/engine.py` — builds the connection-pooled `Engine` and session factory; exposes `get_session()` as a FastAPI dependency (a session per request, always closed) and `dispose_engine()` for graceful shutdown.
- `db/repository.py` — query functions over the models, with bounded reads (page sizes are clamped so a caller can never request an unbounded read).
- `db/seed.py` — idempotent seed loading.

Schema changes are versioned in `migrations/` (Alembic) — not by editing the database directly.

### `middleware/` — cross-cutting request handling

- `middleware/observability.py` — the per-request observability middleware: it sets a correlation id, times the request, records metrics, and emits a structured request log.
- `middleware/errors.py` — global exception handling that turns every error into a consistent [RFC 7807](https://www.rfc-editor.org/rfc/rfc7807) *Problem Details* JSON response, each carrying the request's correlation id so a failing response is traceable to its logs.

### `observability/` — metrics, SLOs, tracing

- `metrics.py` — the in-process metrics registry, fed by the middleware and read by `/metrics` and `/health`.
- `slo.py` — the SLO definitions (typed config — the single source of truth) and their evaluation.
- `provisioning.py` — pure functions that turn the SLO definitions into Prometheus alert rules and a Grafana dashboard (serialised into `infra/observability/` by `scripts/gen_observability.py`).
- `tracing.py` / `datastores.py` — OpenTelemetry auto-instrumentation setup.
- `recoverability.py` — process-wide recoverability metrics (retries, recoveries, circuit-breaker state).

Observability is covered in depth on the [Observability](observability.md) page.

### `resilience/` — retry and circuit breaker

- `resilience/retry.py` — a retry decorator (exponential backoff + jitter, built on tenacity) that records recoverability metrics.
- `resilience/circuit_breaker.py` — a named circuit breaker (built on pybreaker) whose state transitions are logged and mirrored into the recoverability metrics.

Wrap a call to an unstable dependency with these instead of writing ad-hoc retry loops.

## `infra/` — running and deploying

```text
infra/
├── compose/          # Docker Compose files (base + per-environment overlays)
├── docker/           # the application Dockerfile (+ entrypoint)
├── observability/    # config for the obs stack (prometheus, grafana, loki, tempo, otel, …)
├── traefik/          # the local HTTPS reverse proxy config + certs
└── deploy/           # deploy targets
```

The Compose files compose by overlay: a shared `base.yml` plus per-environment overlays (`dev.yml`, `test.yml`, an `observability.yml` overlay, and the staging/prod files). How they fit together for local development is covered on [Run locally](run-locally.md).

## `tests/` — the test tiers

```text
tests/
├── unit/             # fast, in-process, no I/O
├── functional/       # in-process against real components (e.g. a testcontainers Postgres)
├── e2e/              # end-to-end against the full app + a real database
├── smoke/            # phase-1 probes against a running target
├── sniff/            # phase-2 probes against a running target
└── non_functional/   # load / SLO checks against a running target
```

A bare `pytest` collects the in-process tiers (`unit`, `functional`, `e2e`); the target-aimed tiers (`smoke`, `sniff`, `non_functional`) run against a deployed target via their own tasks. The everyday loop and the coverage gates over these tiers are covered on [Run locally](run-locally.md) and [Quality gates](quality-gates.md).

## Why this shape

The point of a fixed layout is that the *interesting* decisions — how to wire observability, how to handle errors, how to structure the data layer — are already made, consistently, in the same place every time. You add your domain logic into a structure that already does the cross-cutting work, rather than re-deriving it per project. The framework owns the scaffolding so you can own the application.
