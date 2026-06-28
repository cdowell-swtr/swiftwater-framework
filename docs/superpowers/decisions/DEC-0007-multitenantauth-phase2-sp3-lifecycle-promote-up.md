<!-- CROSS-REPO-convention: v4 -->
# Promote-Up Record — `multitenantauth` Phase 2 / SP3 (authz re-touch + tenant-lifecycle routes)

> Sub-record of the multitenantauth promote-up ([`DEC-0003`](DEC-0003-multitenantauth-promote-up.md)),
> scoped to **FWK61 Phase 2, SP3 / FWK67** — the authz-mechanism re-touch + control-plane tenant-lifecycle
> routes. Sibling of [`DEC-0004`](DEC-0004-multitenantauth-phase2-sp1-routing-promote-up.md) (SP1, routing core)
> and [`DEC-0005`](DEC-0005-multitenantauth-phase2-sp2-migrate-deploy-rollback-promote-up.md) (SP2, migrate/deploy/rollback).
> Per the vendored [`cross-repo-convention.md`](../../../cross-repo-convention.md) (`CROSS-REPO-convention: v4`).
> Roles unchanged: **generator = meridian** (validated reference impl), **absorber = swiftwater-framework**.
> Design detail lives in `docs/superpowers/specs/2026-06-27-fwk67-sp3-authz-retouch-lifecycle-hardening-design.md`;
> this record holds the cross-repo dimension only.

## Status

**`in-migration` — absorber SHIPPED v0.4.3 (FWK67, combined SP2+SP3 release; build complete + security gate PASSED 2026-06-27).** The
generalization decisions below are settled, and the absorber's implementation (subagent-driven, TDD; 14 tasks across
5 phases) is done and green on a `--with multitenantauth` render. The **security gate is passed**: the branch-end
all-Opus whole-branch review (0 Critical/0 Important; the one actioned Minor, M1, shipped at `c42f3bd`) and the
**Phase-2 Layer-2 all-Opus stance×focus adversarial matrix** (`docs/superpowers/eval-scorecards/2026-06-27-fwk67-sp3-layer2-security-matrix.md`
— **GREEN, 0 confirmed Critical/High**; the two confirmed Low audit-completeness TOCTOUs P4/P5 fixed in-branch at
`0ba950c`, taking I-AUDIT-COMPLETE to HOLDS-AFTER-FIX). The **combined SP2+SP3 tagged release** shipped as v0.4.3
(closing FWK66's deferred tail). This sub-record advances the parent DEC-0003
promote-up (still `in-migration`) toward Phase-2 completion — it does **not** change the parent's status, and it
does **not** move anything to `adopted`. **Flips to `adopted` only when Meridian deletes its lifecycle/authz fork**
gated on the conformance contract below.

## Source / generator

- **Repo:** `meridian` (`$DEV_ROOT/meridian`) — the lifecycle/authz model read directly (consistent with SP1/SP2).
- **Capability promoted:** control-plane **tenant-lifecycle routes** (deactivate/suspend/reactivate, resource-role
  grant/revoke, slug rename), **resource-grant audit completeness** (`AuthzEvent.resource_id`), and a dedicated
  **tenant-lifecycle audit** (`TenantLifecycleEvent`) — generalized from Meridian's product-coupled lifecycle/audit
  surface into the generic battery.
- **Explicitly NOT in this slice:** the `subtree_exists` wildcard-subtree re-arm (the seal-walk). It stays the inert,
  fail-closed default (DV-5 posture); no SP3 route uses a wildcard subtree, and arming it needs a locked `expr.py`
  signature change. Meridian's seal-walk lands it in a later, separately-reviewed slice.

## What is validated reference vs. designed-fresh

- **Validated reference (Meridian's model):** the *existence* of tenant-lifecycle operations (suspend/reactivate/
  rename) and a per-grant authz audit. The framework generalizes the shapes — generic permission vocabulary, no
  EDR/product domains — rather than lifting Meridian's modules.
- **Designed-fresh (hardened by the SP3 adversarial design panel — FWK58 two-layer method, 6-lens all-Opus + a
  recovered completeness lens):** the specific route shapes. The panel materially changed the design from the
  brainstorm (spec §10 records five reversed decisions):
  - **Route A split into single-domain routes.** A mixed-domain `ANY` arm was dead code (the membership-404
    precondition fires before expr evaluation; an operator reactivate on a `{tenant_id}` path red-fails the T2
    fitness test). Resolution: tenant-admin self-deactivate carries `{tenant_id}` in the **path**; operator
    suspend/reactivate carry `tenant_id` in the **body** (so `needs_tenant=False` — a non-member operator is
    reachable and T2 stays clean), guarded `platform:manage-tenant-lifecycle`.
  - **Route B bootstrap `ANY` guard.** The first resource grant cannot require a pre-existing resource grant
    (deadlock); `ANY(resource:manage on the resource leaf, tenant:manage-members on the tenant)` lets a tenant-admin
    bootstrap via the second leaf. Cross-tenant safety is a route-layer `membership.tenant_id` check → 404.
  - **Slug reaper → lazy-delete-on-reclaim** (no scheduled Celery-beat reaper; nothing reads expired rows).
  - **Lifecycle mutations are audited now** (the dedicated append-only `TenantLifecycleEvent`, not overloaded onto
    the grant audit).
  - **`subtree_exists` deferred** (kept inert) — see above.

## What was specialized (reference-impl assumptions NOT promoted)

- Meridian's **product/EDR lifecycle vocabulary** → NOT promoted. The seed catalog ships only the generic perms the
  routes need (`tenant:deactivate`, `tenant:rename-slug`, `platform:manage-tenant-lifecycle`, `resource:manage`) +
  a generic `resource.admin` resource-domain built-in role.
- Meridian's **wildcard-subtree / seal-walk** resolution → deferred (inert default); not in this slice.
- A **scheduled slug reaper** → specialized down to lazy-delete-on-reclaim (YAGNI; fail-closed today).
- A **DB-level ≥1-admin guard** → remains app-level for this slice (hard-teardown and its DB-level guards stay
  deferred to the phase-2 teardown work).

## Generalization decisions (the calls, as settled)

- **Operator lifecycle is platform-scoped + body-carried.** Suspend/reactivate guard on `platform:manage-tenant-lifecycle`
  with the target `tenant_id` in the body — never a `{tenant_id}` path param (which would 404 a non-member operator
  before the platform leaf and trip T2). Tenant-admin self-deactivate stays path-scoped on `tenant:{tenant_id}`.
- **Resource grants bootstrap via `tenant:manage-members`**; cross-tenant isolation is enforced at the route layer
  (membership-tenant mismatch → 404, existence never leaked).
- **`AuthzEvent.resource_id`** (additive, nullable; migration `c0004`) closes precondition (b) — resource grants are
  auditable with their resource. **`TenantLifecycleEvent`** (migration `c0005`, `action ∈ {suspend,reactivate,rename}`,
  append-only) is the lifecycle audit.
- **DV-5 residuals closed in-slice:** t4 (`deps.py` reorder removing the privilege-influence adjacency), t2 (a
  **per-leaf** resource-binding **fitness test** + negative control — the only acceptable shape; in-mechanism guards
  were explicitly OUT), t1/t3 (a documented sample consumer resolver + the `{tenant_id}` route-naming contract).
- **`slug_cooling_days`** promoted from a module constant to a floored `Settings` field (`ge=1`); single source of truth.
- **SP2 carry-overs:** P13 break-glass audit line (the `ALLOW_CONTRACT_ROLLBACK=1` override is now attributable),
  P11 advisory-backstop documentation (data-integrity reviewer is opt-in via `ANTHROPIC_<PKG>_CI_RUNTIME` + branch
  protection), P16 deferral note (per-release control-rev tracking deferred; over-refusal is fail-closed today).
- **Everything gates on the `multitenantauth` battery**; the new control schema is integrity-LOCKED (`c0004`/`c0005`
  added to `BATTERY_LOCKED_SRC`) so a consumer cannot silently fork the security-critical lifecycle/audit machinery.

## Migration sequence (upstream-first)

1. **Generalize in the absorber first** — SP3 build per the approved spec (**done**, 2026-06-27).
2. **Conformance suite** (rendered authz/lifecycle suite + mechanism-lock integrity + the DV-5 t2 per-leaf fitness
   test + the branch-end Layer-2 matrix) — see below.
3. **Ship tagged** — the **combined SP2+SP3** Phase-2 release (closes FWK66's deferred, untagged tail).
4. **Generator adopts + deletes its fork** — Meridian re-points lifecycle/authz at the battery, gated on the
   conformance suite; arms `subtree_exists`/seal-walk in its own later slice.
5. **Roll the parent DEC-0003 toward `adopted`** — only once Meridian's fork (auth + routing + ops + lifecycle) is
   fully deleted.

## Conformance contract (gates Meridian's lifecycle/authz fork-deletion)

- **Rendered authz + lifecycle suites:** the route tests (tenant-role + resource-role + lifecycle routes), the
  service/seed/catalog tests, the fitness suite, the settings + registry tests — all green on a real-Postgres render.
- **Mechanism-lock integrity:** `tests/integrity/test_auth_mechanism_lock.py` + `framework integrity` against a
  render — the whole locked `multitenantauth` tree, including `c0004`/`c0005`, is checksummed.
- **DV-5 t2 per-leaf fitness test** (`test_T2_DV5_resource_leaves_bind_canonical_resource_id` + its negative
  control): every `/resource:` Perm leaf binds exactly `{resource_id}` — catches a multi-resource over-grant the
  route-level `resource_params()` check passes.
- **Phase-2 Layer-2 adversarial security matrix** (all-Opus stance×focus), mandatory before release. New cells:
  `id↔slug-desync`, `cross-tenant resource over-grant`, `deactivate/reactivate asymmetry` **with an explicit
  non-member-operator reachability assertion**, `control-migration data-safety`, `lifecycle-audit completeness`.
  Scorecard → `docs/superpowers/eval-scorecards/2026-06-27-fwk67-sp3-layer2-security-matrix.md`.

## Generator confirmation (requested)

Meridian to confirm, async, against this record: (1) the generalized lifecycle/audit model faithfully represents the
intended capability; (2) the panel-driven route shapes (Route A single-domain split with body-carried operator id,
Route B bootstrap `ANY`, lazy-delete cooling) are acceptable for its adoption; (3) `subtree_exists`/seal-walk
deferral is acknowledged as Meridian-owned for a later slice. No operator gate is open; a single-confirmation ask,
not a Negotiation Thread.

## References

- SP3 design: `docs/superpowers/specs/2026-06-27-fwk67-sp3-authz-retouch-lifecycle-hardening-design.md`
- SP3 plan: `docs/superpowers/plans/2026-06-27-fwk67-sp3-authz-retouch-lifecycle-hardening.md`
- SP2 PUR: `docs/superpowers/decisions/DEC-0005-multitenantauth-phase2-sp2-migrate-deploy-rollback-promote-up.md`
- SP1 PUR: `docs/superpowers/decisions/DEC-0004-multitenantauth-phase2-sp1-routing-promote-up.md`
- Parent PUR: `docs/superpowers/decisions/DEC-0003-multitenantauth-promote-up.md`
- SP3 Layer-2 scorecard (**GREEN**, 2026-06-27): `docs/superpowers/eval-scorecards/2026-06-27-fwk67-sp3-layer2-security-matrix.md`
