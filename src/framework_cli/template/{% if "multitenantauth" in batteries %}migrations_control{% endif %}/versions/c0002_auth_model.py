"""control plane — auth / RBAC model

Revision ID: c0002
Revises: c0001
Create Date: 2026-06-24

Expand-only, additive. Adds the auth/RBAC tables: app_user, role, permission, role_permission,
tenant_membership, tenant_role_assignment, platform_role_assignment, authz_event, session,
invite_token.

Note on domain values: `ck_role_domain` and `ck_permission_domain` allow
('tenant', 'platform', 'resource') — 'product' is intentionally excluded (generic battery).

NOTE: downgrade() drops these tables in FK-topological order (children before parents). It
exists for the guard and for dev; it must NEVER be run against an environment with real users /
sessions / audit (irreversible customer-data loss) — roll back by deploying prior code.
"""

import sqlalchemy as sa

from alembic import op

revision = "c0002"
down_revision = "c0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_canonical", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("hash_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("born", sa.String(length=16), nullable=False),
        sa.Column("signed_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("email_canonical", name="uq_app_user_email_canonical"),
        sa.CheckConstraint(
            "email_canonical = lower(email_canonical)", name="ck_app_user_email_lower"
        ),
        sa.CheckConstraint(
            "born IN ('signup', 'invite', 'operator')", name="ck_app_user_born"
        ),
        sa.CheckConstraint(
            "(born = 'signup') = (signed_up_at IS NOT NULL)",
            name="ck_app_user_born_signup",
        ),
    )

    op.create_table(
        "role",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_role_name"),
        sa.UniqueConstraint("id", "domain", name="uq_role_id_domain"),
        sa.CheckConstraint(
            "domain IN ('tenant', 'platform', 'resource')", name="ck_role_domain"
        ),
    )

    op.create_table(
        "permission",
        sa.Column("name", sa.String(length=64), primary_key=True),
        sa.Column("domain", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("gating_task", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "domain IN ('tenant', 'platform', 'resource')", name="ck_permission_domain"
        ),
    )

    op.create_table(
        "role_permission",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_name", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_name"], ["permission.name"]),
        sa.PrimaryKeyConstraint("role_id", "permission_name"),
    )

    op.create_table(
        "tenant_membership",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["app_user.id"]),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),
    )
    op.create_index("ix_membership_tenant", "tenant_membership", ["tenant_id"])
    op.create_index("ix_membership_user", "tenant_membership", ["user_id"])

    op.create_table(
        "tenant_role_assignment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role_domain", sa.String(length=16), nullable=False, server_default="tenant"
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
            name="fk_tra_role_domain",
        ),
        sa.UniqueConstraint("membership_id", "role_id", name="uq_tra_membership_role"),
        sa.CheckConstraint("role_domain = 'tenant'", name="ck_tra_role_domain"),
    )
    op.create_index("ix_tra_membership", "tenant_role_assignment", ["membership_id"])

    op.create_table(
        "platform_role_assignment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role_domain",
            sa.String(length=16),
            nullable=False,
            server_default="platform",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["role_id", "role_domain"],
            ["role.id", "role.domain"],
            name="fk_pra_role_domain",
        ),
        sa.UniqueConstraint("user_id", "role_id", name="uq_pra_user_role"),
        sa.CheckConstraint("role_domain = 'platform'", name="ck_pra_role_domain"),
    )
    op.create_index("ix_pra_user", "platform_role_assignment", ["user_id"])

    op.create_table(
        "authz_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("subject_user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["subject_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.CheckConstraint(
            "action IN ('grant', 'revoke')", name="ck_authz_event_action"
        ),
    )
    op.create_index("ix_authz_event_subject", "authz_event", ["subject_user_id"])
    op.create_index("ix_authz_event_tenant_at", "authz_event", ["tenant_id", "at"])

    op.create_table(
        "session",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_session_user", "session", ["user_id"])
    op.create_index("ix_session_expires", "session", ["expires_at"])

    op.create_table(
        "invite_token",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["app_user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["tenant_membership.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_invite_user", "invite_token", ["user_id"])


def downgrade() -> None:
    # FK-topological order: drop children before parents. NEVER run with real auth data present.
    op.drop_index("ix_invite_user", table_name="invite_token")
    op.drop_table("invite_token")
    op.drop_index("ix_session_expires", table_name="session")
    op.drop_index("ix_session_user", table_name="session")
    op.drop_table("session")
    op.drop_index("ix_authz_event_tenant_at", table_name="authz_event")
    op.drop_index("ix_authz_event_subject", table_name="authz_event")
    op.drop_table("authz_event")
    op.drop_index("ix_pra_user", table_name="platform_role_assignment")
    op.drop_table("platform_role_assignment")
    op.drop_index("ix_tra_membership", table_name="tenant_role_assignment")
    op.drop_table("tenant_role_assignment")
    op.drop_index("ix_membership_user", table_name="tenant_membership")
    op.drop_index("ix_membership_tenant", table_name="tenant_membership")
    op.drop_table("tenant_membership")
    op.drop_table("role_permission")
    op.drop_table("permission")
    op.drop_table("role")
    op.drop_table("app_user")
