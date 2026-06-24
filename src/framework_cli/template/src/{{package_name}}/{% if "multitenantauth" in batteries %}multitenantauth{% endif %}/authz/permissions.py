"""The permission catalog — the SOURCE OF TRUTH for authorization vocabulary.

This file ships INTENTIONALLY_UNLOCKED: it is the policy layer, not framework
infrastructure. Consumers are expected and encouraged to replace this example
catalog with their own domain vocabulary before going to production.

The catalog is materialized into the ``permission`` table (by ``seed.py``) with a
reconciliation check that guards against cross-domain bundles.

Enforcement code references these names directly (e.g. ``Perm("tenant:read", ...)``).
Adding a new permission here + running ``seed.py`` is sufficient to make it available
to the resolution engine.

**Example catalog (starter set — replace with your domain vocabulary):**

``tenant`` domain
    tenant:read                  Read tenant resources (memberships, metadata).
    tenant:manage-members        Invite, grant, and revoke tenant membership roles.

``platform`` domain
    platform:provision-tenant    Provision a new tenant. Required by POST /tenants
                                 (Task 16a). A platform-wide operation — requires a
                                 ``platform.admin`` role assignment, never a tenant one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermDef:
    name: str
    domain: str  # 'tenant' | 'platform' | 'resource'
    description: str
    is_active: bool
    gating_task: str | None = None


# ── Catalog ────────────────────────────────────────────────────────────────────
#
# Replace this example catalog with your own domain vocabulary.
# Constraints:
#   - ``name`` must be globally unique and follow ``<scope>:<action>`` convention.
#   - ``domain`` must be one of 'tenant', 'platform', or 'resource'.
#   - ``is_active=False`` marks a forward-declared (not yet live) permission; no
#     role bundle may reference an inactive permission (reconciliation will raise).
#   - Run ``seed.py`` after any catalog change to materialize it into the DB.

CATALOG: tuple[PermDef, ...] = (
    # tenant-domain permissions (live)
    PermDef("tenant:read", "tenant", "Read tenant resources", True),
    PermDef(
        "tenant:manage-members",
        "tenant",
        "Invite/grant/revoke tenant members",
        True,
    ),
    # platform-domain permissions (live)
    # Required by: POST /tenants (Task 16a — platform:provision-tenant guard)
    PermDef("platform:provision-tenant", "platform", "Provision a new tenant", True),
)

ALL_NAMES: frozenset[str] = frozenset(d.name for d in CATALOG)
LIVE_NAMES: frozenset[str] = frozenset(d.name for d in CATALOG if d.is_active)
