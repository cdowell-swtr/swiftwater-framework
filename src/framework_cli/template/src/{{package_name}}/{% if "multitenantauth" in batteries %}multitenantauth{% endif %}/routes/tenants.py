"""Tenant management routes.

Endpoints:
- ``POST /tenants``                       — provision a tenant (PLATFORM-level op;
  distinct from signup's founder-tenant). Guarded ``platform:provision-tenant``.
- ``GET /tenants/{tenant_id}/members``    — list members (read-only, guarded tenant:read).
- ``POST /tenants/{tenant_id}/members``   — invite a user to a tenant (adds membership + role).
- ``DELETE /tenants/{tenant_id}/members/{membership_id}`` — remove a member.

The member routes are guarded with the Task-14 ``guard(Perm(...))``; the ``{tenant_id}``
path param is ALWAYS bound in the Perm expression — satisfying the T2 fitness-test
requirement that every ``{tenant_id}`` route binds it.

``tenant:manage-members`` is required for mutating member operations; ``tenant:read``
for reads; ``platform:provision-tenant`` (a platform-domain grant) for ``POST /tenants``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.control import models as m
from ..authz.expr import Perm
from ..authz.service import add_membership, remove_member
from ..deps import control_session, current_user, guard
from ..errors import LastAdminError
from ..tenancy.registry import activate_tenant, register_tenant

router = APIRouter(prefix="/tenants")

# A routing-agnostic Phase-1 placeholder DSN. The registry NEVER connects to it (Phase 2 wires
# physical per-tenant routing); it only persists the string. Mirrors routes/auth.py.
_PLACEHOLDER_DSN = "postgresql+psycopg://unprovisioned/placeholder"

# ── request/response models ────────────────────────────────────────────────────


class ProvisionTenantBody(BaseModel):
    name: str = Field(max_length=200)
    slug: str = Field(max_length=63)


class AddMemberBody(BaseModel):
    user_id: uuid.UUID
    role_name: str = Field(default="tenant.member")


class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    roles: list[str]


# ── routes ─────────────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(guard(Perm("platform:provision-tenant", on="platform")))],
)
def provision_tenant(
    body: ProvisionTenantBody,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> dict:
    """Provision a tenant (PLATFORM-level — distinct from signup's founder-tenant).

    Guarded: requires ``platform:provision-tenant`` on the platform. Registers +
    activates the tenant in the control plane (routing-agnostic; never connects to a
    tenant DB). Returns the OPAQUE, auto-generated tenant id.
    A bad-charset / taken slug surfaces as a generic 400/409.
    """
    try:
        tenant = register_tenant(s, body.name, slug=body.slug, dsn=_PLACEHOLDER_DSN)
        s.flush()
        activate_tenant(s, tenant.id)
        s.commit()
    except ValueError as exc:
        s.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"tenant_id": tenant.id, "slug": body.slug}


@router.get(
    "/{tenant_id}/members",
    dependencies=[Depends(guard(Perm("tenant:read", on="tenant:{tenant_id}")))],
)
def list_members(
    tenant_id: str,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> list[MemberOut]:
    """List members of *tenant_id*.  Guarded: requires ``tenant:read`` on the tenant."""
    memberships = s.scalars(
        select(m.TenantMembership).where(m.TenantMembership.tenant_id == tenant_id)
    ).all()
    out: list[MemberOut] = []
    for membership in memberships:
        member_user = s.get(m.AppUser, membership.user_id)
        roles = list(
            s.scalars(
                select(m.Role.name)
                .join(
                    m.TenantRoleAssignment,
                    m.TenantRoleAssignment.role_id == m.Role.id,
                )
                .where(m.TenantRoleAssignment.membership_id == membership.id)
            ).all()
        )
        out.append(
            MemberOut(
                membership_id=membership.id,
                user_id=membership.user_id,
                email=member_user.email if member_user else "",
                roles=roles,
            )
        )
    return out


@router.post(
    "/{tenant_id}/members",
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(guard(Perm("tenant:manage-members", on="tenant:{tenant_id}")))
    ],
)
def add_member(
    tenant_id: str,
    body: AddMemberBody,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> dict:
    """Add *body.user_id* as a member of *tenant_id* with *body.role_name*.

    Guarded: requires ``tenant:manage-members`` on the tenant.
    The target user must already exist.
    """
    target = s.get(m.AppUser, body.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    membership = add_membership(
        s,
        user_id=body.user_id,
        tenant_id=tenant_id,
        role_name=body.role_name,
        actor_id=user.id,
        invited=True,
    )
    s.commit()
    return {"membership_id": str(membership.id)}


@router.delete(
    "/{tenant_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(guard(Perm("tenant:manage-members", on="tenant:{tenant_id}")))
    ],
)
def remove_member_route(
    tenant_id: str,
    membership_id: uuid.UUID,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> None:
    """Remove membership *membership_id* from *tenant_id*.

    Guarded: requires ``tenant:manage-members`` on the tenant.
    Enforces the ≥1-admin invariant via the service layer (raises ``LastAdminError``
    → 409).
    """
    membership = s.get(m.TenantMembership, membership_id)
    if membership is None or membership.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Membership not found")

    try:
        remove_member(s, membership_id=membership_id, actor_id=user.id)
        s.commit()
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
