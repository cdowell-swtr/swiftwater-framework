# Meridian → Framework: v0.4.5 upstream asks (promote-up residuals)

**Date:** 2026-06-29 · **From:** Meridian (`cdowell-swtr/meridian`) — generator / reference impl of the
`multitenantauth` de-fork (DEC-0003) and its Phase-2 slices (DEC-0004/0005/0007).
**To:** swiftwater-framework (`cdowell-swtr/swiftwater-framework`) — absorber.
**Re:** the framework-locked-seam fixes Meridian needs from the battery, **verified open against the
shipped v0.4.5** battery (`_commit: v0.4.5`). Meridian cannot fix any of these consumer-side — every
seam named below is integrity-LOCKED.

**Relationship:** promote-up, directional (per `cross-repo-convention.md` v4). These are **generator-side
residuals** on already-shipped promote-ups, not new capabilities — so each is a *proposed* item for the
absorber to dispose (accept → fold into the owning DEC / a new DEC + fix; or counter). None is asserted as
a unilateral bug; where a behavior is documented as deliberate (MDN96 ↔ DEC-0007), the item is framed as a
hardening question against that design. **No conformance suite / copy-deletion applies** — Meridian holds
no local copy of this locked battery code to retire; these are upstream fix-asks, not capability lifts.

**Mode:** one-shot (operator-relay), the convention's default for clear-cut items — a single delivered doc,
no per-item Negotiation Thread. Escalate any individual item to a Negotiation Thread only if the absorber
disputes its generalization. **Status of each item: `proposed`.**

**Delivery:** authored in Meridian `_docs/cross-repo/`; delivered into the framework repo
(`docs/superpowers/assessments/`) via a PR from a clone — the same lightweight doc-exchange as the v0.4.0
divergences report (FWK PR #81) and `meridian-local-builds-response.md`.

---

## TL;DR — the asks, by owning DEC

| # | Ask | Locked seam | Owning DEC | Severity | Verified v0.4.5 |
|---|-----|-------------|------------|----------|-----------------|
| A-1 | **DV-7 (still open):** async resolver fails OPEN | `multitenantauth/deps.py::_adapt_resource_grant` | DEC-0003 (DV-5 seam) | **HIGH-class for the shared lib** (LOW for Meridian) | ✅ `bool(resolver(...))`, no await |
| A-2 | **Resource-grant route accepts an arbitrary `resource_id`** (no existence/visibility check) | `multitenantauth/routes/roles.py::grant_resource_role` | DEC-0007 | MEDIUM (hardening) | ✅ guard is `ANY(...)`, service writes raw id |
| A-3 | **`seed_authz` has no reap path** (upsert-only) | `multitenantauth/authz/seed.py::seed_authz` | DEC-0007 | LOW (consumer ergonomics) | ✅ no deactivate-absent |
| A-4 | **DSN-cache write-back is not epoch-guarded** (lost-update vs `invalidate_dsn_cache`) | `multitenantauth/tenancy/session.py::_resolve_dsn` | DEC-0004 | MEDIUM **when armed** (dormant today) | ✅ blind write under dropped lock |
| A-5 | **Engine-registry validates under the lock + no `connect_timeout`** (one unreachable tenant DB wedges all lookups) | `multitenantauth/tenancy/engine_registry.py::get` + `_default_builder` | DEC-0004/0005 | MEDIUM (availability), topology-dependent | ✅ validate-in-lock, no timeout |
| A-6 | **Container naming + reserved-slug-set seam** (two tiny promote-ups) | compose `name:` + `db/control` `_assert_slug_claimable` | DEC-0003/0004 | LOW | n/a (feature seam) |
| A-7 | **`react` battery FE dev-dep CVEs** (battery owns the lockfile) | `frontend/package-lock.json` | (react battery) | LOW (dev/build-only) | ✅ `vite ^5.4.9`, `npm audit` 7 vulns |

**Also owed (MDN77 / the other direction):** Meridian's **single-confirmation CONCUR on DEC-0004 (SP1
routing) and DEC-0007 (SP3 lifecycle)** — both records have an open operator gate awaiting the generator's
confirmation. See *Confirmations* below.

---

## A-1 · DV-7 — async `resource_grant` resolver fails OPEN *(still open; never delivered)*

**Owning DEC:** DEC-0003 (the DV-5 `register_authz_resolver_factory` seam). DEC-0007 closed DV-5 residuals
t1–t4 (deps.py reorder, per-leaf fitness test, sample resolver, route-naming contract) — **but not this
one.** It was queued in the v0.4.0 divergences doc "for the NEXT delivery / 0.4.2" and never shipped.

**Defect (verified v0.4.5 — `deps.py::_adapt_resource_grant`):**
```python
def _ctx_resource_grant(name: str, path: dict[str, str]) -> bool:
    resource_id = path.get("resource_id")
    if resource_id is None:
        return False
    try:
        return bool(resolver(name, resource_id))   # <-- no await, no coroutine check
```
The DV-5 contract types the resolver `Callable[..., bool]` (mypy-only). At runtime, an **async** resolver
returns a truthy **coroutine** → `bool(<coroutine>)` is `True` → **every resource leaf evaluates True →
fail-OPEN authz.** The registration validator (`register_authz_resolver_factory`) rejects a non-mapping /
missing-key / raising factory, but does **not** reject a coroutine-function resolver.

**Severity:** **HIGH-class for the framework** (a shared library that silently disables resource authz for
any consumer who registers a reasonable `async def` resolver). **LOW for Meridian** — our
`_seal_resolver_factory` is sync and pinned by a unit test (and MDN70 just re-hardened the sync-only
constraint at both choke points). We are safe as shipped; this is filed for the next consumer.

**Proposed fix (generalization):** in `_adapt_resource_grant`, detect a coroutine result
(`inspect.iscoroutine(result)`) → **log + DENY** (fail-closed), never hand a coroutine to `bool()`; and/or
reject a coroutine-function at registration (`inspect.iscoroutinefunction(resolver)`). Either makes the
shared seam fail-closed against the async mistake. Full repro: Meridian
`_docs/architecture/superpowers/plans/2026-06-25-t7-seam-security-review.md` (F2).

## A-2 · Resource-grant route accepts an arbitrary, unvalidated `resource_id`

**Owning DEC:** DEC-0007 — which **documents the `ANY` guard as a deliberate bootstrap-deadlock breaker**
(the first resource grant cannot require a pre-existing resource grant) and ships a per-leaf fitness test
(`test_T2_DV5_resource_leaves_bind_canonical_resource_id`) proving every `/resource:` leaf binds exactly
`{resource_id}`. **This ask does not dispute that design** — it asks about a gap the fitness test does not
cover.

**Observation (verified v0.4.5 — `routes/roles.py::grant_resource_role`):**
```python
_RESOURCE_GUARD = guard(ANY(
    Perm("resource:manage", on="tenant:{tenant_id}/resource:{resource_id}"),
    Perm("tenant:manage-members", on="tenant:{tenant_id}"),
))
@router.post(".../resources/{resource_id}/roles", dependencies=[Depends(_RESOURCE_GUARD)])
def grant_resource_role(..., resource_id: str, ...):
    assign_resource_role(..., resource_id=resource_id, ...)   # raw path id, no existence/visibility check
```
A tenant-admin (holding `tenant:manage-members`) satisfies the `ANY` for **any `resource_id` string** and
the service writes a resource-domain grant on it — with **no check that the id names a real, visible
resource.** The fitness test pins that the grant *binds* the canonical id; it does not assert the id
*exists* or is visible to the actor. Cross-tenant isolation holds (the grant is scoped under
`tenant:{tenant_id}`), so this is **not** a cross-tenant breach — it is an unvalidated-target /
grant-on-phantom-resource hardening gap.

**Why it matters to Meridian:** our seal resolver answers resource leaves with product logic
(`resource_id == product_id`); MDN70 banned generic resource grants so a non-product leaf can't be
*evaluated*, but the **route** still lets a tenant-admin *write* a grant on an arbitrary id. We carry the
local residual as MDN69 (reconcile/retire the duplicated member/role surface); the **framework** half is
this ask.

**Proposed fix (generalization):** offer a consumer-injectable resource-existence/visibility predicate the
route consults before `assign_resource_role` (defaulting to permissive to preserve today's behavior), **or**
make the resource-grant route consumer-optional (mountable only by consumers who validate the id). Keep the
bootstrap-`ANY` for the first-grant deadlock; add the existence gate orthogonally.

## A-3 · `seed_authz` is upsert-only — no reap path for removed vocabulary

**Owning DEC:** DEC-0007 (seed catalog + lifecycle). Distinct from DEC-0007's *slug* reaper
(specialized to lazy-delete-on-reclaim) — this is the **authz seed** runner.

**Behavior (verified — `authz/seed.py`):** `seed_authz` upserts the in-code catalog; it never
deactivates/deletes a permission or role that the catalog **removed**. So a consumer who drops a perm/role
(exactly Meridian's MDN70 ban of `resource:manage`/`resource.admin`) is left with **orphaned DB rows** that
the seed will not clean — the consumer must hand-write a `# deploy: contract` migration (Meridian's MDN95)
and lean on runtime guards (Meridian's import-time catalog guard + the request-time self-check) to keep the
orphans inert until that release.

**Proposed fix (generalization):** a seed-reap (deactivate-absent: mark `is_active=False` for catalog-absent
rows, never hard-delete — rolling-safe), **or** a documented contract-migration helper + the explicit
statement that catalog removal is a two-release contract change. Either turns "code-only ban + hand-rolled
cleanup" into a supported path. (Meridian's `reconcile_authz` already tolerates an orphaned `resource:manage`
row by construction — see `test_reconcile_tolerates_orphaned_db_resource_perm` — so a reap is an ergonomics
upgrade, not a safety fix.)

## A-4 · DSN-cache write-back is not epoch-guarded

**Owning DEC:** DEC-0004 (SP1 routing/session). **Dormant today** (`dsn` is write-once — no UPDATE path),
so no live impact on the current battery; filed as a **precondition** for any DSN-rotation feature.

**Defect (verified v0.4.5 — `tenancy/session.py::_resolve_dsn`):** the resolver drops `_dsn_lock` over the
(potentially slow) resolver call, then **blind-writes** the result into the cache. A resolve begun *before*
an `invalidate_dsn_cache(tid)` can land *after* it, clobbering the fresh entry for the full TTL (default
300s) — a classic lost-update. Today benign (nothing mutates a live tenant's DSN); it **arms to a live
MEDIUM** the moment a secrets/credential-rotation backend or an "update tenant DSN" path ships (serves a
stale credential up to the TTL, defeating invalidation; cross-tenant bleed a further conditional escalation
if a DB instance is recycled).

**Proposed fix:** epoch/version-guarded write-back — capture an epoch before releasing the lock; on
write-back, skip if an invalidation bumped the epoch during the resolve. **Must land before the trigger
feature ships** (that feature has no id in either repo yet). Repro: Meridian
`…/2026-06-25-fwk61-routing-seam-security-review.md` (C2, Damage×F4).

## A-5 · Engine-registry validates under the lock + no `connect_timeout`

**Owning DEC:** DEC-0004/0005 (routing + ops). The framework's own DEC-0004 already flagged a fail-OPEN
connection-budget drift in this area (Drift #2); this is a **distinct** lock-hygiene + timeout concern.

**Defect (verified v0.4.5 — `tenancy/engine_registry.py`):** `get()` builds **and validates** a tenant
engine **while holding the registry RLock**, and `_default_builder` sets **no `connect_timeout`**. So one
tenant whose DB instance is unreachable (per-tenant dedicated instances, which `dsn.py` explicitly
supports) blocks on `engine.connect()` for the full OS TCP timeout **with the shared lock held**, wedging
**every** tenant's engine lookup. This is the code-level form of a connection hiccup amplifying into a full
wedge. **MEDIUM (availability/reliability), topology-dependent** — worst on per-tenant dedicated instances,
negligible on a single shared instance. **No isolation breach** (no wrong engine is ever returned).

**Proposed fix:** validate **outside** the lock (build + validate unlocked; take the lock only to
insert/evict) **or** a per-endpoint validate-once flag with back-off on repeated failure; **and** add
`connect_args={"connect_timeout": N}` to `_default_builder`. Repro: same routing-seam review (F-1 ⊕ F-5
compound).

## A-6 · Container naming + reserved-slug-set seam *(two tiny promote-ups)*

**Owning DEC:** DEC-0003/0004 (the battery + its provisioning/slug machinery).

**(a) Container naming.** Ensure every generated compose stack pins `name: {{ project_slug }}` so containers
are product-named. Meridian's own `base.yml` already does (`name: meridian`); the gap is the **framework's
own** acceptance-test / standalone containers (e.g. `swfwacc-*` / unlabeled). Chris (Meridian operator)
approved this container PUR ("a tiny PUR to FWK… keep it and normalize it").

**(b) Reserved-slug set.** Make the battery's `_assert_slug_claimable` consult a **configurable reserved-set
seam** so the denylist Meridian holds consumer-side (`db/control/reserved_slugs.py`, MDN71 — company/product
reservation + id-shape exclusion + the IA §5 public-surface words) can become battery-owned for any consumer.
This is the upstream half of MDN71.

**Proposed fix:** (a) template the compose `name:`; (b) add a reserved-set injection point to
`_assert_slug_claimable` (default = today's built-in set). Both are small, consumer-general seams.

## A-7 · `react` battery FE dev-dependency CVEs

**Owning DEC:** the `react` battery (no DEC; battery owns `frontend/package-lock.json`).

**Observation (verified v0.4.5):** `npm audit` reports 7 vulns (2 critical / 2 high / 3 moderate), **all in
build/test tooling** — `vite`/`vitest`/`esbuild`/`vite-node`/`@vitest/*` etc. `vite` is still `^5.4.9` (the
non-breaking subset of fixes needs no major bump; the breaking subset needs `vite` v6). These are
`devDependencies`, **not runtime-shipped** (the SPA runtime is react/react-dom/web-vitals), and `npm audit`
is **not** a CI gate (only Python `pip-audit` is). **LOW / build-time-only.**

**Proposed fix:** a battery-side dep-bump (the non-breaking subset via `npm audit fix`; schedule the `vite`
v6 major separately), **or** an explicit accept-and-document (dev-only, not gated). Meridian carries this as
MDN90; a consumer-side lockfile override would fork the battery's lockfile, so the clean fix is generator-side.

---

## Confirmations owed (the other direction — MDN77)

Two shipped Phase-2 records carry an **open operator gate awaiting Meridian's single-confirmation** (not a
Negotiation Thread):

- **DEC-0004 (SP1 routing promote-up)** — *"Meridian's async confirmation is requested."*
- **DEC-0007 (SP3 lifecycle promote-up)** — *"a single-confirmation ask."*

**Meridian's draft CONCUR (pending operator sign-off = this PR's merge):** Meridian **CONCURs** with both
generalizations. Basis: Meridian runs on the v0.4.5 battery today; the de-fork conformance suite (MDN63) is
green; and **MDN70 ("ban generic resource grants") was just built end-to-end against the v0.4.5 resource-grant
vocabulary** with `task ci` green — exercising the SP3 lifecycle/resource-grant surface in anger. The only
attached residuals are the hardening asks A-1…A-3 above (filed, not blocking). Treat the merge of this PR as
Meridian's operator-gated CONCUR on DEC-0004 + DEC-0007.

## Previously reported (FWK PR #81) — re-confirm on the v0.4.5 upgrade path

DV-1 (`pi_prefix` empty on pre-FWK9 upgrade), DV-4 (`.pre-commit-config.yaml` duplicate key on upgrade),
DV-6 (`migrations_control` reuses `c0001`/`c0002` ids with different schema → blocks a persisted-control-DB
upgrade) were delivered in PR #81 as upgrade-path gaps. Meridian worked around all three (pinned
`pi_prefix: "MDN"`; de-duped the pre-commit keys; rebuilds its dev control DB), so **none blocks us** — but
they bite any *other* pre-existing-project upgrader, and the v0.4.5 upgrade path should be re-tested for
them. Not re-filed as asks here; pointer only.
