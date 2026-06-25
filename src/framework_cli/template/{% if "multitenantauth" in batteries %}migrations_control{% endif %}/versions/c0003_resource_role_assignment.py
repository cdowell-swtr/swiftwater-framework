"""control plane — resource_role_assignment (expand-only)

Revision ID: c0003
Revises: c0002
Create Date: 2026-06-24

Adds `resource_role_assignment`: a resource-domain role granted to a tenant membership ON a
specific opaque resource_id. Clones the tenant/platform assignment domain-integrity idiom:
role_domain pinned to 'resource' by CHECK + composite FK (role_id, role_domain) → role(id, domain).
resource_id is an opaque scope string (no cross-DB FK). Additive only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0003"
down_revision = "c0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_role_assignment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role_domain",
            sa.String(length=16),
            nullable=False,
            server_default="resource",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["tenant_membership.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_id", "role_domain"],
            ["role.id", "role.domain"],
            name="fk_rra_resource_role_domain",
        ),
        sa.UniqueConstraint(
            "membership_id",
            "resource_id",
            "role_id",
            name="uq_rra_membership_resource_role",
        ),
        sa.CheckConstraint(
            "role_domain = 'resource'", name="ck_rra_resource_role_domain"
        ),
    )
    op.create_index("ix_rra_membership", "resource_role_assignment", ["membership_id"])
    op.create_index("ix_rra_resource", "resource_role_assignment", ["resource_id"])


def downgrade() -> None:
    op.drop_index("ix_rra_resource", table_name="resource_role_assignment")
    op.drop_index("ix_rra_membership", table_name="resource_role_assignment")
    op.drop_table("resource_role_assignment")
