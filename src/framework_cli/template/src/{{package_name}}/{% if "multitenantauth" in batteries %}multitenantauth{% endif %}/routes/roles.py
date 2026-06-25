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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...db.control import models as m
from ..authz.expr import Perm
from ..authz.service import assign_role, revoke_role
from ..deps import control_session, current_user, guard
from ..errors import DomainMismatchError, LastAdminError

router = APIRouter(prefix="/tenants")

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
