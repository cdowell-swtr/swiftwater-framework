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

from collections.abc import Iterator
from datetime import datetime, timezone

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

    def _dep(
        request: Request,
        user: m.AppUser = Depends(current_user),
        cs: Session = Depends(control_session),
    ) -> None:
        path = dict(request.path_params)
        tenant_perms: set[str] = set()
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

        ctx = {
            "tenant_perms": tenant_perms,
            "platform_perms": platform_permissions(cs, user.id),
            "path": path,
            "subtree_exists": lambda name, resource: False,  # inert (Phase 1; A-F10)
            "resource_grant": _resource_grant,
        }
        _authz_domain = "tenant" if needs_tenant else "platform"
        if not authorized.satisfied(ctx):
            auth_metrics.record_authz("deny", _authz_domain)
            raise HTTPException(status_code=403, detail=AUTHZ_FORBIDDEN_DETAIL)
        auth_metrics.record_authz("allow", _authz_domain)

    _dep.__authorized__ = authorized  # type: ignore[attr-defined]  # fitness-test introspection hook
    return _dep
