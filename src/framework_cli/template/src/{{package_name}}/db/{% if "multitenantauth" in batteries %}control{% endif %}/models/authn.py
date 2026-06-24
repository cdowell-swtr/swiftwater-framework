"""AuthN control-plane models: login identities, server-side sessions, single-use invite tokens."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base import ControlBase


class AppUser(ControlBase):
    """A login identity. `email_canonical` is the uniqueness key (always lowercase — CHECK-enforced);
    `email` preserves the as-entered form for display/delivery. `password_hash` is NULL until set
    (invited users). Account birth is recorded positively by `born` ('signup' ⟺ `signed_up_at` set),
    so the platform-level signup-xor-invite is a real constraint, not an inferred NULL."""

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_canonical: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    hash_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    born: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # 'signup'|'invite'|'operator'
    signed_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("email_canonical", name="uq_app_user_email_canonical"),
        CheckConstraint(
            "email_canonical = lower(email_canonical)", name="ck_app_user_email_lower"
        ),
        CheckConstraint(
            "born IN ('signup', 'invite', 'operator')", name="ck_app_user_born"
        ),
        CheckConstraint(
            "(born = 'signup') = (signed_up_at IS NOT NULL)",
            name="ck_app_user_born_signup",
        ),
    )


class Session(ControlBase):
    """An opaque server-side session — identity only, NEVER tenant-bound. `token_hash` is
    HMAC(token, session_pepper); the row IS the credential. Expiry is checked at read time."""

    __tablename__ = "session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_session_user", "user_id"),
        Index("ix_session_expires", "expires_at"),
    )


class InviteToken(ControlBase):
    """A single-use invite/set-password token. `membership_id` (nullable) names the tenant being
    joined; redemption sets the password if absent, stamps the membership's `accepted_at`, and marks
    `used_at`. Operator-created platform users have a NULL `membership_id`."""

    __tablename__ = "invite_token"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenant_membership.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_invite_user", "user_id"),)
