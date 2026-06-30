# Incoming (from bearing) — active-tenant boot migrate fan-out aborts on active+placeholder tenants + proposed fix

**Date:** 2026-06-30
**Source:** `cdowell-swtr/bearing` (BRG43), observed during its BRG41 v0.4.5 adoption (Task 5 — the BRG15 tenancy-boot reconciliation safety gate).
**Genre:** downstream consumer defect report + proposed fix (companion-style cross-repo input).
**Status:** `proposed`

## Seam

The `multitenantauth` battery owns **both** sides of a contract that currently disagree:

- **Tenant lifecycle (signup):** `multitenantauth/routes/auth.py::signup` registers a tenant with a
  **placeholder DSN** (`postgresql+psycopg://unprovisioned/placeholder`) and **immediately
  `activate_tenant()`s it** — physical database provisioning is a separate, deferred step. So a
  just-signed-up tenant is `status='active'` **with a placeholder DSN**: a normal steady state.
- **Boot migrate fan-out:** the locked `scripts/entrypoint.sh` runs
  `python -m <pkg>.multitenantauth.tenancy.migrate`, whose `upgrade_all()` enumerates fan-out
  targets via `db/control/repository.py::active_tenant_dsns`, which selects **`WHERE status ==
  'active'`** and returns the stored DSN **with no provisioned/placeholder filter**.

All of these files are **integrity-LOCKED** mechanism, so a consumer cannot reconcile them in-tree
without locked-file drift.

## Defect (observed on bearing — framework v0.4.5)

The boot fan-out tries to migrate the placeholder DSN of an active-but-unprovisioned tenant and
**aborts boot**:

1. `active_tenant_dsns(cs)` returns `(tenant_id, "postgresql+psycopg://unprovisioned/placeholder")`
   for the signed-up tenant (it passes the `status=='active'` filter).
2. `upgrade_all()` calls `migrate_tenant(placeholder_dsn)` → alembic connects to the unroutable host
   `unprovisioned` → raises. `upgrade_all` is best-effort per tenant (records the exception **class
   name**, continues), so it does not itself raise.
3. `main()` calls `report_failed(report)` and **returns exit 1** because a tenant failed.
4. `scripts/entrypoint.sh` runs the migrate module under **`set -e`**, so the exit-1 **aborts the
   container boot**. (`task db:migrate:all` has the same exposure.)

**A single active+placeholder tenant — i.e. any signed-up-but-not-yet-provisioned tenant — breaks
boot.** Because the framework's own signup creates exactly that state, the framework ships a tenant
lifecycle its own boot path cannot tolerate.

### The internal inconsistency (the root)

`active_tenant_dsns`'s own docstring states the intended contract:

> "Active-only by design: a `provisioning` tenant has no committed schema contract yet …"

i.e. the enumerator assumes **`active` ⟹ has a migratable schema/DSN**. But `signup` marks a tenant
`active` **before** its database exists (placeholder DSN). The two halves of the battery disagree on
what `active` means — that disagreement is the defect.

## Impact

Any consumer using signup with **deferred physical provisioning** (the documented pattern — the
request-path resolver fail-closes access to a placeholder tenant until it is provisioned) has a
**boot-abort latent in the locked entrypoint** as soon as one tenant signs up. It is **deploy-time,
not test-time** (CI runs pytest, not the entrypoint), so it passes CI and only manifests on the next
real boot / rolling deploy. No unlocked seam can filter the boot fan-out: `register_tenant_dsn_resolver`
is request-path only and `register_provision_hook` is provision-time.

## Proposed fix

Two directions; **(A)** is the minimal safe fix, **(B)** reconciles the root inconsistency. They are
complementary.

**(A) Make the boot fan-out skip non-provisioned DSNs (defensive — recommended minimal fix).**
The framework writes the placeholder DSN at signup, so it owns the sentinel and can exclude it.
Either filter in `active_tenant_dsns` (skip rows whose DSN is the placeholder/unprovisioned
sentinel), or skip in the `upgrade_all` fan-out loop (keeping `active_tenant_dsns` returning
all-active for other callers). Expose a canonical `is_provisioned(dsn)` predicate so mechanism and
consumers agree. **Backward-compatible; closes the boot-abort for every consumer immediately.**

**(B) Reconcile the lifecycle so `active` ⟹ provisioned.**
Have signup leave the tenant `provisioning` until physical provisioning completes, flipping to
`active` only when a real DSN is written. This makes `active_tenant_dsns`'s existing docstring
contract true and needs no fan-out filter — but it changes signup/activation semantics, so it must
be checked against any request-path gating that keys on `active`.

**(C) Optional — a fan-out target filter seam.** Symmetric with the request-path
`register_tenant_dsn_resolver`: let consumers register a predicate deciding which active tenants are
migrate targets. Most flexible; heavier than (A).

**Recommendation:** ship **(A)** now (immediate, backward-compatible), and consider **(B)** as the
cleaner long-term reconciliation.

## Provenance

Confirmed in bearing's BRG41 Task 5 (bearing `_docs/cross-repo/2026-06-29-brg41-v045-reconciliation-notes.md`,
seam (e); origin record `_docs/cross-repo/2026-06-30-fwk-boot-fanout-placeholder-tenant.md`). Bearing
retains its own `_is_provisioned`-filtered `tenancy_seams.migrate_all_tenants` +
`scripts/entrypoint_tenancy.sh` as the working mitigation, and pins the gap with a characterization
test (`tests/functional/test_migrate_all_tenants.py::test_v045_active_tenant_fanout_includes_active_placeholder_tenant_brg41`)
that registers + activates a placeholder-DSN tenant and asserts `active_tenant_dsns` returns it.
