# GraphQL Battery (Plan 8d) — Design Spec

**Date:** 2026-05-25
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 8a-1 (the battery mechanism — registry, `--with`, route autodiscovery, conditional rendering), Plan 8b/8c (route-battery + `gates_agent` groundwork; the §5 battery-observability contract; conditional CI steps), Plan 8b-1/8e-1 (the in-process metric-singleton pattern, the separate-alert/dashboard-file pattern, and the downskill `usage_references` byte-identity exclusion), Plan 7 (the review-agent runner, the 12-agent registry, the dynamic CI matrix, and the hermetic eval harness).

---

## 1. Purpose & scope

Add a **GraphQL battery** (`framework new/upskill --with graphql`): a Strawberry, **code-first** GraphQL endpoint at `/graphql`, served by FastAPI, over the **baseline `Item` model** the template already ships. It demonstrates GraphQL alongside the existing REST surface without inventing a second demo domain, and it activates the framework's first **battery-gated review agent** (`review-api-design`) — exercising the `gates_agent` mechanism that Plan 8g (react) will reuse.

**In scope:**
- A `graphql/` package: a code-first schema (`@strawberry.type Item`, `Query.items`, `Mutation.create_item`) reusing the baseline `db/repository.py`; a request-scoped DB-session context; an in-process metrics singleton + a Strawberry `SchemaExtension` emission seam.
- A `/graphql` route module wired by the existing `routes/__init__.py` autodiscovery; GraphiQL IDE + introspection **enabled outside production, disabled in production**, settings-driven.
- The §5 battery-observability contract: `app_graphql_operations_total{operation_type,outcome}` on `/metrics`, a `graphql_alerts.yml`, a `graphql.json` Grafana dashboard.
- A committed `schema.graphql` SDL artifact + an `export-graphql-schema.sh`; CI **staleness** + **breaking-change** detection (the latter via `graphql-core`'s `find_breaking_changes` — pure Python, no Node).
- The `gates_agent` mechanism: a GraphQL-focused `api-design` review agent registered with `active_when="battery"`, `active_agents` extended to add a present battery's gated agent, `review-agents` resolving project batteries, and eval fixtures landing with the registration.
- Conditional `strawberry-graphql[fastapi]` dependency; downskill support.
- Tests: unit, functional, render + format-guard, a Docker `--with graphql` acceptance variant, and the agent's hermetic evals.

**Out of scope (deferred / YAGNI):**
- **Subscriptions** — the `subscription` value exists in the metric label space for completeness, but no subscription resolver / websockets transport ships.
- **DataLoader scaffolding** — the demo (a single flat `Item` list) has no N+1; the `api-design` agent *flags* missing dataloaders in builder code rather than the template shipping unused machinery.
- **Federation, custom scalars** beyond what `Item` needs, **persisted queries**, **query-cost/depth limiting** (a builder add-on; the agent can flag its absence on risky schemas).
- **A latency histogram** — the in-process registry is counter/gauge based (consistent with webhooks/websockets); a builder add-on.
- **Async resolvers / async session** — the template's repository + session are synchronous (`sqlalchemy.orm.Session`); resolvers stay sync to match. No new DB plumbing.

## 2. Battery registration

`batteries.py`: register `graphql` with `requires=()` (it reuses the always-rendered baseline `Item` model — not a battery — so it has no battery dependency) and **`gates_agent="api-design"`** (the field added in 8a-1, inert until now). Independent of webhooks/workers; all combos compose (separate route, separate in-process metrics).

## 3. Package & files

```
src/{{package_name}}/graphql/                          # new battery package (gated dir)
  __init__.py
  schema.py        # @strawberry.type Item; Query; Mutation; strawberry.Schema(..., extensions=[MetricsExtension], + prod introspection rule)
  context.py       # get_context(session: Session = Depends(get_session)) -> dict
  metrics.py       # GraphQLMetrics thread-safe singleton (PLAIN .py — no Jinja, label braces safe)
  extension.py     # MetricsExtension(SchemaExtension) — on_operation hook
src/{{package_name}}/routes/{{ 'graphql.py' if 'graphql' in batteries else '' }}.jinja   # exposes router (prefix /graphql) wrapping GraphQLRouter
scripts/{{ 'export-graphql-schema.sh' if 'graphql' in batteries else '' }}.jinja
{{ 'schema.graphql' if 'graphql' in batteries else '' }}.jinja                            # committed SDL contract artifact
infra/observability/prometheus/alerts/{{ 'graphql_alerts.yml' if 'graphql' in batteries else '' }}.jinja
infra/observability/grafana/dashboards/{{ 'graphql.json' if 'graphql' in batteries else '' }}.jinja
tests/functional/{{ 'test_graphql.py' if 'graphql' in batteries else '' }}.jinja
tests/unit/{{ 'test_graphql_metrics.py' if 'graphql' in batteries else '' }}.jinja
```

Framework source (not template payload):
```
src/framework_cli/review/agents/api-design.md           # the GraphQL-focused agent prompt
tests/eval/fixtures/api-design/bad/*.diff + *.expect.json   # >=2 bad
tests/eval/fixtures/api-design/good/*.diff + *.expect.json  # >=1 good
tests/eval/fixtures/thresholds.yaml                          # add an api-design entry (or inherit defaults)
```

Gated edits to shared files (all `{% if "graphql" in batteries %}`):
- `routes/<graphql>.py` — a **pure file-add** (autodiscovery includes any module exposing `router`); no edit to `main.py`/`routes/__init__.py`.
- `routes/health.py` — `/metrics` append (function-local import of `graphql.metrics`).
- `pyproject.toml` — the `strawberry-graphql[fastapi]` dependency.
- `config/settings.py` — the GraphiQL/introspection toggle field + resolver property.
- `.github/workflows/ci.yml` — the GraphQL contract steps (export + staleness + breaking-change), mirroring the existing OpenAPI block.

## 4. Schema & resolvers (code-first, reuse `Item`)

`graphql/schema.py`, authored as Python (Strawberry derives the SDL):
- **`@strawberry.type Item`** — a thin mapping over the ORM row exposing `id: int`, `name: str`, `created_at: datetime` (the decoupling-from-ORM stance mirrors the REST `ItemRead` Pydantic contract).
- **`Query.items`** → calls the baseline `repository.list_items(session)`, mapping ORM rows to the Strawberry `Item` type.
- **`Mutation.create_item(name: str)`** → calls the baseline `repository.create_item(session, name)` — **deliberately exposing the write path REST left unexposed** (REST ships read-only `GET /items`), so GraphQL is a genuine second surface, not a read-only mirror. No new migration: reuses the baseline `items` table.
- The session comes from the GraphQL context (`info.context["session"]`); resolvers are **synchronous**, calling the sync repository directly.
- `strawberry.Schema(query=Query, mutation=Mutation, extensions=[MetricsExtension, *prod_introspection_rule])`.

`graphql/context.py`: `get_context` is Strawberry's `context_getter` — a FastAPI dependency that yields the request-scoped session via the existing `Depends(get_session)`, returned as `{"session": session}`. This reuses the template's session lifecycle (no separate engine/session for GraphQL).

## 5. Route wiring + IDE / introspection toggle

`routes/<graphql>.py` (gated payload): because `routes/__init__.py` includes each module's `router` with **no prefix**, the module bakes the prefix in —
```python
router = APIRouter()
router.include_router(
    GraphQLRouter(schema, context_getter=get_context, graphiql=get_settings().resolved_graphql_ide),
    prefix="/graphql",
)
```
serving GraphQL (POST) and GraphiQL (GET) at `/graphql`. `GraphQLRouter` is itself an `APIRouter` subclass, so autodiscovery's `isinstance(router, APIRouter)` check passes.

**IDE + introspection policy (prescribed, not a builder choice):** GraphiQL and schema introspection are **enabled outside production, disabled in production**. `config/settings.py` gains:
```python
{%- if "graphql" in batteries %}

    # GraphQL IDE (GraphiQL) + schema introspection: enabled outside production only.
    # Explicit override; if None, resolved_graphql_ide derives it from environment.
    graphql_ide_enabled: bool | None = None
{%- endif %}
```
plus a property `resolved_graphql_ide` returning `graphql_ide_enabled` when set, else `self.environment != "production"` (mirrors the `resolved_log_level` pattern; default-safe — a deployment must declare `APP_ENVIRONMENT=production` to lock the schema down, the same trust model the framework already places in `environment`). When introspection is off, the schema adds graphql-core's `NoSchemaIntrospectionCustomRule` via Strawberry's `AddValidationRules` extension. This pre-empts the common footgun of shipping an introspectable, IDE-exposed schema to production.

## 6. Observability (§5 contract)

GraphQL runs **in the app process**, so — like webhooks/websockets — the emitter is an **in-process thread-safe singleton**, and there is **no new liveness signal** (the app's existing `/health` covers it).

- **`graphql/metrics.py`** (plain `.py`, no Jinja → label braces are safe): a module-level `gql_metrics = GraphQLMetrics()` singleton, one `threading.Lock` guarding a `dict[(operation_type, outcome), int]`. Methods: `operation(operation_type, outcome)` (+1); `render_prometheus() -> str`; `reset()`.
  - **Metric:** `app_graphql_operations_total{operation_type,outcome}` (counter). `operation_type ∈ {query, mutation, subscription}`, `outcome ∈ {success, error}` — **both bounded**. The operation *name* is client-defined / unbounded and is **excluded** (same cardinality discipline as webhooks' no-event-type label).
  - 0-initialize `query`/`mutation` × `success`/`error` so the series exist before first traffic. (`subscription` is in the label space but emits only if a subscription ever runs — none ships.)
- **`graphql/extension.py`** — `MetricsExtension(SchemaExtension)` with an `on_operation` generator hook: `yield`, then read `self.execution_context.operation_type` (→ `query`/`mutation`/`subscription`, defaulting to a safe bucket if absent) and `outcome = "error" if self.execution_context.result and self.execution_context.result.errors else "success"`, and call `gql_metrics.operation(...)`. Registered on the schema → every operation is counted with **zero per-resolver wiring**.
- **`routes/health.py` `/metrics`** — gated `{% if "graphql" in batteries %}` block: a function-local `from {{ package_name }}.graphql.metrics import gql_metrics` + `body += gql_metrics.render_prometheus()`. No try/except (pure in-memory). Placed alongside the existing recoverability/webhooks/websockets/workers appends.
- **`graphql_alerts.yml`** (new; Prometheus globs `alerts/*.yml`; not integrity-tracked) — a **HighGraphQLErrorRate** warning rule: `rate(app_graphql_operations_total{outcome="error"}[5m]) / clamp_min(sum(rate(app_graphql_operations_total[5m])), ...) > 0.1` with a **traffic floor** (the websockets-churn `and ... > N` pattern) so a single early error doesn't fire the alert, `for: 10m`, annotated as an **app-specific default to tune or remove**. Single-brace PromQL selectors are safe in a `.jinja` (only `{{`/`{%`/`{#` are Jinja). Separate untracked file — **never** the LOCKED `slo_alerts.yml`.
- **`graphql.json`** (new; auto-provisioned; not tracked) — a **"GraphQL"** dashboard (`uid: "graphql"`), modeled on `webhooks.json`/`websockets.json`: an operations-rate timeseries (by `operation_type`), an error-rate panel, and a success/error split. Plain legends (no `{{...}}`-style legend vars → no Jinja escaping).

## 7. CI schema contract (staleness + breaking-change, pure Python)

- **`schema.graphql`** — the committed SDL artifact, the contract of record. Generated by:
- **`export-graphql-schema.sh`** — builds the schema (Strawberry's SDL printer) and writes `schema.graphql`. Mirrors `export-openapi.sh`.
- **Staleness (every CI run):** re-export and `git diff --exit-code schema.graphql`; fail if the committed SDL drifted from the code (mirrors the OpenAPI staleness step).
- **Breaking-change (PRs):** a small Python step diffs the base-ref `schema.graphql` against the head schema via `graphql-core`'s `graphql.utilities.find_breaking_changes(old_schema, new_schema)` — the `oasdiff` analog (field/type removals, non-null tightening, enum-value removals), in **pure Python, no Node**. `graphql-core` is already present transitively via Strawberry. Implemented as gated steps in `ci.yml` alongside the existing OpenAPI block (build base + head schemas with `graphql.utilities.build_schema`, fail on any returned `BreakingChange`).

## 8. Review agent + the `gates_agent` mechanism

This is the new machinery — battery → agent gating, reused by 8g.

- **`review/registry.py`:** add `AgentSpec("api-design", _prompt("api-design"), block_threshold=<default>, active_when="battery", model=<default>)`. Prompt at `review/agents/api-design.md` — **GraphQL-focused**: N+1 / missing-DataLoader resolver patterns, nullability discipline (over-nullable or wrongly non-null fields), pagination on list fields, mutation & error-handling design (errors-as-data vs thrown), and **schema evolution / breaking changes** (complements the CI gate with judgment).
- **`active_agents` gains a `batteries` argument** and, instead of filtering battery agents out, **adds each present battery's `gates_agent`:**
  ```python
  def active_agents(event: str, batteries: Sequence[str] = ()) -> list[str]:
      gated = {get_battery(b).gates_agent for b in batteries} - {None}
      base = {
          k for k, s in _SPECS.items()
          if (s.on_push if event == "push" else s.active_when in ("always", "file-trigger"))
      }
      return sorted(base | {k for k, s in _SPECS.items()
                            if s.active_when == "battery" and k in gated})
  ```
  Default `batteries=()` preserves every existing call site (no battery agent activates without a gating battery).
- **`cli.py review-agents`** resolves the project's batteries (`source.read_batteries`) and passes them to `active_agents`, so the command reflects the project's actual battery set.
- **The generated CI matrix** calls `review-agents` *inside the generated project*, which reads that project's `.copier-answers.yml` batteries — so `api-design` joins the matrix exactly when `graphql` is present, no CI-template edit needed beyond what already calls `review-agents`.
- **Eval fixtures land with the registration:** `test_every_registered_agent_has_fixtures` enforces ≥2 bad + ≥1 good fixtures per registered agent, so `tests/eval/fixtures/api-design/{bad,good}/*.diff` + `.expect.json` ship in the same change (GraphQL schema/resolver diffs: e.g. a removed non-null field, an N+1 resolver, a non-paginated unbounded list → bad; a clean paginated additive change → good), plus a `thresholds.yaml` entry. The harness stays hermetic; real scoring is Plan 9's job (the provisional-thresholds caveat applies here too).

## 9. Dependencies, migrations, composition

- **`pyproject.toml`:** conditional `strawberry-graphql[fastapi]>=…` (the `celery[redis]` gating pattern). It is a *template* dependency, not a framework dependency — the framework's own env doesn't grow. `graphql-core` is transitive (also powers the breaking-change check).
- **Migrations:** none — reuses the baseline `items` table. The simplest battery on the DB axis (no `0002`/`0003`-style chain entry).
- **Composition:** independent of webhooks/workers; every combo composes (distinct route + distinct in-process metrics). No managed-section (`.env.example`/`Taskfile.yml`) injection — the IDE toggle is a plain settings field with a safe default, needing no secret.

## 10. Downskill

`framework downskill <project> graphql` (the 8a-2 inverse):
- **Owned files** (two-render set diff): the `graphql/` package, `routes/<graphql>.py`, `export-graphql-schema.sh`, `schema.graphql`, `graphql_alerts.yml`, `graphql.json`, and the generated tests.
- **Shared gated edits** (`health.py`, `pyproject.toml`, `settings.py`, `ci.yml`) are handled by 8b-1's `usage_references` **byte-identity exclusion** (framework-gated content that matches the with-battery render is excluded from the usage scan) → `framework downskill graphql` needs **no `--force`** (consistent with webhooks/websockets).
- `record_batteries(reduced)` + `write_manifest` keep `integrity`/`restore` green. No migration is preserved (none was added).

## 11. Integrity & consistency

- `graphql/*`, the route, the export script, `schema.graphql`, the alert, and the dashboard are **new battery payload** (untracked by the integrity manifest). `health.py`/`settings.py`/`pyproject.toml`/`ci.yml` are non-tracked app/config source (their gated edits are byte-identical without the battery).
- **No LOCKED/HYBRID file is touched, no new Prometheus scrape target** (in-process, like webhooks/websockets) → **no `prometheus.yml` change, no integrity-manifest impact**. The cleanest integrity story of the route batteries, matching 8b-1/8e-1.

## 12. Testing

- **Unit (hermetic):** `graphql/metrics.py` — `operation()` increments the right `(type, outcome)` bucket; `render_prometheus()` emits `app_graphql_operations_total` with correct `# TYPE` + 0-initialized series + bounded labels; `reset()` clears.
- **Functional (TestClient):** POST a `query { items { id name } }` (asserts seeded rows; `/metrics` shows `operation_type="query",outcome="success"` +1) and a `mutation { createItem(name: "x") { id } }` (asserts the row is created via the repository; mutation counter +1); assert an invalid query bumps `outcome="error"`; assert **introspection is rejected when the IDE flag is off** (and GraphiQL GET behaves per the flag). `gql_metrics.reset()` first (process-wide singleton).
- **Render (`tests/test_copier_runner.py`):** with `["graphql"]` → the `graphql/` package, route, `export-graphql-schema.sh`, `schema.graphql`, `graphql_alerts.yml`, `graphql.json` render; `health.py` has the `gql_metrics` append; `settings.py` has the toggle; `pyproject.toml` has the dep; `ci.yml` has the contract steps. Without → none render and those shared files are unchanged. A **graphql-only ruff-format-clean** render guard (the 8c pre-commit-cleanliness regression class).
- **Eval-registration tests:** `test_every_registered_agent_has_fixtures` passes for `api-design`; `active_agents("pull_request", ["graphql"])` includes `api-design` and `active_agents("pull_request", [])` does not.
- **Acceptance (Docker):** a `--with graphql` variant runs the generated suite against real Postgres — the functional query + mutation hit the `items` table end-to-end and the schema export script runs.

## 13. Self-review

- **Placeholders:** none — the package layout, the code-first schema (with the exact baseline functions reused), the route/prefix wiring, the settings toggle (with the exact derivation rule + prod introspection rule), the metrics singleton + label set + extension hook, the `/metrics` append, the concrete alert/dashboard, the CI staleness + `find_breaking_changes` mechanism, the `active_agents` signature change (with code), and the test tiers are all specified. Subscriptions/dataloaders/federation/histograms/async are explicitly deferred with reasons.
- **Internal consistency:** in-process surface → in-process singleton + no liveness (matches webhooks/websockets); reuse of the baseline `Item`/repository → no new migration and a sync resolver matching the sync session; bounded labels (cardinality discipline); SDL exported either way → the breaking-change gate holds under code-first; the `gates_agent` field (8a-1) finally consumed; downskill clean via the 8b-1 exclusion.
- **Scope:** one cohesive battery (route + schema + observability + CI contract) **plus** the reusable `gates_agent` machinery (one new agent + the `active_agents`/`review-agents` wiring). Larger than the backfills, but a single coherent plan; 8g reuses the machinery without re-deciding it.
- **Ambiguity:** "schema-first" (meta-plan wording) resolved to **code-first** with SDL as the contract artifact; IDE/introspection pinned to `environment != "production"` (overridable); "messages/operations" pinned to per-operation counting via the extension hook with bounded `(type, outcome)` labels; breaking-change detection pinned to `graphql-core.find_breaking_changes` (no Node).

---

*End of design. Next step: `superpowers:writing-plans` for Plan 8d.*
