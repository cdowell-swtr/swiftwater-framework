"""Tenant management routes.

Endpoints:
- ``POST /tenants``                       — provision a tenant (PLATFORM-level op;
  distinct from signup's founder-tenant). Requires the platform-provisioning permission.
- ``GET /tenants/{tenant_id}/members``    — list members (read-only, requires read access).
- ``POST /tenants/{tenant_id}/members``   — invite a user to a tenant (adds membership + role).
- ``DELETE /tenants/{tenant_id}/members/{membership_id}`` — remove a member.

The member routes are guarded with the Task-14 ``guard(Perm(...))``; the ``{tenant_id}``
path param is ALWAYS bound in the Perm expression — satisfying the T2 fitness-test
requirement that every ``{tenant_id}`` route binds it.

Mutating member operations require the member-management permission; read-only member
operations require the read permission; tenant provisioning requires the platform-level
provisioning grant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...db.control import models as m
from ..authz.expr import Perm
from ..authz.service import add_membership, remove_member
from ..deps import control_session, current_user, guard
from ..errors import DomainMismatchError, LastAdminError
from ..tenancy.registry import (
    activate_tenant,
    deactivate_tenant,
    reactivate_tenant,
    record_lifecycle_event,
    register_tenant,
    rename_slug,
    resolve_slug,
)

router = APIRouter(prefix="/tenants")

# A routing-agnostic Phase-1 placeholder DSN. The registry NEVER connects to it (Phase 2 wires
# physical per-tenant routing); it only persists the string. Mirrors routes/auth.py.
_PLACEHOLDER_DSN = "postgresql+psycopg://unprovisioned/placeholder"

# Generic error details — never echo the registry's raw message (it can name the colliding
# tenant's opaque id; Layer-2 finding A). Mirrors routes/auth.py's _GENERIC_* constants.
_GENERIC_BAD_REQUEST = "Invalid request"
_GENERIC_SLUG_TAKEN = "Tenant slug unavailable"

# ── request/response models ────────────────────────────────────────────────────


class ProvisionTenantBody(BaseModel):
    name: str = Field(max_length=200)
    slug: str = Field(max_length=63)


class TenantLifecycleBody(BaseModel):
    tenant_id: str = Field(max_length=64)


class RenameSlugBody(BaseModel):
    slug: str = Field(max_length=63)


class AddMemberBody(BaseModel):
    user_id: uuid.UUID
    role_name: str


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

    Guarded: requires the platform-level provisioning permission. Registers +
    activates the tenant in the control plane (routing-agnostic; never connects to a
    tenant DB). Returns the OPAQUE, auto-generated tenant id.
    A taken slug surfaces as a GENERIC 409 (never the colliding tenant's id); a bad-charset
    slug as a generic 400.
    """
    # Pre-check the slug collision (live OR cooling) → a generic 409 that never reveals the
    # colliding tenant's opaque id (Layer-2 finding A). This leaves register_tenant's only
    # residual ValueError the bad-charset case → a deterministic 400 below (Layer-2 finding C).
    if resolve_slug(s, body.slug) is not None:
        raise HTTPException(status_code=409, detail=_GENERIC_SLUG_TAKEN)
    try:
        tenant = register_tenant(s, body.name, slug=body.slug, dsn=_PLACEHOLDER_DSN)
        s.flush()
        activate_tenant(s, tenant.id)
        s.commit()
    except ValueError:
        s.rollback()
        raise HTTPException(status_code=400, detail=_GENERIC_BAD_REQUEST) from None
    except IntegrityError:
        # TOCTOU race against the pre-check: the slug column is DB-UNIQUE → 409, never a 500
        # (Layer-2 finding P).
        s.rollback()
        raise HTTPException(status_code=409, detail=_GENERIC_SLUG_TAKEN) from None
    return {"tenant_id": tenant.id, "slug": body.slug}


@router.post(
    "/suspend",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(guard(Perm("platform:manage-tenant-lifecycle", on="platform")))
    ],
)
def operator_suspend_route(
    body: TenantLifecycleBody,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> None:
    """Operator suspend (fleet-wide). tenant_id is a target selector in the body, not an authz operand."""
    try:
        deactivate_tenant(s, body.tenant_id)
        record_lifecycle_event(
            s, actor_id=user.id, tenant_id=body.tenant_id, action="suspend"
        )
        s.commit()
    except LookupError:
        s.rollback()
        raise HTTPException(status_code=404, detail="Tenant not found") from None
    except ValueError as exc:
        s.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/reactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(guard(Perm("platform:manage-tenant-lifecycle", on="platform")))
    ],
)
def operator_reactivate_route(
    body: TenantLifecycleBody,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> None:
    """Operator reactivation: suspended → active (409 if not suspended, 404 if absent)."""
    try:
        reactivate_tenant(s, body.tenant_id)
        record_lifecycle_event(
            s, actor_id=user.id, tenant_id=body.tenant_id, action="reactivate"
        )
        s.commit()
    except LookupError:
        s.rollback()
        raise HTTPException(status_code=404, detail="Tenant not found") from None
    except ValueError as exc:
        s.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{tenant_id}/deactivate",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(guard(Perm("tenant:deactivate", on="tenant:{tenant_id}")))],
)
def deactivate_tenant_route(
    tenant_id: str,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> None:
    """Tenant-admin self-offboard: suspend the tenant (reversible). Reactivation is operator-only."""
    try:
        deactivate_tenant(s, tenant_id)
        record_lifecycle_event(
            s, actor_id=user.id, tenant_id=tenant_id, action="suspend"
        )
        s.commit()
    except LookupError:
        s.rollback()
        raise HTTPException(status_code=404, detail="Tenant not found") from None
    except ValueError as exc:
        s.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch(
    "/{tenant_id}/slug",
    dependencies=[Depends(guard(Perm("tenant:rename-slug", on="tenant:{tenant_id}")))],
)
def rename_slug_route(
    tenant_id: str,
    body: RenameSlugBody,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> dict:
    """Rename the tenant's slug (tenant-admin). Old slug retires into a cooling window."""
    # Generic-409 pre-check (live OR cooling → taken); never echo the colliding tenant's id (Layer-2 A).
    if resolve_slug(s, body.slug) is not None:
        raise HTTPException(status_code=409, detail=_GENERIC_SLUG_TAKEN)
    # Fetch BEFORE mutating so a missing tenant is a clean 404, not an AttributeError 500.
    tenant = s.get(m.Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    old = tenant.slug
    try:
        rename_slug(s, tenant_id, body.slug)
        record_lifecycle_event(
            s,
            actor_id=user.id,
            tenant_id=tenant_id,
            action="rename",
            detail=f"{old}→{body.slug}",
        )
        s.commit()
    except ValueError:
        s.rollback()
        raise HTTPException(status_code=400, detail=_GENERIC_BAD_REQUEST) from None
    except IntegrityError:
        s.rollback()
        raise HTTPException(status_code=409, detail=_GENERIC_SLUG_TAKEN) from None
    return {"tenant_id": tenant_id, "slug": body.slug}


@router.get(
    "/{tenant_id}/members",
    dependencies=[Depends(guard(Perm("tenant:read", on="tenant:{tenant_id}")))],
)
def list_members(
    tenant_id: str,
    s: Session = Depends(control_session),
    user: m.AppUser = Depends(current_user),
) -> list[MemberOut]:
    """List members of *tenant_id*.  Guarded: requires the read permission on the tenant."""
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

    Guarded: requires the member-management permission on the tenant.
    The target user must already exist.
    """
    target = s.get(m.AppUser, body.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        membership = add_membership(
            s,
            user_id=body.user_id,
            tenant_id=tenant_id,
            role_name=body.role_name,
            actor_id=user.id,
            invited=True,
        )
        s.commit()
    except (ValueError, DomainMismatchError) as exc:
        # Unknown role (ValueError) or wrong-domain role (DomainMismatchError) → 400, not an
        # uncaught 500 — mirrors grant_role (Layer-2 finding D / add_member 500s).
        s.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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

    Guarded: requires the member-management permission on the tenant.
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
