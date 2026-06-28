"""add tenant_lifecycle_event audit table

Revision ID: c0005
Revises: c0004
Create Date: 2026-06-27

Adds the append-only `tenant_lifecycle_event` table for auditing tenant-lifecycle
mutations (suspend/reactivate/rename). `actor_id` is nullable (NULL = system/operator
action). An explicit CHECK constraint on `action` prevents invalid values at the DB layer.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0005"
down_revision = "c0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_lifecycle_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('suspend', 'reactivate', 'rename')",
            name="ck_tle_action",
        ),
    )
    op.create_index("ix_tle_tenant_at", "tenant_lifecycle_event", ["tenant_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_tle_tenant_at", table_name="tenant_lifecycle_event")
    op.drop_table("tenant_lifecycle_event")
