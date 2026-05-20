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
    non_functional/             # k6 scripts; thresholds map 1:1 to SLO definitions
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
      review-data-integrity.yml
      review-data-lineage.yml
      review-application-logic.yml
      review-observability.yml
      review-test-quality.yml
      review-architecture.yml
      review-performance.yml
      review-compliance.yml
      review-privacy.yml
      review-api-design.yml
      review-accessibility.yml
      review-usability.yml
      review-documentation.yml
      review-dependency.yml
      review-aggregator.yml
    dependabot.yml
  .claude/
    settings.json               # hooks: ruff, mypy, targeted test runner
  .framework/
    integrity.lock              # checksums of locked + hybrid files; two-tier (tracked / gitignored)
  CLAUDE.md                     # TDD contract, testing obligations, conventions (hybrid: managed section)
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

- `.py` saved → `ruff check` + `mypy` on that file only
- Python test file saved → run that test file with `pytest`, report coverage delta
- `.ts` / `.tsx` / `.js` / `.jsx` saved → `eslint` + `tsc --noEmit` on that file (React battery)
- `.css` / `.scss` saved → `stylelint` on that file (React battery)
- `.yml` / `.yaml` saved → `yamllint` on that file; `actionlint` if under `.github/workflows/`
- `Dockerfile*` saved → `hadolint` on that file
- `.sh` saved → `shellcheck` on that file
- `.toml` saved → `taplo fmt --check` on that file
- `pyproject.toml` or `requirements*.txt` changed → `pip-audit`
- `.env` changed → `gitleaks` scan

### CLAUDE.md Conventions
- All configuration access via `settings.*` — never hardcoded
- `log.*` not `print()` — always include context keys
- Never use bare `except` — handle every identified error case explicitly
- Schema changes require a new migration — never modify existing migrations
- Updating an endpoint requires updating its contract test
- API routes versioned as `/api/v1/`

---

## 5. Pre-commit Layer

Runs before every commit. Target: <10 seconds total — all tools run on staged files only, not the whole project. No AI, no network calls.

**Always active:**

| Check | Tool | File types |
|---|---|---|
| Lint + format | `ruff` | `.py` |
| Type checking | `mypy` | `.py` |
| TOML formatting | `taplo` | `.toml` |
| YAML lint | `yamllint` | `.yml`, `.yaml` |
| GitHub Actions lint | `actionlint` | `.github/workflows/*.yml` |
| Dockerfile lint | `hadolint` | `Dockerfile*` |
| Shell script lint | `shellcheck` | `.sh` |
| JSON format | `prettier` | `.json` |
| Secrets scan | `gitleaks` | All files |
| Line endings | `.gitattributes` + pre-commit check | All files |
| Unit + functional coverage on changed modules | `coverage` (unit + functional contexts only) | `.py` (default 70%, configurable) |

All checks above are blocking.

**Why unit + functional only in pre-commit:** E2E tests require the full Docker stack and take minutes. NFR tests are slow by nature. Running either in pre-commit would make the hook unusable. The pre-commit threshold is intentionally lower (default 70%) to reflect partial coverage — the full picture is only available in CI where all test types run.

**Active when React battery is included:**

| Check | Tool | File types |
|---|---|---|
| Lint | `eslint` (with TypeScript plugin) | `.ts`, `.tsx`, `.js`, `.jsx` |
| Type checking | `tsc --noEmit` | `.ts`, `.tsx` |
| CSS / SCSS lint | `stylelint` | `.css`, `.scss` |
| Format | `prettier` | `.ts`, `.tsx`, `.js`, `.jsx`, `.css`, `.scss`, `.html`, `.md` |

All React checks are blocking.

---

## 6. Coverage Model

### Coverage Contexts
The framework uses `coverage.py` **dynamic contexts** to tag which test type covered each line. Each suite runs separately with its own context label:

```bash
pytest tests/unit       --cov --cov-context=unit
pytest tests/functional --cov --cov-context=functional
pytest tests/e2e        --cov --cov-context=e2e
```

This produces a combined report showing, for every line: which test types covered it and which did not. This is the mechanism that distinguishes a genuinely uncovered line from a line that is covered only at the integration level.

For the React frontend, Vitest runs with Istanbul coverage contexts for unit/functional, and Playwright is configured to collect Istanbul coverage from the running browser for E2E.

### Coverage Thresholds by Stage

| Stage | Test types run | Threshold | Rationale |
|---|---|---|---|
| Pre-commit | Unit + functional | 70% (configurable) | E2E requires full stack; NFR is slow. Lower threshold reflects partial picture. |
| CI | Unit + functional + E2E | 85% (configurable) | Full picture. E2E fills the gap on integration paths. |
| CI (combined) | All types | Reported, not gated | Total visibility; NFR paths are tracked separately (see below). |

### Lines Covered Only by E2E
A line covered by E2E but not by any unit or functional test is **not a failure** — some lines are only reachable via full integration. However, CI flags these as "integration-only coverage" in the report and the review-application-logic agent is instructed to assess whether a unit test is warranted. This creates pressure toward the right level of isolation without making it a hard gate.

### NFR Coverage
NFR tests (performance, load, resilience) execute the same code paths as unit/functional tests but assert on timing, throughput, and failure behaviour — they do not add unique line coverage. NFR coverage is therefore tracked by the presence and completeness of NFR scaffolds, not by line counters:

- A function that triggered an NFR heuristic (§4) must have a corresponding test in `tests/non_functional/`
- That test must have a defined threshold (no `# SLO: p99 < ???ms` markers remaining)
- CI fails on undefined NFR thresholds after a configurable grace period (default: 5 commits)

### Sniff Test Coverage
Sniff tests run against real deployed environments and cannot collect application-level coverage (the app is not instrumented in staging/prod). Sniff coverage is tracked by whether every consumer-facing surface defined in the project has a corresponding entry in `tests/sniff/`. CI fails if a consumer-facing surface exists with no sniff test.

---

## 7. Layer 3 — Integration Intelligence Layer

### AI Review Agents
Each agent runs as a named GitHub Check Run. Findings are posted as inline diff annotations. Agents run in parallel.

| Agent | Domain | Blocks merge on | Active when |
|---|---|---|---|
| `review-security` | Auth, injection, secrets, CVEs, OWASP Top 10 | HIGH / CRITICAL findings | Always |
| `review-data-integrity` | Data model, validation, migrations, store consistency | Any finding | Always |
| `review-data-lineage` | Data flow documentation, multi-store ownership, PII routing, deletion cascade coverage, cross-paradigm consistency, audit trails | PII to undocumented locations; deletion gaps; cross-paradigm writes with no consistency strategy | Always |
| `review-application-logic` | Correctness, edge cases, error handling, recoverability | Any finding | Always |
| `review-observability` | Metrics/logs/traces on new code paths, SLO thresholds defined, correlation ID propagation, error paths logged with context | New untraced/unmetered code paths | Always |
| `review-test-quality` | Tests assert behaviour not implementation; mocks match real interfaces; unhappy paths assert failure behaviour; NFR heuristics addressed | Tests that could pass regardless of code behaviour | Always |
| `review-architecture` | Layering violations (routes calling DB directly), circular dependencies, inappropriate coupling, boundary adherence | Layering violations; circular deps | Always |
| `review-performance` | N+1 queries, algorithm complexity, memory allocation in hot paths, missed caching opportunities, connection pool exhaustion | Clear regressions against defined SLOs | Always |
| `review-compliance` | GDPR, data retention, audit logging, right-to-erasure coverage | Clear violations | Always |
| `review-privacy` | PII data minimisation, logging of sensitive fields, data flow necessity, retention beyond purpose | PII in logs; unnecessary PII collection | Always |
| `review-api-design` | Naming consistency, error response consistency (RFC 7807), pagination patterns, versioning adherence, rate limiting headers | Advisory (warning) | REST or GraphQL battery |
| `review-accessibility` | ARIA, semantic HTML, WCAG 2.1 AA, axe-core findings | Advisory (warning) | React battery |
| `review-usability` | UX patterns, error messages, loading/empty/error states, form validation feedback | Advisory (warning) | React battery |
| `review-documentation` | Public interfaces documented, `.env.example` updated for new vars, complex logic explained, API spec current | Advisory (warning) | Always |
| `review-dependency` | New dependency justification, maintenance health, existing alternatives, supply chain risk | Advisory (warning) | Only fires when dependency files change |

### Agent Interactions
Some findings should propagate across agents automatically:
- A lineage finding (PII reaching an undocumented store) automatically triggers privacy and compliance agents to re-evaluate in that context
- A performance finding (unbounded query) cross-references data integrity (missing index)
- The aggregator surfaces these cross-agent relationships in its PR summary

### Aggregator
A `review-aggregator` job runs after all agents complete and posts a single PR comment containing: all findings grouped by severity, cross-agent relationships, affected files, suggested fixes, and a pass/fail summary. The builder sees the full picture in one place without hunting through individual check runs.

### Triggering
- All applicable agents run on every PR
- Security, data-integrity, data-lineage, and observability agents also run on direct pushes to `main`

---

## 8. Observability Stack

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

## 9. Environment Model

### Docker Compose Profiles

| Profile | Activated by | Contains |
|---|---|---|
| `dev` | `task dev` | All services + observability stack + hot reload |
| `dev:lite` | `task dev:lite` | App services + DB + Redis only (no observability) |
| `test` | `task test` | App services + isolated test DB + Redis |
| `ci` | GitHub Actions | Same as test, no volumes |
| `staging` | `deploy-staging.yml` | Full stack, production-equivalent config |
| `prod` | `deploy-prod.yml` | Full stack, no dev tooling |

**`task ci` vs `task push`:** These are distinct and intentionally separate.

`task ci` runs the full local CI suite against the already-running dev stack — no container spin-up cost, warm services, fast feedback. It runs: lint + type checks across all file types; unit + functional + E2E tests with coverage; pip-audit; OpenAPI export and diff; NFR/load tests; and, if a Claude API key is present in the environment, the AI review agents. This catches the vast majority of issues before anything touches GitHub.

`task push` does `git push`, which triggers GitHub Actions to run the authoritative CI pipeline. The Actions run is the canonical green-badge source — it runs on a clean environment, builds fresh images, and is what gates staging deployment. A builder should typically run `task ci` first, address any findings, then `task push`.

The local `task ci` is not a substitute for the Actions run — it is a fast pre-flight that makes the Actions run more likely to pass on the first attempt.

### Local HTTPS (mkcert)
The pre-flight check on first `task dev` installs mkcert if absent, generates certificates for `localhost` and `*.localhost`, and installs them into the system trust store. Traefik runs as a local reverse proxy terminating SSL — its label-based Docker service discovery makes it the natural fit for Compose. All local endpoints are HTTPS. No `verify=False` anywhere in code. Works on Windows, Mac, and Linux.

### Container Startup Ordering
Every service defines a `healthcheck` in the Compose file. All dependent services use `depends_on: condition: service_healthy`. The dependency graph is kept **minimal** — a service declares only the dependencies that genuinely block it from starting, not convenience groupings. Services with no mutual dependency start in parallel automatically; Docker Compose's scheduler handles this without explicit configuration.

Example dependency graph for a full stack (arrows = blocks):
```
postgres ──┐
            ├──► app
redis ─────┤
            └──► worker
traefik ─────────────── (no deps, starts immediately)
otel-collector ──────── (no deps, starts immediately)
prometheus ──┐
loki ────────┴──► grafana
alertmanager ─────────── (no deps, starts immediately)
promtail ─────────────── (no deps, starts immediately)
```

In this graph, postgres + redis + traefik + otel-collector + alertmanager + promtail all start in parallel on `task dev`. App and worker start as soon as their actual dependencies (postgres + redis) are healthy. Grafana waits only for prometheus and loki. First-run `task dev` never fails due to race conditions.

### Database Initialisation
`task dev` on first run: waits for DB health, runs migrations, loads seed data — automatically. `task dev:reset` tears down and rebuilds. Subsequent `task dev` runs detect existing data and skip seeding.

### Test Database Isolation
A separate test database service exists in the `test` Compose profile. The test suite is configured to use it automatically. The test database is reset to a known state between test runs.

### Database Paradigm Wizard
`framework new` (when `--with database` is active) does not assume a single-paradigm answer. Most real projects need more than one paradigm. The wizard reasons about use cases and composes a multi-paradigm recommendation.

For each distinct use case the builder describes, the wizard asks:
- What is the shape of this data? (structured / semi-structured / graph / time-series / vector / ephemeral)
- How dense are the relationships between entities in this use case?
- What are the primary query patterns? (relational joins / document lookup / graph traversal / time-range / similarity search / key lookup)
- What are the rough scale and retention expectations?

The wizard then recommends a paradigm per use case, identifies overlaps (e.g., Redis serves both caching and session storage), and presents a composed recommendation:

> "For user data with relationships → PostgreSQL. For session management and rate limiting → Redis. For semantic search over user content → pgvector (as a PostgreSQL extension, no extra service needed)."

All recommended paradigms are scaffolded. The builder can accept the full recommendation or deselect individual paradigms. Paradigms can be added later via `framework upskill --with database:<paradigm>`.

| Paradigm | Technology | Notes |
|---|---|---|
| Relational | PostgreSQL + SQLAlchemy + Alembic | Default for structured data with relationships |
| Document | MongoDB + Motor (async) | Semi-structured, flexible schema |
| Key-value / cache / session | Redis | Often needed alongside another paradigm |
| Time-series | TimescaleDB | PostgreSQL extension — no extra service if already using PostgreSQL |
| Vector / semantic search | pgvector (PostgreSQL ext.) or Qdrant | pgvector preferred if PostgreSQL already present |
| Graph | Neo4j | Dense relationship traversal |

When multiple paradigms are active, the data lineage review agent tracks data flows across all stores.

---

## 10. Secrets and Configuration Management

- `.env.example` is committed — documents every required variable with description and example value
- `.env` is gitignored — never committed
- All configuration access goes through `settings.py` (`pydantic-settings`) — no hardcoded values anywhere
- `gitleaks` runs in pre-commit and in CI to catch accidental secret commits
- CI secrets are injected via GitHub Secrets — never logged, never in env output
- Staging and prod use the same `.env.example` contract with environment-appropriate values

---

## 11. API Contracts and Versioning

- FastAPI auto-generates OpenAPI spec; `scripts/export-openapi.sh` runs in CI to produce `openapi.json` which is committed back to the branch
- CI diffs `openapi.json` on every PR — breaking changes (removed fields, changed types) fail the pipeline
- All API routes are versioned: `/api/v1/`
- When the `consumers` battery is active, Pact contract tests are scaffolded for inter-service contracts

---

## 12. Dependency Security

- `pip-audit` runs in CI after every dependency install step — failing CVEs block the pipeline
- `dependabot.yml` is scaffolded — auto-opens PRs for dependency updates weekly
- `gitleaks` in pre-commit catches secrets before they reach the repository

---

## 13. Frontend (React Battery)

When the `react` battery is active:
- TypeScript is mandatory
- Vite for bundling with HMR in dev
- Vitest for unit and functional tests
- Playwright for E2E (same Playwright instance used for API E2E)
- `playwright-axe` for accessibility assertions in E2E runs
- Same testing obligations apply as backend: happy path + error states + loading states + empty states + boundary inputs + unhappy E2E paths

---

## 14. CI/CD Pipeline

### CI (`ci.yml`) — triggers on every push and PR
0. **Framework integrity** — `framework integrity --ci` verifies the tracked + checksummed tier (gitignored existence checks skipped). Fails fast if scaffolding is compromised.
1. Pre-flight: install deps, run `pip-audit`
2. Lint + type check: `ruff`, `mypy`, `taplo`, `yamllint`, `actionlint`, `hadolint`, `shellcheck`, `prettier` (JSON); plus `eslint`, `tsc`, `stylelint`, `prettier` (full) when React battery active
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
A lightweight load test (k6, scaffolded by the framework) runs the primary API paths at a configurable request rate and asserts that SLO thresholds hold under load. k6's `thresholds` map 1:1 to the framework's SLO definitions — a threshold breach is an SLO breach, expressed once. Results are written via Prometheus remote-write into the same Grafana stack the framework already runs, so load results appear on the same dashboards as application metrics, and are stored as a CI artefact for comparison across deploys. This catches performance regressions that pass unit and E2E tests but degrade under realistic concurrency.

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

## 15. Local Development Experience

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
| `task ci` | Full local CI suite against the running dev stack (fast pre-flight before push) |
| `task push` | `git push` — triggers authoritative GitHub Actions CI pipeline |
| `task integrity` | `framework integrity` — verify framework scaffolding (auto-runs as precondition on every task) |
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

## 16. Framework Version and Upgrade

- `.copier-answers.yml` records the framework version used to scaffold the project
- `framework check` compares the local version to the latest release and shows a changelog diff with breaking changes clearly marked
- `framework upskill` runs `copier update` followed by `task test` — the upskill only succeeds if the project is green after template changes are applied

---

## 17. Framework Integrity

A self-check that verifies the framework's own scaffolding is intact — that the builder hasn't moved, deleted, or altered the files the framework relies on to support them. Distinct from `framework check` (version/changelog) and `framework upskill` (add batteries). Where `check` asks "is there a newer framework?", `integrity` asks "is *this* framework still whole?"

### File Classification
Every scaffolded file is declared in the Copier template as one of three classes:

1. **Locked** — full-file checksum. Pure framework infrastructure the builder should never edit: CI workflows, review-agent definitions, observability config, Compose files, pre-commit config, resilience scaffolds. Modifying these breaks the upskill contract.
2. **Hybrid (managed sections)** — files the builder is expected to extend, containing a framework-owned block delimited by `<!-- FRAMEWORK:BEGIN -->` … `<!-- FRAMEWORK:END -->` (comment syntax varies by file type). The delimited section is checksummed; everything outside it is the builder's to edit freely. Applies to `CLAUDE.md` (TDD contract and conventions locked; project-specific context free), `.env.example`, `pyproject.toml` (framework-managed dependency block), and `TASKFILE.yml` (framework tasks vs. builder tasks).
3. **Builder-owned** — not checked. Application code, tests, migrations.

### The Manifest
`.framework/integrity.lock` records every locked and hybrid entry with its expected checksum. Generated at `framework new`, updated on `framework upskill`. The manifest is itself checksummed to detect tampering.

The manifest has **two tiers**:
- **Tracked + checksummed** — git-tracked files, verified in every environment (local, CI, staging, prod)
- **Gitignored + existence-only** — framework-managed files legitimately absent from a fresh clone (`.env` derived from `.env.example`; mkcert certs in `infra/traefik/certs/`). Verified locally only; never in CI.

**Invariant:** checksummed files must be git-tracked. You cannot reliably checksum-verify a file that was never committed. The Copier template generation enforces this — if a file marked for checksumming matches a `.gitignore` pattern, that is flagged as a framework authoring error and not shipped.

### Execution
`framework integrity` is wired into `TASKFILE.yml` as a precondition on every target — it runs before `task dev`, `task test`, `task ci`, and all others. Taskfile dedupes preconditions within a run, so a chained task triggers it once. Performance budget is sub-second (hashing ~30–50 files), so it never becomes friction.

It is also **step 0 of the GitHub Actions CI pipeline**, so CI fails fast if scaffolding is compromised. In CI (detected via a known env var, and by reading `.gitignore`), only the tracked + checksummed tier is verified — gitignored existence checks are skipped, so a fresh checkout never fails spuriously.

The integrity logic lives in the installed CLI (`uv tool install framework`), not in the project's scaffolded code — so a builder deleting project files cannot disable the very check that detects it.

### Failure and Remediation
- **Missing locked/hybrid file** → hard fail with specific guidance
- **Altered locked file** → hard fail by default; `framework restore <file>` re-fetches the canonical version from the template at the project's recorded version
- **Altered hybrid framework section** → hard fail; `framework restore` rewrites only the framework block, preserving the builder's surrounding content
- **Intentional divergence** → `--allow-drift` escape hatch, set per-file and recorded in the manifest so the divergence is explicit and visible (and surfaced during `upskill`)

---

## 18. Emergent CLI Surface

The CLI is a thin shell over Copier and the task runner. Commands are defined as they become necessary — not designed upfront.

**Baseline commands:**

| Command | Action |
|---|---|
| `framework new <name> [--with <battery>...]` | Scaffold a new project |
| `framework upskill <name> [--with <battery>...]` | Add batteries to an existing project |
| `framework check` | Check framework version and show changelog diff |
| `framework integrity [--ci] [--allow-drift <file>]` | Verify framework scaffolding is intact (runs as a Taskfile precondition and CI step 0) |
| `framework restore <file>` | Re-fetch a canonical framework file from the template at the recorded version |

Additional commands emerge from builder needs. The CLI is UX sugar — the substance lives in the layers beneath it.

---

## 19. Error Handling and Recoverability Scaffold

Every service ships the following patterns from day one — builders extend them, not create them:

- **Global exception handler** — catches unhandled exceptions, returns RFC 7807 Problem Details responses, logs with full context and correlation ID
- **Retry decorator** — `tenacity`-based, configurable backoff + jitter, logs each attempt
- **Circuit breaker** — `pybreaker`-based, state exposed via `/metrics`, transitions logged
- **Dead letter queue** — for workers: failed jobs go to DLQ after configurable retry count, DLQ depth is a recoverability metric
- **Graceful shutdown** — services handle `SIGTERM` gracefully, finish in-flight requests, close DB connections cleanly

CLAUDE.md instruction: no bare `except` clauses; every identified error case is handled explicitly; recovery paths are part of outcome space mapping.

---

*End of spec.*
