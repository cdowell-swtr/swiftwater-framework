"""Seed the authorization vocabulary (permissions + roles + bundles) into the control plane.

This file is MECHANISM — do not edit; it is managed by the framework. The consumer-editable
POLICY is the catalog in ``authz/permissions.py`` (permissions) and ``authz/roles.py`` (role
bundles); this runner only materializes what those declare. Change the policy there, not here.

The code catalog (``authz/permissions.py``) and role bundles (``authz/roles.py``) are the
source of truth. This module materializes them so the control DB's foreign keys have rows
to point at. It seeds the VOCABULARY only — NOT user grants (those become ``authz_event``
rows when a user is actually granted a role, in later operations).

``seed_authz`` is designed to run at startup across several app replicas concurrently, so it
must be both idempotent and race-safe: it uses Postgres upserts (INSERT ... ON CONFLICT),
never SELECT-then-INSERT. The caller owns the transaction boundary (this function does not
commit).

**Reconciliation:**

``reconcile_authz`` validates the in-code bundle definitions against the materialized
permissions. It is called by ``seed_authz`` at the end of every seed run. Two invariants
are enforced:

1. Every permission name referenced in a bundle must exist AND be live (``is_active=True``)
   in the DB.
2. A role's bundle must contain only permissions from the same domain as the role
   (cross-domain guard — MDN48).

The reconciliation accepts the bundle definitions as parameters (defaulting to the real
catalog) so tests can inject bad bundles without triggering DB FK violations.

Entry point::

    python -m <package_name>.multitenantauth.authz.seed

"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ...db.control import models as m
from ...db.control.engine import control_engine
from ...logging_config import get_logger
from .permissions import CATALOG
from .roles import BUILTIN_BUNDLES, BUILTIN_DOMAINS, CUSTOM_DB_ROLES

_log = get_logger()


def _seed_role(
    session: Session,
    *,
    name: str,
    domain: str,
    description: str,
    is_builtin: bool,
    grants: set[str],
) -> None:
    """Upsert one role + its bundle rows.

    Race-safe: ON CONFLICT DO NOTHING on the role's unique ``name``, then re-read
    the surviving row's id to attach bundle rows (the id we proposed may have lost
    the race, so we never assume ours won).
    """
    session.execute(
        pg_insert(m.Role)
        .values(
            id=uuid4(),
            name=name,
            domain=domain,
            description=description,
            is_builtin=is_builtin,
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={
                "description": description,
                "is_builtin": is_builtin,
                "is_active": True,
            },
        )
    )
    role_id = session.scalar(select(m.Role.id).where(m.Role.name == name))
    for perm in grants:
        session.execute(
            pg_insert(m.RolePermission)
            .values(role_id=role_id, permission_name=perm)
            .on_conflict_do_nothing()
        )


def reconcile_authz(
    session: Session,
    *,
    bundles: dict[str, set[str]] | None = None,
    domains: dict[str, str] | None = None,
    custom: dict[str, dict] | None = None,
) -> None:
    """Validate the in-code bundle definitions against the materialized permissions.

    Accepts bundle/domain/custom definitions as parameters (defaulting to the real catalog
    constants) so callers — including tests — can inject bad bundles without inserting invalid
    DB rows that would be rejected by the ``role_permission.permission_name`` FK.

    Raises ``RuntimeError`` if either invariant is violated:

    1. **Unknown or inactive permission**: a bundled permission name is absent from the DB
       or has ``is_active=False``.
    2. **Cross-domain bundle** (MDN48): a role's grant set contains a permission from a
       different domain than the role itself.
    """
    _bundles = bundles if bundles is not None else BUILTIN_BUNDLES
    _domains = domains if domains is not None else BUILTIN_DOMAINS
    _custom_roles = custom if custom is not None else CUSTOM_DB_ROLES

    # Build a name → Permission row map from the materialized catalog.
    perm_map: dict[str, m.Permission] = {
        p.name: p for p in session.scalars(select(m.Permission))
    }

    def _check_bundle(role_name: str, role_domain: str, grants: set[str]) -> None:
        for perm_name in grants:
            perm = perm_map.get(perm_name)
            if perm is None or not perm.is_active:
                raise RuntimeError(
                    f"role {role_name!r} bundles permission {perm_name!r} which is "
                    f"{'unknown' if perm is None else 'inactive (forward-declared)'} — "
                    "only live permissions may be bundled"
                )
            if perm.domain != role_domain:
                raise RuntimeError(
                    f"cross-domain bundle: role {role_name!r} is domain {role_domain!r} "
                    f"but bundles permission {perm_name!r} (domain {perm.domain!r}) — "
                    "a role may only bundle permissions from its own domain (MDN48)"
                )

    for role_name, grants in _bundles.items():
        role_domain = _domains.get(role_name, "")
        _check_bundle(role_name, role_domain, grants)

    for role_name, spec in _custom_roles.items():
        role_domain = spec.get("domain", "")
        custom_grants: set[str] = spec.get("grants", set())
        _check_bundle(role_name, role_domain, custom_grants)


def seed_authz(session: Session) -> None:
    """Materialize the permission catalog, built-in roles, and custom DB roles into the control plane.

    Idempotent and multi-replica-race-safe via Postgres upserts. Permissions DO UPDATE so the
    table tracks code (e.g. an ``is_active`` flip); roles/bundles DO NOTHING (their identity is
    stable). Does NOT commit — the caller owns the transaction.

    Raises ``ValueError`` if ``CUSTOM_DB_ROLES`` shadows a built-in role name.
    Raises ``RuntimeError`` (via ``reconcile_authz``) if the bundle definitions are invalid.
    """
    # Shadow guard: a custom DB role must never shadow a built-in name.
    shadowed = set(CUSTOM_DB_ROLES) & set(BUILTIN_BUNDLES)
    if shadowed:
        raise ValueError(f"custom DB roles shadow built-in roles: {shadowed}")

    active_permission_names = {perm.name for perm in CATALOG}
    active_role_names = set(BUILTIN_BUNDLES) | set(CUSTOM_DB_ROLES)

    # Permissions — DO UPDATE so the table stays synced with the code catalog.
    for perm in CATALOG:
        session.execute(
            pg_insert(m.Permission)
            .values(
                name=perm.name,
                domain=perm.domain,
                description=perm.description,
                gating_task=perm.gating_task,
                is_active=perm.is_active,
            )
            .on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "domain": perm.domain,
                    "description": perm.description,
                    "gating_task": perm.gating_task,
                    "is_active": perm.is_active,
                },
            )
        )
    session.execute(
        update(m.Permission)
        .where(m.Permission.name.not_in(active_permission_names))
        .values(is_active=False)
    )

    # Built-in roles (seeded from code; edit/shadow-protected).
    for name, domain in BUILTIN_DOMAINS.items():
        _seed_role(
            session,
            name=name,
            domain=domain,
            description=name,
            is_builtin=True,
            grants=BUILTIN_BUNDLES[name],
        )

    # Custom DB roles (prove the extension seam; not built-in).
    for name, spec in CUSTOM_DB_ROLES.items():
        _seed_role(
            session,
            name=name,
            domain=spec["domain"],
            description=spec["description"],
            is_builtin=False,
            grants=spec["grants"],
        )
    session.execute(
        update(m.Role)
        .where(m.Role.name.not_in(active_role_names))
        .values(is_active=False)
    )

    _log.info(
        "authz.seed.complete",
        permissions=len(CATALOG),
        builtin_roles=len(BUILTIN_DOMAINS),
        custom_roles=len(CUSTOM_DB_ROLES),
    )

    # Reconcile bundle definitions against the materialized permissions.
    reconcile_authz(session)


def main() -> None:  # pragma: no cover
    """Seed the authz vocabulary into the control DB.

    Invoked by: ``python -m <package_name>.multitenantauth.authz.seed``

    The module-level entrypoint for the deferred Task 8 ``python -m <pkg>.authz.seed``
    call. Opens a control session, runs ``seed_authz``, and commits.
    """
    with Session(control_engine()) as session:
        seed_authz(session)
        session.commit()
    _log.info("authz.seed.main.done")


if __name__ == "__main__":
    main()
