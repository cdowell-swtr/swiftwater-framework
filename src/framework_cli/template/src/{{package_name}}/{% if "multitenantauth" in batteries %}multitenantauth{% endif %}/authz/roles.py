"""Role → permission bundles for the authorization seed catalog.

This file is consumer-editable POLICY — edit this catalog. It ships
INTENTIONALLY_UNLOCKED (the framework will not lock or overwrite it): it is the
policy layer, not framework infrastructure. Consumers should replace the built-in
set with their own role taxonomy before going to production. (The seed runner
``authz/seed.py`` that materializes this is mechanism — do not edit that; change the
policy here.)

**Built-in roles (seeded with ``is_builtin=True``):**

  tenant.admin    Tenant admin: full tenant read + member management.
  tenant.member   Tenant member: read-only access.
  platform.admin  Platform operator: can provision tenants.

Built-ins are idempotent on re-seed (ON CONFLICT DO NOTHING on role.name) and
are never deleted by the framework. A consumer that wants to rename or remove a
built-in should do so via a data migration, not by editing this file after go-live.

**Custom DB roles (``CUSTOM_DB_ROLES``) — the extension seam:**

Custom roles live in the DB too, but are seeded with ``is_builtin=False``. This
proves the extension seam: a consumer adds a new role to ``CUSTOM_DB_ROLES`` here
and it will be seeded on next startup without writing migration SQL. The domain and
grant set are checked by reconciliation — cross-domain bundles are rejected at
seed time, not silently persisted.

``CUSTOM_DB_ROLES`` names must never shadow a built-in name (``seed.py`` will raise
at startup if a collision is detected).
"""

from __future__ import annotations

# ── Built-in roles ─────────────────────────────────────────────────────────────
#
# Keys must match an entry in BUILTIN_DOMAINS.
# Grants must be a subset of LIVE_NAMES from permissions.py (reconciliation
# enforces this; a bundle referencing an unknown or inactive permission raises).

BUILTIN_BUNDLES: dict[str, set[str]] = {
    "tenant.admin": {"tenant:read", "tenant:manage-members"},
    "tenant.member": {"tenant:read"},
    "platform.admin": {"platform:provision-tenant"},
}

# Maps each built-in role name to its domain ('tenant' | 'platform' | 'resource').
# The reconciliation cross-domain guard uses this: a 'tenant' role must bundle only
# 'tenant' permissions; a 'platform' role only 'platform' permissions.

BUILTIN_DOMAINS: dict[str, str] = {
    "tenant.admin": "tenant",
    "tenant.member": "tenant",
    "platform.admin": "platform",
}

# ── Custom DB roles — extension seam ──────────────────────────────────────────
#
# Add your own roles here. Each entry will be seeded with ``is_builtin=False``.
# The name must not collide with any key in BUILTIN_BUNDLES (seed.py enforces
# this at startup). Same cross-domain rule applies: 'tenant' roles bundle only
# 'tenant' permissions.
#
# Example (uncomment and adapt):
#   "tenant.steward": {
#       "domain": "tenant",
#       "description": "Read + manage members (DB-defined)",
#       "grants": {"tenant:read", "tenant:manage-members"},
#   },

CUSTOM_DB_ROLES: dict[str, dict] = {
    "tenant.viewer": {
        "domain": "tenant",
        "description": "Read-only tenant access (custom-DB-role seam example)",
        "grants": {"tenant:read"},
    },
}
