"""Control-plane reads/writes: the tenant registry and slug history.

All operations are session-scoped: callers own the session lifecycle
(begin/commit/rollback). Never connects to a tenant dsn — routing-agnostic.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models.tenant import Tenant, TenantSlugHistory


def add_tenant(
    session: Session,
    *,
    id: str,
    name: str,
    slug: str,
    dsn: str,
    status: str = "provisioning",
) -> Tenant:
    """Insert a new tenant row and return it (caller must commit)."""
    t = Tenant(id=id, name=name, slug=slug, dsn=dsn, status=status)
    session.add(t)
    session.flush()  # populate server defaults without committing
    return t


def get_tenant(session: Session, tenant_id: str) -> Tenant | None:
    """Return the Tenant with this id, or None if not found."""
    return session.get(Tenant, tenant_id)


def get_tenant_dsn(session: Session, tenant_id: str) -> str | None:
    """Return only the DSN string for a tenant (avoids loading the full row)."""
    row = session.execute(
        select(Tenant.dsn).where(Tenant.id == tenant_id)
    ).scalar_one_or_none()
    return row


def active_tenant_dsns(session: Session) -> list[tuple[str, str]]:
    """Return (tenant_id, dsn) for every active tenant — the migrate fan-out target set.

    Active-only by design: a ``provisioning`` tenant has no committed schema contract yet,
    and ``suspended`` is an SP3 lifecycle concern. Returns the stored control-row DSN — this
    is an operator/boot path, not a request path, so it deliberately does NOT go through the
    request-scoped ``resolve_dsn`` seam.
    """
    rows = session.execute(
        select(Tenant.id, Tenant.dsn).where(Tenant.status == "active")
    ).all()
    return [(row.id, row.dsn) for row in rows]


def live_slug_tenant_id(session: Session, slug: str) -> str | None:
    """Return the tenant_id for a live (current) slug, or None if not found."""
    return session.execute(
        select(Tenant.id).where(Tenant.slug == slug)
    ).scalar_one_or_none()


def get_slug_history(session: Session, slug: str) -> TenantSlugHistory | None:
    """Return the TenantSlugHistory row for this slug, or None."""
    return session.get(TenantSlugHistory, slug)


def add_slug_history(
    session: Session,
    *,
    slug: str,
    tenant_id: str,
    reserved_until: datetime,
) -> TenantSlugHistory:
    """Upsert a retired-slug history row (caller must commit).

    ``slug`` is the sole primary key, so a slug that is reclaimed and later
    retired again must update the existing row in place rather than blind-insert
    (which would raise IntegrityError on the PK collision).
    """
    existing = session.get(TenantSlugHistory, slug)
    if existing is not None:
        existing.tenant_id = tenant_id
        existing.reserved_until = reserved_until
        session.flush()
        return existing
    hist = TenantSlugHistory(
        slug=slug,
        tenant_id=tenant_id,
        reserved_until=reserved_until,
    )
    session.add(hist)
    session.flush()
    return hist


def is_slug_cooling(session: Session, slug: str) -> bool:
    """Return True if this slug is in a cooling window (reserved_until > now)."""
    row = get_slug_history(session, slug)
    if row is None:
        return False
    if row.reserved_until is None:
        return False
    return row.reserved_until > datetime.now(timezone.utc)


def delete_slug_history(session: Session, slug: str) -> None:
    """Delete a TenantSlugHistory row by slug if present (lazy-delete on reclaim). Caller commits."""
    row = session.get(TenantSlugHistory, slug)
    if row is not None:
        session.delete(row)
        session.flush()
