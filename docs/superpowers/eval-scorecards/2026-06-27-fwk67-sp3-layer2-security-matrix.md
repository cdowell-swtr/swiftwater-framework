# FWK67 SP3 — Tenant lifecycle / authz / slug / audit — Layer-2 adversarial security matrix

**Date:** 2026-06-27
**Subject:** FWK67 SP3 (`--with multitenantauth`): operator tenant-lifecycle authz (suspend / reactivate /
self-deactivate), resource-isolation membership + resource-role grant/revoke, slug rename with cooling-window
reclaim, and the append-only `TenantLifecycleEvent` / `AuthzEvent` audit trail — control-plane registry
(`tenancy/registry.py`), authz service (`authz/service.py`), and the `c0004`/`c0005` control migrations.
**Reviewed render:** clean `framework new --with multitenantauth` (package `demo`) on branch
`fwk67-sp3-authz-retouch-lifecycle`, matrix run against HEAD `c42f3bd` (the M1 symmetric-409 guard); pre-rendered at
`/var/tmp/fwk67final/demo`. The two confirmed below-the-line gaps were **fixed in-branch after the matrix** at
`0ba950c` (see "P4/P5 — the fix"); file:line evidence below is cited from the `c42f3bd` render the matrix read.
**Method:** all-Opus (`claude-opus-4-8`, effort high) stance×focus matrix (run `wf_9ae4b7ed-c98`) — 15 cells
(stances `operator-abuse / cross-tenant-attacker / dataloss-chaos` × focuses `F-LIFECYCLE-AUTH / F-RESOURCE-ISO /
F-SLUG / F-MIGRATION / F-AUDIT`) → triage adjudication (dedup + promote invariant-touching borderline items) →
default-to-refuted verify with **static-trace-primary** `mechanism_verified` (one skeptic per promoted finding) →
synthesis fed the **real serialized verify verdicts** (the SP2 `[object]` synthesis-provenance bug is fixed —
this scorecard and the workflow's own narrative agree). 23 agents, ~1.29M subagent tokens, 273 tool calls, ~21 min.
**Gate rule:** count CONFIRMED findings (`refuted=false` AND `mechanism_verified=true`) at Critical/High; **PASS iff that count is 0.**

---

## Merge-gate verdict: **GREEN — 0 confirmed Critical/High**

8 raw cell findings → 6 promoted → verified. The orchestrator's gate-of-record count of confirmed Critical/High is
**0**. No promoted hypothesis verified to a reachable Critical/High break of a crown-jewel invariant on a shipped
entrypoint (the lifecycle routes, the resource-role routes, the slug rename, or the `c0004`/`c0005` migrations).

**The GREEN is earned by severity, not by refutation — read this carefully.** Unlike a typical run, **nothing was
refuted this matrix: all six promoted findings are CONFIRMED** (`refuted=false` AND `mechanism_verified=true`). Every
mechanism checked out under static trace. The gate is GREEN **only because all six confirmed findings are Low** → 0
confirmed Critical/High. This is "six real mechanisms, all below the Crit/High line," not "a clean, mostly-refuted surface."

**Where the matrix earned its keep (the SP2-P15 lesson, applied).** Reading *every* confirmed disposition — not just
the Crit/High band — surfaced **two confirmed Low gaps that are reachable on shipped routes** and that left the
**I-AUDIT-COMPLETE** invariant **AT-RISK** on the reviewed render. Both are **fail-safe** (access control intact;
audit-log-only) so the gate stayed GREEN, but both reopened or widened an audit clause the slice is meant to hold —
so, on the operator's call, both were **fixed in-branch** before release (commit `0ba950c`), upgrading the invariant to **HOLDS-AFTER-FIX**.

| ID | Confirmed Low | Invariant | Reachability | Disposition |
|----|---------------|-----------|--------------|-------------|
| **P4** | **Phantom duplicate `suspend` audit row** — two concurrent authorized suspends both pass M1's in-Python guard and each write a `suspend` event; `deactivate_tenant`'s `s.get` took no `with_for_update` (the sibling `_assert_not_last_admin` TOCTOU does) | I-AUDIT-COMPLETE | **Shipped** (operator `/tenants/suspend` vs self `/tenants/{id}/deactivate`, one target) | **FIXED IN-BRANCH (`0ba950c`)** |
| **P5** | **Dangling `grant` with no closing revoke** — `remove_member`'s non-locking capture races a concurrent `assign_resource_role`; the membership CASCADE deletes the new grant with no revoke event (2 of 3 lock orderings) | I-AUDIT-COMPLETE | **Shipped** (DELETE `…/members/{mid}` vs POST `…/resources/{rid}/roles`) | **FIXED IN-BRANCH (`0ba950c`)** |

---

## P4 / P5 — the fix (headline)

**Mechanism (both confirmed by static trace on the `c42f3bd` render).** Both are read-modify-write TOCTOUs under
PostgreSQL READ COMMITTED with no row lock on the read:

- **P4** — `registry.deactivate_tenant` did `tenant = s.get(m.Tenant, tenant_id)` (no lock), evaluated the M1 guard
  `if tenant.status == "suspended"` in Python, then set `status="suspended"`. Two overlapping authorized suspends
  (sync handlers in the anyio threadpool, fresh `control_session` each) both read `active`, both pass the guard, both
  `record_lifecycle_event(action="suspend")`, both commit — **two `suspend` rows for one state change**, the exact
  phantom-row class M1's docstring claims to prevent. (`reactivate_tenant` carried the identical structure for
  `reactivate` rows.)
- **P5** — `service.remove_member` captured `ResourceRoleAssignment` rows via a non-locking SELECT, then
  `s.delete(membership)` CASCADE-deleted them (FK `ondelete=CASCADE`), replaying revoke events only for the captured
  set. A concurrent `assign_resource_role` committing a **new** grant inside the capture→delete window is
  CASCADE-removed with **no** revoke event → a dangling `grant` as the last audit word.

**The fix is the repo's own proven idiom — not a new mechanism.** `authz.service._assert_not_last_admin` already makes
the structurally identical ≥1-admin TOCTOU safe with `SELECT … FOR UPDATE`; SP3's lifecycle/membership mutators simply
omitted the equivalent lock. The fix adds it:

- `deactivate_tenant` **and** `reactivate_tenant` now `s.get(m.Tenant, tenant_id, with_for_update=True)` (symmetric —
  both lifecycle status-mutators). The second concurrent suspend/reactivate blocks on the first's row lock, re-reads the
  committed status, and 409s instead of writing a phantom event.
- `remove_member` now locks the membership row (`s.get(m.TenantMembership, membership_id, with_for_update=True)`)
  **before** the capture. A concurrent `assign_resource_role` takes `FOR KEY SHARE` on that parent via its FK, so it
  serializes against the delete: it blocks until `remove_member` commits, then its FK check finds the parent gone and it
  rolls back cleanly — no dangling grant.

**Verification basis (operator-accepted).** Timing races are not deterministically TDD-testable without flaky threading,
so — exactly as the matrix verified them — the fix is substantiated by **static trace + idiom-consistency with the
proven `_assert_not_last_admin` lock + a full clean-render regression**: the locks are no-ops without contention, so the
rendered project is **428/428** (full functional/real-Postgres + unit + e2e + smoke + sniff), `ruff format --check` +
`ruff check` clean, `mypy src` clean (the `with_for_update=True` `s.get` type-checks). No behavior change on any
single-request path.

**Why fixed in-branch, not deferred (operator decision).** Both are strict *tightenings* of the exact audit invariant
SP3 delivers, in security-critical locked code on this branch, with a one-idiom fix the repo already applies elsewhere;
P4 in particular reopened the M1 guarantee shipped earlier this slice. The de-fork's most security-sensitive slice
should not ship a confirmed, shipped-reachable AT-RISK audit invariant when the fix is the repo's own one-liner.

---

## Crown-jewel invariants — re-verified on the shipped surface

- **I-LIFECYCLE-AUTH (operator lifecycle transitions are authz-gated and land in an intended state) — HOLDS.**
  The authz guards are intact on every shipped lifecycle entrypoint: `platform:manage-tenant-lifecycle` on operator
  suspend/reactivate (body-carried `tenant_id` ⇒ `needs_tenant=False` ⇒ a non-member operator is reachable and a
  non-platform-admin is 403); path-scoped `tenant:deactivate` on self-offboard. The one finding here (**P1** —
  `reactivate_tenant` forcing a `provisioning` tenant to `active`) is a **state-machine completeness gap, not an authz
  bypass**, and is **unreachable on any shipped path**: every tenant-creating route commits an `active` row
  (`register(provisioning)→flush→activate_tenant→commit`; model column default `active`); no shipped caller persists a
  `provisioning` row. **HOLDS.**

- **I-RESOURCE-ISO (membership/resource-role grants confine access to the owning tenant) — HOLDS.**
  No confirmed finding breaks resource isolation. The route-layer `membership.tenant_id != tenant_id → 404` and the
  DV-5 per-leaf `{resource_id}` binding hold. The only resource-cell finding (P5) is an **audit-completeness** gap with
  the access side explicitly fail-safe (*"no cross-tenant leak, no privilege retention, no auth bypass"* — after the
  CASCADE the membership genuinely loses the role). **HOLDS.**

- **I-SLUG-INTEGRITY (lazy-delete on rename never clears another tenant's live or cooling reservation) — HOLDS (with documented limitation).**
  **P6** confirms a real mechanism — `rename_slug`'s `_assert_slug_claimable` uses non-locking SELECTs then
  `delete_slug_history(new_slug)` deletes unconditionally; the model docstring states claimability is enforced app-layer,
  not in the DB — so an extreme interleave could erase another tenant's cooling row. But it is **production-unreachable**:
  a cooling row cannot pre-exist at the check (it would raise on `is_slug_cooling`), so the attacker must land **two
  committed transactions** inside the gap between two consecutive synchronous DB calls with **no attacker-controlled
  IO/sleep**. By-design, acknowledged in the docstring → DOCUMENTED-LIMITATION. **HOLDS** on the shipped surface.

- **I-MIGRATION-SAFETY (control migrations are non-destructive; audit tables append-only) — HOLDS (with M4 forward-flag).**
  `c0004` is an additive nullable `add_column` (no backfill/narrowing), `c0005` is an append-only audit `create_table`,
  both upgrades non-destructive with present downgrades, chain `down_revision=c0004` correct, no autogenerate drift
  (migration ↔ model agree exactly). **P2** confirms the **M4 forward-flag**: `TenantLifecycleEvent.tenant_id` carries
  `ondelete=CASCADE` while `AuthzEvent.tenant_id` has no `ondelete` (RESTRICT) — an asymmetry that *would* cascade-erase
  lifecycle audit on a hard tenant delete. That delete path **does not ship** (repo-wide scan finds no Tenant-row
  hard-delete; CASCADE inert), and the `authz_event` RESTRICT would block a naive teardown first. **HOLDS** — recorded for the deferred hard-teardown slice.

- **I-AUDIT-COMPLETE (every lifecycle/authz mutation emits exactly one event; no phantom rows; grant↔revoke complete) — HOLDS-AFTER-FIX.**
  On the `c42f3bd` render this invariant was **AT-RISK**: **P4** (phantom duplicate `suspend` row) and **P5** (dangling
  `grant` with no revoke) confirmed its no-phantom-row and grant↔revoke clauses violable under concurrency on shipped
  routes. Both were **fixed in-branch** at `0ba950c` (the `with_for_update` locks above) → **HOLDS-AFTER-FIX**. The third
  finding here (**P3** — `activate_tenant` flips `suspended→active` writing no `TenantLifecycleEvent`) is reachable only
  via the module-level `provision_tenant`, which has **no shipped caller** (tests only; the route-level handler is
  distinct and 409s on an existing slug before `activate_tenant`) → recorded as a latent-landmine carry-over.

---

## Promoted findings — full disposition (gate-of-record verify verdicts)

`refuted`/`mech` = the verify agent's `refuted` / `mechanism_verified`. **All six are CONFIRMED** (`refuted=no`, `mech=yes`).
The "Inv" column uses each finding's `invariant` field (not the producing cell name).

| ID | Finding (abbrev.) | Inv | Sev | refuted | mech | Disposition |
|----|-------------------|-----|-----|---------|------|-------------|
| P1 | `reactivate_tenant` flips a `provisioning` tenant straight to `active` — no shipped path commits a `provisioning` row | I-LIFECYCLE-AUTH | Low | no | yes | NO-ACTION (carry-over) |
| P2 | `TenantLifecycleEvent.tenant_id` `ondelete=CASCADE` vs `authz_event` RESTRICT — would cascade-erase lifecycle audit on a hard tenant delete; no delete path ships | I-MIGRATION-SAFETY | Low | no | yes | DOCUMENTED-LIMITATION (M4 forward-flag) |
| P3 | `activate_tenant()` flips `suspended→active` with no `TenantLifecycleEvent`; reachable only via module-level `provision_tenant` (no shipped caller) | I-AUDIT-COMPLETE | Low | no | yes | DOCUMENTED-LIMITATION (latent landmine) |
| **P4** | **Concurrent suspends both write a phantom `suspend` row** — `deactivate_tenant` lacked `with_for_update` | I-AUDIT-COMPLETE | Low | no | yes | **FIXED IN-BRANCH (`0ba950c`)** |
| **P5** | **`remove_member` CASCADE-deletes a concurrent resource grant with no revoke event** | I-AUDIT-COMPLETE | Low | no | yes | **FIXED IN-BRANCH (`0ba950c`)** |
| P6 | Cooling reclaim is app-layer-only — rename lazy-delete can erase another tenant's cooling reservation under an extreme interleave | I-SLUG-INTEGRITY | Low | no | yes | DOCUMENTED-LIMITATION |

(Triage dropped 2 raw findings as duplicates of P2 — the same CASCADE mechanism from the cross-tenant and dataloss stances.)

---

## Documented limitations / carry-overs (recorded, non-blocking)

- **P2 — CASCADE on `tenant_lifecycle_event.tenant_id` (Low, M4 forward-flag).** Asymmetric vs `authz_event` RESTRICT;
  inert until a hard tenant-teardown ships, and the `authz_event` RESTRICT backstops a naive teardown first. →
  **Carry-over:** reconcile the two audit tables' tenant-delete behavior (append-only-preserving) when the deferred
  hard-teardown slice is designed.
- **P3 — un-audited `activate_tenant` via module-level `provision_tenant` (Low, latent).** Real audit-bypass mechanism,
  **no shipped caller**. → **Carry-over:** the moment a CLI/worker wires the module-level `provision_tenant`, the
  `suspended→active` resume becomes a reachable un-audited reactivate — emit a `TenantLifecycleEvent` from the resume
  branch before that wiring lands.
- **P6 — app-layer-only cooling reclaim (Low, DOCUMENTED-LIMITATION).** Acknowledged in the model docstring; breakable
  only via an extreme, production-unreachable interleave. → **Carry-over:** a DB-level cooling constraint or
  `SELECT … FOR UPDATE` on the history row would make it DB-enforced if a hardening DECISION is taken.
- **P1 — `reactivate_tenant` provisioning-skip (Low, NO-ACTION).** Forward-looking state-machine note; not an authz
  bypass, unreachable today. → **Carry-over:** a future async-provisioning consumer that persists `provisioning` should
  make reactivate restore the prior status (was-active vs was-provisioning) rather than force `active`.

---

## Net

**Gate GREEN: 0 confirmed Critical/High.** PASS, reported verbatim from the orchestrator's in-script gate-of-record
(not the synthesis narrative). The distinguishing fact of this matrix is that **all six promoted findings are confirmed**
(nothing refuted) — six real mechanisms, every one Low, so the Crit/High count is 0 and the merge gate is GREEN. Three
crown-jewel invariants hold cleanly (I-LIFECYCLE-AUTH, I-RESOURCE-ISO), two hold with by-design/forward-flag documented
limitations that fail safe and are production-unreachable (I-SLUG-INTEGRITY, I-MIGRATION-SAFETY). The matrix earned its
keep on **I-AUDIT-COMPLETE**: P4 (phantom duplicate `suspend` row) and P5 (dangling `grant` with no revoke) were
confirmed Low, shipped-route-reachable violations of its no-phantom-row and grant↔revoke clauses — both **fixed
in-branch** (`0ba950c`) with the repo's own `with_for_update` idiom, taking the invariant to **HOLDS-AFTER-FIX** with a
clean 428/428 regression. P1/P2/P3/P6 are recorded carry-overs. The synthesis-provenance regression from SP2 (verdicts
arriving as `[object]`) is fixed — the workflow's own narrative and this gate-of-record scorecard agree.
