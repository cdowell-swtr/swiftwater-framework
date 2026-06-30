<!-- CROSS-REPO-convention: v4 -->
# Promote-Up Record — `multitenantauth` Phase 2 / SP1 (physical routing core)

> Sub-record of the multitenantauth promote-up ([`DEC-0003`](DEC-0003-multitenantauth-promote-up.md)),
> scoped to **FWK61 Phase 2, SP1** — the physical per-tenant routing core. Per the vendored
> [`cross-repo-convention.md`](../../../cross-repo-convention.md) (`CROSS-REPO-convention: v4`).
> Roles unchanged: **generator = meridian** (validated reference impl), **absorber = swiftwater-framework**.
> Design detail lives in `docs/superpowers/specs/2026-06-25-fwk61-sp1-physical-routing-core-design.md`;
> this record holds the cross-repo dimension only (it does not duplicate the spec).

## Status

**`in-migration` — absorber SHIPPED v0.4.2 (FWK61; spec approved 2026-06-25, build complete).** The generalization
decisions below are settled and the absorber's implementation (subagent-driven, TDD) shipped. This sub-record advances the
parent DEC-0003 promote-up (still `in-migration`) toward Phase-2 completion — it does **not** change the
parent's status, and it does **not** move anything to `adopted`. **Meridian's async confirmation is requested
against this record** (see *Generator confirmation* below); the absorber proceeded by reading Meridian's code
directly this round, with MD busy, but this PUR is the durable artifact future coordination uses.

## Source / generator

- **Repo:** `meridian` (`~/Claude Code/Projects/meridian`), Phase-2 routing read directly (MD busy; one-time exception).
- **Capability promoted:** physical per-tenant DB **routing** — a bounded, connection-budgeted engine registry; connect-time DSN resolution + tenant `Session`; idempotent physical provisioning (`CREATE DATABASE` → migrate → activate). Meridian built and ran this in production; its engine/budget core is the **validation oracle**.

## What was specialized (reference-impl assumptions NOT promoted)

- `seed_base_vocabulary` (EDR domain seeding) → excluded; its slot is the generic no-op post-migrate hook.
- `db/edr/**`, `seed_self.py` → Meridian-local product code, not promoted.
- The `meridian_tenant_<id>` DB-name prefix → parametrized (`tenant_db_name_prefix` setting).
- Caller-supplied `tenant_id` → replaced by the battery's opaque, internally-generated id (Phase-1 invariant).

## Generalization decisions (the calls, as settled)

- **Lift the validated engine/budget/registry core; REBUILD provision/migrate on the battery registry.** The validated core (per-endpoint LRU + fail-closed connection budget MDN47, DSN cache, `tenant_session`, identical-404 routing gate) is generalized as-is. Meridian's `provision.py`/`migrate_all.py` are **NOT** lifted — they have drifted and are broken (see *Drift finding*).
- **Secrets: match + seam.** Ship Meridian's validated posture (DSN in the control-row column + `never-log`) plus a thin injectable `resolve_dsn` seam. A real secrets backend is **deferred to the Secrets-backing Horizon item** (PLAN.md:56), not built into SP1. Meridian deletes its fork without a posture change.
- **Topology: one server you own + idempotent `CREATE DATABASE`,** with the *entire* physical-create step skippable/injectable so a managed-Postgres / bring-your-own-DSN consumer opts out.
- **Count-only LRU** eviction (no idle/TTL tier); **alembic via the Python API** (not subprocess); **OTel spans + per-endpoint gauges** added (the surface Meridian lacked).
- **Mechanism stays integrity-LOCKED.** New routing/provisioning modules are added to `BATTERY_LOCKED_SRC`; the consumer seams (`resolve_dsn`, `provision_hook`) register from the consumer's unlocked `create_app()`, exactly as the DV-5 authz-resolver seam does.

## Migration sequence (upstream-first)

1. **Generalize in the absorber first** — SP1 build per the approved spec (this step, pending).
2. **Conformance suite (drift-aware) seeded from intended behavior + the validated read-path** — see below.
3. **Ship tagged** — SP1 lands in a Phase-2 release (with SP2/SP3 or incrementally; TBD at build time).
4. **Generator adopts + deletes its routing fork** — Meridian re-points routing at the battery, registers its EDR seed through `provision_hook`, deletes `db/engine_registry.py`/`tenancy/*`/`auth/deps.py` routing, gated on the conformance suite.
5. **Roll the parent DEC-0003 toward `adopted`** — only once Meridian's fork (auth + routing) is fully deleted.

## Conformance contract (drift-aware)

Gates Meridian's routing-fork deletion. **Seeded from intended behavior + Meridian's validated read-path, NOT
its current write-path** (which is broken — see below):
- **Pure-unit (runs everywhere):** registry LRU/eviction, budget math, DSN-cache TTL/invalidation, `default_tenant_dsn` name-swap, `resolve_dsn` default + override + fail-closed.
- **Real-Postgres acceptance tier (`render-complete`, never skip-neutral):** tenant isolation (A's write invisible to B), end-to-end provisioning (create → migrate → hook → activate → route), fail-closed routing 404s.
- **Phase-2 Layer-2 adversarial security pass** scoped to routing/provisioning, like Phase 1.

## Drift finding (verified — evidence for the promote-up)

Meridian's Phase-2 **write path** is broken against real Postgres, hidden by docker-gated, stale tests:
- `db/tenancy/provision.py:67-69` calls `add_tenant(...)` with **no `slug`**, but `repository.add_tenant(*, id, name, slug, dsn, status)` requires it → `TypeError`.
- `db/tenancy/migrate_all.py:13` imports `all_tenant_dsns`, absent from `control.repository` → `ImportError`.

**Drift #2 — fail-OPEN connection budget in the split-control config (caught during SP1 Task 3 build, 2026-06-25).**
The lifted `engine_registry` computes `includes_control = endpoint == endpoint_of(settings.database_url)`, but the
control pool connects to `control_database_url`. Meridian's default co-locates control on `database_url`, so the
bug is latent there; in a **split-control deployment** (`APP_CONTROL_DATABASE_URL` on its own Postgres) the budget
under-counts the control pool → silent over-subscription (fail-OPEN), violating the very fail-closed invariant the
budget exists to enforce. The absorber **generalized the fix** (`endpoint_of(settings.control_database_url)`, +
split-endpoint regression test) because the framework treats control-DB separation as first-class; Meridian should
adopt the corrected resolution. A second public-API thread-safety nit (`cached_count` read outside the RLock) was
also hardened.

The engine/budget **core is otherwise validated**; these are edge-config / concurrency latents, not a broken happy
path. Both drifts **strengthen** the promote-up: adoption deletes the broken write-path module and inherits the
corrected budget resolution. A clean inversion of [[meridian-is-the-de-facto-integration-test]] — this round the
absorber's scrutiny caught **two** latent generator bugs. To be relayed to Meridian (operator-gated; absorber does
not write to the generator's repo unprompted).

## Generator confirmation (requested)

Meridian to confirm, async, against this record: (1) the validated core is faithfully represented; (2) the
match+seam secrets line and the skippable-physical-create topology are acceptable for its adoption; (3) the
drift finding is acknowledged and the broken module will be deleted on adoption (not patched-then-kept). No
operator gate is open; this is a single-confirmation ask, not a Negotiation Thread.

**RECEIVED — CONCUR (2026-06-29).** Meridian delivered a draft CONCUR in its v0.4.5 upstream-asks doc
(`docs/superpowers/assessments/2026-06-29-meridian-to-framework-v045-upstream-asks.md`), operator-gated on
that PR's merge (FWK PR #109, merged 2026-06-29) per `cross-repo-convention.md` v4. Basis: Meridian runs on
v0.4.5 today; MDN63 de-fork conformance green. Two SP1 hardening residuals are attached and accepted by the
absorber as framework follow-ups (tracked under FWK137), **not** blockers: A-4 (DSN-cache write-back not
epoch-guarded — dormant today, arms when a DSN-rotation path ships) and A-5 (engine-registry validates under
the lock + no `connect_timeout` — availability, topology-dependent).

## References

- SP1 design: `docs/superpowers/specs/2026-06-25-fwk61-sp1-physical-routing-core-design.md`
- Parent PUR: `docs/superpowers/decisions/DEC-0003-multitenantauth-promote-up.md`
- Deferred to SP3: FWK63 seam residuals — scorecard `docs/superpowers/eval-scorecards/2026-06-25-fwk62-dv5-resolver-seam-security-review.md`
