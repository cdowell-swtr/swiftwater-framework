"""AuthZ control-plane models: roles, permissions, role→permission bundles, tenant/platform/resource
role assignments, and the append-only authz audit. Domain integrity is enforced via the composite FK
`(role_id, role_domain) → role(id, domain)` + a per-table CHECK on `role_domain`."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import ControlBase


class Role(ControlBase):
    """A named bundle of permissions. Built-ins are seeded from code (`is_builtin`, edit/shadow-
    protected); custom roles (e.g. `tenant.steward`) are seeded rows too. `UNIQUE(id, domain)` is the
    target of the assignment tables' composite FK that enforces domain integrity."""

    __tablename__ = "role"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    domain: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # 'tenant'|'platform'|'resource'
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Named to match the migration's `uq_role_name` (was an inline `unique=True`, which
        # autogenerates an anonymous constraint name → alembic check reports drift).
        UniqueConstraint("name", name="uq_role_name"),
        UniqueConstraint("id", "domain", name="uq_role_id_domain"),
        CheckConstraint(
            "domain IN ('tenant', 'platform', 'resource')", name="ck_role_domain"
        ),
    )


class Permission(ControlBase):
    """A `scope:action` grant. The code catalog (`auth/permissions.py`) is the source of truth and is
    materialized here for FK integrity. `is_active` distinguishes live from forward-declared grants."""

    __tablename__ = "permission"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)  # 'tenant:read'
    domain: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    gating_task: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "domain IN ('tenant', 'platform', 'resource')", name="ck_permission_domain"
        ),
    )


class RolePermission(ControlBase):
    """A role↔permission bundle row.

    Cross-domain bundles (e.g. a tenant-domain role carrying a platform permission) are rejected at
    seed-time reconciliation (Task 17), not at the DB level. This is sufficient in Phase 1 because no
    runtime bundle-mutation route ships — bundles are seeded, not API-mutable. A consumer that later
    adds a RolePermission-writing route MUST add a DB-level guard (trigger or CHECK) for this invariant.
    """

    __tablename__ = "role_permission"

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    permission_name: Mapped[str] = mapped_column(
        String(64), ForeignKey("permission.name"), primary_key=True
    )


class TenantRoleAssignment(ControlBase):
    """A role granted within a tenant membership. `role_domain` is pinned to 'tenant' by CHECK and the
    composite FK `(role_id, role_domain) → role(id, domain)` ensures the role is actually tenant-domain
    — so a platform role physically cannot be assigned here."""

    __tablename__ = "tenant_role_assignment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant_membership.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    role_domain: Mapped[str] = mapped_column(
        String(16), nullable=False, default="tenant"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("membership_id", "role_id", name="uq_tra_membership_role"),
        CheckConstraint("role_domain = 'tenant'", name="ck_tra_role_domain"),
        ForeignKeyConstraint(
            ["role_id", "role_domain"],
            ["role.id", "role.domain"],
            name="fk_tra_role_domain",
        ),
        Index("ix_tra_membership", "membership_id"),
    )


class PlatformRoleAssignment(ControlBase):
    """A global platform role granted to a user (subjectless). Symmetric to the tenant assignment;
    `role_domain` pinned to 'platform' by CHECK + composite FK."""

    __tablename__ = "platform_role_assignment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    role_domain: Mapped[str] = mapped_column(
        String(16), nullable=False, default="platform"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_pra_user_role"),
        CheckConstraint("role_domain = 'platform'", name="ck_pra_role_domain"),
        ForeignKeyConstraint(
            ["role_id", "role_domain"],
            ["role.id", "role.domain"],
            name="fk_pra_role_domain",
        ),
        Index("ix_pra_user", "user_id"),
    )


class ResourceRoleAssignment(ControlBase):
    """A resource-domain role granted to a tenant membership ON a specific (opaque) resource id.
    `resource_id` is an opaque scope string (no cross-DB FK) — like `tenant_id`. `role_domain` is
    pinned to 'resource' by CHECK + the composite FK `(role_id, role_domain) → role(id, domain)`,
    so a tenant or platform role physically cannot be assigned at resource grain. A resource grant
    presupposes tenant membership (FK to tenant_membership)."""

    __tablename__ = "resource_role_assignment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenant_membership.id", ondelete="CASCADE"), nullable=False
    )
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    role_domain: Mapped[str] = mapped_column(
        String(16), nullable=False, default="resource"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "membership_id",
            "resource_id",
            "role_id",
            name="uq_rra_membership_resource_role",
        ),
        CheckConstraint("role_domain = 'resource'", name="ck_rra_resource_role_domain"),
        ForeignKeyConstraint(
            ["role_id", "role_domain"],
            ["role.id", "role.domain"],
            name="fk_rra_resource_role_domain",
        ),
        Index("ix_rra_membership", "membership_id"),
        Index("ix_rra_resource", "resource_id"),
    )


class AuthzEvent(ControlBase):
    """Append-only audit of grant/revoke events — the durable system of record for "who granted X".
    `actor_id` NULL ⇒ a system grant (signup founder, seed). `tenant_id` NULL ⇒ a platform grant."""

    __tablename__ = "authz_event"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("app_user.id"))
    subject_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("role.id"), nullable=False
    )
    tenant_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("tenant.id"))
    resource_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # 'grant'|'revoke'
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("action IN ('grant', 'revoke')", name="ck_authz_event_action"),
        Index("ix_authz_event_subject", "subject_user_id"),
        Index("ix_authz_event_tenant_at", "tenant_id", "at"),
    )
