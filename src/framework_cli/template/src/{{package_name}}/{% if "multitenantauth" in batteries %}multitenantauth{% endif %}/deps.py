"""The request authorization chain (FastAPI dependencies).

Order per request: ``current_user`` (401 on no/invalid/expired/disabled session) →
``active_tenant`` (404 if the URL's tenant is unknown / not active / not a member of —
existence is never leaked) → ``guard(expr)`` (403 if the permission expression is
unsatisfied). ``guard`` for a tenant-scoped expression performs the membership precondition
itself, so a non-member always gets **404 before 403** — a policy-leaking 403 can never
precede the existence check.

All dependencies share one ``control_session`` (FastAPI caches it within a request), so user
+ membership + permission resolution run on a single control connection.

Design note: this module intentionally holds BOTH AuthN/tenancy dependencies
(``current_user`` / ``active_tenant``) and the AuthZ dependency (``guard``). They are
NOT split into separate modules: ``guard`` re-asserts the membership-404 precondition
*inside itself* before the 403 permission check, so the 404-before-403 ordering and
the single-pass request efficiency are co-located here on purpose. Keep them together.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Iterator
from datetime import datetime, timezone
from typing import cast

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config.settings import get_settings
from ..db.control import engine as ctrl_engine
from ..db.control import models as m
from .authz.expr import Authorized, Expr
from .authz.resolution import has_membership, platform_permissions, tenant_permissions
from .authn.tokens import hash_token
from .errors import AUTHZ_FORBIDDEN_DETAIL
from .metrics import auth_metrics
from .tenancy.session import tenant_session

logger = logging.getLogger(__name__)

# ── Pluggable authz-resolver seam (DV-5 / FWK62) ─────────────────────────────────
# The authz evaluator (authz/expr.py) delegates resource-scoped leaves to ctx callables. By
# DEFAULT the battery wires them flat/inert: a concrete-resource grant resolved via control-DB
# membership only, and an inert wildcard-subtree resolver that denies (A-F10). A consumer with
# resource hierarchies / scoped visibility may register a per-request resolver FACTORY from their
# own (unlocked) startup to supply a richer resource-grant resolver — without editing this
# integrity-LOCKED file. A deliberate, bounded exception to the Option-B lock: ONE controlled
# injection point into the GRANT decision.
#
#   register_authz_resolver_factory(factory)
#       factory(control_session, app_user, active_tenant_id) -> {"resource_grant": resolver}
#
# The battery honors the resource_grant key only. The per-call resolver is TENANT-FREE:
#       resource_grant(perm_name, resource_id) -> bool | Awaitable[bool]
# resource_id is the BARE id the battery extracts from the route (it owns the resource:{id}
# convention); the active tenant binds ONCE, in the factory closure (active_tenant_id), never per
# call — so a resolver can never trust a raw path tenant. The wildcard-subtree resolver is NOT
# consumer-overridable in this release: no shipped route uses a wildcard subtree, so it stays the
# inert default (A-F10), deferred to a real need with a properly-designed shape.
#
# SECURITY: a registered resolver participates in the GRANT decision for resource-scoped leaves
# ONLY — tenant/platform authz (tenant_perms / platform_perms) is untouched, and this
# registration API and the evaluator both stay locked. The factory is consulted only AFTER the
# membership-404 precondition passes, so it ALWAYS receives a resolved, membership-gated active
# tenant — never a raw request value (feeding an unresolved tenant would break cross-tenant
# compartmentalization: grants match on membership_id AND resource together). Everything fails
# CLOSED: a factory that raises / returns a non-mapping / omits the resource_grant key, or a
# resolver that raises, all DENY (403) — never 500, never allow. A registered factory OWNS
# resource grants: absent ⇒ deny, NOT a fall-back to the flat default (registration is strictly
# opt-in).
#
# CONSUMER ROUTE CONTRACT (DV-5 t1) — name your tenant path param `{tenant_id}`. The membership-404
# precondition and the `needs_tenant` detection in `guard` both key on the LITERAL name `tenant_id`
# (`needs_tenant = "tenant_id" in resource_params()`; the precondition reads `path["tenant_id"]`). A
# tenant-scoped route that names its param `{org_id}` (and writes the guard leaf as
# `on="tenant:{org_id}"`) gets `needs_tenant=False`: the membership check never fires and
# `tenant_perms` stays empty, so the leaf evaluates against an empty grant set and DENIES every
# caller. This is fail-CLOSED (no over-grant, no existence leak) but the route is silently broken —
# always 403, even for legitimate members. So: bind tenant-scoped leaves to `{tenant_id}` and name
# the path param `{tenant_id}` to match. The T2 fitness test (`test_T2_tenant_routes_bind_tenant_id`)
# catches a `{tenant_id}` PATH that the guard fails to bind, but cannot see a DIFFERENTLY-named param
# — that contract lives here.
#
# CONSUMER RESOLVER EXAMPLE (DV-5 t3) — a correct factory scopes every lookup to the closure tenant
# and the calling user's membership; the active tenant binds ONCE (never per call):
#
#   from your_package.multitenantauth.deps import register_authz_resolver_factory
#
#   def _resource_grant_factory(cs, user, active_tenant_id):
#       # active_tenant_id is the resolved, membership-gated tenant — never a raw path value.
#       def resource_grant(perm_name: str, resource_id: str) -> bool:
#           # Look the grant up scoped to THIS tenant + THIS user; resource_id is the bare id the
#           # battery extracted (you never parse a concatenated "tenant:…/resource:…" string).
#           return my_grants.exists(
#               tenant_id=active_tenant_id, user_id=user.id, perm=perm_name, resource_id=resource_id,
#           )
#       return {"resource_grant": resource_grant}
#
#   # Call from your OWN (unlocked) startup — e.g. create_app() — NOT this locked file:
#   register_authz_resolver_factory(_resource_grant_factory)
#
# A mapping whose resource_grant value is a sync or async (perm_name, resource_id) resolver.
ResourceResolvers = dict[str, Callable[..., object]]
AuthzResolverFactory = Callable[[Session, m.AppUser, str], ResourceResolvers]

_resolver_factory: AuthzResolverFactory | None = None


def register_authz_resolver_factory(factory: AuthzResolverFactory | None) -> None:
    """Register a per-request authz-resolver factory (pass ``None`` to reset to the flat default).

    The battery's ``guard`` calls ``factory(control_session, user, active_tenant_id)`` once per
    request — only after the membership-404 precondition passes, so ``active_tenant_id`` is the
    resolved, membership-gated tenant, never a raw request value — and uses the returned
    ``resource_grant`` resolver (``(perm_name, resource_id) -> bool | Awaitable[bool]``,
    tenant-free) in place of the flat default for resource-scoped leaves. A registered factory OWNS
    resource grants: if it omits the key, raises, or returns a non-mapping, every resource leaf
    DENIES (fail-closed) — it does NOT fall back to the flat default. Call this from your own
    (unlocked) startup, e.g.
    ``create_app()``. See the module note above for the full security contract.
    """
    global _resolver_factory
    _resolver_factory = factory


def _deny(*_args: object, **_kwargs: object) -> bool:
    """The inert default resolver: deny every resource-scoped leaf (A-F10 / fail-closed)."""
    return False


def _is_awaitable(value: object) -> bool:
    return inspect.isawaitable(value)


def _adapt_resource_grant(resolver: Callable[..., object]) -> Callable[..., object]:
    """Adapt a consumer resolver — ``resource_grant(perm_name, resource_id) -> bool`` — to the
    evaluator's ctx call ``(name, path)``. The battery owns the ``resource:{resource_id}`` route
    convention, so it extracts the BARE resource id HERE and hands the consumer only
    ``(perm_name, resource_id)``: the consumer never touches path params or a per-call tenant — the
    active tenant binds ONCE, in the factory closure. Fails CLOSED: any error (or a missing
    resource id) DENIES — logs, never 500s, never allows."""

    async def _ctx_resource_grant(name: str, path: dict[str, str]) -> bool:
        resource_id = path.get("resource_id")
        if resource_id is None:
            return False
        try:
            result = resolver(name, resource_id)
            if _is_awaitable(result):
                result = await cast(Awaitable[object], result)
            return bool(result)
        except Exception:
            logger.warning(
                "authz resource_grant resolver raised; denying (fail-closed)",
                exc_info=True,
            )
            return False

    return _ctx_resource_grant


def control_session() -> Iterator[Session]:
    """A control-plane session for the request (cached by FastAPI across the chain)."""
    with ctrl_engine.control_session_factory()() as session:
        yield session


def current_user(request: Request, cs: Session = Depends(control_session)) -> m.AppUser:
    """Resolve the session token (httpOnly cookie OR ``Authorization: Bearer``) to a user.
    401 on a missing/invalid/expired session or a disabled user. The stored hash lookup IS
    the check."""
    settings = get_settings()
    raw = request.cookies.get(settings.session_cookie_name)
    if not raw:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            raw = header[7:]
    raw = (raw or "").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")
    row = cs.get(m.Session, hash_token(raw))
    if row is None or row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = cs.get(m.AppUser, row.user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def active_tenant(
    request: Request,
    user: m.AppUser = Depends(current_user),
    cs: Session = Depends(control_session),
) -> str:
    """The URL-selected tenant, asserted to exist + be active + have the user as a member.
    404 otherwise (never reveal whether a tenant exists or whether you're simply not a
    member)."""
    tenant_id = request.path_params.get("tenant_id")
    if tenant_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    tenant = cs.get(m.Tenant, tenant_id)
    if (
        tenant is None
        or tenant.status != "active"
        or not has_membership(cs, user.id, tenant_id)
    ):
        raise HTTPException(status_code=404, detail="Not found")
    return tenant_id


def tenant_db(
    tenant_id: str = Depends(active_tenant),
    cs: Session = Depends(control_session),
) -> Iterator[Session]:
    """Yield a session bound to the active tenant's database, resolving the DSN on the
    request's existing control session (no extra control connection). A resolution failure
    maps to 404 — never leak whether a tenant/DB exists. A LookupError raised by the route
    handler AFTER the session is yielded propagates normally (it is a handler bug, not a
    routing miss)."""
    entered = False
    try:
        with tenant_session(tenant_id, control_session=cs) as session:
            entered = True
            yield session
    except LookupError:
        if entered:
            raise  # post-yield LookupError = handler bug → 500, do not mask as 404
        raise HTTPException(status_code=404, detail="Not found") from None


def guard(expr: Expr):
    """Build a route-guard dependency from a permission expression.

    For a tenant-scoped expression it enforces the membership 404 precondition *inside*
    the guard (so 404 precedes the 403 — A-F8), then evaluates the expression against
    the request's domain-split grants. Returns a FastAPI dependency carrying
    ``__authorized__`` (read by the T1–T4 fitness tests; never serialized to a client).

    The inline membership-404 re-check is load-bearing: a guard-only route that binds
    ``{tenant_id}`` but does NOT depend on ``active_tenant`` must still gate non-members
    with 404, not 403. Do NOT refactor this check to rely on ``active_tenant``.
    """
    authorized = Authorized(expr)
    needs_tenant = "tenant_id" in authorized.resource_params()

    async def _dep(
        request: Request,
        user: m.AppUser = Depends(current_user),
        cs: Session = Depends(control_session),
    ) -> None:
        path = dict(request.path_params)
        tenant_perms: set[str] = set()
        # Set ONLY after the membership-404 check below (never a raw request value).
        active_tenant_id: str | None = None
        if needs_tenant:
            tenant_id = path.get("tenant_id")
            tenant = cs.get(m.Tenant, tenant_id) if tenant_id is not None else None
            if (
                tenant_id is None
                or tenant is None
                or tenant.status != "active"
                or not has_membership(cs, user.id, tenant_id)
            ):
                raise HTTPException(
                    status_code=404, detail="Not found"
                )  # 404 before 403 (A-F8)
            tenant_perms = tenant_permissions(cs, user.id, tenant_id)
            # resolved + membership-gated (never a raw value)
            active_tenant_id = tenant_id

        def _resource_grant(name: str, path: dict[str, str]) -> bool:
            # Flat, control-DB only: does the user (via their (user, tenant) membership) hold a
            # resource-role granting `name` on this exact resource_id? tenant_id/resource_id come
            # straight from the bound path params — never parsed out of a concatenated resource
            # string (A-F1).
            tid, rid = path.get("tenant_id"), path.get("resource_id")
            if tid is None or rid is None:
                return False
            membership_id = cs.scalar(
                select(m.TenantMembership.id).where(
                    m.TenantMembership.user_id == user.id,
                    m.TenantMembership.tenant_id == tid,
                )
            )
            if membership_id is None:  # resolve membership by (user, tenant) FIRST
                return False
            hit = cs.scalar(
                select(m.ResourceRoleAssignment.id)
                .join(
                    m.RolePermission,
                    m.RolePermission.role_id == m.ResourceRoleAssignment.role_id,
                )
                .where(
                    m.ResourceRoleAssignment.membership_id
                    == membership_id,  # (membership, resource) TOGETHER
                    m.ResourceRoleAssignment.resource_id == rid,
                    m.RolePermission.permission_name == name,
                )
                .limit(1)
            )
            return hit is not None

        # DV-5 t4: compute platform_perms BEFORE the resolver-factory call below, so a registered
        # factory can never sit upstream of (and thus influence) the platform-perm computation.
        # Pure control-DB read — behaviour-preserving.
        platform_perms = platform_permissions(cs, user.id)

        # Default = today's flat resolver (unchanged when no factory is registered).
        resource_grant: Callable[..., object] = _resource_grant
        factory = _resolver_factory
        if factory is not None and active_tenant_id is not None:
            # A registered factory OWNS resource grants. It runs ONLY here — after the
            # membership-404 precondition — so it always gets a resolved, membership-gated active
            # tenant (never a raw value). An absent "resource_grant" key, a non-mapping return, or
            # a raise all DENY: fail closed, never a 500, never a silent fall-back to the flat
            # default (registration is strictly opt-in).
            resource_grant = _deny
            try:
                overrides = factory(cs, user, active_tenant_id)
                consumer_grant = overrides.get("resource_grant")
            except Exception:
                logger.warning(
                    "authz resolver factory failed (raised or returned a non-mapping); "
                    "denying all resource leaves (fail-closed)",
                    exc_info=True,
                )
            else:
                if consumer_grant is not None:
                    resource_grant = _adapt_resource_grant(consumer_grant)

        ctx = {
            "tenant_perms": tenant_perms,
            "platform_perms": platform_perms,
            "path": path,
            # Inert: the wildcard-subtree resolver denies and is NOT consumer-overridable in this
            # release (no shipped route uses it; deferred to a real need — A-F10).
            "subtree_exists": _deny,
            "resource_grant": resource_grant,
        }
        _authz_domain = "tenant" if needs_tenant else "platform"
        if not await authorized.satisfied_async(ctx):
            auth_metrics.record_authz("deny", _authz_domain)
            raise HTTPException(status_code=403, detail=AUTHZ_FORBIDDEN_DETAIL)
        auth_metrics.record_authz("allow", _authz_domain)

    _dep.__authorized__ = authorized  # type: ignore[attr-defined]  # fitness-test introspection hook
    return _dep
