"""Per-tenant DSN derivation + idempotent database creation (SP1).

A tenant's database is co-located with the app instance (settings.database_url) by default,
named "<tenant_db_name_prefix>_<tenant_id>"; the full DSN is recorded on the Tenant row and
is the routing key. Granularity is DSN-pluggable — a tenant can later move to a dedicated
instance by changing only its stored DSN (a bring-your-own-DSN provision skips this module)."""

from __future__ import annotations

from sqlalchemy import create_engine, make_url, text

from ...config.settings import get_settings


def default_tenant_dsn(tenant_id: str) -> str:
    """Derive a tenant DB DSN from the app URL by swapping the database name. tenant_id is
    already constrained to ^[a-z0-9_]+$ by the registry, so it is a safe identifier component."""
    settings = get_settings()
    base = make_url(settings.database_url)
    name = f"{settings.tenant_db_name_prefix}_{tenant_id}"
    return base.set(database=name).render_as_string(hide_password=False)


def create_database(dsn: str) -> None:
    """Idempotently CREATE DATABASE for `dsn`, connecting to the instance's `postgres`
    maintenance db with AUTOCOMMIT (CREATE DATABASE cannot run inside a transaction)."""
    url = make_url(dsn)
    dbname = url.database
    maint = create_engine(
        url.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with maint.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        maint.dispose()
