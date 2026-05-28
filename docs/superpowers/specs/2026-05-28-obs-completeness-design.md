# Observability-completeness — Design

**Date:** 2026-05-28
**Status:** Approved (brainstorm), ready for plan
**Spec:** `docs/superpowers/specs/2026-05-20-framework-design.md` §5 (battery-observability contract)
**Related follow-ups:** the "observability-completeness review gap" and "split `review-observability` into infra/db/app/fe" Known follow-ups in `CLAUDE.md`.

## Problem

The §5 contract says every new runtime surface (service / process / store) ships its observability: a metric-or-exporter, a Prometheus scrape target (if a separate process), an alert rule, a Grafana dashboard, and a `/health` signal. Today that contract is fully *honored* by all 11 batteries but nothing *enforces* it. The exact gap — "a new service/store added WITHOUT its §5 observability" — has slipped **twice** and was caught both times by a **human**, not by any test or review agent (mongodb shipped full obs while baseline postgres had none → Plan 8i; battery services weren't in prod → SVC-PROD).

This slice closes that gap with two facets. A third (obs-infra-scaling guidance) is **deferred to the Plan 12 docs pack**.

## Facet 1 — A deterministic framework-authoring invariant

A hermetic pytest in the framework's own `tests/` (no LLM, no Anthropic key) that fails CI if a battery's rendered observability doesn't match its declared obs surface.

### Declared obs surface on `BatterySpec`

Add a **required** field to `BatterySpec` (`src/framework_cli/batteries.py`), no default — so registering any battery forces an explicit obs declaration and the dataclass won't construct without one:

```python
obs: Literal["service", "in-process", "rides-existing"]
```

Backfill the existing registry:

| `obs` value | Batteries | Meaning |
|---|---|---|
| `service` | `mongodb`, `workers`, `redis` | Adds a separate process/exporter → owes scrape + alert + dashboard + prod-wiring |
| `in-process` | `webhooks`, `websockets`, `graphql` | Emits metrics on the app's own `/metrics` (no new scrape target) → owes alert + dashboard |
| `rides-existing` | `pgvector`, `timescaledb`, `age`, `react`, `consumers` | No new §5 surface — postgres-extension batteries ride the always-on postgres-exporter; `react`'s frontend obs is deferred; `consumers` is a test harness |

A single enum value per battery is sufficient — no current battery is simultaneously a separate-process *and* in-process metric source. If a future battery needs both, `service` (the stronger obligation) applies and the field can become a tuple then.

### The test

`tests/test_obs_completeness.py`, parametrized over **every** registered battery. For each, render the bundled template twice — bare baseline and `--with <battery>` — and diff the observability artifacts (the *with-battery* render minus the *baseline* render). Rendering each battery against bare baseline isolates its own contribution, so the shared `workers`/`redis` redis-service and exporter don't confound a single battery's diff. Assert the diff matches the declared surface:

| `obs` | Artifacts that MUST appear in the diff | Artifacts that MUST NOT appear |
|---|---|---|
| `service` | a new Prometheus **scrape job** (in `prometheus.yml`) **and** a new **`*_alerts.yml`** **and** a new Grafana **dashboard** (`*.json`) **and** the service in **`infra/compose/services.yml`** (prod) **and** its exporter in **`infra/compose/observability.yml`** (the SVC-PROD prod-wiring gap) | — |
| `in-process` | a new **`*_alerts.yml`** **and** a new **dashboard** | no new **prod** service (`services.yml`), no new scrape job |
| `rides-existing` | — | no new alert, dashboard, **prod** service (`services.yml`), or scrape job |

The "service appeared" check keys off the **prod overlay `infra/compose/services.yml`**, not `dev.yml`. This is deliberate: the SVC-PROD gap was *prod-wiring*, and it cleanly excludes dev-only tooling services (e.g. the `react` battery's Vite dev server lives only in `dev.yml`, owes no §5 observability, and is correctly `rides-existing`). The scrape-job, `services.yml`, and `observability.yml` checks read the **rendered** files (battery-gated Jinja blocks already render these as static YAML — verified), so no `docker compose` merge is needed. The assertion is on artifact *categories* being non-empty (not exact filenames), so the `workers` battery legitimately bringing two exporters' worth of artifacts (celery + redis) still passes.

This is both a **forcing function** (a battery cannot be registered without declaring its obs intent) and a **lie-detector** (the render-diff proves the declaration matches what the template actually ships). It closes the service-omission gap *and* the in-process-omission gap that pure render-diff heuristics would miss.

## Facet 2 — Split `review-observability` into domain reviewers

The current single `review-observability` agent (`active_when="always"`, `on_push`, blocking-`high`) reviews **app/code-level** diffs only and under-serves infrastructure and data-store observability. Split into three agents (skip `fe` — there is no frontend-obs surface yet; React ships zero telemetry and the fe-obs feature is deferred, so its reviewer rides in with that feature later).

| Agent | Reviews | `active_when` | Block |
|---|---|---|---|
| `review-observability` (app, unchanged) | App/code diffs: untraced/unmetered code path, error not logged with correlation id, missing/undefined SLO threshold | `always` (`on_push`) | `high` |
| `review-observability-infra` (new) | Infra diffs: a new Compose service or scrape job without alert + dashboard; an alert with no dashboard panel; dev-only obs that never reaches `services.yml`/`observability.yml` (the OBS-PROD/SVC-PROD class) | `file-trigger` on `infra/**` (Compose, Prometheus, Grafana, alertmanager) | `high` |
| `review-observability-db` (new) | Data-store obs completeness: a repository/query path without store-level metrics; a missing store signal on `/health` | `file-trigger` on the data layer (`*/db/*`, `*models*`, `*repository*`, `migrations/*`, and battery store packages `*/vectors/*`, `*/cache/*`, document/timeseries/graph repos) | `high` |

**Why `db` is `file-trigger`, not battery-gated:** the baseline project always ships postgres + a repository layer, so data-store obs is relevant to *every* project — battery-gating would skip the most-used store. `file-trigger` keeps the same cost discipline as `infra` (only runs when relevant files change) while still covering baseline postgres. (`fnmatch` matches full path or basename and `*` spans `/`, so path-prefix globs work against a rendered project's diff paths.)

Each new agent ships **eval fixtures (3 bad + 1 good)** — the `test_every_registered_agent_has_fixtures` gate forces them to land in the same task. Thresholds are **provisional**; real-key scoring is **deferred to Plan 11** (identical state to `review-contracts`, `review-accessibility`, `review-usability`, and the original 7d set — none has been scored against a real Anthropic key).

## Out of scope / deferred

- **Facet 3 — obs-infra-scaling guidance** (when to graduate the co-located per-host obs stack: centralize, dedicated obs host, retention/resource sizing). Fuzziest of the three, most naturally documentation → **Plan 12 docs pack**.
- **Frontend obs feature + its reviewer** (`review-observability-fe`): web-vitals reporter → backend ingest → `/metrics` + dashboard + alert. A future slice; the fe reviewer ships with it.
- **Real-key scoring** of the two new agents → **Plan 11**.

## Testing

- Facet 1: the new parametrized `tests/test_obs_completeness.py` (hermetic render + diff), plus the dataclass-enforced required field surfacing via the existing battery tests/mypy.
- Facet 2: the existing review-registry tests (`tests/review/test_registry.py`) extend to the two new agents (activation matrix: `infra` file-triggers on `infra/**`, `db` file-triggers on the data layer, both excluded from a no-relevant-change PR); the parametrized prompt-contract test covers the two new prompts; `test_every_registered_agent_has_fixtures` enforces fixtures.
- No baseline manifest shift expected (no template payload changes — the agents are framework-side prompts/registry, the invariant is a framework-side test; the `obs` field is framework-internal metadata).

## Success criteria

- `BatterySpec.obs` is required and backfilled for all 11 batteries; omitting it on a new battery fails construction.
- `tests/test_obs_completeness.py` is green for all batteries and would fail if a `service`/`in-process` battery dropped any required artifact (verified by a temporary mutation during the build).
- `review-observability-infra` and `review-observability-db` are registered, prompt-contract-clean, fixture-backed, and wired into the dynamic CI matrix with correct activation.
- Full framework gate green (`pytest`/`ruff`/`mypy`/`uv lock --check`/`uv build`); no baseline manifest shift.
