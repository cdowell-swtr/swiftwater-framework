# Run locally

Your project drives everything through [Task](https://taskfile.dev) (`Taskfile.yml`). Running `task` with no arguments lists every available task with a one-line description; the framework-managed tasks sit between the `FRAMEWORK:BEGIN`/`FRAMEWORK:END` markers, and you add your own below them.

This page covers the everyday local loop: bring the stack up, run the tests, change the schema.

## Bring the stack up

The project ships two ways to run locally, depending on how much you want running.

### `task dev` — the full stack

```bash
task dev
```

This brings up the complete local environment over HTTPS: the application (with hot reload), a Postgres database, the full observability stack, and a [Traefik](https://traefik.io) reverse proxy terminating TLS. Under the hood it runs:

```bash
docker compose -f infra/compose/base.yml -f infra/compose/observability.yml -f infra/compose/dev.yml --profile dev up --build
```

so the `dev` Compose profile is layered as `base.yml` + the `observability.yml` overlay + `dev.yml`. The observability stack runs locally exactly as it runs in staging and production — you can see your SLO dashboard on your own machine before anything reaches CI.

`task dev` has preconditions: it needs Docker, a `uv.lock` (run `uv sync` first — the image build uses `--frozen`), and local TLS certs. Run `task certs` once up front to install the [mkcert](https://github.com/FiloSottile/mkcert) local CA and issue `localhost` certificates for Traefik.

### `task dev:lite` — app only

```bash
task dev:lite
```

The resource-light option: just the application over plain HTTP at `http://localhost:8000` (plus its Postgres), no Traefik and no observability overlay. It runs the `lite` Compose profile:

```bash
docker compose -f infra/compose/base.yml -f infra/compose/dev.yml --profile lite up --build
```

Use `dev:lite` when you only need the API up and don't want the full obs stack consuming resources. (`dev:lite` is the one local mode that opts out of the observability stack — see [Observability](observability.md).)

### `task dev:reset` — start clean

```bash
task dev:reset
```

Tears the full `dev` stack down *including its volumes* (so the database is wiped), then brings it back up. Reach for this when you want a clean slate — a corrupted local DB, stale state, or a fresh start.

## The application URLs

- With `task dev`: the app is served over HTTPS via Traefik (routed by host).
- With `task dev:lite`: `http://localhost:8000`.
- `/heartbeat` is the liveness ping; `/health` returns the readiness + SLO report; `/metrics` is the Prometheus exposition.

## Run the tests

The in-process test tiers run with no infrastructure beyond what the tests start themselves (the functional/e2e tiers spin up a throwaway Postgres via testcontainers).

```bash
task test          # the whole in-process suite (unit + functional + e2e)
task test:unit     # unit tests only — the fastest loop
```

A bare `uv run pytest` collects the `unit`, `functional`, and `e2e` tiers. The target-aimed tiers run against a running deployment:

```bash
task test:smoke    # phase-1 smoke probes  (SMOKE_TARGET, default localhost:8000)
task test:sniff    # phase-2 sniff probes  (SNIFF_TARGET, default localhost:8000)
task test:e2e      # end-to-end against a real Postgres (needs Docker)
```

For the coverage gate that runs on every commit (and its stricter CI sibling), see [Quality gates](quality-gates.md).

## Database migrations

Schema changes are versioned with [Alembic](https://alembic.sqlalchemy.org); you never edit the database by hand.

```bash
task db:migrate    # apply pending migrations (uv run alembic upgrade head)
task db:seed       # load seed data (idempotent — a no-op if rows already exist)
```

`task db:migrate` targets the database in `APP_DATABASE_URL`. The `dev`/`lite` stacks publish Postgres on `localhost:5432`, so you can run migrations and `psql` from the host against the running database. (Migrations also run automatically in the container entrypoint on startup, so a freshly-brought-up stack is already migrated.)

## A typical loop

1. `uv sync` once to create the lockfile and install dependencies.
2. `task certs` once (only needed for the full `task dev`).
3. `task dev` (or `task dev:lite`) to bring the stack up — the app hot-reloads as you edit `src/`.
4. `task test:unit` as you go; `task test` before you're done.
5. Commit — the pre-commit gate runs automatically (see [Quality gates](quality-gates.md)).

The reload watcher picks up changes under `src/` immediately, so the inner loop is just edit-and-refresh while `task dev` keeps running.
