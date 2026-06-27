<!-- CROSS-REPO-convention: v4 -->
# Promote-Up Record — `multitenantauth` Phase 2 / SP2 (plane-aware migrate / deploy / rollback)

> Sub-record of the multitenantauth promote-up ([`DEC-0003`](DEC-0003-multitenantauth-promote-up.md)),
> scoped to **FWK61 Phase 2, SP2 / FWK66** — plane-aware migrate / deploy / rollback. Sibling of
> [`DEC-0004`](DEC-0004-multitenantauth-phase2-sp1-routing-promote-up.md) (SP1, the routing core). Per the
> vendored [`cross-repo-convention.md`](../../../cross-repo-convention.md) (`CROSS-REPO-convention: v4`).
> Roles unchanged: **generator = meridian** (validated reference impl), **absorber = swiftwater-framework**.
> Design detail lives in `docs/superpowers/specs/2026-06-25-fwk66-sp2-plane-aware-migrate-deploy-rollback-design.md`;
> this record holds the cross-repo dimension only.

## Status

**`designed` (spec approved 2026-06-25; build pending).** The generalization decisions below are settled and the
absorber's design is approved; implementation (subagent-driven, TDD) follows. This sub-record advances the parent
DEC-0003 promote-up (still `in-migration`) toward Phase-2 completion — it does **not** change the parent's status,
and it does **not** move anything to `adopted`. Meridian's async confirmation is requested against this record (see
*Generator confirmation*); the absorber proceeded by reading Meridian's code directly this round (MD busy), but this
PUR is the durable artifact future coordination uses.

## Source / generator

- **Repo:** `meridian` (`~/Claude Code/Projects/meridian`), Phase-2 migrate/deploy read directly (MD busy; one-time
  exception, consistent with SP1).
- **Capability promoted:** **plane-aware migration fan-out** (control-first → default business DB → every active
  tenant DB), the plane-aware container **boot wiring**, and the plane-split **seed** ordering — plus the **CD
  deploy/rollback semantics** that Meridian reasoned through (its `DEPLOY.md` / MDN46 / MDN59 hazard analysis) but
  never wired.

## What is validated reference vs. designed-fresh

- **Validated reference (Meridian built + runs it):** `db/tenancy/migrate_all.py::upgrade_all()` (control-first,
  then a fan-out over `active` tenant DSNs, returning a per-target result map); `scripts/entrypoint_tenancy.sh`
  (control → fan-out → seed on boot); `scripts/seed.py` (plane-split). The framework re-implements the *behavior*
  on its own SP1 Python-API primitive (`migrate_tenant`), not Meridian's `alembic -x dsn=…` **subprocess** shape.
- **Designed fresh (informed by Meridian's hazard analysis, not its code):** the **CD deploy/rollback** semantics.
  Meridian's `DEPLOY.md` documents the MDN46 hazard — that after the MDN34 cutover a CD rollback would
  `alembic downgrade` the *control* DB (irreversible auth/customer-data loss) — and that `strategy.sh` /
  `entrypoint` / CD were **not yet plane-aware**. Neither repo had wired the fix. The framework designs it:
  **image-only rollback under the battery (no schema downgrade on any plane), gated by the expand-only contract,
  with contract migrations as an explicit rollback floor.** Meridian can adopt this in turn.

## What was specialized (reference-impl assumptions NOT promoted)

- The **subprocess** alembic invocation (`alembic -x dsn=…`) → replaced by the Python-API `migrate_tenant` primitive
  (SP1's choice; consistent driver across the battery).
- Meridian's repurposing of `database_url` **as** the control plane → NOT adopted. The framework keeps
  `database_url` as the **live default business DB** and `control_database_url` (co-located by default) as control,
  so the framework's forward sequence is **3-step** (control → default → tenants), where Meridian's is 2-step.
- `seed_base_vocabulary` / EDR seed ordering → stays the generic no-op post-migrate hook (SP1 decision; unchanged).
- The fixed migrate ordering with no failure map → generalized to control-fail-fast + tenant-best-effort + a typed
  result map + non-zero exit.

## Generalization decisions (the calls, as settled)

- **Rebuild the fan-out on SP1's primitive; do not lift Meridian's module.** `upgrade_all()` is new framework code
  over `migrate_tenant` + a new `active_tenant_dsns` control-repo function.
- **3-step forward sequence** (control-fail-fast → default `database_url` → active-tenant fan-out, best-effort,
  non-zero exit on any failure). Sequential, not parallel (YAGNI; future concurrency knob keeps the result-map
  contract).
- **Image-only rollback under the battery** — no `alembic downgrade` on any plane; rely on the framework's
  expand-only contract (`scripts/check_migrations.py`). **Contract migrations = rollback floor**: refuse a one-click
  rollback that crosses a `# deploy: contract` migration in *either* chain.
- **Everything gates on the `multitenantauth` battery.** A render without the battery behaves **exactly** as today
  (`strategy.sh` byte-identical; `db:migrate`/entrypoint unchanged). The single-DB rollback posture is deliberately
  **not** reopened.
- **`check_migrations.py` scans both chains** (app + control) — closes the SP1-scorecard latent follow-up; the
  contract-floor logic needs both chains' markers to be authoritative.

## Migration sequence (upstream-first)

1. **Generalize in the absorber first** — SP2 build per the approved spec (this step, pending).
2. **Conformance suite (drift-aware), seeded from intended behavior + Meridian's validated read-path** — see below.
3. **Ship tagged** — SP2 lands in a Phase-2 release (with SP3 or incrementally; TBD at build time).
4. **Generator adopts + deletes its fork** — Meridian re-points migrate/boot at the battery, adopts the image-only
   plane-aware rollback (closing its own MDN46), gated on the conformance suite.
5. **Roll the parent DEC-0003 toward `adopted`** — only once Meridian's fork (auth + routing + ops) is fully
   deleted.

## Conformance contract (drift-aware)

Gates Meridian's migrate/deploy fork-deletion. **Seeded from intended behavior + Meridian's validated read-path:**
- **Pure-unit (runs everywhere):** result-map shape; control-first ordering + control-fail-fast; tenant best-effort
  + non-zero exit; contract-floor detection across both chains; `active_tenant_dsns` = active-only.
- **Real-Postgres acceptance tier (`render-complete`, never skip-neutral):** fan-out brings control + default +
  every tenant DB to head with isolation intact; a broken tenant is flagged in the map while the rest migrate
  (non-zero exit). The never-skip-neutral tier is load-bearing — a skip-degraded fan-out test is exactly what hid
  Meridian's earlier drift.
- **Non-battery render:** `strategy.sh` byte-identical; deploy/migrate behavior identical.
- **Phase-2 Layer-2 adversarial security pass** scoped to migrate/deploy/rollback (incl. the migration-data-safety
  cell), like Phase 1.

## Drift-note correction (vs. DEC-0004)

DEC-0004 recorded Meridian's Phase-2 **write path** as broken (`provision.py` `add_tenant` missing `slug` →
`TypeError`; `migrate_all.py` importing the absent `all_tenant_dsns` → `ImportError`). **Re-read 2026-06-25:** both
are **fixed** — Meridian's `migrate_all.py` now queries `Tenant` directly (`select(Tenant.dsn).where(status ==
"active")`), `provision.py` passes `slug`, and the plane-aware boot/seed all work. The DEC-0004 drift finding is
therefore **superseded** for the migrate fan-out: it is a *validated* reference, not broken code. The genuinely
unwired part on Meridian's side is the **CD deploy/rollback** (their open MDN46) — which is exactly the
designed-fresh half above. This does not change the absorber's plan (we rebuild on our own primitive and seed
conformance from intended behavior regardless of Meridian's code state) — only the cross-repo framing is corrected,
recorded here so DEC-0004's stale note does not mislead future coordination.

## Generator confirmation (requested)

Meridian to confirm, async, against this record: (1) the validated fan-out/boot behavior is faithfully represented;
(2) the 3-step sequence (vs. Meridian's 2-step `database_url`-as-control) and the battery-gated image-only rollback
are acceptable for its adoption (Meridian closes MDN46 by adopting, not by patching its own `strategy.sh`); (3) the
DEC-0004 drift-note correction is acknowledged. No operator gate is open; a single-confirmation ask, not a
Negotiation Thread.

## References

- SP2 design: `docs/superpowers/specs/2026-06-25-fwk66-sp2-plane-aware-migrate-deploy-rollback-design.md`
- SP1 PUR: `docs/superpowers/decisions/DEC-0004-multitenantauth-phase2-sp1-routing-promote-up.md`
- Parent PUR: `docs/superpowers/decisions/DEC-0003-multitenantauth-promote-up.md`
- SP1 Layer-2 scorecard: `docs/superpowers/eval-scorecards/2026-06-25-fwk61-sp1-layer2-security-matrix.md`
