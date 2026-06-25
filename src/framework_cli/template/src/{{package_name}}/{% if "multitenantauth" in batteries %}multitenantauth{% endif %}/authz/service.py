"""Membership / role-assignment service layer.

Grants and revokes tenant and platform roles, each recording an append-only ``AuthzEvent``
(``actor_id=None`` ⇒ a system action). The ≥1-admin invariant — a tenant can never be left
with zero admins — is enforced TOCTOU-safely: ``_assert_not_last_admin`` locks the entire
admin-assignment set for the tenant with ``SELECT ... FOR UPDATE``, so two concurrent demotions
serialize and cannot both pass the count.

Service functions never commit — the caller owns the transaction boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config.settings import get_settings
from ...db.control import models as m
from ..errors import DomainMismatchError, LastAdminError
from ..metrics import auth_metrics


def _resolve_role(s: Session, role_name: str) -> m.Role:
    """Look up a role by name; raise ValueError for an unknown role."""
    role = s.scalar(select(m.Role).where(m.Role.name == role_name))
    if role is None:
        raise ValueError(f"unknown role: {role_name!r}")
    return role


def _require_domain(role: m.Role, expected: str) -> None:
    """Guard that a role's domain matches the assignment kind (tenant vs platform)."""
    if role.domain != expected:
        raise DomainMismatchError(
            f"role {role.name!r} is domain {role.domain!r}, expected {expected!r}"
        )


def _record_event(
    s: Session,
    *,
    actor_id: uuid.UUID | None,
    subject_user_id: uuid.UUID,
    role_id: uuid.UUID,
    tenant_id: str | None,
    action: str,
    role_domain: str = "tenant",
) -> None:
    """Append an authz audit row (grant/revoke) and emit a metrics counter."""
    s.add(
        m.AuthzEvent(
            actor_id=actor_id,
            subject_user_id=subject_user_id,
            role_id=role_id,
            tenant_id=tenant_id,
            action=action,
        )
    )
    auth_metrics.record_grant(action, role_domain)


def _get_membership(s: Session, membership_id: uuid.UUID) -> m.TenantMembership:
    membership = s.get(m.TenantMembership, membership_id)
    if membership is None:
        raise ValueError(f"unknown membership: {membership_id!r}")
    return membership


def _assert_not_last_admin(
    s: Session, *, tenant_id: str, removing_membership_id: uuid.UUID
) -> None:
    """Enforce the ≥1-admin invariant TOCTOU-safely.

    Locks the ENTIRE admin-assignment set for this tenant (``SELECT ... FOR UPDATE``) so
    concurrent demotions serialize — two simultaneous demotions can't both pass the count,
    which would orphan the tenant.
    """
    admin_role_name = get_settings().admin_role_name
    admin_role_id = s.scalar(select(m.Role.id).where(m.Role.name == admin_role_name))
    if admin_role_id is None:
        # Fail CLOSED: if the configured admin role does not resolve to a seeded role, we
        # cannot evaluate the invariant — refuse rather than degrade to a vacuous count.
        raise RuntimeError(
            f"admin role {admin_role_name!r} is not configured; cannot enforce "
            "the >=1-admin invariant"
        )
    admin_membership_ids = (
        s.execute(
            select(m.TenantRoleAssignment.membership_id)
            .join(
                m.TenantMembership,
                m.TenantRoleAssignment.membership_id == m.TenantMembership.id,
            )
            .where(
                m.TenantMembership.tenant_id == tenant_id,
                m.TenantRoleAssignment.role_id == admin_role_id,
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )
    if (
        removing_membership_id in admin_membership_ids
        and len(admin_membership_ids) <= 1
    ):
        raise LastAdminError(f"cannot remove the last admin of tenant {tenant_id!r}")


def assign_role(
    s: Session, *, membership_id: uuid.UUID, role_name: str, actor_id: uuid.UUID | None
) -> None:
    """Grant a tenant-domain role to a membership (idempotent); record an authz ``grant`` event."""
    role = _resolve_role(s, role_name)
    _require_domain(role, "tenant")
    membership = _get_membership(s, membership_id)

    existing = s.scalar(
        select(m.TenantRoleAssignment).where(
            m.TenantRoleAssignment.membership_id == membership_id,
            m.TenantRoleAssignment.role_id == role.id,
        )
    )
    if existing is None:
        s.add(
            m.TenantRoleAssignment(
                membership_id=membership_id,
                role_id=role.id,
                role_domain="tenant",
            )
        )
        s.flush()
        # Only a NEW assignment is a real state change worth auditing. An idempotent no-op
        # (role already held) records nothing — otherwise an admin could fabricate phantom
        # ``grant`` history via repeated PATCHes.
        _record_event(
            s,
            actor_id=actor_id,
            subject_user_id=membership.user_id,
            role_id=role.id,
            tenant_id=membership.tenant_id,
            action="grant",
            role_domain="tenant",
        )


def revoke_role(
    s: Session, *, membership_id: uuid.UUID, role_name: str, actor_id: uuid.UUID | None
) -> None:
    """Revoke a tenant-domain role from a membership; record an authz ``revoke`` event.

    If the role is the configured admin role, the ≥1-admin invariant is enforced FIRST
    (TOCTOU-safe).
    """
    role = _resolve_role(s, role_name)
    _require_domain(role, "tenant")
    membership = _get_membership(s, membership_id)

    admin_role_name = get_settings().admin_role_name
    if role.name == admin_role_name:
        _assert_not_last_admin(
            s, tenant_id=membership.tenant_id, removing_membership_id=membership_id
        )

    assignment = s.scalar(
        select(m.TenantRoleAssignment).where(
            m.TenantRoleAssignment.membership_id == membership_id,
            m.TenantRoleAssignment.role_id == role.id,
        )
    )
    if assignment is not None:
        s.delete(assignment)
        s.flush()
        # Only a row that actually existed is a real revoke. Revoking a role the membership
        # never held records nothing — no phantom ``revoke`` audit history.
        _record_event(
            s,
            actor_id=actor_id,
            subject_user_id=membership.user_id,
            role_id=role.id,
            tenant_id=membership.tenant_id,
            action="revoke",
            role_domain="tenant",
        )


def change_role(
    s: Session,
    *,
    membership_id: uuid.UUID,
    from_role: str,
    to_role: str,
    actor_id: uuid.UUID | None,
) -> None:
    """Demote/promote a membership: revoke ``from_role`` then assign ``to_role``.

    Because revoke runs first, a demotion away from admin is guarded by the ≥1-admin invariant.
    """
    revoke_role(s, membership_id=membership_id, role_name=from_role, actor_id=actor_id)
    assign_role(s, membership_id=membership_id, role_name=to_role, actor_id=actor_id)


def add_membership(
    s: Session,
    *,
    user_id: uuid.UUID,
    tenant_id: str,
    role_name: str,
    actor_id: uuid.UUID | None,
    invited: bool,
) -> m.TenantMembership:
    """Get-or-create a ``(user_id, tenant_id)`` membership, then assign ``role_name``.

    ``invited=True`` stamps ``invited_at`` (an invited member); ``False`` leaves it NULL
    (a founder).
    """
    membership = s.scalar(
        select(m.TenantMembership).where(
            m.TenantMembership.user_id == user_id,
            m.TenantMembership.tenant_id == tenant_id,
        )
    )
    if membership is None:
        membership = m.TenantMembership(
            user_id=user_id,
            tenant_id=tenant_id,
            invited_at=datetime.now(timezone.utc) if invited else None,
        )
        s.add(membership)
        s.flush()

    assign_role(s, membership_id=membership.id, role_name=role_name, actor_id=actor_id)
    return membership


def remove_member(
    s: Session, *, membership_id: uuid.UUID, actor_id: uuid.UUID | None
) -> None:
    """Remove a membership (assignments CASCADE) and record a ``revoke`` event per held role.

    If the membership holds the admin role, the ≥1-admin invariant is enforced first.
    """
    membership = _get_membership(s, membership_id)

    assignments = list(
        s.scalars(
            select(m.TenantRoleAssignment).where(
                m.TenantRoleAssignment.membership_id == membership_id
            )
        )
    )
    # The membership delete CASCADEs ResourceRoleAssignment rows too — capture them so each
    # gets a revoke AuthzEvent. Without this the resource grant's last audit word is a
    # dangling 'grant' (Layer-2 INV-AUDIT-SUPPRESS-RESOURCE-REVOKE).
    resource_assignments = list(
        s.scalars(
            select(m.ResourceRoleAssignment).where(
                m.ResourceRoleAssignment.membership_id == membership_id
            )
        )
    )

    admin_role_name = get_settings().admin_role_name
    admin_role_id = s.scalar(select(m.Role.id).where(m.Role.name == admin_role_name))
    if admin_role_id is None:
        # Fail CLOSED: a misconfigured admin_role_name (no seeded role matches) must NOT
        # silently skip the >=1-admin guard via the `any(... == None)` short-circuit below
        # (every role_id is non-null, so the check would pass and the last admin become
        # removable). Refuse the removal loudly instead (Layer-2 finding E).
        raise RuntimeError(
            f"admin role {admin_role_name!r} is not configured; refusing member removal "
            "(cannot verify the >=1-admin invariant)"
        )
    if any(a.role_id == admin_role_id for a in assignments):
        _assert_not_last_admin(
            s, tenant_id=membership.tenant_id, removing_membership_id=membership_id
        )

    held_role_ids = [a.role_id for a in assignments]
    resource_role_ids = [a.role_id for a in resource_assignments]
    user_id = membership.user_id
    tenant_id = membership.tenant_id

    s.delete(membership)
    s.flush()

    for role_id in held_role_ids:
        _record_event(
            s,
            actor_id=actor_id,
            subject_user_id=user_id,
            role_id=role_id,
            tenant_id=tenant_id,
            action="revoke",
            role_domain="tenant",
        )
    for role_id in resource_role_ids:
        _record_event(
            s,
            actor_id=actor_id,
            subject_user_id=user_id,
            role_id=role_id,
            tenant_id=tenant_id,
            action="revoke",
            role_domain="resource",
        )


def assign_resource_role(
    s: Session,
    *,
    membership_id: uuid.UUID,
    resource_id: str,
    role_name: str,
    actor_id: uuid.UUID | None,
) -> None:
    """Grant a resource-domain role to a membership ON a resource (idempotent); audit on real change."""
    role = _resolve_role(s, role_name)
    _require_domain(role, "resource")
    membership = _get_membership(s, membership_id)

    existing = s.scalar(
        select(m.ResourceRoleAssignment).where(
            m.ResourceRoleAssignment.membership_id == membership_id,
            m.ResourceRoleAssignment.resource_id == resource_id,
            m.ResourceRoleAssignment.role_id == role.id,
        )
    )
    if existing is None:
        s.add(
            m.ResourceRoleAssignment(
                membership_id=membership_id,
                resource_id=resource_id,
                role_id=role.id,
                role_domain="resource",
            )
        )
        s.flush()
        _record_event(
            s,
            actor_id=actor_id,
            subject_user_id=membership.user_id,
            role_id=role.id,
            tenant_id=membership.tenant_id,
            action="grant",
            role_domain="resource",
        )


def revoke_resource_role(
    s: Session,
    *,
    membership_id: uuid.UUID,
    resource_id: str,
    role_name: str,
    actor_id: uuid.UUID | None,
) -> None:
    """Revoke a resource-domain role on a resource (idempotent); audit on real change."""
    role = _resolve_role(s, role_name)
    _require_domain(role, "resource")
    membership = _get_membership(s, membership_id)

    assignment = s.scalar(
        select(m.ResourceRoleAssignment).where(
            m.ResourceRoleAssignment.membership_id == membership_id,
            m.ResourceRoleAssignment.resource_id == resource_id,
            m.ResourceRoleAssignment.role_id == role.id,
        )
    )
    if assignment is not None:
        s.delete(assignment)
        s.flush()
        _record_event(
            s,
            actor_id=actor_id,
            subject_user_id=membership.user_id,
            role_id=role.id,
            tenant_id=membership.tenant_id,
            action="revoke",
            role_domain="resource",
        )


def add_platform_role(
    s: Session, *, user_id: uuid.UUID, role_name: str, actor_id: uuid.UUID | None
) -> None:
    """Grant a platform-domain role to a user (idempotent); record a platform ``grant`` event.

    De-fork fix (A-F4): ``_record_event`` is INSIDE the ``if existing is None`` block so a
    repeated grant is a true no-op — no phantom audit row. (The reference recorded the event
    unconditionally, writing a second ``grant`` event for every idempotent call.)
    """
    role = _resolve_role(s, role_name)
    _require_domain(role, "platform")

    existing = s.scalar(
        select(m.PlatformRoleAssignment).where(
            m.PlatformRoleAssignment.user_id == user_id,
            m.PlatformRoleAssignment.role_id == role.id,
        )
    )
    if existing is None:
        s.add(
            m.PlatformRoleAssignment(
                user_id=user_id,
                role_id=role.id,
                role_domain="platform",
            )
        )
        s.flush()
        # A-F4: event recorded INSIDE the if-block (idempotent repeat = no phantom audit).
        _record_event(
            s,
            actor_id=actor_id,
            subject_user_id=user_id,
            role_id=role.id,
            tenant_id=None,
            action="grant",
            role_domain="platform",
        )
