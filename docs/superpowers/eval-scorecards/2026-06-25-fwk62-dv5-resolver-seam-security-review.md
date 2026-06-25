# FWK62 DV-5 — pluggable authz-resolver seam, focused security review (scorecard)

**Date:** 2026-06-25  ·  **Branch:** `fwk62-resolver-seam-v041`  ·  **Reviewed commit:** `9db22b7` (the seam as shipped)  ·  **Method:** focused all-Opus adversarial review of one injection point — the DV-5 `resource_grant` seam on the integrity-LOCKED `multitenantauth/deps.py` — white-box, pre-merge.

**Run:** Workflow (all-Opus / high-effort, every stage) — 6 attack lenses → triage → default-to-refuted verify → synthesis. 12 agents, 685,725 tokens, ~14 min. Reviewed a clean render of `--with multitenantauth` at `/var/tmp/fwk-demo-render`; reviewers read the RENDERED `deps.py`, `authz/expr.py`, and `tests/functional/test_auth_deps.py` and traced each finding to primary source.

Scope was deliberately narrow because the change is narrow: a single injection point (`register_authz_resolver_factory` → adapter → `resource_grant`), with `subtree_exists` left inert/non-overridable (A-F10). The grant-via-ancestor reachability lens was mandatory (MD's request) and ran as attack lens #1.

## Merge-gate verdict

**0 confirmed Critical/High → GATE: PASS.** 5 raw findings across 6 lenses; triage promoted 4 (t1–t4); the default-to-refuted Opus verify stage refuted **all four** as concrete battery breaks (each `refuted=true, mechanism_verified=false`); 0 survivors. The CONFIRMED bar (`refuted=false AND mechanism_verified=true`) was met by nothing.

### Invariants independently re-verified (HOLD)

- **I3 fail-closed completeness** — the factory slot is set to `_deny` BEFORE the factory call (`deps.py:254`); factory raise / non-mapping / absent-key, and adapter missing-id / resolver-raise / non-callable value, all DENY (403), never 500/allow. Pinned by tests `test_auth_deps.py:790-855`.
- **I4 404-before-403** — the factory is consulted only when `factory is not None AND active_tenant_id is not None` (`deps.py:248`); `active_tenant_id` is set only after the membership-404 precondition (`deps.py:197-211`). `test_nonmember_is_404_before_the_factory_is_ever_consulted` asserts the factory `called == 0`.
- **I2 cross-tenant** — the flat default binds `membership_id`-AND-`resource_id` structurally (`deps.py:221-243`); the factory receives the resolved, membership-gated tenant (`deps.py:256`), so its closure can scope grants to one tenant.
- **I5 blast radius** — `subtree_exists` is hardcoded `_deny`; a factory's `subtree_exists` key is ignored (`deps.py:274`, test `770-787`); tenant/platform authz untouched.
- **I1 over-grant** — the seam REPLACES `resource_grant` by design; the locked evaluator passes the discrete `path` dict, never a re-parsed composite (`expr.py:148-155`, A-F1 preserved).

## Promoted findings (t1–t4) — all REFUTED, none gate-blocking

Disposition key: **HARDEN-FOLLOWUP** = real latent property, defense-in-depth, tracked as a follow-up (not reachable on the shipped artifact) · **DOC** = documentation/sample · **NO-ACTION** = refuted, no residual.

### [t2] Adapter + flat default key on a hardcoded `resource_id`; a two-distinct-resource route would over-grant on its secondary resource
- **Verify verdict:** REFUTED (residual Low)  ·  **Disposition:** HARDEN-FOLLOWUP
- **The real code characteristic (true):** the evaluator computes the per-leaf bound resource (`expr.py:142`) but discards it on the resource-grant branch; both the adapter (`deps.py:109`) and the flat default (`deps.py:218`) key on a hardcoded `resource_id`. A consumer-authored `ALL(Perm(on='.../resource:{resource_id}'), Perm(on='.../resource:{other_id}'))` route would silently over-grant on `other_id`.
- **Why refuted:** not reachable on the shipped artifact — no such route exists; the seam contract is explicitly single-resource (`deps.py:53-57`); and it **equally affects the flat default** (`deps.py:218` keys identically), so it is a pre-existing evaluator/resolver property, **not seam-introduced**. This is the only fail-OPEN direction in the residual set.
- **Hardening (deferred, follow-up):** a **fitness test** (additive, non-locked, ships to consumer CI) — mirroring the recursive wildcard-under-ALL guard at `authz/expr.py:52-78` — requiring any resource-scoped Perm leaf (`/resource:` in `on`) to bind the canonical `resource_id` param; OR have the evaluator pass the per-leaf bound resource (`expr.py:142`) to `resource_grant`. **Not landed in v0.4.1:** the in-locked-mechanism option (construction-time guard / evaluator change) would alter the grant-path mechanism *after* this review blessed `9db22b7`, so the fitness-test form is the only acceptable shape and it is tracked as a follow-up.

### [t1] Seam delegates the resource→tenant ownership binding to the consumer (no battery-side membership_id-AND-resource JOIN on the seam path)
- **Verify verdict:** REFUTED (residual Info)  ·  **Disposition:** DOC
- **Why refuted:** a structural downgrade *only* on the seam path vs the flat default's JOIN, but with no factory registered (the default) the flat `_resource_grant` enforces the tenant binding structurally; on the seam path the factory closure holds the resolved membership-gated tenant, so a correct consumer resolver scopes to one tenant. No reachable cross-tenant break on the shipped battery.
- **Doc (deferred, follow-up):** ship a sample correct consumer resolver that scopes `resource_id` by the closure tenant (`cs` + `active_tenant_id`) to make the delegated-grant contract (`deps.py:53-70`) concrete and shrink the cross-tenant footgun surface.

### [t3 / t1-doc] Membership-404 precondition keys on the literal `'tenant_id'` param; a differently-named tenant placeholder silently skips the seam
- **Verify verdict:** REFUTED (residual None)  ·  **Disposition:** DOC
- **Why refuted:** `deps.py:186` computes `needs_tenant = "tenant_id" in authorized.resource_params()`. A route naming the tenant placeholder differently is **fail-closed** — uniform 403, no leak — it just silently skips the seam. No over-grant, no information disclosure.
- **Doc (this branch):** documented in the spec that a consumer's tenant placeholder MUST be named `tenant_id` (added to the DV-5 spec section, NOT the locked `deps.py`). Generalizing `needs_tenant` detection is a possible follow-up.

### [t4] Factory invoked before `platform_perms` is computed; a factory writing `PlatformRoleAssignment` rows could influence platform authz under autoflush
- **Verify verdict:** REFUTED (residual None)  ·  **Disposition:** HARDEN-FOLLOWUP
- **Why refuted:** the ordering is real (`deps.py:256` factory call precedes `deps.py:270` `platform_permissions`), but it is **not request-reachable** — only trusted startup registers a factory; resolvers are read paths. Below the threat model.
- **Hardening (deferred, follow-up):** compute `ctx['platform_perms']` BEFORE invoking the factory — a cheap ordering change that removes the privilege-influence adjacency. **Not landed in v0.4.1:** it is a locked-`deps.py` edit and would change the reviewed mechanism post-review; tracked as a follow-up.

## Why no hardening lands in v0.4.1

The all-Opus gate blessed the locked mechanism (`deps.py`, `authz/expr.py`) exactly as shipped at `9db22b7`. The t2 and t4 in-mechanism hardenings would change grant-path code the review never saw — either forcing a re-review (scope balloon) or shipping unreviewed mechanism (undercutting the gate). All three residuals are non-reachable on the shipped artifact (t2 additionally is pre-existing and equally affects the flat default), so they are correctly defense-in-depth, not release blockers. They are bundled into one hardening follow-up (`PLAN.md`), with the only acceptable in-code form being the **additive, non-locked fitness test** for t2. The t3 tenant-naming note (documentation, not mechanism) is added to the spec on this branch.

**Net:** merge gate = **0 confirmed Critical/High, mechanism-verified.** Ship v0.4.1 on the PASS; t2/t4/t3-sample tracked as a hardening follow-up.
