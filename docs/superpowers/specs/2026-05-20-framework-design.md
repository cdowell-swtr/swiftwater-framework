# Framework Design Spec
**Date:** 2026-05-20
**Status:** Draft — awaiting implementation plan

---

## 1. Purpose and Goals

A CLI scaffold framework that allows any builder — regardless of experience level — to produce solid, observable, testable, deployable Python applications from their first line of code to their ten-millionth. The framework offloads quality, testing, observability, security, and deployment concerns so the builder can focus on application logic.

**Antipatterns the framework prevents:**
- Tests written after the fact, or not at all
- Happy-path-only testing; absence of error, edge, and unhappy-path coverage
- "Works on my machine" environment drift between dev, CI, staging, and prod
- Secrets baked into code or inconsistently managed across environments
- No staging environment; code going straight from CI to prod
- No CI pipeline, or CI that doesn't enforce quality gates
- No E2E tests for consumer-facing surfaces
- No AI-assisted review with separation of concerns (security, accessibility, compliance, data integrity, etc.)
- Builder assumed to be omniscient; no scaffolding or helpers for common failure states
- Poor data model choices; wrong database paradigm for the problem
- Lack of error handling and recoverability in application code
- No structured observability; no SLO definitions; no recoverability metrics

---

## 2. Core Architecture

The framework has three layers plus an observability stack that runs across all of them.

### Layer 1 — Template Layer (structural)
A [Copier](https://copier.readthedocs.io/) template repository that generates and maintains project skeletons. Owns: directory layout, Docker Compose files, GitHub Actions workflows, `pyproject.toml`, pre-commit config, Taskfile, environment conventions, and all scaffolded code patterns. `copier update` (exposed as `framework upskill`) keeps generated projects in sync with the evolving template — merging non-destructively and flagging conflicts.

Every generated project includes a `.copier-answers.yml` recording which batteries were included and which framework version was used. This manifest is what makes `upskill` safe.

### Layer 2 — Dev Intelligence Layer (development-time)
A generated `CLAUDE.md` and `.claude/settings.json` that configure Claude Code's behaviour within the project. Encodes the framework's TDD contract, testing obligations, outcome space mapping requirements, error handling patterns, and logging conventions as Claude Code instructions and file-change hooks. Hooks are **surgical** — they trigger on the specific file being edited, not the whole project.

### Layer 3 — Integration Intelligence Layer (CI-time)
Specialised AI review agents running as GitHub Actions Check Runs on every push and PR. Each agent reviews one concern domain. Deep, thorough, token-intensive work happens here — not in the inner loop.

### Pre-commit Layer (between Layers 2 and 3)
Deterministic, fast (<10s), no AI. Catches 80% of issues before they reach CI.

### Observability Stack
Runs identically in every environment. Provides the monitoring, alerting, and insight surface that makes the application behaviour visible from dev through prod.

---

## 3. Layer 1 — Template Layer

### Copier Template Structure
Template files at the template root become the generated project root. `{{project_slug}}` is the output directory name, not a subdirectory.

```
template/
  copier.yml                    # questions, conditionals, batteries
  src/
    {{package_name}}/
      routes/
        health.py               # /health, /heartbeat, /metrics — always scaffolded
      config/
        settings.py             # pydantic-settings, all config from env
      middleware/
        logging.py              # structlog setup, correlation IDs
        errors.py               # global exception handler, RFC 7807
      resilience/
        retry.py                # tenacity decorators
        circuit_breaker.py      # pybreaker setup
  tests/
    unit/
    functional/
    e2e/
    non_functional/
    sniff/                      # fast stateless probes run post-deploy against real environments
  scripts/
    export-openapi.sh           # generates openapi.json; run by CI, output committed
  infra/
    compose/
      base.yml
      dev.yml
      test.yml
      ci.yml
      staging.yml
      prod.yml
    traefik/
      certs/                    # mkcert-generated certs (gitignored)
      traefik.yml
    observability/
      prometheus/
        prometheus.yml
        alerts/                 # auto-generated from SLO definitions
      grafana/
        dashboards/             # auto-provisioned from SLO definitions
        datasources/
      loki/
      alertmanager/
      otel/
        otel-collector.yml
  .github/
    workflows/
      ci.yml
      deploy-staging.yml
      deploy-prod.yml
      review-security.yml
      review-accessibility.yml
      review-data-integrity.yml
      review-application-logic.yml
      review-compliance.yml
      review-usability.yml
      review-aggregator.yml
    dependabot.yml
  .claude/
    settings.json               # hooks: ruff, mypy, targeted test runner
  CLAUDE.md                     # TDD contract, testing obligations, conventions
  TASKFILE.yml                  # cross-platform task runner
  pyproject.toml
  .env.example                  # all required vars documented
  .gitattributes                # enforce LF
  .pre-commit-config.yaml
  .copier-answers.yml
  .python-version
```

### Available Batteries
Batteries are activated at scaffold time via `framework new my-app --with <battery>` and added later via `framework upskill my-app --with <battery>`.

| Battery | Activates |
|---|---|
| `rest` | FastAPI, Uvicorn, OpenAPI export |
| `graphql` | Strawberry GraphQL, schema-first scaffold |
| `workers` | Celery, Redis, dead letter queue, beat scheduler |
| `webhooks` | Inbound webhook handler, signature validation, idempotency |
| `websockets` | FastAPI WebSocket routes, connection manager |
| `react` | Vite + TypeScript frontend, Vitest, Playwright, axe-core |
| `database` | Database paradigm wizard (see §8) |
| `consumers` | Pact contract testing for inter-service contracts |
| `observability` | Full observability stack **(default-on — opt out with `--without observability`)** |

---

## 4. Layer 2 — Dev Intelligence Layer

### CLAUDE.md — TDD Contract

Claude Code is instructed to apply the following testing obligations before considering any deliverable complete. The obligation is determined by what is being built, not by a fixed hierarchy:

| What's being built | Required tests |
|---|---|
| Any code unit | Unit tests — write failing test first, confirm red, implement, confirm green |
| Any behaviour or feature | Functional tests — assert outcomes, not implementation details |
| Identified non-functional requirement | Non-functional tests — see NFR heuristics below |
| Any service | Health / heartbeat / metrics endpoints — scaffolded as part of service skeleton |
| Consumer-facing surface (API endpoint, webhook, UI, WebSocket) | E2E tests — against the real running stack |

**E2E tests are not complete unless they include at least one unhappy path per consumer-facing surface.**

### NFR Heuristics
Claude Code does not wait for an NFR to be stated. It applies these heuristics to identify where non-functional tests are warranted:

| Signal | NFR test to scaffold |
|---|---|
| Function operates on unbounded or variable-size collection | Scalability / performance benchmark |
| I/O-bound operation (DB, HTTP, file) | Latency + timeout test |
| Function in a hot path (high call frequency) | Throughput test |
| CPU-bound processing (encoding, transformation, aggregation) | Performance benchmark |
| Function with retry / circuit-breaker logic | Resilience + failure injection test |
| Any external dependency | Unavailability simulation test |

Unset thresholds are scaffolded with `# SLO: p99 < ???ms` markers. The CI pipeline warns on unset thresholds during a grace period, then fails.

### Outcome Space Mapping
Claude Code and all Layer 3 agents explicitly map the full outcome space before any surface is considered complete:

- **Happy path** — expected inputs, expected outputs
- **Error cases** — every exception type the unit can raise, with a test for each
- **Edge cases** — boundary inputs, empty collections, None/null, concurrent access, maximum sizes
- **E2E unhappy paths** — dependency down, auth failure, rate limit hit, partial failure, timeout, malformed input

### Claude Code Hooks (`.claude/settings.json`)
Hooks are surgical — they fire on the specific file being changed, not the whole project:

- Python file saved → run `ruff check` and `mypy` on that file only
- Test file saved → run that test file with `pytest` and report coverage delta
- `requirements` or `pyproject.toml` changed → run `pip-audit`
- `.env` changed → run `gitleaks` scan

### CLAUDE.md Conventions
- All configuration access via `settings.*` — never hardcoded
- `log.*` not `print()` — always include context keys
- Never use bare `except` — handle every identified error case explicitly
- Schema changes require a new migration — never modify existing migrations
- Updating an endpoint requires updating its contract test
- API routes versioned as `/api/v1/`

---

## 5. Pre-commit Layer

Runs before every commit. Target: <10 seconds. No AI, no network calls.

| Check | Tool | Failure behaviour |
|---|---|---|
| Lint + format | `ruff` | Blocking |
| Type checking | `mypy` | Blocking |
| Coverage threshold on changed modules | `coverage` | Blocking (threshold configurable, default 80%) |
| Secrets scan | `gitleaks` | Blocking |
| Line endings | `.gitattributes` + pre-commit check | Blocking |

---

## 6. Layer 3 — Integration Intelligence Layer

### AI Review Agents
Each agent runs as a named GitHub Check Run. Findings are posted as inline diff annotations.

| Agent | Domain | Blocks merge |
|---|---|---|
| `review-security` | Auth, injection, secrets, CVEs, OWASP Top 10 | HIGH / CRITICAL findings |
| `review-data-integrity` | Data model, validation, migrations, consistency | Any finding |
| `review-application-logic` | Correctness, edge cases, error handling, recoverability | Any finding |
| `review-compliance` | GDPR, data retention, audit logging, PII handling | Clear violations |
| `review-accessibility` | ARIA, semantic HTML, WCAG 2.1 AA | Advisory (warning) |
| `review-usability` | UX patterns, error messages, loading/empty states | Advisory (warning) |

### Aggregator
A `review-aggregator` job runs after all agents complete and posts a single PR comment with the full picture: all findings, severities, affected files, and suggested fixes. The builder sees everything in one place.

### Triggering
- All agents run on every PR
- Security and data integrity agents also run on direct pushes to `main`

---

## 7. Observability Stack

Runs identically in dev, CI, staging, and prod. A developer can see their SLO dashboard locally before anything touches CI.

### Stack Components
| Component | Role |
|---|---|
| Prometheus | Scrapes `/metrics` from all services |
| Grafana | Auto-provisioned dashboards from SLO definitions |
| Alertmanager | Fires alerts when SLOs breach thresholds |
| Loki | Structured log aggregation |
| Promtail | Log shipping to Loki |
| OpenTelemetry Collector | Unified trace / metric / log pipeline |

### SLO-Defined Monitoring Endpoints
Every scaffolded service ships `/health`, `/heartbeat`, and `/metrics` endpoints. These return structured SLO status — not booleans:

```json
{
  "status": "degraded",
  "slos": {
    "request_latency_p99_ms": { "threshold": 200, "current": 340, "status": "breached" },
    "error_rate_pct":         { "threshold": 1.0,  "current": 0.3,  "status": "ok" },
    "recovery_rate_pct":      { "threshold": 95.0, "current": 91.2, "status": "warning" }
  }
}
```

SLO definitions live in code as configuration. Grafana dashboards and Alertmanager rules are auto-generated from them — single source of truth across all environments.

### Recoverability Metrics (first-class)
- Error counts by type and recovery outcome (recovered / unrecovered / escalated)
- Circuit breaker state transitions (open / half-open / closed)
- Retry attempt counts and success rates
- Dead letter queue depths (workers / pipelines)
- Mean time to recovery (MTTR) per error class
- Graceful degradation events

### Structured Logging
`structlog` is the standard. A correlation ID is generated at every request boundary and propagated through async context — all log entries within a request share it. Log level is environment-aware: DEBUG locally, INFO in CI/staging/prod. Secrets and PII fields are redacted at the logger level before any entry is written.

---

## 8. Environment Model

### Docker Compose Profiles

| Profile | Activated by | Contains |
|---|---|---|
| `dev` | `task dev` | All services + observability stack + hot reload |
| `dev:lite` | `task dev:lite` | App services + DB + Redis only (no observability) |
| `test` | `task test` | App services + isolated test DB + Redis |
| `ci` | GitHub Actions | Same as test, no volumes |
| `staging` | `deploy-staging.yml` | Full stack, production-equivalent config |
| `prod` | `deploy-prod.yml` | Full stack, no dev tooling |

### Local HTTPS (mkcert)
The pre-flight check on first `task dev` installs mkcert if absent, generates certificates for `localhost` and `*.localhost`, and installs them into the system trust store. Traefik runs as a local reverse proxy terminating SSL — its label-based Docker service discovery makes it the natural fit for Compose. All local endpoints are HTTPS. No `verify=False` anywhere in code. Works on Windows, Mac, and Linux.

### Container Startup Ordering
Every service defines a `healthcheck` in the Compose file. All dependent services use `depends_on: condition: service_healthy`. The database is not "up" until it accepts connections. Workers do not start until the broker (Redis) is healthy. First-run `task dev` never fails due to race conditions.

### Database Initialisation
`task dev` on first run: waits for DB health, runs migrations, loads seed data — automatically. `task dev:reset` tears down and rebuilds. Subsequent `task dev` runs detect existing data and skip seeding.

### Test Database Isolation
A separate test database service exists in the `test` Compose profile. The test suite is configured to use it automatically. The test database is reset to a known state between test runs.

### Database Paradigm Wizard
`framework new` (when `--with database` is active) asks the builder:
- What is the shape of your data? (structured / semi-structured / graph / time-series / vector)
- How dense are the relationships between entities?
- What are the primary query patterns?
- What are the rough scale expectations?

Based on answers, the framework recommends and scaffolds the appropriate paradigm:

| Paradigm | Technology |
|---|---|
| Relational | PostgreSQL + SQLAlchemy + Alembic |
| Document | MongoDB + Motor (async) |
| Key-value / cache | Redis |
| Time-series | TimescaleDB |
| Vector / semantic search | pgvector or Qdrant |
| Graph | Neo4j |

---

## 9. Secrets and Configuration Management

- `.env.example` is committed — documents every required variable with description and example value
- `.env` is gitignored — never committed
- All configuration access goes through `settings.py` (`pydantic-settings`) — no hardcoded values anywhere
- `gitleaks` runs in pre-commit and in CI to catch accidental secret commits
- CI secrets are injected via GitHub Secrets — never logged, never in env output
- Staging and prod use the same `.env.example` contract with environment-appropriate values

---

## 10. API Contracts and Versioning

- FastAPI auto-generates OpenAPI spec; `scripts/export-openapi.sh` runs in CI to produce `openapi.json` which is committed back to the branch
- CI diffs `openapi.json` on every PR — breaking changes (removed fields, changed types) fail the pipeline
- All API routes are versioned: `/api/v1/`
- When the `consumers` battery is active, Pact contract tests are scaffolded for inter-service contracts

---

## 11. Dependency Security

- `pip-audit` runs in CI after every dependency install step — failing CVEs block the pipeline
- `dependabot.yml` is scaffolded — auto-opens PRs for dependency updates weekly
- `gitleaks` in pre-commit catches secrets before they reach the repository

---

## 12. Frontend (React Battery)

When the `react` battery is active:
- TypeScript is mandatory
- Vite for bundling with HMR in dev
- Vitest for unit and functional tests
- Playwright for E2E (same Playwright instance used for API E2E)
- `playwright-axe` for accessibility assertions in E2E runs
- Same testing obligations apply as backend: happy path + error states + loading states + empty states + boundary inputs + unhappy E2E paths

---

## 13. CI/CD Pipeline

### CI (`ci.yml`) — triggers on every push and PR
1. Pre-flight: install deps, run `pip-audit`
2. Lint + type check: `ruff`, `mypy`
3. Unit + functional tests with coverage threshold
4. Build Docker images
5. Start CI Compose stack
6. E2E tests (including unhappy paths)
7. Export and diff `openapi.json`
8. All Layer 3 AI review agents (parallel)
9. Review aggregator — post PR summary comment

### CD Staging (`deploy-staging.yml`) — triggers on merge to `main`

Staging deployment runs a four-phase validation sequence. Each phase must pass before the next begins. Any failure triggers auto-rollback and blocks the prod promotion gate.

**Phase 1 — Smoke tests (immediate, ~30s)**
Runs immediately after deploy. Fast enough to catch a broken deployment before anything else runs.
- Hit `/health` and `/heartbeat` on every service — any non-200 response triggers rollback
- Verify SLO status blocks report no `breached` entries
- Verify all services respond within 2× their defined p99 latency threshold

**Phase 2 — Sniff tests (~2–5 min)**
Lightweight probes of critical paths — not exhaustive, but covers the skeleton of the system. These are a dedicated `tests/sniff/` suite, distinct from E2E, written to be fast and stateless.
- Auth flow: can a token be issued and validated?
- Core read path: does the primary data surface return expected shape?
- Core write path: does a minimal write operation succeed end-to-end?
- Worker heartbeat: is the task broker accepting and processing jobs?
- Webhook ingress: does an inbound webhook reach the handler?
- WebSocket handshake: does a connection upgrade succeed? (if battery active)

Sniff tests run against the real deployed staging environment — they catch environment-specific config issues (wrong secrets, misconfigured DNS, real SSL problems) that CI's containerised environment cannot surface.

**Phase 3 — Full E2E suite against staging (~10–20 min)**
The same E2E suite from CI, now run against the real staging environment. This includes all happy paths and all unhappy paths (dependency failures, auth failures, rate limits, malformed input). Staging E2E is the definitive confidence gate before prod — if it passes here, prod promotion is permitted.

**Phase 4 — SLO load validation (~5–10 min)**
A lightweight load test (k6 or Locust, scaffolded by the framework) runs the primary API paths at a configurable request rate and asserts that SLO thresholds hold under load. This catches performance regressions that pass unit and E2E tests but degrade under realistic concurrency. Results are posted to the Grafana staging dashboard and stored as a CI artefact for comparison across deploys.

**On success:** the staging deployment is marked prod-ready and the prod promotion gate opens.
**On any failure:** auto-rollback, deployment marked failed, prod gate stays closed, notify.

### CD Prod (`deploy-prod.yml`) — triggers on manual approval or tagged release
Prod deployment only opens after staging has passed all four phases above.

1. Manual approval gate — a human reviews the staging validation results before proceeding
2. Build prod images (same artefacts as staging — no rebuild)
3. Deploy to prod
4. Smoke tests — same as staging Phase 1, against prod endpoints
5. Sniff tests — same as staging Phase 2, against prod endpoints (read-only paths only — no writes in prod sniff)
6. Auto-rollback if smoke or sniff fails
7. Notify with link to Grafana prod dashboard

The framework never deploys to prod without: a passing staging validation, a human approval, and a passing post-deploy smoke + sniff.

---

## 14. Local Development Experience

### Single Command Startup
`task dev` brings up the full local world: all application services, observability stack (Prometheus, Grafana, Loki, Alertmanager), local HTTPS via Traefik + mkcert, hot reload, database with seed data.

`task dev:lite` runs app services + DB + Redis only — for resource-constrained machines.

### Cross-Platform Task Runner
All tasks defined in `TASKFILE.yml` using [Taskfile](https://taskfile.dev/) — works natively on Windows, Mac, and Linux without WSL. No `make` dependency.

### Key Tasks

| Task | Action |
|---|---|
| `task dev` | Full local stack |
| `task dev:lite` | Lightweight local stack |
| `task dev:reset` | Tear down and rebuild with fresh seed data |
| `task test` | Run full test suite in isolated test environment |
| `task test:unit` | Unit tests only |
| `task test:e2e` | E2E tests only |
| `task test:sniff` | Sniff tests against a target environment (`SNIFF_TARGET=https://staging.example.com`) |
| `task lint` | ruff + mypy |
| `task db:migrate` | Run pending migrations |
| `task db:seed` | Load seed data |
| `task certs` | Regenerate local mkcert certificates |
| `task audit` | Run pip-audit |

### Pre-flight Check
`task dev` on first run validates:
- Docker is running
- Python version matches `.python-version`
- `uv` is installed
- mkcert is installed (installs if absent)
- Required environment variables are present in `.env` (compared against `.env.example`)

Any failure produces a specific, actionable error message — not a stack trace.

### First-Run Green Suite
The scaffold generates a passing test suite on day one: a unit test, a health endpoint test, and a smoke E2E test. `framework new` runs `task test` automatically after scaffolding. The builder's first interaction with the project is a green suite. The framework starts trusted.

### IDE Integration
- `.devcontainer/devcontainer.json` for VS Code containerised development
- `.vscode/launch.json` for Python debugger attachment to running containers
- JetBrains run configurations scaffolded in `.idea/`

### Platform Consistency
- `.python-version` pins Python version (read by uv / pyenv)
- `uv.lock` locks all dependencies
- `.gitattributes` enforces LF for all code files
- All services in Compose set `TZ=UTC` explicitly
- File watchers use polling mode on Windows (configured in Compose dev profile)

### Service Addressing
A `SERVICES.md` in every generated project documents each service's internal Docker hostname (for service-to-service calls) and external HTTPS address (for host browser access). Builders never guess.

---

## 15. Framework Version and Upgrade

- `.copier-answers.yml` records the framework version used to scaffold the project
- `framework check` compares the local version to the latest release and shows a changelog diff with breaking changes clearly marked
- `framework upskill` runs `copier update` followed by `task test` — the upskill only succeeds if the project is green after template changes are applied

---

## 16. Emergent CLI Surface

The CLI is a thin shell over Copier and the task runner. Commands are defined as they become necessary — not designed upfront.

**Baseline commands:**

| Command | Action |
|---|---|
| `framework new <name> [--with <battery>...]` | Scaffold a new project |
| `framework upskill <name> [--with <battery>...]` | Add batteries to an existing project |
| `framework check` | Check framework version and show changelog diff |

Additional commands emerge from builder needs. The CLI is UX sugar — the substance lives in the layers beneath it.

---

## 17. Error Handling and Recoverability Scaffold

Every service ships the following patterns from day one — builders extend them, not create them:

- **Global exception handler** — catches unhandled exceptions, returns RFC 7807 Problem Details responses, logs with full context and correlation ID
- **Retry decorator** — `tenacity`-based, configurable backoff + jitter, logs each attempt
- **Circuit breaker** — `pybreaker`-based, state exposed via `/metrics`, transitions logged
- **Dead letter queue** — for workers: failed jobs go to DLQ after configurable retry count, DLQ depth is a recoverability metric
- **Graceful shutdown** — services handle `SIGTERM` gracefully, finish in-flight requests, close DB connections cleanly

CLAUDE.md instruction: no bare `except` clauses; every identified error case is handled explicitly; recovery paths are part of outcome space mapping.

---

*End of spec.*
