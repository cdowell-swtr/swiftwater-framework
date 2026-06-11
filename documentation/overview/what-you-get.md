# What you get

Running `framework new "My App"` produces a complete project directory. Here is a concrete account of what is in it.

---

## TDD and quality gates

Every generated project ships with a four-layer test suite: `tests/unit/`, `tests/functional/`, `tests/e2e/`, and `tests/non_functional/`. The framework uses `coverage.py` dynamic contexts to tag which test type covered each line, so a CI report can distinguish a line covered only by E2E from one with unit-level coverage.

Coverage thresholds are enforced at two points: pre-commit (unit + functional, 70% by default) and CI (all test types, 85% by default). Both thresholds are configurable per project.

The generated `CLAUDE.md` encodes a TDD contract: Claude Code is instructed to write a failing test before implementing any unit, confirm it red, implement the minimum to make it green, and confirm it green. The obligation is determined by what is being built — a consumer-facing surface requires E2E tests including unhappy paths; an identified non-functional requirement requires a benchmark in `tests/non_functional/`.

## Pre-commit quality layer

A pre-commit configuration runs on every commit, targeting staged files only to stay under 10 seconds. It runs: `ruff` (lint + format), `mypy` (type checking), `gitleaks` (secrets scan), `actionlint` (GitHub Actions lint), `shellcheck`, and the standard pre-commit-hooks (`end-of-file-fixer`, `trailing-whitespace`, `mixed-line-ending`, `check-yaml`, `check-toml`, `check-merge-conflict`). Migration files also trigger a `migrations-reversible` check; the `coverage-threshold` hook enforces the pre-commit coverage gate. All checks are blocking.

The pre-commit layer has no AI and no network calls. It catches the majority of issues before anything reaches CI.

## AI review agents (CI)

A suite of domain-specific AI review agents gate your changes at commit and in CI — each covering one concern (security, data integrity, observability, test quality, and more), with additional agents activating for batteries that need them. The agents run in-process via the `framework` CLI and support two backends: a paid API backend (Anthropic API key in CI) and a free subagent backend (the `claude` CLI). Both backends use the same engine; the reviewer pipeline is identical regardless of which backend is active. See [The review system](../working/review-system.md) for the concept and architecture.

## Observability stack

The generated project includes a complete observability stack that runs identically in dev, CI, staging, and prod. A developer can see their SLO dashboard locally before anything touches CI.

- **Prometheus** scrapes `/metrics` from all services
- **Grafana** provides auto-provisioned dashboards driven by the project's SLO definitions
- **Alertmanager** fires alerts to the channels configured in the scaffold wizard (Slack, email, PagerDuty)
- **Loki** aggregates structured logs; **Promtail** ships them
- **Tempo** stores distributed traces; **OpenTelemetry Collector** routes traces, metrics, and logs to their respective backends

Every scaffolded service ships three distinct endpoints: `/heartbeat` (liveness probe, minimal), `/health` (structured SLO status JSON, used by load balancers), and `/metrics` (Prometheus text format). SLO definitions are a single source of truth — they drive the `/health` evaluation, Grafana dashboards, and Alertmanager rules simultaneously.

Structured logging uses `structlog`. A correlation ID is generated at every request boundary and propagated through async context. Log level is environment-aware (DEBUG locally, INFO in CI/staging/prod). Secrets and PII fields are redacted at the logger level before any entry is written.

## Environment parity

The same Compose definitions span every environment. Profile tokens (`dev`, `lite`, `test`) select service subsets within the dev and test overlays; staging and prod use separate Compose files (`staging.yml`, `prod.yml`) selected with `-f`. There is no separate "local config" that diverges from what runs in CI or staging. `task dev` on first run generates local HTTPS certificates via mkcert and starts Traefik as a local reverse proxy; all local endpoints are HTTPS with no `verify=False` anywhere.

`task ci` runs the full local CI suite against the already-running dev stack. `task push` triggers the authoritative GitHub Actions pipeline. The local run is a fast pre-flight; the Actions run is the canonical gate.

Container startup ordering is defined via healthchecks and `depends_on: condition: service_healthy` — first-run `task dev` never fails due to race conditions.

## CD pipeline

The generated project ships staging and prod deployment workflows. After a merge to `main`, the staging deployment runs a four-phase validation sequence: smoke tests (30s), sniff tests (stateless probes against real endpoints, 2–5 min), the full E2E suite against staging (10–20 min), and an SLO load validation (5–10 min). Any failure triggers auto-rollback and blocks the prod promotion gate. Prod deployment requires a human approval gate after staging passes all four phases.

## The battery system

Batteries are opt-in feature sets activated at scaffold time. Each battery is integrated end-to-end — it adds services, tests, observability, and any applicable CI review agents. The available batteries are:

| Battery | Adds |
|---|---|
| `workers` | Celery + Redis async task workers, DB-backed dead-letter queue, beat scheduler |
| `webhooks` | Signed inbound webhook ingress (HMAC) with an idempotent inbox |
| `websockets` | FastAPI WebSocket routes + connection manager |
| `graphql` | Strawberry code-first GraphQL endpoint; activates `review-api-design` |
| `react` | React + TypeScript SPA, Vitest, Playwright, axe-core; activates accessibility and usability review agents |
| `consumers` | Pact consumer-driven contract testing; activates `review-contracts` |
| `redis` | Redis key/value store (cache/sessions) |
| `mongodb` | MongoDB document store with full observability |
| `pgvector` | PostgreSQL pgvector extension for vector similarity search |
| `timescaledb` | PostgreSQL TimescaleDB extension for time-series data |
| `age` | Apache AGE openCypher graph queries on Postgres |

Batteries can be added later via `framework upskill my-app --with <battery>`. The upskill path merges non-destructively; conflict markers appear only where a generated file was edited in ways that conflict with the update.

## Framework integrity

Every generated project includes a `.framework/integrity.lock` — a manifest of checksums for framework-managed files. Running `framework integrity` (or `task integrity`) verifies that locked files have not been unintentionally altered. The integrity check distinguishes between locked files (must match exactly), hybrid files (a managed section must match; edits outside are fine), and gitignored files. Intentional divergence can be recorded explicitly with `framework integrity --allow-drift <file>`.

The integrity check runs automatically as a precondition on every `task` command, so a project is always aware of drift before any task executes.
