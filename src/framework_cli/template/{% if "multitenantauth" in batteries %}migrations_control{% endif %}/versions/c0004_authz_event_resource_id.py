"""add authz_event.resource_id

Revision ID: c0004
Revises: c0003
Create Date: 2026-06-27

Adds a nullable `resource_id` column to `authz_event` so that resource-grant and
resource-revoke events record WHICH resource the role was granted on. Tenant and
platform events leave `resource_id` NULL by construction. Additive, expand-only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0004"
down_revision = "c0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "authz_event",
        sa.Column("resource_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("authz_event", "resource_id")
