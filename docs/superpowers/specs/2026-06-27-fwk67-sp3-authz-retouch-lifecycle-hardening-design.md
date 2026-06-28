# FWK67 (SP3) — multitenantauth authz re-touch + tenant-lifecycle routes — Design

> **Status:** design APPROVED (pending operator spec-review) · **Date:** 2026-06-27 · **Ships:** a release (template payload)
> **Phase:** FWK58 Phase-2 sub-project 3 of 3 (after SP1/FWK61 routing, SP2/FWK66 migrate-deploy-rollback)
> **Source of truth:** `PLAN.md` rows FWK67 / FWK63 / FWK61 · scorecards
> `2026-06-25-fwk62-dv5-resolver-seam-security-review.md`,
> `2026-06-25-fwk61-sp1-layer2-security-matrix.md`,
> `2026-06-27-fwk66-sp2-layer2-security-matrix.md`
> **Promote-up:** `cross-repo/v4` — generator = Meridian reference impl, absorber = framework; PUR `DEC-0007` (this slice).

## 1. Purpose & scope

SP3 is the third and final sub-project of the `--with multitenantauth` de-fork Phase 2. It is **route-complete**:
it ships three control-plane tenant-lifecycle routes **with their preconditions met**, closes the deferred
DV-5 resolver-seam residuals (FWK63 t1–t4), folds in the SP2 review carry-overs, and lands the named
Phase-2 Layer-2 cells (id↔slug-desync, control-migration data-safety).

This design was hardened **before spec-lock** via the FWK58 two-layer adversarial method: a 6-lens all-Opus
design panel (37 findings raised → 14 confirmed) plus a separately-recovered completeness-critic lens (9
findings, 3 High). Every confirmed finding is dispositioned here; see §10 for provenance and the decisions
that reversed earlier choices.

### 1.1 The lock-scope reality (sets review weight)

The integrity manifest `src/framework_cli/integrity/classes.py` (`BATTERY_LOCKED_SRC`, lines 157–202) locks
**nearly the entire `multitenantauth` tree** — including `routes/roles.py`, `routes/tenants.py`,
`authz/service.py`, `tenancy/registry.py`, `db/control/repository.py`, and all `db/control/models/*`. The
completeness test `tests/integrity/test_auth_mechanism_lock.py` walks the rendered tree and fails if any
mechanism file is absent from the manifest, so a **new** route/model file cannot dodge the lock — it must be
added to the manifest (and re-checksummed).

**Consequence:** essentially the whole SP3 *code* surface is locked → the build is **all-Opus heavy review
end-to-end** and gets one branch-end Layer-2 stance×focus matrix. The "front-loaded locked block vs light
routes" framing from the brainstorm is wrong and is corrected here.

**Genuinely light-review surfaces** (the only ones): the authz **policy catalog** `authz/permissions.py` +
`authz/roles.py` (ship `INTENTIONALLY_UNLOCKED`, consumer-editable), the **fitness/functional tests**, the new
**settings field** in `config/settings.py` (co-owned, not in the manifest), `scripts/` (`rollback_guard.py`,
`check_migrations.py`), `infra/deploy/`, and docs.

## 2. Architecture at a glance

| Bucket | Items | Review |
|---|---|---|
| **§A Control-plane data model** (locked) | `AuthzEvent.resource_id`; new `TenantLifecycleEvent`; DV-5 t4 reorder | heavy (Layer-2) |
| **§B Routes** (locked — `routes/*`, `service.py`, `registry.py`) | A (deactivate/suspend/reactivate), B (resource grant/revoke), C (rename-slug) | heavy (Layer-2) |
| **§C Non-locked hardening** | DV-5 t2 fitness test; t1/t3 docs+sample; **seed-catalog extension**; cooling-window setting; P11 reword; P13 audit line | light |
| **§D Tests** | positive reachability + cross-tenant + ALLOW-path functional tests; lock re-checksum | light |

All three routes are **control-plane** (`control_session`, no per-tenant engine session), so SP1's data-plane
guards (sentinel / parse-before-cache / lock-hygiene) **stay deferred** (§9).

## 3. §A — Control-plane data-model changes (locked)

### A1. `AuthzEvent.resource_id` — close Phase-1 precondition (b): resource-grant audit completeness
Today `assign_resource_role` / `revoke_resource_role` and the `remove_member` cascade-revoke loop record a
resource-domain `AuthzEvent` with **no resource_id** (`authz/service.py:342, 376, 300–309`), so the audit can't
say *which* resource a grant was for.

- Add `resource_id: Mapped[str | None] = mapped_column(String(255))` to `AuthzEvent`
  (`db/control/models/authz.py`). **Nullable** — tenant/platform events have none.
- Thread `resource_id` through `_record_event(..., resource_id=None)` and pass the real id at all three
  resource-domain call sites (incl. the `remove_member` cascade loop at `service.py:300–309`, which iterates
  `resource_assignments` that already carry `.resource_id`).
- New control migration (`migrations_control/versions/c0004_*`). **Additive nullable column** → expand-only,
  no backfill, not a contract migration.

### A2. `TenantLifecycleEvent` — audit the new lifecycle mutations (operator decision: audit now)
`AuthzEvent.action` has a `CHECK action IN ('grant','revoke')` so it structurally cannot record
suspend/reactivate/rename. Add a **separate append-only** control model rather than overloading the grant audit:

```
TenantLifecycleEvent(ControlBase)         # db/control/models/tenant.py (or a new lifecycle.py)
  id            uuid pk
  actor_id      uuid | None  FK app_user.id   # None ⇒ system/operator-tooling
  tenant_id     str          FK tenant.id
  action        str          CHECK IN ('suspend','reactivate','rename')
  detail        str | None                   # for rename: "old_slug→new_slug"; else NULL
  at            datetime tz   server_default now()
  Index(tenant_id, at)
```

Lands as control migration `c0005` (sibling of A1's `c0004`). The model file (new or `tenant.py`) is locked,
and the new migration files (`c0004`, `c0005`) are mechanism → add all to `BATTERY_LOCKED_SRC` and re-checksum;
`test_auth_mechanism_lock` enforces their presence.

### A3. DV-5 t4 reorder (the only remaining locked-mechanism touch)
In `deps.py`, compute `ctx['platform_perms']` **before** the resolver-factory call (removes the
privilege-influence adjacency; not request-reachable today, rides this review since the file is locked).

> **Dropped from SP3 (operator decision):** the `subtree_exists` override seam. No SP3 route uses a wildcard
> subtree (A = tenant/platform, B = concrete `resource:{resource_id}`, C = tenant), and honoring it cleanly
> would require a **locked `expr.py:147` evaluator-signature change** — `subtree_exists` is handed the
> *composite bound string* whereas `resource_grant` gets the *discrete path dict* (A-F1). It stays **inert**
> (DV-5 posture); `_has_wildcard_leaf` (`expr.py:52–78`) stays intact. Meridian's seal-walk lands it later
> against a real generic need with the "properly-designed shape" DV-5 scorecard line 29 already names.

## 4. §B — The three routes (locked: `routes/*`, `service.py`, `registry.py`)

> **Guard mechanics that constrain these routes** (`deps.py`): `needs_tenant = "tenant_id" in
> authorized.resource_params()`; when true, the guard runs the membership-404 precondition
> (`deps.py:218–229`: tenant exists ∧ `status=='active'` ∧ `has_membership`) **before** the expression is
> evaluated. So a tenant-scoped leaf forces membership-gating; a platform-only guard skips it. The shipped
> `test_T2_tenant_routes_bind_tenant_id` flags any route whose **path** contains `{tenant_id}` whose guard
> doesn't bind it. These two facts shape the split below.

### Route A — tenant deactivate / operator suspend / operator reactivate
Soft-deactivate only; `Tenant.status` already has `'suspended'`, so **no migration**. Split into single-domain
routes (the mixed `ANY(tenant, platform)` from the brainstorm is undeliverable — the operator arm is dead code
behind the membership-404, and a platform-only route on a `{tenant_id}` path red-fails T2; confirmed by 5
panel lenses):

| Endpoint | Guard | Notes |
|---|---|---|
| `POST /tenants/{tenant_id}/deactivate` | `Perm("tenant:deactivate", on="tenant:{tenant_id}")` | tenant-admin **self**-offboard; needs_tenant=True, membership-gated; T2 satisfied. → `status='suspended'` |
| `POST /tenants/suspend` (body `{tenant_id}`) | `Perm("platform:manage-tenant-lifecycle", on="platform")` | operator suspends an abusive tenant; **no `{tenant_id}` in path** ⇒ needs_tenant=False (operator reachable as a non-member) ⇒ T2 never fires. Handler `cs.get(Tenant, body.tenant_id)` → 404 if absent. |
| `POST /tenants/reactivate` (body `{tenant_id}`) | `Perm("platform:manage-tenant-lifecycle", on="platform")` | operator-only (a tenant-admin can deactivate but **cannot** reactivate — the intended asymmetry). |

**Operator-route shape:** tenant id travels in the **request body**, not the path — `platform:manage-tenant-lifecycle`
is fleet-wide so the id is a *target selector*, not an authz operand (no IDOR). This needs **zero** change to
the locked guard or the shipped T2 invariant. *(Rejected alternative: a reviewed T2 carve-out permitting
pure-platform routes to carry `{tenant_id}` in the path — it weakens a shipped consumer invariant for cosmetic
RESTfulness.)*

**reactivate is a real state-machine transition**, not a bare flip: load the tenant → **404** if absent →
**409** if `status != 'suspended'` (never silently activate a `provisioning` tenant). Prefer a
`registry.reactivate_tenant()` helper asserting the precondition, mirroring `activate_tenant()` as the
canonical status mutator. Document deactivate's transition contract symmetrically.

Every Route-A mutation records a `TenantLifecycleEvent`.

### Route B — resource-grant / revoke (in `routes/roles.py`)
Exposes the existing `assign_resource_role` / `revoke_resource_role` service fns.

- `POST   /tenants/{tenant_id}/members/{membership_id}/resources/{resource_id}/roles` (body `{role_name}`)
- `DELETE /tenants/{tenant_id}/members/{membership_id}/resources/{resource_id}/roles/{role_name}`

**Guard** (bootstrap-safe — a lone resource `Perm` deadlocks first-grant):
```
ANY(
  Perm("resource:manage", on="…/resource:{resource_id}"),   # resource-holder path (DV-5 seam consumer)
  Perm("tenant:manage-members", on="tenant:{tenant_id}"),   # tenant-admin bootstrap/management leg
)
```
*(Exact `on=` prefix per the `/resource:` convention in `authz/expr.py`; the implementer takes the literal
format from there. `resource:manage` and the role it bundles are the starter-catalog example names — §C3.)*
**Mandatory route-layer precondition** (the cross-tenant invariant — service fns do **not** check it):
load the target membership and **404 unless `membership.tenant_id == path {tenant_id}`**, mirroring
`roles.py:64` / `tenants.py:206`, for **both** arms. The tenant binding comes from the membership FK, never
from the opaque `resource_id` (`String(255)`, no FK). Records an `AuthzEvent` carrying `resource_id` (A1).

> DV-5 t2 footgun note: the per-leaf binding correctness is enforced by the **per-leaf fitness test** (§C1),
> not by this route alone.

### Route C — rename-slug (in `routes/tenants.py`)
`PATCH /tenants/{tenant_id}/slug` (body `{slug}`), guard `Perm("tenant:rename-slug", on="tenant:{tenant_id}")`
(tenant-admin — the slug is the tenant's own vanity identity).

Flow: claimability check via `resolve_slug` (already checks live + cooling) → update `Tenant.slug` → insert the
old slug into `TenantSlugHistory(reserved_until = now + slug_cooling_days)` → **lazy-delete** any *expired*
history row for the slug being (re)claimed in the same transaction. Records a `TenantLifecycleEvent('rename',
detail="old→new")`. `Tenant.id` is immutable — the rename never touches the id or the Phase-2 per-tenant
DB-name key (id↔slug-desync cell, §6).

> **No scheduled reaper** (reconciles the two lenses): nothing reads expired history rows — there is no 301
> route, `resolve_slug`/`is_slug_cooling` already treat them as inert, and `add_slug_history` upserts on the
> slug PK. A Celery-beat reaper would also couple `multitenantauth` (which `requires=()`) to the workers
> battery. Lazy-delete-on-reclaim is sufficient; a scheduled reaper is a deferred option (§9) if rename volume
> ever justifies it.

## 5. §C — Non-locked hardening

- **C1 · DV-5 t2 fitness test (PER-LEAF, not route-level).** New test in `tests/functional/test_authz_fitness.py`:
  iterate `auth.perm_leaves()` and, for every leaf whose `on` contains `/resource:`, assert the resource
  segment references **exactly** `{resource_id}`. (The route-level `resource_params()` form passes a
  multi-resource over-grant — `ALL(Perm(on=".../resource:{resource_id}"), Perm(on=".../resource:{other_id}"))`
  — because the resolver keys on the hardcoded `path['resource_id']`.) Ship a **RED fixture** proving the
  route-level form is insufficient. This is the *only acceptable shape* per the FWK62 scorecard (in-mechanism
  guard is OUT).
- **C2 · DV-5 t1/t3 docs + sample resolver.** A documented sample correct consumer `resource_grant` factory
  scoping `resource_id` by the closure tenant (`cs` + `active_tenant_id`); a doc note that a consumer's tenant
  placeholder MUST be named `tenant_id`. `needs_tenant` generalization stays **docs-only** (won't touch locked
  `deps.py` for a non-reachable case).
- **C3 · Seed-catalog extension (policy, unlocked) — REQUIRED for the routes to function.** Without this the
  new guards reference unseeded permissions → permanent 403, and Route B's resource role doesn't exist →
  `_resolve_role` raises → 400. Add to `authz/permissions.py CATALOG`: `tenant:deactivate` (tenant),
  `tenant:rename-slug` (tenant), `platform:manage-tenant-lifecycle` (platform), `resource:manage` (resource);
  bundle the tenant/platform perms into `tenant.admin` / `platform.admin` (`authz/roles.py BUILTIN_BUNDLES`);
  add a **new resource-domain built-in role** `resource.admin` bundling `{resource:manage}` + register it in
  `BUILTIN_DOMAINS` (domain `'resource'`) — `resource.admin` is also the grantable `domain='resource'` role
  Route B needs (`assign_resource_role` requires one to exist). Drive each route's **ALLOW** path with a seeded
  admin in a functional test (TDD forces
  the catalog work and proves route-complete is real, not deny-path-only).
- **C4 · Cooling-window setting + floor.** Promote `slug_cooling_days` to a setting in `config/settings.py`
  (`Field(default=30, ge=1)`, mirroring `max_cached_engines`) + a per-setting `ValidationError` floor test
  (mirror `test_max_cached_engines_floor_rejects_zero`). Single source of truth: the reaper/lazy-delete and
  claimability both read the same `reserved_until`; **no second retention/age knob** (a 0/negative window is
  the SP1 P3/P4 degrade-to-permissive class — instant squat + collapsed redirect). Explicitly warn the
  implementer off the `prune_expired(retention_days)`/`retired_at` age-based convention.
- **C5 · P11 — data-integrity reviewer as the (advisory) destructive-migration backstop.** The rollback floor
  only catches AST-marked contract migrations; raw-SQL / type-narrowing destructive migrations evade it. The
  real backstop is commit/CI-time semantic review. Document this in `scripts/check_migrations.py` +
  `infra/deploy/README`. **Accurate posture:** the rendered reviewer is **off-by-default / advisory** (gated on
  the `ANTHROPIC_<PKG>_CI_RUNTIME` secret, neutral on a missing key, only blocking if the consumer adds it to
  branch protection) — tell consumers to wire the secret + require the check to make it load-bearing. Confirm
  prompt-fit per `check-agent-prompt-fit-before-adding-to-target` before relying on it.
- **C6 · P13/P17 — break-glass audit line.** Emit an audit-log line when `ALLOW_CONTRACT_ROLLBACK=1` is
  exercised (keep it warning-loud *and* now audited). `infra/deploy/strategy.sh` / `scripts/rollback_guard.py`.

> **P16 deferred** (one-line note in `rollback_guard.py`): per-release control-rev tracking is premature — the
> control-floor over-refusal cannot fire until a control **contract** migration exists, and c0001–c0004 are all
> additive/expand-only. The over-refusal is fail-closed and harms nothing today; revisit when a control
> contract is first authored.

## 6. §D — Shipped behavioural tests (the load-bearing CI backstops)

- Non-member operator holding `platform:manage-tenant-lifecycle` **reaches** `suspend` + `reactivate`
  (200, not 404) — the entire dead-platform-arm bug class is invisible to member-based tests.
- Tenant-admin **can** self-deactivate but **cannot** reactivate (403).
- `reactivate` on a `provisioning` tenant → 409; on an absent tenant → 404.
- Route B: a cross-tenant `membership_id` (membership of tenant Y under `/tenants/X/...`) → **404**, both arms.
- Each route's **ALLOW** path with a seeded admin (depends on C3).
- Route C: still-cooling slug remains non-claimable after a reclaim/lazy-delete; nothing routes on `slug`.

## 7. Branch-end Layer-2 all-Opus stance×focus matrix — new cells

`id↔slug-desync` · `cross-tenant resource over-grant` · `deactivate/reactivate asymmetry` **with an explicit
non-member-operator reachability assertion** · `control-migration data-safety` (resource_id + lifecycle_event
are additive/nullable) · `lifecycle-audit completeness`. *(The `subtree_exists seam` cell is dropped — seam not
shipped.)*

## 8. Promote-up & release

- **PUR `DEC-0007`** (`docs/superpowers/decisions/`): generator = Meridian reference impl, absorber = framework;
  status `designed`. The lifecycle routes + resource-grant audit are the absorbed capability; the
  `subtree_exists` seam is explicitly **not** in this slice (deferred).
- **Release:** closes FWK66's deferred tail — cut the **combined SP2 + SP3** release (tag) after the branch
  merges, per `release-cut-procedure`. SP2 has been on `main` untagged since 2026-06-27; this is the tag that
  makes both visible to `framework upgrade`.

## 9. Explicit OUTs — deferred obligations (NOT closed)

Recorded so no future implementer mistakes a deferral for a closure:

- **Phase-2 hard-teardown** (physical tenant-DB drop) and everything it arms: SP1 data-plane guards
  (sentinel / parse-before-cache / lock-hygiene), a scoped `tenant_teardown()` ≥1-admin bypass
  (`trusted_seed_provisioning` contextvar pattern), the `reason` snapshot fork (offboard-retain vs GDPR-erase).
- **DB-level ≥1-admin guard** — Phase-1 precondition (a) is **deferred-with-hard-teardown**, *not* closed; the
  current enforcement is **application-level** (`_assert_not_last_admin`), the requested DB-level guard is
  unbuilt.
- **reactivate-onto-stale-schema catch-up** — SP2's `active_tenant_dsns` skips `suspended` tenants
  (`repository.py:46–57`, "suspended is an SP3 lifecycle concern"); a tenant suspended across a migration is
  reactivated onto a possibly-stale schema. Not runtime-reachable today (no `tenant_db` request route), so
  recorded as a deferred obligation that lands with the data plane (migrate-on-reactivate, or
  operator-migrates) — keeps SP3 control-plane-pure.
- **`subtree_exists` re-arm** + the `_has_wildcard_leaf` relaxation.
- **Fitness-suite `tenant_db` / `INLINE_AUTHZ` re-arm** (no tenant-engine route ships).
- **P16 per-release control-rev tracking**; **scheduled slug reaper** (lazy-delete suffices now).

## 10. Design-panel provenance & reversed decisions

Hardened by the FWK58 two-layer method before spec-lock:
- **6-lens all-Opus design panel** (`wf_9505b8c3-7bd`): 37 raised → 14 confirmed (default-to-refute
  verification). Dominant finding (5 lenses converged): Route A's mixed `ANY` is undeliverable → **route split**.
- **Recovered completeness-critic lens** (the panel's 6th lens died on a transient `server_error` — see
  `FWK73`): 9 findings, 3 High — the **seed-catalog false-closure** (C3), the **Route B first-grant deadlock**
  (the bootstrap `ANY`), and a duplicate of the Route-A split.

**Decisions this design records that changed earlier brainstorm choices:**
1. **`subtree_exists`: deferred** (was "override seam only") — unused by any SP3 route + needs a locked
   `expr.py` signature change to do cleanly.
2. **Route A: split into single-domain routes** (was one mixed `ANY` guard) — the operator arm was dead code +
   reactivate red-failed T2.
3. **Lock scope: the whole code build is heavy-review** (was "routes UNLOCKED") — corrected against the manifest.
4. **Slug reaper: lazy-delete, not a scheduled Celery-beat task** — nothing reads expired rows; avoids a
   workers-battery coupling.
5. **Lifecycle mutations are audited** (new `TenantLifecycleEvent`) — operator decision.
