"""control plane — tenant registry

Revision ID: c0001
Revises:
Create Date: 2026-06-24

Creates the tenant registry tables: `tenant` (opaque id + mutable slug + status lifecycle)
and `tenant_slug_history` (retired slug cooling window for 301 redirects). `tenant_membership`
is created in c0002 because it carries FKs to `app_user` which doesn't exist yet.
"""

import sqlalchemy as sa

from alembic import op

revision = "c0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column("dsn", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_tenant_slug"),
        sa.CheckConstraint(
            "id ~ '^[a-z0-9_]+$'",
            name="ck_tenant_id_charset",
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$' AND char_length(slug) <= 63",
            name="ck_tenant_slug_dns_label",
        ),
        sa.CheckConstraint(
            "status IN ('provisioning', 'active', 'suspended')",
            name="ck_tenant_status",
        ),
    )

    op.create_table(
        "tenant_slug_history",
        sa.Column("slug", sa.String(length=255), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "retired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_slug_history_tenant", "tenant_slug_history", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_slug_history_tenant", table_name="tenant_slug_history")
    op.drop_table("tenant_slug_history")
    op.drop_table("tenant")
