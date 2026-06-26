"""Physical per-tenant provisioning (Phase 2 / SP1).

provision_tenant: register the tenant (control row) → [optionally] create + migrate its
physical database → run the post-migrate hook → activate. Idempotent and re-runnable: a
prior partial run is detected by slug and resumed (the physical steps are existence-checked
/ upgrade-no-op). NEVER rolls back a partially-created physical DB — teardown is a lifecycle
concern (SP3). The post-migrate hook is the consumer's seam for tenant-scoped seeding; the
generic battery seeds nothing."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from ...db.control import repository as control_repo
from .dsn import create_database
from .registry import activate_tenant, register_tenant
from .session import invalidate_dsn_cache

logger = logging.getLogger(__name__)

# A post-migrate hook: (control_session, tenant_id, tenant_dsn) -> None.
ProvisionHook = Callable[[Session, str, str], None]


def _noop_hook(control_session: Session, tenant_id: str, tenant_dsn: str) -> None:
    return None


_provision_hook: ProvisionHook = _noop_hook


def register_provision_hook(hook: ProvisionHook | None) -> None:
    """Register a post-migrate provisioning hook (pass None to reset to the no-op default).
    Runs AFTER the tenant DB is created + migrated, BEFORE activation — the place to seed
    tenant-scoped reference data. Call from your own (unlocked) create_app(). This locked
    file must NOT be edited to add seeding; register a hook instead."""
    global _provision_hook
    _provision_hook = hook or _noop_hook


def _project_root() -> Path:
    # src/<pkg>/multitenantauth/tenancy/provision.py → project root is parents[4].
    return Path(__file__).resolve().parents[4]


def migrate_tenant(dsn: str) -> None:
    """Run the APP migration chain to head against a tenant DSN (Python API; env.py honors the
    pre-set sqlalchemy.url, so this targets the tenant DB, not the app DB)."""
    cfg = Config(str(_project_root() / "alembic.ini"))
    # Escape % so stdlib ConfigParser BasicInterpolation cannot raise a ValueError whose
    # message embeds the plaintext DSN + credentials (Layer-2 P1, I-CRED). env.py reads the
    # url via the interpolating get_main_option / get_section, which un-escape %% -> % — so
    # the DSN round-trips intact while the credential can never reach an interpolation error.
    cfg.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
    command.upgrade(cfg, "head")


def provision_tenant(
    control_session: Session,
    name: str,
    *,
    slug: str,
    dsn: str | None = None,
    run_physical: bool = True,
) -> str:
    """Provision a tenant end-to-end; return the opaque tenant id. Idempotent by slug."""
    existing_id = control_repo.live_slug_tenant_id(control_session, slug)
    if existing_id is not None:
        tenant = control_repo.get_tenant(control_session, existing_id)
        if tenant is not None and tenant.status == "active":
            return tenant.id  # already fully provisioned — no-op
        tenant_id = existing_id  # resume a prior partial run
        tenant_dsn = control_repo.get_tenant_dsn(control_session, existing_id) or ""
    else:
        tenant = register_tenant(
            control_session, name, slug=slug, dsn=dsn, status="provisioning"
        )
        control_session.flush()
        tenant_id, tenant_dsn = tenant.id, tenant.dsn

    if run_physical:
        create_database(tenant_dsn)
        migrate_tenant(tenant_dsn)

    _provision_hook(control_session, tenant_id, tenant_dsn)
    activate_tenant(control_session, tenant_id)
    invalidate_dsn_cache(tenant_id)
    return tenant_id
