"""Plane-aware migration fan-out (Phase 2 / SP2).

upgrade_all: migrate the control plane (fail-fast), then the default business DB, then every
ACTIVE tenant DB (best-effort) — built on SP1's per-tenant migrate primitive. A single
`alembic upgrade head` migrates only one plane; this reaches all three. Returns a per-target
result map; values are exception CLASS names only (never a DSN/credential). Sequential and
idempotent (every step is `upgrade head`).

Invoked at boot / pre-roll as a module: ``python -m <your_package>.multitenantauth.tenancy.migrate``.
This file is integrity-LOCKED mechanism."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import cast

from alembic import command
from alembic.config import Config

from ...db.control.engine import control_session_factory
from ...db.control.repository import active_tenant_dsns
from .provision import migrate_tenant

# active_tenant_dsns / migrate_tenant / control_session_factory are imported as module-level
# names (not called via a `repo.`/module qualifier) so the unit test can monkeypatch them on
# this module: `monkeypatch.setattr(migrate, "active_tenant_dsns", ...)` only rebinds the
# module-level name, never an attribute reached through a qualifier.

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    # src/<pkg>/multitenantauth/tenancy/migrate.py → project root is parents[4].
    return Path(__file__).resolve().parents[4]


def _upgrade_control() -> None:
    """Upgrade the CONTROL chain to head. control env.py always points at control_database_url,
    so no url injection is needed here."""
    command.upgrade(Config(str(_project_root() / "alembic_control.ini")), "head")


def _upgrade_default() -> None:
    """Upgrade the APP chain to head against the default business DB. app env.py falls back to
    database_url when no sqlalchemy.url is injected, so a plain upgrade targets the default DB."""
    command.upgrade(Config(str(_project_root() / "alembic.ini")), "head")


def upgrade_all() -> dict[str, object]:
    """Control-first → default DB → active-tenant fan-out. See module docstring."""
    report: dict[str, object] = {"control": None, "default": None, "tenants": {}}

    # Control plane FIRST, fail-fast: the registry that enumerates tenants lives here.
    try:
        _upgrade_control()
        report["control"] = "ok"
    except Exception as exc:  # noqa: BLE001 — record class name, abort, never leak the message
        report["control"] = type(exc).__name__
        logger.error("migrate.control.failed error=%s", type(exc).__name__)
        return report  # do NOT touch any tenant on a broken control plane

    # Default business DB (independent of tenants — record, do not abort the fan-out).
    try:
        _upgrade_default()
        report["default"] = "ok"
    except Exception as exc:  # noqa: BLE001
        report["default"] = type(exc).__name__
        logger.error("migrate.default.failed error=%s", type(exc).__name__)

    # Enumerate the active-tenant fan-out targets. This is a CONTROL-plane read; if it fails we
    # cannot know the targets, so treat it as a control-plane failure (fail-fast, no tenant
    # touched) rather than letting upgrade_all raise and break its dict contract. Class name
    # only — never leak the query or a DSN.
    try:
        with control_session_factory()() as cs:
            targets = active_tenant_dsns(cs)
    except Exception as exc:  # noqa: BLE001
        report["control"] = type(exc).__name__
        logger.error("migrate.tenant_enumeration.failed error=%s", type(exc).__name__)
        return report

    # Tenant fan-out, best-effort.
    tenants: dict[str, str] = {}
    for tenant_id, dsn in targets:
        try:
            migrate_tenant(dsn)
            tenants[tenant_id] = "ok"
        except Exception as exc:  # noqa: BLE001
            tenants[tenant_id] = type(exc).__name__
            logger.warning(
                "migrate.tenant.failed tenant_id=%s error=%s",
                tenant_id,
                type(exc).__name__,
            )
    report["tenants"] = tenants
    return report


def report_failed(report: dict[str, object]) -> list[str]:
    """Target labels that did not migrate (control/default that ran-and-failed, or any tenant).
    A None default means control aborted before the default was reached — already a failure."""
    failed: list[str] = []
    if report["control"] != "ok":
        failed.append("control")
    if report["default"] not in ("ok", None):
        failed.append("default")
    tenants = cast("dict[str, str]", report["tenants"])  # always a dict
    failed.extend(t for t, v in tenants.items() if v != "ok")
    return failed


def main() -> int:
    report = upgrade_all()
    print(json.dumps(report))
    failed = report_failed(report)
    if failed:
        print(f"migrate failed for: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
