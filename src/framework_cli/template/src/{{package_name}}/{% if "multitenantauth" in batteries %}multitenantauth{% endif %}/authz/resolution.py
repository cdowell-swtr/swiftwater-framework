"""Resolve a user's effective permissions, SPLIT BY DOMAIN. tenant grants apply only to their tenant;
platform grants are global. The split lets the evaluator (``expr.evaluate``) ensure a platform grant
can never satisfy a tenant-scoped leaf and vice-versa."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.control import models as m


def _perms_for_roles(s: Session, role_ids: set[uuid.UUID]) -> set[str]:
    if not role_ids:
        return set()
    return set(
        s.scalars(
            select(m.RolePermission.permission_name).where(
                m.RolePermission.role_id.in_(role_ids)
            )
        )
    )


def platform_permissions(s: Session, user_id: uuid.UUID) -> set[str]:
    role_ids = set(
        s.scalars(
            select(m.PlatformRoleAssignment.role_id).where(
                m.PlatformRoleAssignment.user_id == user_id
            )
        )
    )
    return _perms_for_roles(s, role_ids)


def tenant_permissions(s: Session, user_id: uuid.UUID, tenant_id: str) -> set[str]:
    role_ids = set(
        s.scalars(
            select(m.TenantRoleAssignment.role_id)
            .join(
                m.TenantMembership,
                m.TenantRoleAssignment.membership_id == m.TenantMembership.id,
            )
            .where(
                m.TenantMembership.user_id == user_id,
                m.TenantMembership.tenant_id == tenant_id,
            )
        )
    )
    return _perms_for_roles(s, role_ids)


def effective_permissions(
    s: Session, user_id: uuid.UUID, tenant_id: str | None
) -> set[str]:
    if tenant_id is None:
        raise ValueError(
            "tenant_id is required; use platform_permissions/effective_permissions_global "
            "for non-tenant checks"
        )
    return platform_permissions(s, user_id) | tenant_permissions(s, user_id, tenant_id)


def effective_permissions_global(s: Session, user_id: uuid.UUID) -> set[str]:
    return platform_permissions(s, user_id)


def has_membership(s: Session, user_id: uuid.UUID, tenant_id: str) -> bool:
    return (
        s.scalar(
            select(m.TenantMembership.id)
            .where(
                m.TenantMembership.user_id == user_id,
                m.TenantMembership.tenant_id == tenant_id,
            )
            .limit(1)
        )
        is not None
    )
