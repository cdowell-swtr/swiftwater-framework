# FWK61 SP1 — Physical per-tenant routing core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add physical per-tenant database routing to the `multitenantauth` battery — a bounded, connection-budgeted tenant-engine registry, connect-time DSN resolution behind an injectable seam, and idempotent physical provisioning — generalized from Meridian's validated implementation.

**Architecture:** A new **tenant plane** under `multitenantauth/tenancy/` mirrors the existing control plane. `TenantEngineRegistry` holds a per-endpoint LRU of sync engines under a fail-closed connection budget; `tenant_session` resolves a tenant's DSN (cache → control row, via an overridable `resolve_dsn` seam) and yields a request-scoped `Session`; `provision_tenant` registers a tenant then creates+migrates its physical database behind a skippable step with a no-op post-migrate hook. The routing dep `tenant_db` composes with the pre-existing fail-closed `active_tenant`.

**Tech Stack:** Python 3.12, SQLAlchemy 2 (sync `Engine`/`Session`), Alembic (Python API), FastAPI deps, hand-rolled Prometheus exposition. Postgres via testcontainers in the acceptance tier.

**Design spec:** `docs/superpowers/specs/2026-06-25-fwk61-sp1-physical-routing-core-design.md`. **PUR:** `docs/superpowers/decisions/DEC-0004-multitenantauth-phase2-sp1-routing-promote-up.md`.

## Global Constraints

- **Mechanism ships integrity-LOCKED.** Every new file under `src/{package_name}/multitenantauth/tenancy/` is framework-owned mechanism. Add its path to `BATTERY_LOCKED_SRC` in `src/framework_cli/integrity/classes.py` **in the same task that creates it** — `tests/integrity/test_auth_mechanism_lock.py` walks the `multitenantauth` tree and FAILS on any unlisted `.py` file. (Do NOT defer lock-registration to a final task: an intermediate render would ship the file unlocked and the framework gate would be red.)
- **Locked-file edits are deliberate + Layer-2-reviewed.** `tenancy/registry.py` and `deps.py` are already locked; the edits here (Tasks 6, 9) are intentional mechanism re-touches. They re-checksum on the next `build_manifest`; the branch-end Phase-2 Layer-2 security review (Task 12) is their gate, exactly as DEC-0003 anticipates.
- **Consumer seams register from the UNLOCKED `create_app()`** — `register_tenant_dsn_resolver` and `register_provision_hook` follow the DV-5 `register_authz_resolver_factory` pattern. Locking the mechanism never blocks these.
- **Sync engines only** (match the control plane + Meridian). No async/await anywhere in this plan.
- **Fail-closed, always.** Unknown/non-active/non-member tenant → identical `404` (never 403, never an existence leak). Budget over-allocation → `BudgetExceeded` (never silently over-allocate). A `resolve_dsn` resolver that raises/returns non-str → deny.
- **Never log a DSN or credentials.** Not in logs, not in OTel span attributes. The tenant id is the only routing identifier that may be recorded.
- **DSN is id-derived and immutable in SP1.** The physical DB name derives from the opaque tenant id; no move/suspend/rename-of-DSN is in scope. The DSN cache is therefore effectively write-once per tenant — do NOT build move/suspend cache-invalidation (deferred to SP3). Keep only `invalidate_dsn_cache()` for provisioning + test reset.
- **Settings env prefix is `APP_`** (e.g. `APP_TENANT_POOL_SIZE`). Defaults below match Meridian's validated values.
- **Two test loops.** *Framework tests* (`uv run pytest tests/...` from the repo root) validate the template render, the integrity lock, and obs completeness. *Rendered-project tests* (the new `tests/` files in the template payload) run inside a generated project via the template-payload TDD loop ([[template-payload-tdd-loop]]): render a `multitenantauth` project → `uv sync` → edit the framework template source → mirror the changed file into the render (`cp` for `.py`; render + `cp` for `.jinja`) → `pytest` in the render → `ruff format --check` the rendered output. `TMPDIR=/var/tmp` for renders.

---

## File Structure

**New (all under `src/{package_name}/multitenantauth/tenancy/`, all LOCKED):**
- `metrics.py` — `TenantEngineMetrics` singleton (eviction + DSN-cache counters).
- `engine_registry.py` — `endpoint_of`, `required_connections`, `BudgetExceeded`, `validate_endpoint_budget`, `TenantEngineRegistry`, `tenant_engines` singleton.
- `dsn.py` — `default_tenant_dsn`, `create_database`.
- `session.py` — `tenant_session`, the `resolve_dsn` seam (`register_tenant_dsn_resolver`), the DSN cache, `invalidate_dsn_cache`, `reset_tenant_engines`.
- `provision.py` — `provision_tenant`, `register_provision_hook`, `migrate_tenant`.

**Modified:**
- `src/{package_name}/config/settings.py.jinja` — 8 new settings (Task 1).
- `migrations/env.py.jinja` — honor a pre-injected `sqlalchemy.url` (Task 7).
- `src/{package_name}/multitenantauth/tenancy/registry.py` (LOCKED) — `register_tenant` `dsn` becomes optional (Task 6).
- `src/{package_name}/multitenantauth/deps.py` (LOCKED) — add `tenant_db` (Task 9).
- `src/{package_name}/routes/health.py.jinja` — expose tenant-engine metrics at `/metrics` (Task 10).
- `src/framework_cli/integrity/classes.py` — 5 new `BATTERY_LOCKED_SRC` entries (Tasks 2–5, 8).
- `infra/observability/grafana/dashboards/...` + `prometheus/alerts/...` (multitenantauth's existing files) — add a pool/budget panel + alert (Task 10).

**Rendered-project tests (template payload):**
- `tests/unit/{{ 'test_tenant_engine_registry.py' if 'multitenantauth' ... }}.jinja`
- `tests/unit/{{ 'test_tenant_dsn.py' ... }}.jinja`
- `tests/unit/{{ 'test_tenant_session_seam.py' ... }}.jinja`
- `tests/functional/{{ 'test_tenant_provisioning.py' ... }}.jinja` (acceptance, real PG)
- `tests/functional/{{ 'test_tenant_routing_deps.py' ... }}.jinja` (real PG)

---

## Task 1: Settings — tenant pool / budget / DSN knobs

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja` (add fields after `control_database_url`)
- Test: `tests/unit/{{ 'test_settings_auth.py' if 'multitenantauth' in batteries else '' }}.jinja` (rendered project)

**Interfaces:**
- Produces: `Settings.tenant_pool_size: int=2`, `tenant_max_overflow: int=3`, `max_cached_engines: int=12`, `control_pool_size: int=5`, `control_max_overflow: int=10`, `db_pool_safety_factor: float=0.8`, `tenant_dsn_cache_ttl_seconds: int=300`, `tenant_db_name_prefix: str="{{package_name}}_tenant"`. Consumed by every later task.

- [ ] **Step 1: Write the failing test** (append to the rendered `test_settings_auth.py`)

```python
def test_tenant_routing_settings_defaults() -> None:
    from {{ package_name }}.config.settings import Settings

    s = Settings()
    assert s.tenant_pool_size == 2
    assert s.tenant_max_overflow == 3
    assert s.max_cached_engines == 12
    assert s.control_pool_size == 5
    assert s.control_max_overflow == 10
    assert s.db_pool_safety_factor == 0.8
    assert s.tenant_dsn_cache_ttl_seconds == 300
    assert s.tenant_db_name_prefix  # non-empty; defaults to "<package>_tenant"


def test_tenant_db_name_prefix_env_override(monkeypatch) -> None:
    from {{ package_name }}.config.settings import Settings

    monkeypatch.setenv("APP_TENANT_DB_NAME_PREFIX", "acme_t")
    assert Settings().tenant_db_name_prefix == "acme_t"
```

- [ ] **Step 2: Run it (rendered project) — expect FAIL** (`AttributeError`, fields don't exist)

Run (in the render): `uv run pytest tests/unit/test_settings_auth.py -q`
Expected: FAIL.

- [ ] **Step 3: Add the fields** to `settings.py.jinja`, gated on the battery, after the `control_database_url` block

```jinja
{% if "multitenantauth" in batteries %}
    # ── Phase 2 / SP1: physical per-tenant routing (MDN47) ──────────────────────
    # Per-tenant engine pool sizing + the per-endpoint LRU cap, kept small so the
    # control pool + N tenant pools cannot exhaust the shared Postgres max_connections.
    tenant_pool_size: int = 2
    tenant_max_overflow: int = 3
    max_cached_engines: int = 12
    control_pool_size: int = 5
    control_max_overflow: int = 10
    # Fraction of a server's live max_connections the app is allowed to plan for (fail-closed budget).
    db_pool_safety_factor: float = 0.8
    # DSN cache TTL: a backstop only — the per-tenant DSN is immutable in SP1.
    tenant_dsn_cache_ttl_seconds: int = 300
    # Physical DB name = "<prefix>_<tenant_id>" on the app instance (co-located default).
    tenant_db_name_prefix: str = "{{ package_name }}_tenant"
{% endif %}
```

- [ ] **Step 4: Mirror + run — expect PASS**

Render+mirror `settings.py.jinja`, then in the render: `uv run pytest tests/unit/test_settings_auth.py -q` → PASS. `ruff format --check` the rendered `settings.py`.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/src/'{{package_name}}'/config/settings.py.jinja src/framework_cli/template/tests/unit/*test_settings_auth*
git commit -m "feat(FWK61 SP1): tenant routing/budget/DSN settings"
```

---

## Task 2: `tenancy/metrics.py` — tenant-engine counters

**Files:**
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "multitenantauth" in batteries %}multitenantauth{% endif %}/tenancy/metrics.py`
- Modify: `src/framework_cli/integrity/classes.py` (BATTERY_LOCKED_SRC)
- Test: `tests/unit/{{ 'test_tenant_engine_registry.py' ... }}.jinja` (shared with Task 3; add the metrics cases here)

**Interfaces:**
- Produces: module singleton `tenant_engine_metrics` with `record_eviction(endpoint: str)`, `record_dsn_hit()`, `record_dsn_miss()`, `render_prometheus() -> str`, `reset()`. Counters: `app_tenant_engine_evictions_total{endpoint}`, `app_tenant_dsn_cache_total{outcome}` (outcome∈{hit,miss}).

- [ ] **Step 1: Write the failing test** (rendered project)

```python
def test_tenant_engine_metrics_counters() -> None:
    from {{ package_name }}.multitenantauth.tenancy.metrics import tenant_engine_metrics as tm

    tm.reset()
    tm.record_dsn_hit()
    tm.record_dsn_miss()
    tm.record_eviction("db:5432")
    out = tm.render_prometheus()
    assert 'app_tenant_dsn_cache_total{outcome="hit"} 1' in out
    assert 'app_tenant_dsn_cache_total{outcome="miss"} 1' in out
    assert 'app_tenant_engine_evictions_total{endpoint="db:5432"} 1' in out
```

- [ ] **Step 2: Run it — expect FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Create `tenancy/metrics.py`**

```python
"""Tenant-engine subsystem metrics — hand-rolled Prometheus exposition (house pattern).

Counters for the routing subsystem; the live pool gauges are rendered by the registry
itself (engine_registry.render_pool_gauges). Endpoint labels are host:port (bounded by the
fleet's DB topology, never user-supplied)."""

from __future__ import annotations

import threading


class TenantEngineMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._evictions: dict[str, int] = {}
        self._dsn: dict[str, int] = {"hit": 0, "miss": 0}

    def record_eviction(self, endpoint: str) -> None:
        with self._lock:
            self._evictions[endpoint] = self._evictions.get(endpoint, 0) + 1

    def record_dsn_hit(self) -> None:
        with self._lock:
            self._dsn["hit"] += 1

    def record_dsn_miss(self) -> None:
        with self._lock:
            self._dsn["miss"] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            evict = "".join(
                f'app_tenant_engine_evictions_total{{endpoint="{ep}"}} {n}\n'
                for ep, n in sorted(self._evictions.items())
            )
            dsn = "".join(
                f'app_tenant_dsn_cache_total{{outcome="{o}"}} {self._dsn[o]}\n'
                for o in ("hit", "miss")
            )
        return (
            "# HELP app_tenant_engine_evictions_total Tenant-engine LRU evictions per endpoint\n"
            "# TYPE app_tenant_engine_evictions_total counter\n"
            f"{evict}"
            "# HELP app_tenant_dsn_cache_total Tenant DSN-cache lookups by outcome\n"
            "# TYPE app_tenant_dsn_cache_total counter\n"
            f"{dsn}"
        )

    def reset(self) -> None:
        with self._lock:
            self._evictions = {}
            self._dsn = {"hit": 0, "miss": 0}


tenant_engine_metrics = TenantEngineMetrics()
"""Process-wide singleton imported by the engine registry + session resolver."""
```

- [ ] **Step 4: Register the lock entry** — add to `BATTERY_LOCKED_SRC` in `src/framework_cli/integrity/classes.py`:

```python
    "src/{package_name}/multitenantauth/tenancy/metrics.py": ("multitenantauth",),
```

- [ ] **Step 5: Run both loops — expect PASS**

Framework: `uv run pytest tests/integrity/test_auth_mechanism_lock.py -q` → PASS (file now locked). Rendered: mirror `metrics.py` + run the unit test → PASS. `ruff format --check`.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/src/'{{package_name}}'/'{% if "multitenantauth" in batteries %}multitenantauth{% endif %}'/tenancy/metrics.py src/framework_cli/integrity/classes.py src/framework_cli/template/tests/unit/*test_tenant_engine_registry*
git commit -m "feat(FWK61 SP1): tenant-engine metrics counters (locked)"
```

---

## Task 3: `tenancy/engine_registry.py` — bounded per-endpoint budgeted LRU

**Files:**
- Create: `.../multitenantauth/tenancy/engine_registry.py`
- Modify: `src/framework_cli/integrity/classes.py`
- Test: rendered `tests/unit/test_tenant_engine_registry.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `tenant_engine_metrics` (Task 2).
- Produces: `endpoint_of(dsn)->str`, `required_connections(settings, *, includes_control)->int`, `class BudgetExceeded(RuntimeError)`, `validate_endpoint_budget(engine, *, settings, includes_control)->None`, `class TenantEngineRegistry` with `get(dsn)->Engine`, `cached_count(endpoint)->int`, `reset()->None`, `render_pool_gauges()->str`; module singleton `tenant_engines`.

- [ ] **Step 1: Write the failing tests** (rendered project; pure-unit, no real PG — inject fakes)

```python
import threading
import pytest
from {{ package_name }}.multitenantauth.tenancy.engine_registry import (
    TenantEngineRegistry, BudgetExceeded, endpoint_of, required_connections,
)
from {{ package_name }}.config.settings import Settings


class _FakeEngine:
    def __init__(self, url): self.url = url; self.disposed = False
    def dispose(self): self.disposed = True
    class _Pool:  # render_pool_gauges tolerates pools without checkedout()
        def checkedout(self): return 0
    pool = _Pool()


def _registry(settings, *, budget_ok=True):
    built = []
    def builder(dsn, **kw): e = _FakeEngine(dsn); built.append(e); return e
    def validator(engine, *, settings, includes_control):
        if not budget_ok: raise BudgetExceeded("nope")
    reg = TenantEngineRegistry(builder=builder, budget_validator=validator,
                               settings_provider=lambda: settings)
    return reg, built


def test_endpoint_of_defaults_port_5432():
    assert endpoint_of("postgresql+psycopg://u:p@host/db") == "host:5432"


def test_get_caches_and_reuses_one_engine_per_dsn():
    reg, built = _registry(Settings())
    a = reg.get("postgresql+psycopg://u:p@h/t1")
    b = reg.get("postgresql+psycopg://u:p@h/t1")
    assert a is b and len(built) == 1


def test_lru_evicts_oldest_when_endpoint_full(monkeypatch):
    s = Settings(); object.__setattr__(s, "max_cached_engines", 2)  # if frozen; else s.max_cached_engines=2
    reg, built = _registry(s)
    e1 = reg.get("postgresql+psycopg://u:p@h/t1")
    e2 = reg.get("postgresql+psycopg://u:p@h/t2")
    reg.get("postgresql+psycopg://u:p@h/t1")          # touch t1 → t2 is now LRU
    reg.get("postgresql+psycopg://u:p@h/t3")          # over cap → evict t2
    assert e2.disposed is True
    assert reg.cached_count("h:5432") == 2


def test_budget_exceeded_disposes_engine_and_does_not_cache():
    reg, built = _registry(Settings(), budget_ok=False)
    with pytest.raises(BudgetExceeded):
        reg.get("postgresql+psycopg://u:p@h/t1")
    assert built[0].disposed is True
    assert reg.cached_count("h:5432") == 0


def test_required_connections_includes_control_when_colocated():
    s = Settings()
    n = required_connections(s, includes_control=True)
    assert n == s.max_cached_engines * (s.tenant_pool_size + s.tenant_max_overflow) \
        + s.control_pool_size + s.control_max_overflow
```

> Note: if `Settings` is a frozen pydantic model, set `max_cached_engines` via `Settings(max_cached_engines=2)` rather than `object.__setattr__`. Use whichever the model allows.

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Create `engine_registry.py`** (ported from Meridian's validated module; import paths adjusted to `...config.settings` / `.metrics`; the tenant engine builder uses `create_engine` directly so the baseline `db/engine.py` stays untouched)

```python
"""Bounded per-endpoint tenant-engine registry (MDN47).

Postgres max_connections is a server-wide ceiling. With DB-per-tenant on one cluster the
control pool + every tenant pool draw on it, so an unbounded tenant-engine cache exhausts
it. This registry bounds the cache per ENDPOINT (host:port from the DSN) and refuses,
fail-closed, to plan past the endpoint's live max_connections × safety_factor."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable

from sqlalchemy import Engine, create_engine, make_url

from ...config.settings import Settings, get_settings
from .metrics import tenant_engine_metrics


def endpoint_of(dsn: str) -> str:
    """The host:port an engine for `dsn` connects to (port defaults to 5432)."""
    url = make_url(dsn)
    return f"{url.host}:{url.port or 5432}"


def required_connections(settings: Settings, *, includes_control: bool) -> int:
    """Worst-case connections against one endpoint: per-endpoint LRU cap × per-tenant pool,
    plus the control pool when the control plane is co-located on that endpoint."""
    tenant = settings.max_cached_engines * (
        settings.tenant_pool_size + settings.tenant_max_overflow
    )
    control = (
        settings.control_pool_size + settings.control_max_overflow
        if includes_control
        else 0
    )
    return tenant + control


class BudgetExceeded(RuntimeError):
    """Raised fail-closed when an endpoint's planned footprint exceeds its ceiling."""


def _live_max_connections(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.exec_driver_sql("SHOW max_connections").scalar_one())


def validate_endpoint_budget(
    engine: Engine, *, settings: Settings, includes_control: bool
) -> None:
    """Assert this endpoint's worst-case footprint fits under live max_connections ×
    safety_factor. Raises BudgetExceeded otherwise (a mis-tuning fails loudly on first DB
    use, never silently wedges a tenant under load)."""
    ceiling = _live_max_connections(engine)
    budget = int(ceiling * settings.db_pool_safety_factor)
    required = required_connections(settings, includes_control=includes_control)
    if required > budget:
        raise BudgetExceeded(
            f"connection budget exceeded for endpoint {endpoint_of(str(engine.url))}: "
            f"required={required} > budget={budget} (max_connections={ceiling} × "
            f"{settings.db_pool_safety_factor}). Lower max_cached_engines / pool sizes or "
            "raise the server's max_connections."
        )


def _default_builder(dsn: str, *, pool_size: int, max_overflow: int) -> Engine:
    """Build a pooled tenant engine. Uses create_engine directly (NOT the baseline
    db.engine.build_engine) so the tenant plane owns its pool sizing without coupling the
    baseline engine to multitenantauth-only settings."""
    return create_engine(
        dsn,
        pool_pre_ping=True,
        future=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=30,
    )


class TenantEngineRegistry:
    """A bounded LRU of tenant Engines keyed by DSN, accounted per endpoint. On overflow the
    per-endpoint LRU engine is evicted and soft-disposed (idle conns close now; checked-out
    conns close on return, so an in-flight request finishes safely)."""

    def __init__(
        self,
        *,
        builder: Callable[..., Engine] = _default_builder,
        budget_validator: Callable[..., None] = validate_endpoint_budget,
        settings_provider: Callable[..., Settings] = get_settings,
    ) -> None:
        self._engines: OrderedDict[str, Engine] = OrderedDict()  # dsn -> engine (LRU order)
        self._endpoints: dict[str, str] = {}  # dsn -> endpoint
        self._validated: set[str] = set()  # endpoints whose budget has been probed
        self._lock = threading.RLock()
        self._builder = builder
        self._validate = budget_validator
        self._settings = settings_provider

    def get(self, dsn: str) -> Engine:
        with self._lock:
            eng = self._engines.get(dsn)
            if eng is not None:
                self._engines.move_to_end(dsn)
                return eng
            endpoint = endpoint_of(dsn)
            self._evict_if_full(endpoint)
            settings = self._settings()
            eng = self._builder(
                dsn,
                pool_size=settings.tenant_pool_size,
                max_overflow=settings.tenant_max_overflow,
            )
            # Validate BEFORE caching so a fail-closed BudgetExceeded leaks no engine and the
            # next first-touch re-checks (fail-closed must stay closed).
            if endpoint not in self._validated:
                includes_control = endpoint == endpoint_of(settings.database_url)
                try:
                    self._validate(
                        eng, settings=settings, includes_control=includes_control
                    )
                except BaseException:
                    eng.dispose()
                    raise
                self._validated.add(endpoint)
            self._engines[dsn] = eng
            self._endpoints[dsn] = endpoint
            return eng

    def _evict_if_full(self, endpoint: str) -> None:
        while self.cached_count(endpoint) >= self._settings().max_cached_engines:
            for dsn in self._engines:  # OrderedDict iterates oldest→newest
                if self._endpoints[dsn] == endpoint:
                    victim = self._engines.pop(dsn)
                    self._endpoints.pop(dsn)
                    victim.dispose()
                    tenant_engine_metrics.record_eviction(endpoint)
                    break

    def cached_count(self, endpoint: str) -> int:
        return sum(1 for ep in self._endpoints.values() if ep == endpoint)

    def reset(self) -> None:
        with self._lock:
            for eng in self._engines.values():
                eng.dispose()
            self._engines.clear()
            self._endpoints.clear()
            self._validated.clear()

    def render_pool_gauges(self) -> str:
        """Live gauges (cached engine count + pool checkouts) per endpoint, for /metrics."""
        with self._lock:
            counts: dict[str, int] = {}
            checked_out = 0
            for dsn, eng in self._engines.items():
                ep = self._endpoints[dsn]
                counts[ep] = counts.get(ep, 0) + 1
                try:
                    checked_out += eng.pool.checkedout()  # type: ignore[attr-defined]
                except AttributeError:  # non-QueuePool dialect
                    pass
            text = (
                "# HELP app_tenant_engines_cached Cached tenant engines per endpoint\n"
                "# TYPE app_tenant_engines_cached gauge\n"
            )
            for ep, n in sorted(counts.items()):
                text += f'app_tenant_engines_cached{{endpoint="{ep}"}} {n}\n'
            text += (
                "# HELP app_tenant_pool_checked_out Connections checked out across tenant pools\n"
                "# TYPE app_tenant_pool_checked_out gauge\n"
                f"app_tenant_pool_checked_out {checked_out}\n"
            )
            return text


tenant_engines = TenantEngineRegistry()
"""Process-wide singleton. session.tenant_session resolves engines through it."""
```

- [ ] **Step 4: Register the lock entry** — add `"src/{package_name}/multitenantauth/tenancy/engine_registry.py": ("multitenantauth",),` to `BATTERY_LOCKED_SRC`.

- [ ] **Step 5: Run both loops — expect PASS** (framework lock test; rendered unit tests). `ruff format --check`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(FWK61 SP1): TenantEngineRegistry — per-endpoint budgeted LRU (locked)"
```

---

## Task 4: `tenancy/dsn.py` — DSN derivation + database creation

**Files:**
- Create: `.../multitenantauth/tenancy/dsn.py`
- Modify: `src/framework_cli/integrity/classes.py`
- Test: rendered `tests/unit/test_tenant_dsn.py`

**Interfaces:**
- Consumes: `Settings` (Task 1).
- Produces: `default_tenant_dsn(tenant_id: str) -> str` (swaps the app DB name to `<tenant_db_name_prefix>_<tenant_id>`), `create_database(dsn: str) -> None` (idempotent CREATE DATABASE via AUTOCOMMIT maintenance connection).

- [ ] **Step 1: Write the failing unit test** (name-swap is pure; `create_database` is exercised in Task 8's acceptance test)

```python
def test_default_tenant_dsn_swaps_db_name(monkeypatch) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql+psycopg://u:pw@h:5432/appdb")
    monkeypatch.setenv("APP_TENANT_DB_NAME_PREFIX", "acme_t")
    from {{ package_name }}.config.settings import get_settings
    get_settings.cache_clear()  # if lru_cached; else skip
    from {{ package_name }}.multitenantauth.tenancy.dsn import default_tenant_dsn

    dsn = default_tenant_dsn("abc123")
    assert dsn == "postgresql+psycopg://u:pw@h:5432/acme_t_abc123"
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Create `dsn.py`** (generalized from Meridian: prefix is a setting; derive from the app `database_url`)

```python
"""Per-tenant DSN derivation + idempotent database creation (SP1).

A tenant's database is co-located with the app instance (settings.database_url) by default,
named "<tenant_db_name_prefix>_<tenant_id>"; the full DSN is recorded on the Tenant row and
is the routing key. Granularity is DSN-pluggable — a tenant can later move to a dedicated
instance by changing only its stored DSN (a bring-your-own-DSN provision skips this module)."""

from __future__ import annotations

from sqlalchemy import create_engine, make_url, text

from ...config.settings import get_settings


def default_tenant_dsn(tenant_id: str) -> str:
    """Derive a tenant DB DSN from the app URL by swapping the database name. tenant_id is
    already constrained to ^[a-z0-9_]+$ by the registry, so it is a safe identifier component."""
    settings = get_settings()
    base = make_url(settings.database_url)
    name = f"{settings.tenant_db_name_prefix}_{tenant_id}"
    return base.set(database=name).render_as_string(hide_password=False)


def create_database(dsn: str) -> None:
    """Idempotently CREATE DATABASE for `dsn`, connecting to the instance's `postgres`
    maintenance db with AUTOCOMMIT (CREATE DATABASE cannot run inside a transaction)."""
    url = make_url(dsn)
    dbname = url.database
    maint = create_engine(
        url.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with maint.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        maint.dispose()
```

- [ ] **Step 4: Register the lock entry** — `"src/{package_name}/multitenantauth/tenancy/dsn.py": ("multitenantauth",),`.

- [ ] **Step 5: Run both loops — PASS.** `ruff format --check`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(FWK61 SP1): tenant DSN derivation + idempotent CREATE DATABASE (locked)"
```

---

## Task 5: `tenancy/session.py` — `tenant_session` + the `resolve_dsn` seam + DSN cache

**Files:**
- Create: `.../multitenantauth/tenancy/session.py`
- Modify: `src/framework_cli/integrity/classes.py`
- Test: rendered `tests/unit/test_tenant_session_seam.py`

**Interfaces:**
- Consumes: `tenant_engines` (Task 3), `tenant_engine_metrics` (Task 2), control `repository.get_tenant` (existing), `build_session_factory` (baseline `db.engine`).
- Produces: `register_tenant_dsn_resolver(fn | None) -> None` (seam; `fn(tenant_id, *, control_session) -> str`), `tenant_session(tenant_id, *, control_session=None)` (contextmanager → `Session`), `invalidate_dsn_cache(tenant_id=None)`, `reset_tenant_engines()`. Raises `LookupError` on unknown tenant; denies (LookupError) if a registered resolver raises or returns a non-str.

- [ ] **Step 1: Write the failing tests** (rendered project; fakes — no real PG)

```python
import pytest
from {{ package_name }}.multitenantauth.tenancy import session as S


@pytest.fixture(autouse=True)
def _clean():
    S.invalidate_dsn_cache()
    S.register_tenant_dsn_resolver(None)
    yield
    S.invalidate_dsn_cache()
    S.register_tenant_dsn_resolver(None)


def test_default_resolver_reads_control_row(monkeypatch):
    class _T:  # stand-in tenant row
        dsn = "postgresql+psycopg://u:p@h/t_abc"
    monkeypatch.setattr(S, "_get_tenant", lambda cs, tid: _T() if tid == "abc" else None)
    assert S._resolve_dsn("abc", object()) == "postgresql+psycopg://u:p@h/t_abc"


def test_unknown_tenant_raises_lookup(monkeypatch):
    monkeypatch.setattr(S, "_get_tenant", lambda cs, tid: None)
    with pytest.raises(LookupError):
        S._resolve_dsn("nope", object())


def test_registered_resolver_overrides_default():
    S.register_tenant_dsn_resolver(lambda tid, *, control_session: f"postgresql+psycopg://x/{tid}")
    assert S._resolve_dsn("abc", object()) == "postgresql+psycopg://x/abc"


def test_resolver_returning_non_str_denies():
    S.register_tenant_dsn_resolver(lambda tid, *, control_session: 123)  # type: ignore
    with pytest.raises(LookupError):
        S._resolve_dsn("abc", object())


def test_resolver_raising_denies():
    def boom(tid, *, control_session): raise RuntimeError("x")
    S.register_tenant_dsn_resolver(boom)
    with pytest.raises(LookupError):
        S._resolve_dsn("abc", object())


def test_dsn_cache_hit_skips_resolver(monkeypatch):
    calls = []
    S.register_tenant_dsn_resolver(lambda tid, *, control_session: (calls.append(1) or "postgresql+psycopg://x/y"))
    S._resolve_dsn("abc", object())
    S._resolve_dsn("abc", object())
    assert len(calls) == 1  # second call served from cache
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Create `session.py`** (new seam wrapper around Meridian's validated resolver+cache; the default resolver reads the control row, fail-closed)

```python
"""Connect-time tenant DSN resolution + per-tenant Session routing (SP1).

tenant_session(tenant_id) resolves the tenant's DSN (cache → resolver) and yields a Session
bound to that tenant's database via the bounded TenantEngineRegistry. The resolver is a
pluggable SEAM: the default reads the DSN stored on the control row (Meridian's validated
posture); a consumer (or the future secrets backend) registers register_tenant_dsn_resolver
from its own UNLOCKED create_app() to inject credentials. Everything fails CLOSED — an
unknown tenant, a resolver that raises, or a non-str return all raise LookupError, which the
routing dep maps to 404. The kernel must never silently touch the wrong DB."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from ...config.settings import get_settings
from ...db.engine import build_session_factory
from .engine_registry import tenant_engines
from .metrics import tenant_engine_metrics

logger = logging.getLogger(__name__)

# A resolver: (tenant_id, *, control_session) -> dsn. Default reads the control row.
DsnResolver = Callable[..., str]


def _get_tenant(control_session: Session, tenant_id: str):  # type: ignore[no-untyped-def]
    """Indirection point so unit tests can stub the control read without a DB."""
    from ...db.control import repository as control_repo

    return control_repo.get_tenant(control_session, tenant_id)


def _default_resolver(tenant_id: str, *, control_session: Session) -> str:
    """Read the DSN stored on the tenant's control row (matches Meridian's posture)."""
    tenant = _get_tenant(control_session, tenant_id)
    if tenant is None:
        raise LookupError(f"unknown tenant: {tenant_id!r}")
    return tenant.dsn


_resolver: DsnResolver = _default_resolver


def register_tenant_dsn_resolver(resolver: DsnResolver | None) -> None:
    """Register a connect-time DSN resolver (pass None to reset to the control-row default).

    `resolver(tenant_id, *, control_session) -> dsn`. Fails CLOSED: a resolver that raises or
    returns a non-string DENIES the route (LookupError → 404). Call from your own (unlocked)
    create_app(); this is the forward-compatible hook the Secrets-backing item plugs into."""
    global _resolver
    _resolver = resolver or _default_resolver


# tenant_id -> (dsn, monotonic_expiry). Process-wide cache so the hot path doesn't open a
# control connection per request. DSN is immutable in SP1, so the TTL is a backstop only.
_dsn_cache: dict[str, tuple[str, float]] = {}
_dsn_lock = threading.Lock()


def invalidate_dsn_cache(tenant_id: str | None = None) -> None:
    """Drop a tenant's cached DSN (None = all). Called after provisioning + on test reset."""
    with _dsn_lock:
        if tenant_id is None:
            _dsn_cache.clear()
        else:
            _dsn_cache.pop(tenant_id, None)


def _resolve_dsn(tenant_id: str, control_session: Session | None) -> str:
    """Resolve tenant_id -> dsn via the cache; on miss, call the active resolver. Fails closed:
    a resolver error or a non-str return raises LookupError."""
    now = time.monotonic()
    with _dsn_lock:
        cached = _dsn_cache.get(tenant_id)
        if cached is not None and cached[1] > now:
            tenant_engine_metrics.record_dsn_hit()
            return cached[0]
    tenant_engine_metrics.record_dsn_miss()

    def _call(cs: Session) -> str:
        try:
            dsn = _resolver(tenant_id, control_session=cs)
        except LookupError:
            raise
        except Exception as exc:  # a buggy/hostile resolver must DENY, never leak/500
            logger.warning("tenant DSN resolver raised; denying (fail-closed)", exc_info=True)
            raise LookupError(f"DSN resolution failed for {tenant_id!r}") from exc
        if not isinstance(dsn, str) or not dsn:
            raise LookupError(f"DSN resolver returned a non-string for {tenant_id!r}")
        return dsn

    if control_session is not None:
        dsn = _call(control_session)
    else:
        from ...db.control import engine as ctrl_engine

        with ctrl_engine.control_session_factory()() as cs:
            dsn = _call(cs)
    ttl = get_settings().tenant_dsn_cache_ttl_seconds
    with _dsn_lock:
        _dsn_cache[tenant_id] = (dsn, now + ttl)
    return dsn


def reset_tenant_engines() -> None:
    """Dispose the per-tenant engine cache AND the DSN cache (tests; shutdown)."""
    tenant_engines.reset()
    invalidate_dsn_cache()


@contextmanager
def tenant_session(
    tenant_id: str, *, control_session: Session | None = None
) -> Iterator[Session]:
    """Yield a Session bound to `tenant_id`'s database. Pass the request's control_session to
    avoid a second control connection. Raises LookupError if the tenant is unknown/denied."""
    dsn = _resolve_dsn(tenant_id, control_session)
    factory = build_session_factory(tenant_engines.get(dsn))
    with factory() as session:
        yield session
```

- [ ] **Step 4: Register the lock entry** — `"src/{package_name}/multitenantauth/tenancy/session.py": ("multitenantauth",),`.

- [ ] **Step 5: Run both loops — PASS.** `ruff format --check`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(FWK61 SP1): tenant_session + resolve_dsn seam + DSN cache (locked)"
```

---

## Task 6: `registry.py` — make `register_tenant`'s `dsn` optional (LOCKED edit)

**Files:**
- Modify: `.../multitenantauth/tenancy/registry.py:78-115` (LOCKED)
- Test: rendered `tests/unit/test_tenancy_registry.py` (existing — add a case)

**Interfaces:**
- Produces: `register_tenant(session, name, *, slug, dsn: str | None = None, status="provisioning") -> Tenant` — when `dsn is None`, the id-derived `default_tenant_dsn(tenant_id)` is used. Opaque-id invariant preserved (id still minted internally). Resolves the chicken-and-egg (DSN needs the id; the id is generated here).

- [ ] **Step 1: Write the failing test**

```python
def test_register_tenant_defaults_dsn_from_id(db_session, monkeypatch):
    monkeypatch.setenv("APP_TENANT_DB_NAME_PREFIX", "acme_t")
    from {{ package_name }}.multitenantauth.tenancy.registry import register_tenant
    t = register_tenant(db_session, "Acme", slug="acme")  # no dsn passed
    assert t.dsn.endswith(f"/acme_t_{t.id}")


def test_register_tenant_explicit_dsn_unchanged(db_session):
    from {{ package_name }}.multitenantauth.tenancy.registry import register_tenant
    t = register_tenant(db_session, "Acme", slug="acme2", dsn="postgresql+psycopg://x/byo")
    assert t.dsn == "postgresql+psycopg://x/byo"
```

> These need the control schema. Run them against the control DB fixture pattern from `test_control_migrations.py` (a control-migrated engine), not the app `db_session`. Adapt the fixture accordingly in the test module.

- [ ] **Step 2: Run — expect FAIL** (`dsn` is currently required → `TypeError`).

- [ ] **Step 3: Edit `register_tenant`** — make `dsn` optional and default it after the id is minted:

```python
def register_tenant(
    session: Session,
    name: str,
    *,
    slug: str,
    dsn: str | None = None,
    status: str = "provisioning",
) -> Tenant:
    # ... docstring updated: "dsn defaults to default_tenant_dsn(<generated id>)" ...
    _validate_slug(slug)
    _assert_slug_claimable(session, slug)

    tenant_id = _opaque_id()
    _validate_tenant_id(tenant_id)

    if dsn is None:
        from .dsn import default_tenant_dsn  # local import: dsn.py imports settings only

        dsn = default_tenant_dsn(tenant_id)

    return control_repo.add_tenant(
        session, id=tenant_id, name=name, slug=slug, dsn=dsn, status=status,
    )
```

- [ ] **Step 4: Run both loops — PASS.** The locked-file checksum changes; `uv run pytest tests/integrity/test_auth_mechanism_lock.py -q` still PASSES (the file is still in `BATTERY_LOCKED_SRC`; only its checksum updates on the next `build_manifest`). Confirm no other rendered authz test regressed: run the rendered authz suite. `ruff format --check`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(FWK61 SP1): register_tenant derives default DSN from the opaque id"
```

---

## Task 7: `migrations/env.py.jinja` — honor a pre-injected `sqlalchemy.url`

**Files:**
- Modify: `src/framework_cli/template/migrations/env.py.jinja:14-15`
- Test: framework render test + rendered `test_db_migrations` (control + app migrate still pass) and the Task 8 acceptance (per-tenant migrate hits the tenant DB)

**Interfaces:**
- Produces: per-tenant migrate can target a tenant DSN by pre-setting `sqlalchemy.url` on the `Config`; the normal CLI / control migrate is unchanged (the app `alembic.ini` has no `sqlalchemy.url`, so the settings fallback still applies).

- [ ] **Step 1: Write the failing test** (rendered project — assert an injected url wins)

```python
def test_env_honors_preinjected_sqlalchemy_url(tmp_path, monkeypatch):
    # The app alembic config, with sqlalchemy.url pre-set, must NOT be clobbered by settings.
    from alembic.config import Config
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://injected/here")
    # Loading env in offline mode reads the main option; assert the injected url is used.
    # (Exercised end-to-end against a real tenant DB in test_tenant_provisioning.py.)
    assert cfg.get_main_option("sqlalchemy.url") == "postgresql+psycopg://injected/here"
```

> The real assurance is Task 8's acceptance test (migrating the tenant DB, not the app DB). This unit-level step pins the contract.

- [ ] **Step 2: Run — expect FAIL only if env.py clobbers it; confirm the current clobber, then fix.**

- [ ] **Step 3: Edit `env.py.jinja`** lines 14-15 — fall back to settings ONLY when no url was injected:

```jinja
config = context.config
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
```

- [ ] **Step 4: Run both loops — PASS.** Framework: render baseline + multitenantauth, confirm `tests/unit/test_db_migrations.py` and `test_control_migrations.py` still pass in the render (settings fallback intact — app `alembic.ini` has no url). `ruff format --check`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(FWK61 SP1): alembic env.py honors a pre-injected sqlalchemy.url"
```

---

## Task 8: `tenancy/provision.py` — idempotent physical provisioning

**Files:**
- Create: `.../multitenantauth/tenancy/provision.py`
- Modify: `src/framework_cli/integrity/classes.py`
- Test: rendered `tests/functional/test_tenant_provisioning.py` (ACCEPTANCE, real PG)

**Interfaces:**
- Consumes: `register_tenant`/`activate_tenant`/`live_slug_tenant_id`/`get_tenant` (registry+repo), `create_database` (Task 4), `invalidate_dsn_cache` (Task 5), Alembic Python API.
- Produces: `provision_tenant(control_session, name, *, slug, dsn=None, run_physical=True) -> str` (returns the opaque id; idempotent + re-runnable), `register_provision_hook(hook | None)` (seam; `hook(control_session, tenant_id, tenant_dsn) -> None`, default no-op), `migrate_tenant(dsn) -> None`.

- [ ] **Step 1: Write the failing acceptance test** (real PG; non-transactional — creates + drops real tenant DBs; uses the control-migrated engine pattern from `test_control_migrations.py`)

```python
import uuid
import pytest
from sqlalchemy import create_engine, make_url, text, inspect
from sqlalchemy.orm import Session


def _drop_db(pg_url: str, dbname: str) -> None:
    maint = create_engine(make_url(pg_url).set(database="postgres").render_as_string(hide_password=False),
                          isolation_level="AUTOCOMMIT")
    with maint.connect() as c:
        c.execute(text(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='{dbname}'"))
        c.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
    maint.dispose()


def test_provision_creates_migrates_and_activates(ctrl_engine, control_db_url, monkeypatch):
    # app DB instance == the testcontainer; tenant DBs are siblings on it.
    monkeypatch.setenv("APP_DATABASE_URL", control_db_url)  # same instance; name swapped per tenant
    monkeypatch.setenv("APP_TENANT_DB_NAME_PREFIX", "demo_tenant")
    from {{ package_name }}.config.settings import get_settings
    get_settings.cache_clear()
    from {{ package_name }}.multitenantauth.tenancy.provision import provision_tenant
    from {{ package_name }}.multitenantauth.tenancy.dsn import default_tenant_dsn

    with Session(ctrl_engine) as cs:
        tid = provision_tenant(cs, "Acme", slug="acme")
        cs.commit()
    dsn = default_tenant_dsn(tid)
    dbname = make_url(dsn).database
    try:
        # the tenant DB exists and carries the APP schema (items), NOT control tables
        teng = create_engine(dsn)
        tables = set(inspect(teng).get_table_names())
        teng.dispose()
        assert "items" in tables
        assert "tenant" not in tables  # control tables never in a tenant DB
        # status flipped to active
        with Session(ctrl_engine) as cs:
            from {{ package_name }}.db.control import repository as repo
            assert repo.get_tenant(cs, tid).status == "active"
    finally:
        _drop_db(control_db_url, dbname)


def test_provision_is_idempotent_after_partial(ctrl_engine, control_db_url, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_URL", control_db_url)
    from {{ package_name }}.config.settings import get_settings; get_settings.cache_clear()
    from {{ package_name }}.multitenantauth.tenancy.provision import provision_tenant
    from {{ package_name }}.multitenantauth.tenancy.dsn import default_tenant_dsn
    from {{ package_name }}.db.control import repository as repo

    with Session(ctrl_engine) as cs:
        tid1 = provision_tenant(cs, "Acme", slug="acme"); cs.commit()
    dbname = make_url(default_tenant_dsn(tid1)).database
    try:
        with Session(ctrl_engine) as cs:
            tid2 = provision_tenant(cs, "Acme", slug="acme"); cs.commit()  # re-run same slug
        assert tid1 == tid2  # resumed, not a second tenant
    finally:
        _drop_db(control_db_url, dbname)


def test_provision_hook_runs_before_activate(ctrl_engine, control_db_url, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_URL", control_db_url)
    from {{ package_name }}.config.settings import get_settings; get_settings.cache_clear()
    from {{ package_name }}.multitenantauth.tenancy import provision as P
    from {{ package_name }}.multitenantauth.tenancy.dsn import default_tenant_dsn

    seen = {}
    def hook(cs, tenant_id, tenant_dsn):
        seen["id"] = tenant_id
        seen["status_at_hook"] = __import__("{{ package_name }}.db.control.repository", fromlist=["get_tenant"]).get_tenant(cs, tenant_id).status
    P.register_provision_hook(hook)
    try:
        with Session(ctrl_engine) as cs:
            tid = P.provision_tenant(cs, "Acme", slug="acme"); cs.commit()
        assert seen["id"] == tid
        assert seen["status_at_hook"] == "provisioning"  # hook runs BEFORE activate
    finally:
        P.register_provision_hook(None)
        _drop_db(control_db_url, make_url(default_tenant_dsn(tid)).database)


def test_provision_skips_physical_when_disabled(ctrl_engine, control_db_url, monkeypatch):
    monkeypatch.setenv("APP_DATABASE_URL", control_db_url)
    from {{ package_name }}.config.settings import get_settings; get_settings.cache_clear()
    from {{ package_name }}.multitenantauth.tenancy.provision import provision_tenant
    from {{ package_name }}.db.control import repository as repo

    with Session(ctrl_engine) as cs:
        tid = provision_tenant(cs, "Acme", slug="acme",
                               dsn="postgresql+psycopg://byo/elsewhere", run_physical=False)
        cs.commit()
        t = repo.get_tenant(cs, tid)
    assert t.status == "active"
    assert t.dsn == "postgresql+psycopg://byo/elsewhere"  # no DB created locally
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Create `provision.py`**

```python
"""Physical per-tenant provisioning (Phase 2 / SP1).

provision_tenant: register the tenant (control row) → [optionally] create + migrate its
physical database → run the post-migrate hook → activate. Idempotent and re-runnable: a
prior partial run is detected by slug and resumed (the physical steps are existence-checked
/ upgrade-no-op). NEVER rolls back a partially-created physical DB — teardown is a lifecycle
concern (SP3). The post-migrate hook is the consumer's seam for tenant-scoped seeding; the
generic battery seeds nothing."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from ...db.control import repository as control_repo
from .dsn import create_database
from .registry import activate_tenant, register_tenant
from .session import invalidate_dsn_cache

logger = logging.getLogger(__name__)

# A post-migrate hook: (control_session, tenant_id, tenant_dsn) -> None.
ProvisionHook = Callable[[Session, str, str], None]


def _noop_hook(control_session: Session, tenant_id: str, tenant_dsn: str) -> None:
    return None


_provision_hook: ProvisionHook = _noop_hook


def register_provision_hook(hook: ProvisionHook | None) -> None:
    """Register a post-migrate provisioning hook (pass None to reset to the no-op default).
    Runs AFTER the tenant DB is created + migrated, BEFORE activation — the place to seed
    tenant-scoped reference data. Call from your own (unlocked) create_app(). This locked
    file must NOT be edited to add seeding; register a hook instead."""
    global _provision_hook
    _provision_hook = hook or _noop_hook


def _project_root() -> Path:
    # src/<pkg>/multitenantauth/tenancy/provision.py → project root is parents[4].
    return Path(__file__).resolve().parents[4]


def migrate_tenant(dsn: str) -> None:
    """Run the APP migration chain to head against a tenant DSN (Python API; env.py honors the
    pre-set sqlalchemy.url, so this targets the tenant DB, not the app DB)."""
    cfg = Config(str(_project_root() / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", dsn)
    command.upgrade(cfg, "head")


def provision_tenant(
    control_session: Session,
    name: str,
    *,
    slug: str,
    dsn: str | None = None,
    run_physical: bool = True,
) -> str:
    """Provision a tenant end-to-end; return the opaque tenant id. Idempotent by slug."""
    existing_id = control_repo.live_slug_tenant_id(control_session, slug)
    if existing_id is not None:
        tenant = control_repo.get_tenant(control_session, existing_id)
        if tenant is not None and tenant.status == "active":
            return tenant.id  # already fully provisioned — no-op
        tenant_id = existing_id  # resume a prior partial run
        tenant_dsn = control_repo.get_tenant_dsn(control_session, existing_id) or ""
    else:
        tenant = register_tenant(
            control_session, name, slug=slug, dsn=dsn, status="provisioning"
        )
        control_session.flush()
        tenant_id, tenant_dsn = tenant.id, tenant.dsn

    if run_physical:
        create_database(tenant_dsn)
        migrate_tenant(tenant_dsn)

    _provision_hook(control_session, tenant_id, tenant_dsn)
    activate_tenant(control_session, tenant_id)
    invalidate_dsn_cache(tenant_id)
    return tenant_id
```

- [ ] **Step 4: Register the lock entry** — `"src/{package_name}/multitenantauth/tenancy/provision.py": ("multitenantauth",),`.

- [ ] **Step 5: Run both loops — PASS.** Acceptance test runs against real PG (`TMPDIR=/var/tmp`, Docker available, sandbox disabled). `uv run pytest tests/integrity/test_auth_mechanism_lock.py -q` PASS. `ruff format --check`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(FWK61 SP1): idempotent physical tenant provisioning + post-migrate hook (locked)"
```

---

## Task 9: `deps.py` — add the `tenant_db` routing dependency (LOCKED edit)

**Files:**
- Modify: `.../multitenantauth/deps.py` (LOCKED) — add `tenant_db` after `active_tenant`
- Test: rendered `tests/functional/test_tenant_routing_deps.py` (real PG)

**Interfaces:**
- Consumes: `active_tenant` (existing), `control_session` (existing), `tenant_session` (Task 5).
- Produces: `tenant_db(tenant_id=Depends(active_tenant), cs=Depends(control_session)) -> Iterator[Session]` — yields a Session on the active tenant's DB; a `LookupError` from resolution maps to `404` (no leak).

- [ ] **Step 1: Write the failing test** — a tiny app mounting a `{tenant_id}` route that depends on `tenant_db`; assert a provisioned tenant routes (writes land in the tenant DB) and an unknown tenant 404s. (Build it on the control-migrated `ctrl_engine` + a provisioned tenant from Task 8's helpers.)

```python
def test_tenant_db_routes_to_tenant_database(...): ...   # write via tenant_db, read back from the tenant DB directly
def test_tenant_db_unknown_tenant_returns_404(...): ...  # active_tenant already 404s a non-member/unknown
```

> Keep the assertions concrete in the implementation: provision two tenants, write a row through `tenant_db` under tenant A, assert it is absent from tenant B's DB (isolation) and present in A's.

- [ ] **Step 2: Run — expect FAIL** (`tenant_db` undefined).

- [ ] **Step 3: Add `tenant_db`** to `deps.py` (import `tenant_session` from the tenancy plane; insert after `active_tenant`):

```python
from .tenancy.session import tenant_session

# ... after active_tenant() ...

def tenant_db(
    tenant_id: str = Depends(active_tenant),
    cs: Session = Depends(control_session),
) -> Iterator[Session]:
    """Yield a session bound to the active tenant's database, resolving the DSN on the
    request's existing control session (no extra control connection). A resolution failure
    maps to 404 — never leak whether a tenant/DB exists."""
    try:
        with tenant_session(tenant_id, control_session=cs) as session:
            yield session
    except LookupError:
        raise HTTPException(status_code=404, detail="Not found") from None
```

- [ ] **Step 4: Run both loops — PASS.** Locked-file checksum updates; `test_auth_mechanism_lock` PASS. Full rendered authz suite still green. `ruff format --check`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(FWK61 SP1): tenant_db routing dependency (locked)"
```

---

## Task 10: Observability — expose tenant-engine metrics + spans + panel/alert

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/routes/health.py.jinja:~116-130` (the `/metrics` route)
- Modify: `.../tenancy/session.py` + `.../tenancy/provision.py` — add OTel spans (no DSN in attributes)
- Modify: multitenantauth's existing Grafana dashboard JSON + Prometheus alert YAML under `infra/observability/...`
- Test: rendered `tests/functional/test_auth_routes.py` (or the metrics test) asserts the new series appear at `/metrics`; framework `tests/test_obs_completeness.py` stays green

**Interfaces:**
- Consumes: `tenant_engines.render_pool_gauges()` (Task 3), `tenant_engine_metrics.render_prometheus()` (Task 2).

- [ ] **Step 1: Write the failing test** (rendered project)

```python
def test_metrics_exposes_tenant_engine_series(api_client):
    body = api_client.get("/metrics").text
    assert "app_tenant_engines_cached" in body
    assert "app_tenant_pool_checked_out" in body
    assert "app_tenant_dsn_cache_total" in body
    assert "app_tenant_engine_evictions_total" in body
```

- [ ] **Step 2: Run — expect FAIL.**

- [ ] **Step 3: Wire the exposition** — in `health.py.jinja`'s `metrics()` route, after the `auth_metrics` block, append (battery-gated):

```jinja
{%- if "multitenantauth" in batteries %}
    from {{ package_name }}.multitenantauth.tenancy.engine_registry import tenant_engines
    from {{ package_name }}.multitenantauth.tenancy.metrics import tenant_engine_metrics

    body += tenant_engines.render_pool_gauges()
    body += tenant_engine_metrics.render_prometheus()
{%- endif %}
```

Add OTel spans in `session.tenant_session` (span `tenant.resolve_dsn`, attribute `tenant.id` only) and each `provision.provision_tenant` step (`tenant.provision`, `tenant.create_database`, `tenant.migrate`) — **never** a DSN/credential attribute. Use the house tracing helper (match an existing battery's span usage; grep `start_as_current_span` in the template).

- [ ] **Step 4: Dashboard + alert** — add one panel (`app_tenant_engines_cached`, `app_tenant_pool_checked_out`) to multitenantauth's existing Grafana dashboard JSON, and one alert rule (e.g. sustained `app_tenant_pool_checked_out` near budget, or any `BudgetExceeded`-driven 5xx) to its existing alert file. (The obs-completeness guard only requires the files exist — they do — but the panel/alert make the new surface real.)

- [ ] **Step 5: Run both loops — PASS.** Framework: `uv run pytest tests/test_obs_completeness.py -q` PASS. Rendered: `/metrics` test PASS. `ruff format --check`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(FWK61 SP1): expose tenant-engine metrics + spans + dashboard/alert"
```

---

## Task 11: Conformance — tenant isolation acceptance + final gates

**Files:**
- Create/extend: rendered `tests/functional/test_tenant_provisioning.py` — an isolation case
- Verify: framework lock + obs + render suites; the rendered project's own gate

**Interfaces:** none new — this is the drift-aware conformance gate (DEC-0004 §"Conformance contract").

- [ ] **Step 1: Write the isolation acceptance test** — provision tenants A and B; via `tenant_session` write a distinct row into each tenant's `items` table; assert A's row is absent from B's DB and vice-versa (physical isolation), then drop both DBs.

```python
def test_two_tenants_are_physically_isolated(ctrl_engine, control_db_url, monkeypatch):
    # provision A and B; write through tenant_session(A) and tenant_session(B);
    # assert each row exists only in its own tenant DB. Drop both in teardown.
    ...
```

- [ ] **Step 2: Run — expect FAIL, then PASS once the prior tasks are in.**

- [ ] **Step 3: Full conformance sweep (framework, real PG):**

```bash
TMPDIR=/var/tmp uv run pytest tests/integrity/test_auth_mechanism_lock.py tests/test_obs_completeness.py -q
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Render a `multitenantauth` project and run ITS full suite (authz suite + the new tenant tests) + `ruff format --check` on the rendered output, per the template-payload loop.

- [ ] **Step 4: Branch-end Phase-2 Layer-2 review** — per DEC-0004 §Conformance, run the scoped adversarial security pass over the routing/provisioning surface (all-Opus, per [[security-review-workflow-all-opus]]): tenant-isolation bypass, DSN-resolver injection, budget fail-open, 404→existence leak, CREATE DATABASE injection via tenant_id (guarded by `^[a-z0-9_]+$`), idempotency/resume races. Record a scorecard under `docs/superpowers/eval-scorecards/`.

- [ ] **Step 5: Update state + commit**

Update `PLAN.md` (FWK61 SP1 → Done; SP2 next) + `ACTION_LOG.md`, flip `DEC-0004` status `designed → in-migration` (shipped in the absorber; Meridian adoption pending), then:

```bash
git add -A
git commit -m "feat(FWK61 SP1): tenant-isolation conformance + Layer-2 review; SP1 complete"
```

---

## Self-Review notes (carried into execution)

- **Spec corrections folded in** (this branch): `active_tenant` pre-exists (Task 9 adds `tenant_db` only); baseline `db/engine.py` untouched (Task 3 builds tenant engines directly); routing core lives under `multitenantauth/tenancy/` not `db/tenant/` (lock-guard coverage); the `migrations/env.py` inject-URL change (Task 7) is a new, necessary task; the DSN is id-derived + immutable so cache-invalidation is minimal (SP3 owns move/suspend).
- **Lock-sequencing:** each new mechanism file's `BATTERY_LOCKED_SRC` entry rides in its own task (Tasks 2–5, 8) — never deferred.
- **Idempotency** is by-slug-resume (Task 8), not Meridian's by-id short-circuit (the battery mints the id internally).
- **Acceptance tier is real-PG, never skip-neutral** (Tasks 8, 9, 11) — `CREATE DATABASE` is proven to work in the harness (`test_control_migrations.py` already does it).
