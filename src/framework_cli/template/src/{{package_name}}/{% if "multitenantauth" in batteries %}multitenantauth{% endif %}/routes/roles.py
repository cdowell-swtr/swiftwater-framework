"""Role grant / revoke routes.

Endpoints:
- ``POST /tenants/{tenant_id}/members/{membership_id}/roles``
  — grant a role to a membership.
- ``DELETE /tenants/{tenant_id}/members/{membership_id}/roles/{role_name}``
  — revoke a role from a membership.

Both are guarded with the member-management permission on the tenant (requires the
actor to be a member with that permission, enforced by the guard before any service
call).

The ``{tenant_id}`` path param is bound in every Perm expression (T2 fitness).
"""

from __future__ import annotations

import uuid

from collections.abc import Callable
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...db.control import models as m
from ..authz.expr import ANY, Perm
from ..authz.service import (
    assign_resource_role,
    assign_role,
    revoke_resource_role,
    revoke_role,
)
from ..deps import control_session, current_user, guard
from ..errors import DomainMismatchError, LastAdminError

router = APIRouter(prefix="/tenants")

ResourceTargetValidator = Callable[[Session, m.AppUser, str, str], bool]

_resource_target_validator: ResourceTargetValidator | None = None


def register_resource_target_validator(
    validator: ResourceTargetValidator | None,
) -> None:
    """Register a resource existence/visibility validator for resource-role grants.

    The validator runs after the authz guard and membership tenant check, but before
    ``assign_resource_role`` writes the grant. Return ``True`` to allow, ``False`` to
    hide/deny as 404, or raise ``HTTPException`` for a consumer-owned status such as 403.
    Passing ``None`` restores the compatibility default: permit all resource ids.
    """
    global _resource_target_validator
    _resource_target_validator = validator


def _validate_resource_target(
    s: Session,
    user: m.AppUser,
    tenant_id: str,
    resource_id: str,
) -> None:
    validator = _resource_target_validator
    if validator is None:
        return
    try:
        allowed = validator(s, user, tenant_id, resource_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Resource not found") from None
    if allowed is not True:
        raise HTTPException(status_code=404, detail="Resource not found")


# ── request models ─────────────────────────────────────────────────────────────


class GrantRoleBody(BaseModel):
    role_name: str = Field(min_length=1)


# ── routes ─────────────────────────────────────────────────────────────────────


@router.post(
    "/{tenant_id}/members/{membership_id}/roles",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(guard(Perm("tenant:manage-members", on="tenant:{tenant_id}")))
    ],
)
def grant_role(
    tenant_id: str,
    membership_id: uuid.UUID,
    body: GrantRoleBody,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> None:
    """Grant *body.role_name* to *membership_id* within *tenant_id*.

    Guarded: requires the member-management permission on the tenant.
    The membership must belong to *tenant_id*.
    Idempotent (repeated grant of a held role is a no-op with no audit row).
    """
    membership = s.get(m.TenantMembership, membership_id)
    if membership is None or membership.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Membership not found")

    try:
        assign_role(
            s, membership_id=membership_id, role_name=body.role_name, actor_id=user.id
        )
        s.commit()
    except (ValueError, DomainMismatchError) as exc:
        # Unknown role (ValueError) or wrong-domain role (DomainMismatchError, which is an
        # AuthError not a ValueError) → 400, not an uncaught 500 (Layer-2 finding D).
        s.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError:
        # A concurrent duplicate grant raced the SELECT-then-INSERT; the unique constraint
        # held, so this is the idempotent no-op the single-threaded path already is → 204
        # (Layer-2 finding N).
        s.rollback()


@router.delete(
    "/{tenant_id}/members/{membership_id}/roles/{role_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(guard(Perm("tenant:manage-members", on="tenant:{tenant_id}")))
    ],
)
def revoke_role_route(
    tenant_id: str,
    membership_id: uuid.UUID,
    role_name: str,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> None:
    """Revoke *role_name* from *membership_id* within *tenant_id*.

    Guarded: requires the member-management permission on the tenant.
    Enforces the ≥1-admin invariant (raises ``LastAdminError`` → 409).
    Idempotent (revoking a role not held is a no-op with no audit row).
    """
    membership = s.get(m.TenantMembership, membership_id)
    if membership is None or membership.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Membership not found")

    try:
        revoke_role(
            s, membership_id=membership_id, role_name=role_name, actor_id=user.id
        )
        s.commit()
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, DomainMismatchError) as exc:
        # Unknown role (ValueError) or wrong-domain role (DomainMismatchError) → 400, not an
        # uncaught 500 (Layer-2 finding D).
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── resource role routes ───────────────────────────────────────────────────────

_RESOURCE_GUARD = guard(
    ANY(
        Perm("resource:manage", on="tenant:{tenant_id}/resource:{resource_id}"),
        Perm("tenant:manage-members", on="tenant:{tenant_id}"),
    )
)


class GrantResourceRoleBody(BaseModel):
    role_name: str = Field(min_length=1)


@router.post(
    "/{tenant_id}/members/{membership_id}/resources/{resource_id}/roles",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_RESOURCE_GUARD)],
)
def grant_resource_role(
    tenant_id: str,
    membership_id: uuid.UUID,
    resource_id: str,
    body: GrantResourceRoleBody,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> None:
    """Grant a resource-domain role on {resource_id} to {membership_id}. Tenant-admin bootstraps."""
    membership = s.get(m.TenantMembership, membership_id)
    if membership is None or membership.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    _validate_resource_target(s, user, tenant_id, resource_id)
    try:
        assign_resource_role(
            s,
            membership_id=membership_id,
            resource_id=resource_id,
            role_name=body.role_name,
            actor_id=user.id,
        )
        s.commit()
    except (ValueError, DomainMismatchError) as exc:
        s.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError:
        s.rollback()  # idempotent concurrent duplicate → 204


@router.delete(
    "/{tenant_id}/members/{membership_id}/resources/{resource_id}/roles/{role_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_RESOURCE_GUARD)],
)
def revoke_resource_role_route(
    tenant_id: str,
    membership_id: uuid.UUID,
    resource_id: str,
    role_name: str,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> None:
    """Revoke a resource-domain role on {resource_id} from {membership_id}."""
    membership = s.get(m.TenantMembership, membership_id)
    if membership is None or membership.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Membership not found")
    try:
        revoke_resource_role(
            s,
            membership_id=membership_id,
            resource_id=resource_id,
            role_name=role_name,
            actor_id=user.id,
        )
        s.commit()
    except (ValueError, DomainMismatchError) as exc:
        s.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
