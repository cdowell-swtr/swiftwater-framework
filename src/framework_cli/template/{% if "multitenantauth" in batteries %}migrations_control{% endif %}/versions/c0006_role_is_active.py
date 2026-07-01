"""add role.is_active for authz catalog soft reaping

Revision ID: c0006
Revises: c0005
Create Date: 2026-07-01

Adds a non-null `role.is_active` flag so seed_authz can deactivate roles that
disappear from the in-code catalog without hard-deleting role rows or historical
assignments. Existing roles are live by default; later seed runs own deactivation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0006"
down_revision = "c0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "role",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("role", "is_active")
