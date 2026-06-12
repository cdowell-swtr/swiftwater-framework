# New project & batteries

`framework new` scaffolds a fresh project from the bundled template. This page covers the command, the interactive wizard, and how to choose batteries.

## The command

```bash
framework new "My App"
```

`new` takes one required argument — a human-readable **project name** — plus a few options:

| Option | Default | Purpose |
|---|---|---|
| `NAME` (argument) | — | Human-readable project name. The CLI derives a slug, package name, and a destination directory from it. |
| `--python-version` | `3.12` | Python version the generated project targets. |
| `--with` | (none) | Activate a battery. Repeatable, e.g. `--with workers --with webhooks`. |
| `--alerts` | (prompted / `webhook`) | Alert channels for SLO-breach notifications, comma-separated: `webhook,slack,email,pagerduty`. |

The destination directory is created in your current working directory, named after the derived project slug (e.g. `"My App"` → `my-app`). If that directory already exists, the command refuses and exits rather than overwriting anything.

## The interactive wizard

When you run `framework new` on a terminal (an interactive TTY) **without** specifying batteries or alerts up front, a short wizard prompts you for them:

1. **What kind of data does it store?** — a multi-select over data *needs* rather than raw battery names. Relational storage is always on and is not listed; the choices are:
   - Document store
   - Vector / similarity search
   - Time-series
   - Graph (Cypher)
   - Cache / key-value

   Each selected need maps to a battery (document → `mongodb`, vector → `pgvector`, time-series → `timescaledb`, graph → `age`, cache → `redis`). You can select none and add batteries later.

2. **Where should alerts go?** — a multi-select over `webhook`, `slack`, `email`, and `pagerduty`, with `webhook` pre-checked. A project must have at least one channel.

Flags take precedence over prompts. If you pass `--with`, the battery prompt is skipped; if you pass `--alerts`, the alert prompt is skipped. In a non-interactive context (no TTY — for example a CI step or a piped invocation), the wizard does not prompt: it falls back to no batteries and the default `webhook` alert channel unless you supply the flags.

Note that `--with` accepts any battery token directly (see the table below), whereas the interactive prompt is phrased in terms of data needs and therefore only reaches the database-paradigm batteries. To activate something like `websockets` or `graphql`, pass it with `--with` (or add it later with `upskill`).

## Choosing batteries

Batteries are optional, self-contained feature sets the template can render into a project. Pass each one with a repeated `--with` flag. The full set of battery tokens:

| Battery | What it adds |
|---|---|
| `webhooks` | Signed inbound webhook ingress (HMAC) with an idempotent inbox. |
| `websockets` | FastAPI WebSocket routes plus a connection manager. |
| `workers` | Celery + Redis async task workers with a DB-backed dead-letter queue and a beat scheduler. |
| `graphql` | Strawberry code-first GraphQL endpoint at `/graphql` over the demo Item model. |
| `pgvector` | PostgreSQL pgvector extension plus an embeddings table for vector similarity search. |
| `mongodb` | MongoDB document store (pymongo) with a documents collection and full observability. |
| `timescaledb` | PostgreSQL TimescaleDB extension plus a readings hypertable for time-series data. |
| `age` | Apache AGE openCypher graph queries on Postgres (no new service). |
| `redis` | Redis key/value datastore (cache/sessions) — shares the workers Redis service when both are active. |
| `react` | React + TypeScript SPA served by FastAPI, with Vitest/Playwright/axe and accessibility/usability/frontend-observability review. |
| `consumers` | Pact consumer-driven contract testing (consumer + provider verification) for inter-service contracts. |

Batteries can imply other batteries: when one depends on another, selecting it pulls the dependency in automatically, and the resolved set is what gets recorded. Selecting an unknown battery name fails fast with a message naming the offender and listing the known tokens.

```bash
framework new "My App" --with workers --with redis --alerts slack,pagerduty
```

## What rendering produces

When `new` completes, the destination directory holds a fully wired project: a `pyproject.toml`, a `Taskfile.yml`, Docker Compose files for each environment, a GitHub Actions CI/CD pipeline, pre-commit configuration, an observability stack, and the test-suite layout — with the files for each selected battery merged in. The command also records the framework version and the chosen battery/alert sets into the project's `.copier-answers.yml`, writes an integrity manifest, and generates a `uv.lock` (by running `uv lock`) so that, once committed, the project's first push passes its frozen-dependency CI jobs. It prints a one-line summary of where the project was created and which batteries and alert channels were activated.

`new` does not initialise a git repository — it leaves a directory of files. Setting up version control is your first step in the new project: `git init`, then `git add -A` (be sure `uv.lock` is included) and an initial commit before you push. The recorded `.copier-answers.yml` is what later lets `framework upgrade` pull newer framework releases into the project (see [Upgrading](upgrading.md)).

To add or remove batteries on a project that already exists, see [Add/remove batteries](batteries-add-remove.md).
