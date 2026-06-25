# FWK61 SP1 — Physical per-tenant routing core (design)

> **FWK61 = FWK58 Phase 2** (physical per-tenant routing + ops), the second half of the
> `multitenantauth` Meridian→Framework de-fork. Phase 2 decomposes into **SP1** (this spec —
> the physical routing core), **SP2** (plane-aware migrate/deploy/rollback), **SP3** (authz-mechanism
> re-touch + lifecycle hardening + the folded FWK63 seam residuals). Build order SP1 → SP2 → SP3.
>
> This is a **promote-up** under the vendored `cross-repo-convention.md` (`CROSS-REPO-convention: v4`):
> generator = **meridian** (validated reference impl), absorber = **swiftwater-framework**. Recorded in
> `docs/superpowers/decisions/DEC-0003-multitenantauth-promote-up.md`; SP1 gets its own PUR
> (`DEC-0004`) once this design is approved.

## 1. Problem & strategy

Phase 1 (v0.4.0) shipped the **logical** control plane: an opaque-id/slug tenant **registry**
(`multitenantauth/tenancy/registry.py`) that stores a per-tenant DSN but **never connects to it**
(routing-agnostic by construction). SP1 adds the **physical** plane: given a tenant, resolve and route
to its own database — with bounded, budgeted connection pools and idempotent physical provisioning.

**Strategy — lift the validated core, rebuild the seam.** Meridian built and ran this in production; its
`engine_registry.py` (bounded per-endpoint LRU + connection budget, MDN47), DSN-cache, `tenant_session`
resolution, and the fail-closed identical-404 routing gate are **validated gold** and are lifted as-is
(generalized). Meridian's **provision/migrate write path drifted and is broken** (see §11) — so SP1
**rebuilds** provisioning on the battery's *current* registry (`register_tenant`/`activate_tenant`), it does
**not** lift Meridian's drifted `provision.py`/`migrate_all.py`.

## 2. Scope

**In (SP1):**
- `TenantEngineRegistry` — bounded, per-endpoint-budgeted LRU of **sync** SQLAlchemy engines keyed by DSN.
- `tenant_session(tenant_id, *, control_session)` — connect-time DSN resolution + DSN cache + get-or-create engine → `Session`.
- `resolve_dsn` seam — the injectable connect-time DSN resolver; default reads the stored control-row DSN (matches Meridian); the forward-compatible hook the future **Secrets-backing** Horizon item plugs a vault into.
- Physical provisioning — `provision_tenant(...)`: register → **[skippable]** `CREATE DATABASE` → per-tenant `alembic upgrade head` (Python API) → post-migrate hook (default no-op) → activate. Idempotent / re-runnable.
- `default_tenant_dsn(tenant_id)` — compute the co-located default DSN (parametrized DB-name prefix).
- Routing deps — `active_tenant` (fail-closed identical-404) + `tenant_db` (request-scoped tenant `Session`), composing with the Phase-1/DV-5 authz dep already in `multitenantauth/deps.py`.
- Observability — OTel spans on resolve/provision + per-endpoint pool gauges (the surface Meridian's core lacks).
- Integrity-lock upkeep — register the new mechanism files in `BATTERY_LOCKED_SRC` + regenerate the manifest (§4.7).
- A drift-aware conformance suite split (§8).

**Out (deferred, with the boundary named):**
- **SP2** — plane-aware migrate *fan-out* across all tenants, control-first ordering, deploy/rollback orchestration (MDN59/46). SP1 builds only the **per-tenant migrate primitive** that provisioning needs; SP2 generalizes it.
- **SP3** — re-arming the inert `subtree_exists` hook; the folded FWK63 seam residuals (t1–t4); `AuthzEvent.resource_id` + resource-grant audit completeness; the DB-level ≥1-admin guard; `tenant_slug_history` reaping; the next-pass Layer-2 cells.
- **Secrets-backing** (PLAN.md:56 Horizon item) — a real secrets backend / rotation / field-encryption. SP1 ships the **seam only**; per-tenant DSNs carry creds, which is precisely what pulls Secrets-backing forward in priority (FWK56 edge note) — but it is its own scheduled item, not SP1.
- Logical `tenant_id` scoping of business data (FWK60) and the single-tenant `--with auth` sibling (FWK59).

## 3. Architecture

The control plane already exists and is **synchronous** (`db/control/engine.py`: `control_engine()` /
`control_session_factory()` / `dispose_control_engine()`, double-checked locking, built via shared
`db/engine.py:build_engine`/`build_session_factory`). SP1 adds a **tenant plane** that mirrors it:

```
db/control/                      (Phase 1 — exists)
  engine.py        control_engine(), control_session_factory()
  models/          authn, authz, tenant
  repository.py    add_tenant(*, id, name, slug, dsn, status), get_tenant, get_tenant_dsn, …
db/tenant/                       (SP1 — new; mirrors db/control)
  engine_registry.py  TenantEngineRegistry  — per-endpoint LRU + connection budget
  engine.py           tenant_session(tenant_id, *, control_session)  + DSN cache + resolve_dsn default
multitenantauth/
  tenancy/registry.py  (Phase 1 — exists; routing-agnostic register/activate/resolve)
  tenancy/dsn.py       (SP1 — new) default_tenant_dsn(tenant_id)
  tenancy/provision.py (SP1 — new) provision_tenant(...) + register_provision_hook(...)
  deps.py              (exists; SP1 adds active_tenant + tenant_db routing deps)
```

All engines are **sync** (matching the control plane and Meridian) — no async/await split is introduced.

## 4. Components

### 4.1 `TenantEngineRegistry` (`db/tenant/engine_registry.py`)
A process-global singleton holding a bounded LRU of sync engines keyed by full DSN, accounted **per
endpoint** (`host:port`). Lifted from Meridian's validated core; defaults carried over:

- Per-tenant engine pool: `tenant_pool_size=2`, `tenant_max_overflow=3`.
- Cache bound: `max_cached_engines_per_endpoint=12` (count-driven LRU eviction; soft `Engine.dispose()`; **no idle/TTL tier** — YAGNI, validated without one).
- Connection budget (`validate_endpoint_budget`, **fail-closed**): probe `SHOW max_connections` once per endpoint, multiply by `db_pool_safety_factor=0.8`; refuse to create an engine that would exceed the endpoint's budget (counting the co-located control pool when on the same endpoint). A probe failure denies, never silently allows.
- Thread-safe under an `RLock` (FastAPI runs sync deps in a threadpool — same hazard the control engine's double-checked lock addresses).
- Renders gauges `app_tenant_engines_cached{endpoint}` and `app_tenant_pool_checked_out` (§4.6).

### 4.2 `tenant_session` + the `resolve_dsn` seam (`db/tenant/engine.py`)
`tenant_session(tenant_id, *, control_session)` is a context manager that: resolves the DSN via the seam →
gets-or-creates the engine from the registry → yields a request-scoped `Session` → closes it. A small DSN
cache (`tenant_id → (dsn, expiry)`, TTL `tenant_dsn_cache_ttl=300s`, invalidated on a lifecycle change)
avoids a control-DB read per request.

The **seam** is `resolve_dsn(tenant_id, *, control_session) -> str`, injectable via
`register_tenant_dsn_resolver(fn)` (default-registry pattern, same shape as the DV-5 authz-resolver seam).
**Default** = `get_tenant_dsn(control_session, tenant_id)` — read the DSN stored in the control row, matching
Meridian's validated posture. The **Secrets-backing** item later registers a resolver that merges injected
credentials from a vault. Fail-closed: a resolver raising, or returning a non-string, denies the route.

### 4.3 `default_tenant_dsn` (`multitenantauth/tenancy/dsn.py`)
`default_tenant_dsn(tenant_id) -> str` clones the app/control database URL and swaps the database name to
`{tenant_db_name_prefix}_{tenant_id}` (prefix is a setting, **not** the Meridian-specific `meridian_tenant_`).
`tenant_id` is already constrained to `^[a-z0-9_]+$` by `registry._validate_tenant_id`, so it is always a
safe quoted-identifier component. Co-located on one server by default; the only knob to move a tenant off-box
is a per-tenant DSN that differs in host — which `provision_tenant`'s bring-your-own-DSN path supports.
This module is the **home for DSN-naming policy** — kept out of the registry so the registry owns only id +
row mechanics. It is the one place a consumer changes co-location topology (prefix / host) without touching
the routing core.

**Chicken-and-egg resolution.** The physical DB name is **id-derived** (the opaque id is the stable
`^[a-z0-9_]+$` component; the slug is mutable and hyphenated, so it must not name the DB), but the opaque id
is *generated inside* `register_tenant` and never passed in. SP1 therefore makes `register_tenant`'s `dsn`
**optional**: when omitted, it computes `default_tenant_dsn(<the id it just generated>)` before the
`add_tenant` write. This preserves the opaque-id invariant (id still minted internally), keeps the registry
routing-agnostic (constructing a DSN string is not connecting), and removes the ordering problem.
Bring-your-own-DSN callers pass `dsn` explicitly. *(This is a deliberate edit to the locked Phase-1
`registry.py` — see §4.7.)*

### 4.4 Physical provisioning (`multitenantauth/tenancy/provision.py`)
`provision_tenant(control_session, name, *, slug, dsn=None, run_physical=True)`:
1. `tenant = register_tenant(control_session, name, slug=slug, dsn=dsn, status="provisioning")` → opaque id + control row. With `dsn=None` the registry finalizes the id-derived default DSN itself (§4.3); bring-your-own-DSN callers pass `dsn` explicitly and typically `run_physical=False`. The row's DSN is correct as written — no second update pass.
2. **If `run_physical`:** idempotent `CREATE DATABASE` via an AUTOCOMMIT engine to the maintenance DB (`postgres`); skipped entirely when `run_physical=False` (managed Postgres blocks the maintenance-DB connection, so bring-your-own-DSN must skip the **whole** step, not just the CREATE).
3. **If `run_physical`:** per-tenant migrate primitive — `alembic.command.upgrade(cfg, "head")` against the tenant DSN via a programmatic `Config` (Python API, **not** a subprocess), pointing at the app `migrations/`.
4. Post-migrate hook — `provision_hook(control_session, tenant_id, tenant_session)`, **default no-op**, registered via `register_provision_hook(fn)`. This is exactly where Meridian's EDR `seed_base_vocabulary` lives — cleanly excluded from the generic battery.
5. `activate_tenant(control_session, tenant_id)`.

The flow is **non-transactional and re-runnable** by design (a DB create can't join the control transaction):
each step is idempotent (`get_tenant` short-circuits a re-register; `CREATE DATABASE` is existence-checked;
`upgrade head` is a no-op when current). A half-provisioned tenant stays `provisioning` and is safe to re-run;
SP1 does **not** attempt to roll back a partially-created physical DB (teardown is an SP3/lifecycle concern).

### 4.5 Routing deps (`multitenantauth/deps.py`)
- `active_tenant(...)` — resolve the request's tenant; **fail-closed and identical** for unknown / non-active / non-member: all return the same `404` (never `403`, never a leak of existence). Lifted from Meridian's validated dep.
- `tenant_db(tenant_id=Depends(active_tenant), cs=Depends(control_session)) -> Session` — opens `tenant_session(tenant_id, control_session=cs)` for the request. Lazy: the engine is created on first use and cached.
- Composes with the existing Phase-1/DV-5 authz dep — routing resolves the tenant, authz gates the action; neither is bypassed.

### 4.6 Observability
OTel spans on `resolve_dsn`, engine create/evict, and each `provision_tenant` step (tenant id as an
attribute; **DSN/credentials never recorded** — `never-log` is a hard rule). Gauges
`app_tenant_engines_cached{endpoint}` and `app_tenant_pool_checked_out`, wired through the battery's existing
`metrics.py` and the obs-completeness guard (`battery.obs`).

### 4.7 Integrity-lock impact (mechanism stays locked)
The Phase-1 mechanism is **integrity-locked** (`integrity/classes.py:BATTERY_LOCKED_SRC`): `tenancy/registry.py`,
`db/control/repository.py`, `db/control/engine.py`, `multitenantauth/deps.py`, etc. `tests/integrity/
test_auth_mechanism_lock.py` walks the rendered tree and **fails if any mechanism file is missing** from that
list — so SP1 must keep the lock complete:
- **New mechanism files** — `db/tenant/engine_registry.py`, `db/tenant/engine.py`, `db/tenant/__init__.py`, `multitenantauth/tenancy/dsn.py`, `multitenantauth/tenancy/provision.py` — are added to `BATTERY_LOCKED_SRC` (gated on `multitenantauth`), and the manifest is regenerated (`build_manifest`). Forgetting one fails `test_auth_mechanism_lock.py` (fail-safe).
- **Edits to locked Phase-1 files** — the optional-`dsn` change in `registry.py` (§4.3) and the routing deps added to `deps.py` (§4.5) — are deliberate mechanism re-touches; their checksums regenerate. They are covered by the branch's Phase-2 Layer-2 adversarial review (§9), the same gate the DV-5 seam edit went through. *(DEC-0003 already anticipates this: "Phase 2 re-touches the same mechanism under its own Layer-2 review.")*
- **The consumer seams stay open without unlocking anything** — `register_tenant_dsn_resolver` (§4.2) and `register_provision_hook` (§4.4) are registered from the consumer's **unlocked** `create_app()`, exactly as the DV-5 `register_authz_resolver_factory` seam is. Locking the mechanism does not block the documented customization points.

## 5. Data flow

**Request:** route → `active_tenant` (membership/active check, fail-closed 404) → `tenant_db` →
`tenant_session` → `resolve_dsn` (cache → control row by default) → registry get-or-create (budget-checked) →
request-scoped `Session` → handler → close.

**Provisioning:** `provision_tenant` → register (control tx) → [skippable] CREATE DATABASE → per-tenant
`upgrade head` → post-migrate hook → activate. Idempotent at each step.

## 6. Error handling (fail-closed everywhere)
- Unknown / non-active / non-member tenant → identical `404` (no existence/role leak).
- `resolve_dsn` raises / returns non-string → deny the route.
- `validate_endpoint_budget` can't probe or would exceed budget → refuse engine creation (deny), never silently over-allocate.
- Provisioning is idempotent; a mid-flight failure leaves the tenant `provisioning` (never `active`), re-runnable. No partial-DB rollback in SP1.
- Credentials/DSNs are never logged or put in span attributes.

## 7. Secrets posture (decided: match + seam)
Ship Meridian's validated posture — the DSN (with credentials) lives in the control-row column and is read
back via `get_tenant_dsn` — plus the thin `resolve_dsn` injection seam and `never-log` hygiene. A **real**
secrets backend (vault retrieval, rotation, field-encryption / crypto-shred) is **deferred to the
Secrets-backing Horizon item** (PLAN.md:56). SP1 stays *routing*; Meridian deletes its fork without a posture
change; the seam's contract is pinned here so the future item is a drop-in. *(Rationale: raising the bar now
would turn SP1 into a secrets project and add Meridian adoption friction — rejected.)*

## 8. Conformance contract (drift-aware split)
The conformance suite gates Meridian's fork-deletion (per DEC-0003 / the SP1 PUR). Meridian's write path
broke **invisibly** because its real-Postgres tests were skip-gated *and* stale (§11) — SP1 must not recreate
that failure mode:
- **Pure-unit, runs everywhere:** `TenantEngineRegistry` LRU/eviction, budget math, DSN-cache TTL/invalidation, `default_tenant_dsn` name-swap, `resolve_dsn` default + seam override + fail-closed. No Postgres needed.
- **Real-Postgres acceptance tier (`render-complete`, never skip-neutral):** tenant **isolation** (a write under tenant A is invisible to tenant B), end-to-end **provisioning** (CREATE DATABASE → migrate → hook → activate → route), and the fail-closed routing 404s. These inherently need real Postgres, so they go in the CI tier that runs Postgres and **cannot be skipped** — not a docker-gated tier that degrades to a silent pass.
- Provisioning conformance is **seeded from intended behavior + Meridian's validated read-path**, *not* from Meridian's current (broken) write-path.

Green = the generalization preserved what the reference impl relied on, and the suite would have caught the drift that Meridian's didn't.

## 9. Testing strategy
TDD throughout (red → minimal green). Unit tests for every registry/budget/cache/dsn/seam branch; real-Postgres
acceptance for isolation + provisioning + routing; obs-completeness guard extended for the new gauges;
`render-complete` exercises the rendered project's own suite. Template-payload TDD loop per
`[[template-payload-tdd-loop]]` (render → uv sync → mirror → pytest in the generated project; ruff-format-check
the rendered output). A Phase-2 Layer-2 adversarial security pass (like Phase 1) gates the branch, scoped to
the routing/provisioning surface.

## 10. Phase-1 preconditions (tracked, land in SP3)
Recorded at Phase-1 close, deferred to SP3 (each gates a specific future route, none gates SP1's routing core):
DB-level ≥1-admin guard (before any erasure/teardown route); `AuthzEvent.resource_id` + resource-grant audit
completeness (before a resource-grant route); `tenant_slug_history` reaping (before a `rename_slug` route);
the next-pass Layer-2 cells (migration data-safety; id↔slug desync).

## 11. Meridian drift finding (recorded as promote-up evidence)
Verified directly against Meridian source (`~/Claude Code/Projects/meridian`):
- `db/tenancy/provision.py:67-69` calls `control_repo.add_tenant(cs, id=…, name=…, dsn=…, status=…)` with **no `slug`**, but `repository.add_tenant(*, id, name, slug, dsn, status)` requires it → guaranteed `TypeError`.
- `db/tenancy/migrate_all.py:13` imports `all_tenant_dsns` from `control.repository`, which **does not exist there** → `ImportError`.
- Both survived because Meridian's real-Postgres tests are docker-gated **and** stale.

The engine/budget **core** is unaffected and validated. This is a real Meridian bug (to relay to Meridian, operator-gated) and **evidence for the promote-up**: adopting the battery deletes the broken module. A clean inversion of `[[meridian-is-the-de-facto-integration-test]]` — this time the absorber's scrutiny caught the generator's bug. It also fixes the conformance-seeding rule in §8 (seed from intended behavior, not Meridian's current write-path).

## 12. Generalization decisions (the calls, as settled)
- **Lift the validated engine/budget/registry core; rebuild provision/migrate on the battery registry** (don't lift the drifted modules).
- **Secrets: match + seam**, real backend deferred to Secrets-backing (§7).
- **Topology: one server you own + idempotent `CREATE DATABASE`**, with the *entire* physical-create step skippable/injectable for managed-Postgres / bring-your-own-DSN.
- **Count-only LRU** eviction (no idle/TTL tier).
- **alembic via the Python API**, not a subprocess.
- **OTel spans + per-endpoint gauges** added (the surface Meridian lacked).
- **Drift-aware split conformance**, real-PG tier never skip-neutral.
- Product-specific **excluded**: `seed_base_vocabulary` (→ the no-op hook), `db/edr/**`, `seed_self.py`, the `meridian_tenant_` prefix (→ parametrized).

## 13. References
- Phase 1 / promote-up: `docs/superpowers/decisions/DEC-0003-multitenantauth-promote-up.md`; specs `2026-06-23-fwk58-…` + `2026-06-25-fwk62-…`.
- Meridian validated shape (read directly, MDN busy): `meridian` `db/engine_registry.py`, `db/tenancy/dsn.py`, `db/engine.py`, `auth/deps.py` (validated); `db/tenancy/provision.py`, `db/tenancy/migrate_all.py` (drifted — §11).
- FWK63 residuals folded into SP3: scorecard `docs/superpowers/eval-scorecards/2026-06-25-fwk62-dv5-resolver-seam-security-review.md`.
- Cross-repo convention: vendored `cross-repo-convention.md` (`CROSS-REPO-convention: v4`).
