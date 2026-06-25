# Meridian → Framework: v0.4.0 adoption divergences

**Date:** 2026-06-25 · **From:** Meridian (FWK58 de-fork *generator*, first real consumer) · **Re:** adopting
v0.4.0 + `--with multitenantauth` onto a project created at v0.3.0.
**Status of delivery:** authored in the Meridian repo; delivered into the **framework repo**
(`docs/superpowers/assessments/`) via a PR from a clone — the lightweight doc-exchange, as with
`meridian-local-builds-response.md`. **FWK has not adopted the cross-repo convention yet** (it does so on
the absorber side *after* FWK58), so there is **no formal Promote-Up Record** for this de-fork. That's
fine for now, but worth flagging: now that FWK58 has shipped, the convention's intended next step is for
the framework (the absorber) to **adopt cross-repo + stand up the auth PUR** — which re-anchors the
`proposed → adopted` status and, importantly, the **gate on Meridian deleting its fork** (our copy stays
until a conformance suite passes against the shipped battery).

## TL;DR

The de-fork spine is a **strong fit** — `control_session_factory`, the opaque-id+mutable-slug tenant
registry, two-step provisioning, the named control alembic chain, and the integrity-locked mechanism all
match Meridian's validated shape, and the Layer-2 adversarial matrix passed. Adoption surfaced **six
items**, in two classes:

- **(A) The v0.4.0 *upgrade path for pre-existing projects* is under-tested** — DV-1, DV-4, DV-6. Each
  bites a project created before the new template pieces existed; the acceptance suite covers fresh
  renders / already-answered projects, not the cross-version upgrade we ran.
- **(B) One battery *design seam*** — DV-5 (hierarchical/seal authz). You've already proposed the fix
  (resolver-registration); this confirms the design and asks it ship.

Plus two by-design/minor notes (DV-2, DV-3). None blocks the spine adoption; DV-5 gates our seal-aware
authz (EDR-0004), and DV-6 gates an existing consumer's first `upgrade` against a persisted control DB.

---

## (A) Upgrade-path gaps for pre-existing projects

### DV-1 · `pi_prefix` renders empty on a pre-FWK9 upgrade — *framework bug, low severity*
`pi_prefix` is a properly-defined copier question (`template/copier.yml`, derived default
`(project_slug|upper|…)[:4]`). But `framework upgrade` of a project created **before FWK9** (no persisted
`pi_prefix` answer) renders the managed `AGENTS.md` PI block with an **empty** prefix — the upgrade neither
prompts for the new question nor applies its derived default.
- **Repro:** upgrade any v0.3.x project to v0.4.0; inspect the `AGENTS.md` PI block.
- **Expected:** prompt for the new question, or apply the derived default.
- **Test gap:** the FWK9 acceptance tests only exercise projects that already have a persisted
  `pi_prefix`; the pre-FWK9 upgrade path is untested.
- **Our workaround:** set `pi_prefix: "MDN"` in `.copier-answers.yml` (also the *correct* value — the
  `MERI` derived default would be wrong for us).
- **Suggested fix:** on `upgrade`/`update`, apply derived defaults for newly-introduced questions (or
  prompt); add an acceptance test that upgrades a project missing a later-added answer.

### DV-4 · `.pre-commit-config.yaml` duplicate key on upgrade — *framework bug, low severity*
v0.4.0 moved `conventional-pre-commit` + `default_install_hook_types` into the managed region. A project
that had previously hand-added its own copies (as we had, to wire the commit-msg stage) ends up with a
**duplicate `default_install_hook_types` top-level key → invalid YAML → `check-yaml` fails the first
commit** after upgrade.
- **Repro:** upgrade a v0.3.x project that hand-added those keys.
- **Our workaround:** removed our now-redundant copies (managed region covers them).
- **Suggested fix:** flag/de-dupe on upgrade, or call it out in release notes for upgraders.

### DV-6 · `migrations_control` reuses `c0001`/`c0002` ids with different schema — *framework bug, blocks persisted-DB upgrade*
The battery's `migrations_control` ships `c0001_control_tenant`/`c0002_auth_model` reusing those revision
ids but with **different schema** (adds `slug`, `tenant_slug_history`, resource-domain CHECK, index
drops), under a **new** version table `alembic_version_multitenantauth`.
- **Fresh control DB:** clean replay — fine.
- **Persisted control DB** (an existing consumer who already ran the older c0001/c0002): the new version
  table is empty, so `alembic upgrade head` re-runs the `CREATE TABLE`s against existing objects → fails.
  The consumer must rebuild the control DB or hand-`stamp` the new version table.
- **Suggested fix:** either don't reuse `c0001`/`c0002` ids across the schema change, or document the
  persisted-control-DB upgrade path (rebuild vs stamp). (Dev-DB-rebuildable consumers like us are
  unaffected in practice — we rebuild — but a prod consumer would be blocked.)

## (B) Battery design seam

### DV-5 · The locked `guard` has no seam for hierarchical / seal-aware authz — *design; fix already proposed*
The battery `guard` (`multitenantauth/deps.py`, integrity-LOCKED) wires a **flat** `resource_grant`
(control-DB membership only; `subtree_exists` inert). Meridian's authorization needs a **cross-plane
ancestor walk with nearest-seal-wins** (our EDR-0004 absolute-seal compartmentalization — kept local by
design). Because the mechanism is locked, a consumer can't inject it.
- **FWK's proposed fix (confirmed in dialogue) — we agree:** *finish the seam.* Expose a
  **resolver-registration API** on the locked `deps.py`, defaulting to the inert/flat resolvers, so a
  consumer registers their hierarchical-grant + nearest-seal resolver from their own **unlocked startup
  code** (no locked-file edit). Meridian's logic then runs **through** the battery guard, not alongside it.
- **Ask:** ship the resolver-registration API in a v0.4.x. It's the single thing gating our seal-aware
  authz adoption; until it lands we either hold the seal-dependent product/EDR routes or run a temporary
  local-guard stopgap we'd then delete.
- **Generalization note:** this also generalizes — any consumer with resource hierarchies / scoped
  visibility (not just Meridian) benefits from a pluggable `resource_grant`. Keep it consumer-general.

## By-design / minor (recorded for completeness)

- **DV-2 · env `stage` → `staging`.** The battery's env validator restricts to `{dev,test,staging,prod}`
  (no `stage`/`ci`); our `settings.py` used `stage`. A required local rename — **not a bug**. Suggest a
  one-line mention in upgrade notes so upgraders expect it.
- **DV-3 · `AGENTS.md` became framework-managed (FWK9).** By design; we adopted the `FRAMEWORK:BEGIN/END`
  block and moved our content to "Project notes". **Not an issue** — noted so the reconcile is on record.

---

## Context

Meridian is mid-adoption on branch `MDN61-fwk58-adopt`: base v0.4.0 upgrade is resolved + green (584
tests, integrity OK); the `--with multitenantauth` wave is planned (collapse `product`→`resource`; adopt
the spine; the seal resolver awaits DV-5's seam). Full plan + per-item detail:
`_docs/architecture/superpowers/plans/2026-06-25-fwk58-v040-wave2-reconciliation.md` and the divergence
ledger in `…/2026-06-24-fwk58-v040-reconciliation-note.md`.
