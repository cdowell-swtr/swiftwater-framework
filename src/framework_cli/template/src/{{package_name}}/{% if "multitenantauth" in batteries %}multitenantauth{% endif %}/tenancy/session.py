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
            # Log only the exception TYPE — never exc_info / str(exc), which can carry a
            # DSN a resolver embedded in its own message. Suppress the cause chain (from
            # None) so the DSN-bearing exception is not propagated upward to any logging
            # boundary. The locked mechanism self-protects; it does not trust callers.
            logger.warning(
                "tenant DSN resolver raised (%s); denying (fail-closed)",
                type(exc).__name__,
            )
            raise LookupError(f"DSN resolution failed for {tenant_id!r}") from None
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
