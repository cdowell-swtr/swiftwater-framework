<!-- CROSS-REPO-convention: v4 -->
# Promote-Up Record — `multitenantauth` (Meridian → swiftwater-framework)

> The post-migration source of truth for the multi-tenant identity/session/authz **promote-up**.
> Per the vendored [`cross-repo-convention.md`](../../../cross-repo-convention.md) (`CROSS-REPO-convention: v4`).
> Roles for this promote-up: **generator = meridian** (the reference implementation), **absorber = swiftwater-framework** (drives the generalization). Logged under PI as **FWK58** (Phase 1) + **FWK62** (DV-5 resolver seam); follow-ups **FWK61** (Phase 2), **FWK63** (seam hardening).

## Status

**`adopted` (2026-06-29).** Generalized and shipped in the absorber (v0.4.0 + v0.4.1); the generator (Meridian) has **adopted the battery and deleted its local auth fork**. Confirmed 2026-06-29 by direct read of Meridian on `_commit: v0.4.5`: the generic identity/session/authz chain (`current_user`/`active_tenant`/`guard`/`control_session`) is consumed from the battery, Meridian registers its seal-walk **through** the `register_authz_resolver_factory` seam (`meridian/src/meridian/main.py:99`), and only the carved-out kept-local code (`auth/deps.py::tenant_db` physical-routing seam + `product_access` RBAC/EDR compartmentalization) survives — no generic copy stands. Conformance suite (below) green at release.

Lifecycle: `proposed → in-migration → adopted → downstream-copy-deleted`. We are at **`adopted`** (downstream copy verified deleted).

> **Anti-pattern guard (load-bearing):** the convention's failure test is *"both copies exist + the PUR says `adopted` = the promote-up failed."* **Cleared 2026-06-29** — Meridian's generic auth/routing/ops/lifecycle fork is verified deleted (the surviving `auth/deps.py` is documented kept-local code, not the generalized mechanism; `db/control/models/*` are the integrity-LOCKED battery render, not a hand-written copy). The flip to `adopted` is therefore correct, not a guard violation.

## Source / generator

- **Repo:** `meridian` (`~/Claude Code/Projects/meridian`), reference impl at `meridian@e0cf9cf`.
- **Capability promoted:** multi-tenant **identity · opaque server-side session · authz mechanism · tenant registry** on a logically-separate control plane. Meridian built it first (~2-day agent build) and ran it in production; its impl served as both **reference** and **validation oracle**.

## What was specialized (the reference-impl assumptions)

Meridian's copy baked in product-specific assumptions that must NOT travel upstream:

- A concrete **RBAC policy** + role catalog tuned to Meridian's product.
- **Epistemic-governance compartmentalization** — Meridian's domain model.
- A **sealed / hidden resource-tree** resolver (EDR + physical routing + absolute-seal): a Meridian product feature, not generic mechanism.
- `ProductRoleAssignment` — a Meridian-shaped role-binding table.

## Generalization decisions

What became configurable/injected, what was dropped, what stays — as shipped:

- **Generic resource-scope (Option 1).** A `resource` role-domain replaces Meridian's `ProductRoleAssignment` (Meridian collapses its table onto the generic scope → full de-fork). The recursive grant expression evaluator is **generic mechanism** and ships; the sealed/hidden resolver behind it stays Meridian-local.
- **Control plane: logically-separate-always, physically-co-located-by-default-overridable.** `ControlBase` + `control_session_factory` + `migrations_control` with a **named** version table; `APP_CONTROL_DATABASE_URL` defaults to the app DB. (Phase 2 / FWK61 adds physical per-tenant routing.)
- **Opaque, revocable, server-side sessions** (cookie + bearer) — explicitly *not* stateless JWT (contrast deferred to FWK59 `--with auth`).
- **Tenant identity:** opaque server-side **id** decoupled from a mutable DNS-safe **slug**, with slug-history + cooling.
- **Self-contained Phase 1:** the existing `Item` demo is untouched; no `tenant_id` imposed on consumer domain models (that is FWK60).
- **Pluggable authz-resolver seam (DV-5 / FWK62).** `register_authz_resolver_factory(factory)` on `multitenantauth/deps.py`: `factory(control_session, app_user, active_tenant_id) -> {"resource_grant": (perm_name, resource_id) -> bool}`, defaulting to the flat resolver. The consumer registers its own resolver (e.g. Meridian's seal-walk) from its **unlocked** `create_app()`; the seal-walk runs THROUGH the battery guard, not alongside it. Scope cut: only `resource_grant` is overridable — `subtree_exists` stays inert/non-overridable (no shipped route uses a wildcard subtree). Fail-closed, all-logged.
- **Colonization guard — mechanism ships LOCKED.** The `multitenantauth` mechanism tree ships **integrity-locked** (the framework's first deliberate `src/` lock); policy files stay editable. Generic mechanism only — **Meridian's RBAC policy + epistemic-governance/absolute-seal stay theirs**, behind the inert `resource_grant` / `subtree_exists` hook. Shipped **multitenant-consumer-shaped, not Meridian-shaped**.

## Migration sequence (upstream-first — the order is the rule)

1. **Generalized in the absorber first** — FWK58 Phase 1 build (22 tasks across 8 phases); spec `docs/superpowers/specs/2026-06-23-fwk58-multitenantauth-defork-spine-design.md`, plan `docs/superpowers/plans/2026-06-23-fwk58-multitenantauth-defork-spine.md`.
2. **Conformance suite seeded from the generator's behavior** — see below.
3. **Shipped tagged:** `--with multitenantauth` in **v0.4.0** (PR #79 → master `4317c03`); the DV-5 resolver seam + upgrade-path fixes in **v0.4.1** (FWK62 → master `958522e`).
4. **Generator adopts + deletes its copy** — **DONE (confirmed 2026-06-29).** Meridian (on `_commit: v0.4.5`) consumes the battery, registers its seal-walk through the `register_authz_resolver_factory` seam (`main.py:99`), and deleted its auth/routing/ops/lifecycle fork; only carved-out kept-local code remains.
5. **Mark this PUR `adopted`** — **DONE (2026-06-29).** Step 4 confirmed by direct read of Meridian's repo; tracking row FWK64 closed.

Never the reverse: the generator's copy is not lifted into the absorber with both left standing.

## Conformance contract

A **code/library** capability → a conformance/behavior suite that travels with it in the absorber (not a Pact/contract-broker; there is no deployed service-to-service boundary here). Green = the generalization preserved what the reference impl relied on. The gate on Meridian's copy-deletion:

- **Rendered authz suite — 80 passed** against real Postgres (the generated project's own tests).
- **Auth-mechanism integrity lock — 5 passed** (the LOCKED mechanism tree is unmodified).
- **DV-5 resolver-seam tests** — fail-closed behavior; `subtree_exists` non-overridable (pinned by test).
- **Layer-2 adversarial security matrix** — 0 confirmed Critical/High, all-Opus, mechanism-verified (`docs/superpowers/eval-scorecards/2026-06-24-fwk58-layer2-security-matrix.md`).
- **FWK62 DV-5 focused Opus security review** — PASS, 0 survivors (`docs/superpowers/eval-scorecards/2026-06-25-fwk62-dv5-resolver-seam-security-review.md`).

## References

- Specs: `docs/superpowers/specs/2026-06-23-fwk58-multitenantauth-defork-spine-design.md`, `docs/superpowers/specs/2026-06-25-fwk62-multitenantauth-resolver-seam-and-v041-fixes.md`
- Meridian v0.4.0 adoption divergence report (DV-1..6): `docs/superpowers/assessments/2026-06-25-meridian-to-framework-v040-adoption-divergences.md`
- Mechanism tree (LOCKED): `src/framework_cli/template/src/{{package_name}}/{% if "multitenantauth" in batteries %}multitenantauth{% endif %}/`
- Deferred follow-ups: **FWK61** (Phase 2 — physical per-tenant routing + ops), **FWK63** (DV-5 seam hardening), **FWK59** (`--with auth` single-tenant sibling), **FWK60** (`tenant-data-model`).
