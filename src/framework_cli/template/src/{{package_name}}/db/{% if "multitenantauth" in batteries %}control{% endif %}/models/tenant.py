"""Tenancy control-plane models: the tenant registry and tenant↔user memberships.

`Tenant.id` is an OPAQUE, IMMUTABLE identifier — the PK, routing key, and Phase-2
per-tenant DB-name key. It is generated, never derived from the slug.

`Tenant.slug` is a MUTABLE, UNIQUE, DNS-label-safe label used for URLs/subdomains
only. A rename updates the slug but NEVER the id or per-tenant DB name.

`TenantSlugHistory` maps retired slugs to their tenant (for 301 redirects) and
holds them in a cooling/reserved window so a rename cannot be immediately squatted.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import ControlBase


def _opaque_id() -> str:
    """Generate a 32-char opaque hex identifier that is safe to use as a DB-name component.

    Produces a string of [0-9a-f] — satisfies the ^[a-z0-9_]+$ CHECK and is guaranteed
    never to equal or be derived from the slug.
    """
    return uuid.uuid4().hex


class Tenant(ControlBase):
    """A client tenant. Its data lives in a dedicated database named after `id`
    (Phase 2). `status` tracks provisioning lifecycle (provisioning→active→suspended).

    `id`   — opaque, immutable; PK and DB-name key. Generated, never from slug.
    `slug` — mutable, unique; DNS-label-safe URL/subdomain label only.
    """

    __tablename__ = "tenant"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_opaque_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    dsn: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # routing key; may carry creds — never log
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenant_slug"),
        # id must be a safe DB-identifier component (Phase-2 CREATE DATABASE).
        CheckConstraint(
            "id ~ '^[a-z0-9_]+$'",
            name="ck_tenant_id_charset",
        ),
        # slug is an RFC-1123 DNS label: [a-z0-9], may contain hyphens (not leading/trailing), ≤63 chars.
        CheckConstraint(
            "slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$' AND char_length(slug) <= 63",
            name="ck_tenant_slug_dns_label",
        ),
        CheckConstraint(
            "status IN ('provisioning', 'active', 'suspended')",
            name="ck_tenant_status",
        ),
    )


class TenantSlugHistory(ControlBase):
    """A retired slug and its tenant mapping.

    When a tenant renames (slug changes), the old slug is inserted here.
    `reserved_until` holds it in a cooling window — a slug is only claimable if it
    is neither a live `tenant.slug` nor a history row whose `reserved_until` is in
    the future. (The claimability rule is enforced at the application layer, not in the DB.)
    """

    __tablename__ = "tenant_slug_history"

    slug: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    retired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_slug_history_tenant", "tenant_id"),)


class TenantMembership(ControlBase):
    """Record of a user's association with a tenant + how they joined (invite provenance). Does NOT
    grant anything — permission comes only from assignments. It also backs the member-management UI."""

    __tablename__ = "tenant_membership"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("app_user.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),
        Index("ix_membership_tenant", "tenant_id"),
        Index("ix_membership_user", "user_id"),
    )
