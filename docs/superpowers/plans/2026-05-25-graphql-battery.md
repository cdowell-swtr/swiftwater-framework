# GraphQL Battery (Plan 8d) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `graphql` battery — a Strawberry, code-first GraphQL endpoint at `/graphql` over the baseline `Item` model — and activate the framework's first battery-gated review agent (`api-design`) via the `gates_agent` mechanism.

**Architecture:** A route battery (autodiscovered, in-process). A `graphql/` package holds a code-first schema reusing `db/repository.py`, a request-scoped DB-session context, an in-process metrics singleton, and a Strawberry `SchemaExtension` emission seam. Observability follows the webhooks/websockets in-process pattern (metric on `/metrics`, separate alert + dashboard files). CI gains gated staleness + breaking-change steps using `graphql-core` (no Node). The `gates_agent` field (defined in 8a-1) is finally consumed: `active_agents` gains a `batteries` argument and adds a present battery's gated agent.

**Tech Stack:** Python 3.12, Strawberry GraphQL (`strawberry-graphql[fastapi]`), FastAPI, SQLAlchemy (sync), `graphql-core` (transitive — powers SDL export + breaking-change detection), Copier/Jinja templating, pytest.

**Spec:** `docs/superpowers/specs/2026-05-25-graphql-battery-design.md`

---

## Conventions you MUST follow

- **`src/framework_cli/template/` is template payload**, rendered into generated projects. Files with `{{ }}`/`{% %}` Jinja MUST be `.jinja`; plain Python using only relative imports + no interpolation stays `.py`. The framework's `mypy` excludes the template; the template is validated by render + Docker acceptance.
- **THE JINJA-BRACE PITFALL (critical):** in a `.jinja` file, `{{`, `{%`, `{#` are Jinja. Prometheus metric label literals like `app_x{label="v"}` use **single** braces — those are SAFE in `.jinja`. But an **f-string with doubled braces** (`f'...{{label="{v}"}}...'`) collides with Jinja and breaks rendering. In `.jinja` test files, assert with **plain string literals** (single braces) or **string concatenation** (`'app_x{label="' + v + '"} 0'`) — NEVER f-strings with `{{`. In a **plain `.py`** file (no Jinja), f-strings with `{{` are fine (that's how `webhooks/metrics.py` renders).
- **Whitespace control:** gated `{%- if ... %}` / `{%- endif %}` blocks must leave the no-battery render byte-identical and ruff-format-clean. Mirror the existing webhooks/workers gated blocks exactly. `ci.yml` is **LOCKED_TRACKED** — a gated edit there must be byte-identical without `graphql` (integrity stays green; with `graphql` the battery-aware restore handles it, the workers/`dev.yml` precedent).
- **TDD:** failing test first → confirm red → minimal implementation → confirm green → commit. Run framework tooling via `uv run`.
- **Quality gate before each commit:** `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`.

## File Structure

**Framework source (lint/type-checked as framework code):**
- Modify `src/framework_cli/review/registry.py` — `active_agents(event, batteries=())`; register `api-design`.
- Modify `src/framework_cli/cli.py` — `review-agents` reads project batteries.
- Modify `src/framework_cli/batteries.py` — register `graphql` with `gates_agent="api-design"`.
- Create `src/framework_cli/review/agents/api-design.md` — the GraphQL-focused agent prompt.
- Create `tests/eval/fixtures/api-design/bad/*.diff` + `*.expect.json` (≥2) and `good/*.diff` (≥1).
- Modify/create tests under `tests/review/`, `tests/`, `tests/acceptance/`.

**Template payload (rendered into projects):**
- Create `src/framework_cli/template/src/{{package_name}}/{% if "graphql" in batteries %}graphql{% endif %}/__init__.py`, `schema.py`, `context.py`, `metrics.py`, `extension.py`.
- Create `src/framework_cli/template/src/{{package_name}}/routes/{{ 'graphql.py' if 'graphql' in batteries else '' }}.jinja`.
- Modify `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja` — IDE/introspection toggle.
- Modify `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja` — `/metrics` append.
- Modify `src/framework_cli/template/pyproject.toml.jinja` — conditional dependency.
- Create `src/framework_cli/template/scripts/{{ 'export-graphql-schema.sh' if 'graphql' in batteries else '' }}.jinja`.
- Modify `src/framework_cli/template/.github/workflows/ci.yml.jinja` — gated contract steps.
- Create `src/framework_cli/template/infra/observability/prometheus/alerts/{{ 'graphql_alerts.yml' if 'graphql' in batteries else '' }}.jinja`.
- Create `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'graphql.json' if 'graphql' in batteries else '' }}.jinja`.
- Create `src/framework_cli/template/tests/functional/{{ 'test_graphql.py' if 'graphql' in batteries else '' }}.jinja`.
- Create `src/framework_cli/template/tests/unit/{{ 'test_graphql_metrics.py' if 'graphql' in batteries else '' }}.jinja`.

> **Strawberry API version note:** a few Strawberry symbols have shifted across versions — `strawberry.Info` (vs `strawberry.types.Info`), `GraphQLRouter(..., graphql_ide=...)` (older: `graphiql=`), and `ExecutionContext.operation_type`. The plan uses the current (≥0.235) API. Where a step is annotated **[verify-API]**, confirm the symbol against the installed Strawberry during the red/green loop and adjust if the installed version differs; the tests will catch a mismatch.

---

## Task 1: Battery-gate the review agents (`active_agents` + `review-agents` CLI)

**Files:**
- Modify: `src/framework_cli/review/registry.py:66-73`
- Modify: `src/framework_cli/cli.py:236-244`
- Test: `tests/review/test_registry.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `tests/review/test_registry.py`:

```python
def test_active_agents_excludes_battery_agents_by_default():
    from framework_cli.review.registry import active_agents

    # No batteries → no battery-gated agent appears (and the call still works with the new arg).
    assert active_agents("pull_request") == active_agents("pull_request", [])


def test_active_agents_adds_gated_agent_when_battery_present(monkeypatch):
    from framework_cli import batteries as bat
    from framework_cli.review import registry

    bat._BATTERIES["_demo"] = bat.BatterySpec("_demo", "x", gates_agent="_demo-agent")
    registry._SPECS["_demo-agent"] = registry.AgentSpec(
        "review-demo", "p", "high", "battery", registry.DEFAULT_MODEL
    )
    try:
        assert "_demo-agent" in registry.active_agents("pull_request", ["_demo"])
        assert "_demo-agent" not in registry.active_agents("pull_request", [])
        # push event: a battery agent without on_push is still gated in only when present.
        assert "_demo-agent" not in registry.active_agents("push", [])
    finally:
        del bat._BATTERIES["_demo"], registry._SPECS["_demo-agent"]


def test_active_agents_ignores_none_gates_agent():
    from framework_cli.review.registry import active_agents

    # webhooks/websockets/workers have gates_agent=None → adding them changes nothing.
    assert active_agents("pull_request", ["webhooks", "workers"]) == active_agents("pull_request")
```

- [ ] **Step 2: Run to verify red**

Run: `uv run pytest tests/review/test_registry.py -q`
Expected: FAIL — `active_agents()` takes 1 positional arg, not 2.

- [ ] **Step 3: Implement the signature change**

In `src/framework_cli/review/registry.py`, add the import and replace `active_agents`:

```python
from collections.abc import Sequence  # add to imports

from framework_cli.batteries import get_battery  # add to imports


def active_agents(event: str, batteries: Sequence[str] = ()) -> list[str]:
    """Agent names active for a CI event. On push, the always-on-main subset; otherwise all
    non-battery agents. A battery in `batteries` additionally activates its `gates_agent`."""
    gated = {get_battery(b).gates_agent for b in batteries} - {None}
    if event == "push":
        base = {k for k, s in _SPECS.items() if s.on_push}
    else:
        base = {k for k, s in _SPECS.items() if s.active_when in ("always", "file-trigger")}
    base |= {k for k, s in _SPECS.items() if s.active_when == "battery" and k in gated}
    return sorted(base)
```

> Check for an import cycle: `batteries.py` must not import `registry`. It does not (it only imports `dataclasses`/`collections.abc`), so the new `registry → batteries` import is safe.

- [ ] **Step 4: Wire the CLI to read project batteries**

In `src/framework_cli/cli.py`, replace the `review-agents` command body (lines 236-244):

```python
@app.command(name="review-agents")
def review_agents(
    event: str = typer.Option("", "--event", help="GitHub event name (default: $GITHUB_EVENT_NAME)."),
) -> None:
    """Print the JSON array of review agents active for the event (drives the CI matrix)."""
    import json

    from framework_cli.source import read_batteries

    resolved = event or os.environ.get("GITHUB_EVENT_NAME", "pull_request")
    batteries = read_batteries(Path("."))  # the generated project's recorded battery set
    typer.echo(json.dumps(active_agents(resolved, batteries)))
```

(`Path` and `os` are already imported in `cli.py`; confirm and add only if missing.)

- [ ] **Step 5: Run to verify green**

Run: `uv run pytest tests/review/test_registry.py -q`
Expected: PASS.

- [ ] **Step 6: Full gate + commit**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: PASS (no agent registered yet, so `test_every_registered_agent_has_fixtures` is unaffected).

```bash
git add src/framework_cli/review/registry.py src/framework_cli/cli.py tests/review/test_registry.py
git add CLAUDE.md  # bump Last updated (see "Keeping state current")
git commit -m "feat(review): battery-gate active_agents + review-agents reads project batteries"
```

---

## Task 2: Register the `api-design` agent + the `graphql` battery (+ fixtures)

**Files:**
- Create: `src/framework_cli/review/agents/api-design.md`
- Modify: `src/framework_cli/review/registry.py` (`_SPECS`)
- Modify: `src/framework_cli/batteries.py` (`_BATTERIES`)
- Create: `tests/eval/fixtures/api-design/bad/{breaking-field-removal,n-plus-one,unbounded-list}.diff` + `.expect.json`
- Create: `tests/eval/fixtures/api-design/good/additive-optional-field.diff`
- Test: `tests/test_batteries.py`, `tests/review/test_registry.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/review/test_registry.py`:

```python
def test_graphql_battery_gates_api_design():
    from framework_cli.batteries import get_battery
    from framework_cli.review.registry import active_agents

    assert get_battery("graphql").gates_agent == "api-design"
    assert "api-design" in active_agents("pull_request", ["graphql"])
    assert "api-design" not in active_agents("pull_request", [])
```

Add to `tests/test_batteries.py` (a focused check; mirror existing battery tests there):

```python
def test_graphql_battery_registered():
    from framework_cli.batteries import battery_names, get_battery, resolve

    assert "graphql" in battery_names()
    assert get_battery("graphql").requires == ()
    assert resolve(["graphql"]) == ["graphql"]
```

- [ ] **Step 2: Run to verify red**

Run: `uv run pytest tests/test_batteries.py tests/review/test_registry.py -q`
Expected: FAIL — unknown battery `graphql`; `api-design` not registered.

- [ ] **Step 3: Write the agent prompt**

Create `src/framework_cli/review/agents/api-design.md` (mirror the format of `agents/architecture.md` exactly — terse role + flag list + JSON-only output contract):

```markdown
You are `review-api-design`. Review ONLY the unified diff of a GraphQL schema/resolver change
(Strawberry, code-first). Flag GraphQL API-design problems and cite the changed line:

- N+1 resolvers: a resolver issuing a database/remote query per item in a loop (instead of a
  batched/`DataLoader` fetch). "high".
- Breaking schema changes WITHOUT a compatible path: removing a field/type, renaming, or
  tightening a nullable field to non-null. "high".
- Unbounded list fields: a list-returning field with no pagination (first/after, limit/offset)
  on a collection that can grow. "high".
- Nullability mistakes: a field that can genuinely be absent typed as non-null, or pervasive
  over-nullability that pushes null-handling onto every client. "info".
- Mutation/error design: mutations that swallow errors, return bare scalars instead of a typed
  payload, or lack input validation. "info".

Do NOT flag additive, backwards-compatible changes (a new optional/nullable field, a new query),
or REST/OpenAPI concerns (covered elsewhere).

Return JSON ONLY — an array of {"path","line","severity","message","suggestion"}; [] if none. An
N+1 resolver, an uncompensated breaking change, or an unbounded list field is "high".
```

- [ ] **Step 4: Register the agent + battery**

In `src/framework_cli/review/registry.py`, add to `_SPECS` (alongside the others):

```python
    "api-design": AgentSpec(
        "review-api-design", _prompt("api-design"), "high", "battery", DEFAULT_MODEL
    ),
```

In `src/framework_cli/batteries.py`, add to `_BATTERIES`:

```python
    "graphql": BatterySpec(
        "graphql",
        "Strawberry code-first GraphQL endpoint at /graphql over the demo Item model",
        gates_agent="api-design",
    ),
```

- [ ] **Step 5: Write the eval fixtures**

Create the bad fixtures (each `.diff` + a sibling `.expect.json` = `{"file": "src/myapp/graphql/schema.py"}`):

`tests/eval/fixtures/api-design/bad/breaking-field-removal.diff`:
```diff
--- a/src/myapp/graphql/schema.py
+++ b/src/myapp/graphql/schema.py
@@ -7,7 +7,6 @@ import strawberry
 @strawberry.type
 class Item:
     id: int
-    name: str
     created_at: datetime.datetime
```

`tests/eval/fixtures/api-design/bad/n-plus-one.diff`:
```diff
--- a/src/myapp/graphql/schema.py
+++ b/src/myapp/graphql/schema.py
@@ -18,4 +18,8 @@ class Query:
     @strawberry.field
     def items(self, info) -> list[Item]:
         session = info.context["session"]
-        return [_to_item(r) for r in repository.list_items(session)]
+        out = []
+        for row in repository.list_items(session):
+            owner = session.query(Owner).filter_by(id=row.owner_id).one()  # query per item
+            out.append(_to_item(row, owner))
+        return out
```

`tests/eval/fixtures/api-design/bad/unbounded-list.diff`:
```diff
--- a/src/myapp/graphql/schema.py
+++ b/src/myapp/graphql/schema.py
@@ -18,3 +18,7 @@ class Query:
     @strawberry.field
     def items(self, info) -> list[Item]:
         return [_to_item(r) for r in repository.list_items(info.context["session"])]
+
+    @strawberry.field
+    def all_events(self, info) -> list[Event]:  # no pagination on an unbounded collection
+        return [_to_event(r) for r in info.context["session"].query(Event).all()]
```

The good fixture (no `.expect.json`) — `tests/eval/fixtures/api-design/good/additive-optional-field.diff`:
```diff
--- a/src/myapp/graphql/schema.py
+++ b/src/myapp/graphql/schema.py
@@ -7,6 +7,7 @@ import strawberry
 @strawberry.type
 class Item:
     id: int
     name: str
     created_at: datetime.datetime
+    description: str | None = None  # additive, nullable — backwards compatible
```

- [ ] **Step 6: Run to verify green**

Run: `uv run pytest tests/test_batteries.py tests/review/test_registry.py tests/review/test_evals.py -q`
Expected: PASS — including `test_every_registered_agent_has_fixtures` (api-design now has 3 bad + 1 good) and `test_fixtures_are_wellformed` (each bad fixture's `seeded_file` is among its `+++ b/` paths).

- [ ] **Step 7: Full gate + commit**

```bash
git add src/framework_cli/review/registry.py src/framework_cli/review/agents/api-design.md \
        src/framework_cli/batteries.py tests/eval/fixtures/api-design tests/test_batteries.py \
        tests/review/test_registry.py CLAUDE.md
git commit -m "feat(review): register api-design agent gated by the graphql battery + eval fixtures"
```

---

## Task 3: GraphQL schema, context, route, settings toggle, dependency

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "graphql" in batteries %}graphql{% endif %}/__init__.py`
- Create: `.../{% if "graphql" in batteries %}graphql{% endif %}/schema.py`
- Create: `.../{% if "graphql" in batteries %}graphql{% endif %}/context.py`
- Create: `src/framework_cli/template/src/{{package_name}}/routes/{{ 'graphql.py' if 'graphql' in batteries else '' }}.jinja`
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja`
- Modify: `src/framework_cli/template/pyproject.toml.jinja`
- Create: `src/framework_cli/template/tests/functional/{{ 'test_graphql.py' if 'graphql' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

> The `graphql/` package directory uses the path-templating form `{% if "graphql" in batteries %}graphql{% endif %}` (the webhooks-package precedent — see `find` output for `{% if "webhooks" in batteries %}webhooks{% endif %}`). Files inside use plain relative imports (no `{{ package_name }}`), so they are plain `.py`.

- [ ] **Step 1: Write the failing render tests**

Add to `tests/test_copier_runner.py`:

```python
def test_render_with_graphql_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    pkg = dest / "src" / "demo"
    assert (pkg / "graphql" / "schema.py").is_file()
    assert (pkg / "graphql" / "context.py").is_file()
    assert (pkg / "routes" / "graphql.py").is_file()
    assert (dest / "tests" / "functional" / "test_graphql.py").is_file()
    route = (pkg / "routes" / "graphql.py").read_text()
    assert "GraphQLRouter" in route and 'prefix="/graphql"' in route


def test_render_without_graphql_has_none(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "src" / "demo" / "graphql").exists()
    assert not (dest / "src" / "demo" / "routes" / "graphql.py").exists()


def test_render_graphql_settings_and_dep(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    settings = (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "graphql_ide_enabled" in settings and "resolved_graphql_ide" in settings
    assert "strawberry-graphql[fastapi]" in (dest / "pyproject.toml").read_text()


def test_render_graphql_settings_clean_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert "graphql_ide_enabled" not in (dest / "src" / "demo" / "config" / "settings.py").read_text()
    assert "strawberry-graphql" not in (dest / "pyproject.toml").read_text()


def test_render_graphql_battery_is_ruff_format_clean(tmp_path: Path):
    """Hermetic guard: graphql-only render must be ruff-format-clean without Docker."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    _assert_ruff_format_clean(dest)
```

- [ ] **Step 2: Run to verify red**

Run: `uv run pytest tests/test_copier_runner.py -q -k graphql`
Expected: FAIL — files not rendered.

- [ ] **Step 3: Create the package files**

`graphql/__init__.py`: empty file.

`graphql/context.py`:
```python
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from ..db.engine import get_session


def get_context(session: Annotated[Session, Depends(get_session)]) -> dict:
    """Strawberry context_getter — exposes a request-scoped DB session to resolvers."""
    return {"session": session}
```

`graphql/schema.py` (**[verify-API]** `strawberry.Info`, `AddValidationRules`, `NoSchemaIntrospectionCustomRule`). Note: `extensions` starts empty here; Task 4 adds `MetricsExtension`.
```python
from __future__ import annotations

import datetime

import strawberry
from graphql.validation import NoSchemaIntrospectionCustomRule
from strawberry.extensions import AddValidationRules, SchemaExtension

from ..db import repository
from ..db.models import Item as ItemModel


@strawberry.type
class Item:
    id: int
    name: str
    created_at: datetime.datetime


def _to_item(row: ItemModel) -> Item:
    return Item(id=row.id, name=row.name, created_at=row.created_at)


@strawberry.type
class Query:
    @strawberry.field
    def items(self, info: strawberry.Info) -> list[Item]:
        session = info.context["session"]
        return [_to_item(r) for r in repository.list_items(session)]


@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_item(self, info: strawberry.Info, name: str) -> Item:
        session = info.context["session"]
        return _to_item(repository.create_item(session, name))


def build_schema(*, disable_introspection: bool) -> strawberry.Schema:
    """Build the schema. Introspection is disabled (NoSchemaIntrospectionCustomRule) in
    production; Task 4 prepends the metrics extension."""
    extensions: list[type[SchemaExtension] | AddValidationRules] = []
    if disable_introspection:
        extensions.append(AddValidationRules([NoSchemaIntrospectionCustomRule]))
    return strawberry.Schema(query=Query, mutation=Mutation, extensions=extensions)


# Introspectable schema for SDL export (scripts/export-graphql-schema.sh) + the contract diff.
schema = build_schema(disable_introspection=False)
```

`routes/{{ 'graphql.py' ... }}.jinja` (plain Python; templated only by the path):
```python
from fastapi import APIRouter
from strawberry.fastapi import GraphQLRouter

from ..config.settings import get_settings
from ..graphql.context import get_context
from ..graphql.schema import build_schema

router = APIRouter()

_ide = get_settings().resolved_graphql_ide
_schema = build_schema(disable_introspection=not _ide)

router.include_router(
    GraphQLRouter(
        _schema,
        context_getter=get_context,
        graphql_ide="graphiql" if _ide else None,
    ),
    prefix="/graphql",
)
```

> **[verify-API]** If `uv run mypy src` in the rendered project complains about `GraphQLRouter` generics, parameterize as `GraphQLRouter[dict, None]` or add a targeted `# type: ignore[...]`. The Docker pre-commit/acceptance gate (Task 8) is authoritative.

- [ ] **Step 4: Add the settings toggle**

In `config/settings.py.jinja`, add a gated block after the `workers` block (line 41, before the blank line preceding `resolved_log_level`), mirroring the existing `{%- if %}` style:

```jinja
{%- if "graphql" in batteries %}

    # GraphQL IDE (GraphiQL) + schema introspection: enabled outside production only.
    # Explicit override; if None, resolved_graphql_ide derives it from environment.
    graphql_ide_enabled: bool | None = None
{%- endif %}
```

And add the resolver property after `resolved_log_level` (inside the class, before `@lru_cache`):

```jinja
{%- if "graphql" in batteries %}

    @property
    def resolved_graphql_ide(self) -> bool:
        if self.graphql_ide_enabled is not None:
            return self.graphql_ide_enabled
        return self.environment != "production"
{%- endif %}
```

- [ ] **Step 5: Add the dependency**

In `pyproject.toml.jinja`, insert the graphql line before the workers conditional (lines 17-19):

```jinja
    "pybreaker>=1.2",
{% if "graphql" in batteries %}    "strawberry-graphql[fastapi]>=0.235",
{% endif %}{% if "workers" in batteries %}    "celery[redis]>=5.4",
{% endif %}]
```

> Strawberry ships `py.typed`, so **no** `[[tool.mypy.overrides]]` entry is needed (unlike celery).

- [ ] **Step 6: Write the generated functional test**

`tests/functional/{{ 'test_graphql.py' ... }}.jinja` (uses the `db_session` fixture pattern from `test_items_route.py`; metrics assertions land in Task 4):
```python
from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from {{ package_name }}.db.engine import get_session
from {{ package_name }}.db.repository import create_item
from {{ package_name }}.main import create_app


def _client(db_session: Session) -> TestClient:
    def override() -> Iterator[Session]:
        yield db_session

    app = create_app()
    app.dependency_overrides[get_session] = override
    return TestClient(app)


def _gql(client: TestClient, query: str):
    return client.post("/graphql", json={"query": query})


def test_query_items_returns_created_row(db_session: Session):
    create_item(db_session, "alpha")
    r = _gql(_client(db_session), "{ items { id name } }")
    assert r.status_code == 200
    assert "alpha" in {row["name"] for row in r.json()["data"]["items"]}


def test_create_item_mutation_persists(db_session: Session):
    client = _client(db_session)
    r = _gql(client, 'mutation { createItem(name: "gamma") { id name } }')
    assert r.status_code == 200
    assert r.json()["data"]["createItem"]["name"] == "gamma"
    r2 = _gql(client, "{ items { name } }")
    assert "gamma" in {row["name"] for row in r2.json()["data"]["items"]}


def test_introspection_disabled_when_off():
    from {{ package_name }}.graphql.schema import build_schema

    result = build_schema(disable_introspection=True).execute_sync("{ __schema { queryType { name } } }")
    assert result.errors  # introspection is blocked in production
```

- [ ] **Step 7: Run render tests to verify green**

Run: `uv run pytest tests/test_copier_runner.py -q -k graphql`
Expected: PASS (including the format guard).

- [ ] **Step 8: Full gate + commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py CLAUDE.md
git commit -m "feat(graphql): code-first schema, context, /graphql route, settings toggle, dep"
```

---

## Task 4: Observability — metrics singleton, extension, `/metrics` append

**Files:**
- Create: `.../{% if "graphql" in batteries %}graphql{% endif %}/metrics.py`
- Create: `.../{% if "graphql" in batteries %}graphql{% endif %}/extension.py`
- Modify: `.../graphql/schema.py` (register `MetricsExtension`)
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja`
- Create: `src/framework_cli/template/tests/unit/{{ 'test_graphql_metrics.py' if 'graphql' in batteries else '' }}.jinja`
- Modify: `tests/functional/{{ 'test_graphql.py' ... }}.jinja` (metrics assertions)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render tests**

Add to `tests/test_copier_runner.py`:

```python
def test_render_graphql_metrics_module(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    assert (dest / "src" / "demo" / "graphql" / "metrics.py").exists()
    assert (dest / "src" / "demo" / "graphql" / "extension.py").exists()
    assert (dest / "tests" / "unit" / "test_graphql_metrics.py").exists()
    schema = (dest / "src" / "demo" / "graphql" / "schema.py").read_text()
    assert "MetricsExtension" in schema
    health = (dest / "src" / "demo" / "routes" / "health.py").read_text()
    assert "gql_metrics.render_prometheus" in health


def test_render_health_clean_without_graphql(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert "gql_metrics" not in (dest / "src" / "demo" / "routes" / "health.py").read_text()
```

- [ ] **Step 2: Run to verify red**

Run: `uv run pytest tests/test_copier_runner.py -q -k graphql`
Expected: FAIL.

- [ ] **Step 3: Create the metrics singleton**

`graphql/metrics.py` (plain `.py` — f-strings with `{{`/`}}` are correct here, NOT a `.jinja` file):
```python
"""Process-wide GraphQL operation metrics — counts operations by type and outcome.

A module-level singleton (like observability/recoverability.py), incremented by the schema's
MetricsExtension and appended to the /metrics exposition. Label-light by design: operation_type
and outcome are bounded; the client-defined operation NAME is deliberately NOT a label.
"""

from __future__ import annotations

import threading

OPERATION_TYPES = ("query", "mutation", "subscription")
OUTCOMES = ("success", "error")
# 0-initialized base series (subscription is created lazily only if one ever runs).
_BASE = [("query", "success"), ("query", "error"), ("mutation", "success"), ("mutation", "error")]

_HEADER = (
    "# HELP app_graphql_operations_total GraphQL operations by type and outcome\n"
    "# TYPE app_graphql_operations_total counter\n"
)


class GraphQLMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str], int] = {k: 0 for k in _BASE}

    def operation(self, operation_type: str, outcome: str) -> None:
        """Increment one (type, outcome) bucket. Unknown values are ignored (never crash a
        request, never create an unbounded series)."""
        if operation_type not in OPERATION_TYPES or outcome not in OUTCOMES:
            return
        with self._lock:
            key = (operation_type, outcome)
            self._counts[key] = self._counts.get(key, 0) + 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                f'app_graphql_operations_total{{operation_type="{t}",outcome="{o}"}} {c}'
                for (t, o), c in sorted(self._counts.items())
            ]
        return _HEADER + "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counts = {k: 0 for k in _BASE}


gql_metrics = GraphQLMetrics()
"""The process-wide singleton imported by the MetricsExtension and the /metrics route."""
```

- [ ] **Step 4: Create the extension**

`graphql/extension.py` (**[verify-API]** `on_operation` generator hook + `execution_context.operation_type`):
```python
from __future__ import annotations

from collections.abc import Iterator

from strawberry.extensions import SchemaExtension

from .metrics import gql_metrics


class MetricsExtension(SchemaExtension):
    """Counts every GraphQL operation by type and outcome via the in-process singleton."""

    def on_operation(self) -> Iterator[None]:
        yield
        ec = self.execution_context
        op = ec.operation_type
        # OperationType.QUERY.value == "query"; default to "query" if undetermined.
        op_type = op.value if op is not None else "query"
        outcome = "error" if (ec.result is not None and ec.result.errors) else "success"
        gql_metrics.operation(op_type, outcome)
```

- [ ] **Step 5: Register the extension on the schema**

In `graphql/schema.py`, import and prepend `MetricsExtension` in `build_schema`:
```python
from .extension import MetricsExtension  # add to imports
```
```python
    extensions: list[type[SchemaExtension] | AddValidationRules] = [MetricsExtension]
    if disable_introspection:
        extensions.append(AddValidationRules([NoSchemaIntrospectionCustomRule]))
```

- [ ] **Step 6: Append to `/metrics`**

In `routes/health.py.jinja`, add a gated block after the `websockets` block (after line 59), mirroring the webhooks/websockets style:
```jinja
{%- if "graphql" in batteries %}

    from {{ package_name }}.graphql.metrics import gql_metrics

    body += gql_metrics.render_prometheus()
{%- endif %}
```

- [ ] **Step 7: Write the generated unit test**

`tests/unit/{{ 'test_graphql_metrics.py' ... }}.jinja` — **a `.jinja` file: NO f-strings with `{{`.** Use plain literals (single braces) or concatenation:
```python
"""GraphQL battery — unit tests for the in-process metrics counter (hermetic)."""

from {{ package_name }}.graphql.metrics import OUTCOMES, GraphQLMetrics


def test_operation_increments_bucket():
    m = GraphQLMetrics()
    m.operation("query", "success")
    m.operation("query", "success")
    m.operation("mutation", "error")
    out = m.render_prometheus()
    assert 'app_graphql_operations_total{operation_type="query",outcome="success"} 2' in out
    assert 'app_graphql_operations_total{operation_type="mutation",outcome="error"} 1' in out


def test_base_series_present_at_zero():
    out = GraphQLMetrics().render_prometheus()
    for t in ("query", "mutation"):
        for o in OUTCOMES:
            assert (
                'app_graphql_operations_total{operation_type="' + t + '",outcome="' + o + '"} 0'
            ) in out
    assert "# TYPE app_graphql_operations_total counter" in out


def test_unknown_type_or_outcome_ignored():
    m = GraphQLMetrics()
    m.operation("query", "weird")   # unknown outcome
    m.operation("nonsense", "success")  # unknown type
    out = m.render_prometheus()
    assert "weird" not in out and "nonsense" not in out


def test_reset_clears():
    m = GraphQLMetrics()
    m.operation("query", "success")
    m.reset()
    assert 'app_graphql_operations_total{operation_type="query",outcome="success"} 0' in m.render_prometheus()
```

- [ ] **Step 8: Extend the functional test with metrics assertions**

Append to `tests/functional/{{ 'test_graphql.py' ... }}.jinja` (these are plain literals — single braces — safe in `.jinja`):
```python
def test_metrics_count_graphql_operations(db_session: Session):
    from {{ package_name }}.graphql.metrics import gql_metrics

    gql_metrics.reset()
    client = _client(db_session)
    _gql(client, "{ items { id } }")                          # query success
    _gql(client, 'mutation { createItem(name: "x") { id } }')  # mutation success
    _gql(client, "{ nope }")                                   # query error (unknown field)
    body = client.get("/metrics").text
    assert 'app_graphql_operations_total{operation_type="query",outcome="success"} 1' in body
    assert 'app_graphql_operations_total{operation_type="mutation",outcome="success"} 1' in body
    assert 'app_graphql_operations_total{operation_type="query",outcome="error"} 1' in body
```

- [ ] **Step 9: Run render tests + format guard to verify green**

Run: `uv run pytest tests/test_copier_runner.py -q -k graphql`
Expected: PASS (the format guard catches any `.jinja` brace/whitespace regression).

- [ ] **Step 10: Full gate + commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py CLAUDE.md
git commit -m "feat(graphql): in-process operation metrics via a Strawberry SchemaExtension on /metrics"
```

---

## Task 5: Alerts + dashboard

**Files:**
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/{{ 'graphql_alerts.yml' if 'graphql' in batteries else '' }}.jinja`
- Create: `src/framework_cli/template/infra/observability/grafana/dashboards/{{ 'graphql.json' if 'graphql' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing render tests**

Add to `tests/test_copier_runner.py`:

```python
def test_render_graphql_alerts_and_dashboard(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    alerts = dest / "infra" / "observability" / "prometheus" / "alerts" / "graphql_alerts.yml"
    dash = dest / "infra" / "observability" / "grafana" / "dashboards" / "graphql.json"
    assert alerts.exists() and dash.exists()
    parsed = yaml.safe_load(alerts.read_text())
    assert parsed["groups"][0]["name"] == "graphql"
    json.loads(dash.read_text())  # valid JSON


def test_render_no_graphql_alerts_without_battery(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert not (dest / "infra" / "observability" / "prometheus" / "alerts" / "graphql_alerts.yml").exists()
    assert not (dest / "infra" / "observability" / "grafana" / "dashboards" / "graphql.json").exists()
```

- [ ] **Step 2: Run to verify red**

Run: `uv run pytest tests/test_copier_runner.py -q -k "graphql_alerts"`
Expected: FAIL.

- [ ] **Step 3: Write the alert rule**

`alerts/{{ 'graphql_alerts.yml' ... }}.jinja` (single-brace PromQL selectors are safe in `.jinja`; mirror `webhooks_alerts.yml`):
```yaml
groups:
- name: graphql
  rules:
  - alert: HighGraphQLErrorRate
    # `and ... > 0.05` traffic floor suppresses noise at low request rates (where one error
    # spikes the ratio). App-specific default — tune the threshold/floor or remove.
    expr: sum(rate(app_graphql_operations_total{outcome="error"}[5m])) / clamp_min(sum(rate(app_graphql_operations_total[5m])), 1) > 0.1 and sum(rate(app_graphql_operations_total[5m])) > 0.05
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: Over 10% of GraphQL operations are erroring (resolver failures or invalid queries) — app-specific default; tune the threshold/floor or remove
```

- [ ] **Step 4: Write the dashboard**

`dashboards/{{ 'graphql.json' ... }}.jinja` — model on `webhooks.json`/`websockets.json` (read one for the exact panel schema). Use `uid: "graphql"`, title "GraphQL", and panels: an operations-rate timeseries `sum by (operation_type) (rate(app_graphql_operations_total[5m]))`, an error-rate panel, and a success/error split. **Plain legends only** (no `{{...}}` legend variables → no Jinja escaping). Verify it is valid JSON (the render test parses it).

- [ ] **Step 5: Run to verify green**

Run: `uv run pytest tests/test_copier_runner.py -q -k "graphql"`
Expected: PASS.

- [ ] **Step 6: Full gate + commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py CLAUDE.md
git commit -m "feat(graphql): error-rate alert rule + Grafana dashboard"
```

---

## Task 6: CI schema contract — export script + staleness + breaking-change

**Files:**
- Create: `src/framework_cli/template/scripts/{{ 'export-graphql-schema.sh' if 'graphql' in batteries else '' }}.jinja`
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja`
- Test: `tests/test_copier_runner.py`

> Mirror `openapi.json`: the SDL artifact `schema.graphql` is **not** shipped in the template — the generated project runs the export script and commits `schema.graphql` before its first push; CI's staleness check enforces currency.

- [ ] **Step 1: Write the failing render tests**

Add to `tests/test_copier_runner.py`:

```python
def test_render_graphql_export_script(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["graphql"]})
    script = dest / "scripts" / "export-graphql-schema.sh"
    assert script.is_file()
    assert "schema.graphql" in script.read_text()
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "export-graphql-schema.sh" in ci and "find_breaking_changes" in ci


def test_render_ci_clean_without_graphql(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    ci = (dest / ".github" / "workflows" / "ci.yml").read_text()
    assert "graphql" not in ci and "export-graphql-schema" not in ci
```

- [ ] **Step 2: Run to verify red**

Run: `uv run pytest tests/test_copier_runner.py -q -k "graphql_export or ci_clean"`
Expected: FAIL.

- [ ] **Step 3: Write the export script**

`scripts/{{ 'export-graphql-schema.sh' ... }}.jinja` (mirror `export-openapi.sh.jinja`):
```bash
#!/usr/bin/env bash
# Export the GraphQL SDL to schema.graphql. The schema is committed and CI checks it is current
# and diffs it for breaking changes (.github/workflows/ci.yml). Run after changing the GraphQL
# schema, then commit the result.
set -euo pipefail

uv run python - > schema.graphql <<'PY'
import sys

from {{ package_name }}.graphql.schema import schema

sys.stdout.write(schema.as_str())
sys.stdout.write("\n")
PY
```

- [ ] **Step 4: Add gated CI steps**

In `.github/workflows/ci.yml.jinja`, add gated steps to the existing `contract` job (after the `oasdiff` step, ~line 117), with `{%- if %}` whitespace control so the no-graphql render is **byte-identical** (ci.yml is LOCKED_TRACKED):
```jinja
{%- if "graphql" in batteries %}
      - name: fail if schema.graphql is missing or stale
        run: |
          bash scripts/export-graphql-schema.sh
          if [ -n "$(git status --porcelain -- schema.graphql)" ]; then
            echo "::error::schema.graphql is missing or out of date. Run scripts/export-graphql-schema.sh and commit it."
            git --no-pager diff -- schema.graphql
            exit 1
          fi
      - name: graphql breaking-change check (graphql-core)
        if: {% raw %}${{ github.event_name == 'pull_request' }}{% endraw %}
        run: |
          git show "origin/{% raw %}${{ github.base_ref }}{% endraw %}:schema.graphql" > /tmp/base.graphql 2>/dev/null || { echo "no base schema — skipping"; exit 0; }
          uv run python - <<'PY'
          import sys
          from pathlib import Path

          from graphql import build_schema, find_breaking_changes

          old = build_schema(Path("/tmp/base.graphql").read_text())
          new = build_schema(Path("schema.graphql").read_text())
          breaking = find_breaking_changes(old, new)
          for b in breaking:
              print(f"::error::breaking GraphQL change: {b.type.name}: {b.description}")
          sys.exit(1 if breaking else 0)
          PY
{%- endif %}
```

> The `contract` job already sets `fetch-depth: 0` (needed for `git show origin/<base>`). Confirm the `{%- if %}` placement keeps YAML valid and the no-graphql render unchanged — the `test_render_ci_clean_without_graphql` test guards this.

- [ ] **Step 5: Run to verify green**

Run: `uv run pytest tests/test_copier_runner.py -q -k "graphql_export or ci_clean"`
Expected: PASS.

- [ ] **Step 6: Verify integrity is byte-identical without the battery**

Run:
```bash
uv run python -c "
from pathlib import Path; import tempfile
from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check
d = Path(tempfile.mkdtemp())/'p'
render_project(d, {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'})
print('ci.yml present:', (d/'.github/workflows/ci.yml').is_file())
"
```
Then render WITH `graphql` and run the full render-test suite (`uv run pytest tests/test_copier_runner.py -q`). Expected: PASS — the gated edit does not alter the no-battery `ci.yml`.

- [ ] **Step 7: Full gate + commit**

```bash
git add src/framework_cli/template tests/test_copier_runner.py CLAUDE.md
git commit -m "feat(graphql): CI schema contract — SDL export + staleness + breaking-change (graphql-core)"
```

---

## Task 7: Downskill + integrity (no `--force`)

**Files:**
- Test: `tests/test_downskill.py`

> No production code change is expected — the 8a-2 `remove_battery` two-render set-diff and the 8b-1 `usage_references` byte-identity exclusion already handle a route battery whose only shared edits are framework-gated (`health.py`, `settings.py`, `pyproject.toml`, `ci.yml`). This task **proves** it for `graphql`.

- [ ] **Step 1: Write the failing/uncovered test**

Add to `tests/test_downskill.py`:

```python
def test_remove_battery_graphql_end_to_end(tmp_path, monkeypatch):
    import subprocess

    from typer.testing import CliRunner

    from framework_cli.cli import app
    from framework_cli.downskill import remove_battery
    from framework_cli.source import read_batteries

    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["new", "My App", "--with", "graphql"]).exit_code == 0
    project = tmp_path / "my-app"
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "-c", "commit.gpgsign=false", "-c", "user.email=b@b",
         "-c", "user.name=b", "commit", "-qm", "scaffold"], check=True,
    )

    remove_battery(project, "graphql", force=False)  # no --force needed

    assert not (project / "src" / "my_app" / "graphql").exists()
    assert not (project / "src" / "my_app" / "routes" / "graphql.py").exists()
    assert "graphql_ide_enabled" not in (project / "src" / "my_app" / "config" / "settings.py").read_text()
    assert "strawberry-graphql" not in (project / "pyproject.toml").read_text()
    assert "gql_metrics" not in (project / "src" / "my_app" / "routes" / "health.py").read_text()
    assert read_batteries(project) == []
    monkeypatch.chdir(project)
    assert CliRunner().invoke(app, ["integrity", "--ci"]).exit_code == 0
```

- [ ] **Step 2: Run to verify (red if anything is unhandled)**

Run: `uv run pytest tests/test_downskill.py::test_remove_battery_graphql_end_to_end -q`
Expected: PASS. If it fails on a `usage_references` false positive (a gated shared file flagged), confirm `remove_battery` passes `with_render_root` to `usage_references` for `graphql` (the 8b-1 mechanism); the fix is the same exclusion already used for webhooks/websockets — no new logic, just ensure `graphql` flows through it.

- [ ] **Step 3: Full gate + commit**

```bash
git add tests/test_downskill.py CLAUDE.md
git commit -m "test(graphql): downskill graphql is clean without --force; integrity stays green"
```

---

## Task 8: Docker acceptance variant (`--with graphql`)

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

- [ ] **Step 1: Write the acceptance test**

Add to `tests/acceptance/test_rendered_project.py` (mirror `test_rendered_project_with_websockets_battery_passes`):

```python
@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_graphql_battery_passes(tmp_path: Path):
    data = {**DATA, "batteries": ["graphql"]}
    dest = tmp_path / "demo"
    render_project(dest, data)

    assert (dest / "src" / "demo" / "graphql" / "schema.py").exists()
    assert (dest / "src" / "demo" / "routes" / "graphql.py").exists()
    assert (dest / "tests" / "functional" / "test_graphql.py").exists()

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the graphql battery project:\n"
        + result.stdout + result.stderr
    )
    combined = result.stdout + result.stderr
    cov_line = next((ln for ln in combined.splitlines() if "routes/graphql.py" in ln), "")
    assert "100%" in cov_line, (
        f"graphql route not fully exercised; coverage line: {cov_line!r}\n"
        "Expected 100% of routes/graphql.py — did test_graphql.py's query+mutation run?\n"
        + combined
    )
```

- [ ] **Step 2: Run the acceptance test (Docker)**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_with_graphql_battery_passes -q`
Expected: PASS (requires Docker + uv). This exercises `uv sync` (pulls Strawberry), the generated query/mutation against real Postgres, the metrics on `/metrics`, and introspection-off.

> If the rendered project's `uv run mypy src` or `ruff format` fails inside the gate, fix the template (the **[verify-API]** GraphQLRouter typing or any gated-block whitespace) and re-run. The freshly-rendered project must make a clean first `pre-commit` pass.

- [ ] **Step 3: Full gate + commit**

```bash
git add tests/acceptance/test_rendered_project.py CLAUDE.md
git commit -m "test(graphql): Docker acceptance variant — query+mutation+metrics end-to-end"
```

---

## Final review (after all tasks)

Dispatch a final whole-branch reviewer (opus) that **runs the tooling**:
- `uv run pytest -q` (full suite, including the Docker acceptance tier and the render format guards),
- `uv run ruff check . && uv run ruff format --check . && uv run mypy src`,
- `uv lock --check` (no new **framework** dep — Strawberry is a template dep only),
- `uv build`,
- `framework integrity --ci` on a freshly rendered project **with and without** `graphql`,
- empirically: `framework new --with graphql` → query + mutation work, `/metrics` shows `app_graphql_operations_total`, introspection is rejected under a production environment, `framework downskill graphql` (no `--force`) leaves a green project, and `active_agents("pull_request", ["graphql"])` includes `api-design`.

Then use **superpowers:finishing-a-development-branch**.

---

## Self-Review

**Spec coverage:** §2 battery registration → Task 2. §3 package/files → Tasks 3-6. §4 schema/resolvers → Task 3. §5 route + IDE/introspection toggle → Task 3. §6 observability (singleton, extension, /metrics, alert, dashboard) → Tasks 4-5. §7 CI staleness + breaking-change → Task 6. §8 `gates_agent` machinery (agent, `active_agents`, `review-agents`, fixtures) → Tasks 1-2. §9 deps/migrations(none)/composition → Task 3. §10 downskill → Task 7. §11 integrity → Tasks 6-7 + final review. §12 testing (unit/functional/render/format-guard/acceptance/eval) → Tasks 2-8.

**Placeholder scan:** all code blocks are concrete. The `graphql.json` dashboard (Task 5 Step 4) is described by panels + queries rather than full JSON — deliberate, because it must be modeled byte-for-byte on the existing `webhooks.json`/`websockets.json` panel schema, which the implementer reads; the render test enforces valid JSON + `uid`/group. The **[verify-API]** markers flag the three version-sensitive Strawberry symbols rather than guessing a wrong signature.

**Type consistency:** `build_schema(*, disable_introspection: bool)` and the module-level `schema` are introduced in Task 3 and reused in Tasks 4 (extension prepend) and 6 (export). `gql_metrics` / `GraphQLMetrics.operation(type, outcome)` / `render_prometheus()` / `reset()` are consistent across Tasks 4's metrics module, extension, unit test, and functional test. `active_agents(event, batteries=())` is defined in Task 1 and consumed by Task 2's tests and the CLI. The metric name `app_graphql_operations_total{operation_type,outcome}` is identical in the singleton, the unit test, the functional test, the alert, and the dashboard.

**Jinja-brace discipline:** the only f-strings with `{{`/`}}` are in `graphql/metrics.py`, which is a **plain `.py`** file (safe); the `.jinja` test file uses concatenation/plain-literals.
