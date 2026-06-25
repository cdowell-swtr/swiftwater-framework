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
        self._engines: OrderedDict[str, Engine] = (
            OrderedDict()
        )  # dsn -> engine (LRU order)
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
