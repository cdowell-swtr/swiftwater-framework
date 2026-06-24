# FWK58 multitenantauth — Layer-2 adversarial security review (scorecard)

**Date:** 2026-06-24  ·  **Branch:** `fwk58-multitenantauth-spine`  ·  **Method:** Meridian two-layer adversarial security review, Layer-2 stance×focus matrix (white-box, pre-merge).

**Run:** Workflow `wf_45a9ca5e-b6d` — 3 baseline + 13 matrix cells + triage + default-to-refuted verify + synthesis (18 agents, ~1.42M tokens, ~33 min). Reviewed a clean render of `--with multitenantauth` at `/var/tmp/fwk58-review`.

## Merge-gate verdict

**Open Critical/High: 0 → GATE SATISFIED.** The triage adjudicated all 28 raw findings as Medium or below; the five Crit/High hypotheses (A leak, F CSRF lenient, E/H ≥1-admin, G login DoS) were each refuted to Medium with concrete reasons.

## Meridian oracle reconciliation

Reconciled against Meridian's six threat-model oracle items for this auth + tenant-isolation cutover:

1) Session/CSRF integrity — COVERED. Baseline-security + breakin-F1 + harden-F1 exercised the CSRF middleware and session cookie. Result: the lenient no-Origin/no-Referer branch (finding F) is a documented MDN38 deferral with no working modern-browser repro → Medium, not a gate blocker. Cookie-deletion hygiene (finding B) surfaced as Low.

2) 404-before-403 — COVERED implicitly and HELD. The member routes (tenants.py:182-184, add_member 147-149) return 404 'not found' before the authz guard's 403 surface where appropriate, and the guard(Perm(...)) decorators gate before handler logic. No finding contradicted the 404-before-403 ordering; treat as confirmed-clean.

3) Cross-tenant via id/slug desync — COVERED. breakin-F3 + disrupt-F4 (cluster I) examined resolve_slug / tenant_slug_history. Result: correctness holds but depends on an un-asserted live-before-history ordering and stale rows are never reaped (Low). No exploitable cross-tenant desync found; recommend the explicit regression test in finding I.

4) >=1-admin TOCTOU lock — COVERED, with two distinct residuals. The application-layer guard (_assert_not_last_admin) holds in a seeded deployment. Residual E (fail-OPEN when admin role unseeded, Low — unreachable when seeded) and residual H (no DB-level enforcement; CASCADE could orphan the last admin, Medium — not Phase-1-reachable, no delete route). The pure concurrency TOCTOU window on the lock itself was reviewed but produced no confirmed Crit/High repro.

5) Migration data-safety — COVERED. damage-F5 caught the control-env autogenerate catch-all (finding R, Low) — a latent DROP vector for app-side objects on a co-located DB, inert today. No data-destructive migration confirmed.

6) Fail-closed posture — COVERED. Default-empty allowlists (CSRF, signup) fail closed; prod gates signup to 404; pepper presence is enforced at startup. Residual fail-open hardening items: E (admin-role-None), K (pepper min-length), J (unused effective_permissions union).

UNDER-COVERED vs oracle: (a) The DB-level >=1-admin enforcement (item 4 / finding H) is the weakest-covered oracle item — our matrix confirmed the app-layer guard but only flagged the missing DB-level stop as a hypothesis, not a tested control; this should be an explicit Meridian precondition before any erasure/account-deletion route. (b) Resource-grant audit completeness (finding Q) sits adjacent to oracle items 4/6 and was caught by only one cell (damage-F4) — single-reviewer coverage; worth a second look when assign_resource_role gets a route. No oracle item was missed entirely.

## Findings (deduped, all Medium/Low — none gate-blocking)

Disposition key: **FIX-NOW** = cheap real bug/fail-open/latent-drop, fix before merge · **DECISION** = posture call for the maintainer · **PHASE-2** = precondition flagged for the deferred phase · **DEFER** = noted, low value now.

### [A] provision_tenant 409 body leaks the colliding tenant's opaque tenant_id (and slug-cooling state) via str(exc)
- **Severity:** Medium  ·  **Disposition:** FIX-NOW
- **File:** `src/.../multitenantauth/routes/tenants.py:86-88`
- **Recommendation:** Mirror the signup path's generic collision message (_GENERIC_SIGNUP_COLLISION): on the ValueError-collision branch raise HTTPException(409, detail='tenant slug unavailable') instead of detail=str(exc). Regression test: POST /tenants with a known live slug as a platform admin and assert the 409 body contains neither the live tenant_id nor any cooling-window detail.

### [F] CSRF middleware allows mutating cookie-auth requests when both Origin AND Referer are absent (documented lenient mode)
- **Severity:** Medium  ·  **Disposition:** DECISION
- **File:** `src/.../multitenantauth/csrf.py:52-53`
- **Recommendation:** Track the double-submit-token completion (MDN38) as the canonical close; in the interim consider rejecting mutating cookie-auth requests that carry neither Origin nor Referer unless an explicit same-origin double-submit token is present. Document the residual reliance on browsers always sending Origin. Keep MDN38 in scope (it is not on the brief's out-of-scope list).

### [G] Login endpoint has no rate limiting — argon2id verify reachable unauthenticated in prod
- **Severity:** Medium  ·  **Disposition:** DECISION
- **File:** `src/.../multitenantauth/routes/auth.py:217-240`
- **Recommendation:** Document the assumed proxy/infra rate-limit dependency in the battery's ops notes, and/or set uvicorn --limit-concurrency plus a lightweight per-IP login throttle. Regression test (smoke): assert a documented rate-limit/concurrency control is wired for the login route in the rendered project's prod config.

### [H] ≥1-admin invariant is application-layer only — CASCADE would orphan the last admin
- **Severity:** Medium  ·  **Disposition:** PHASE-2
- **File:** `src/.../multitenantauth/authz/service.py:72-103; db/control/models/tenant.py:115-120; db/control/models/authz.py:103-105`
- **Recommendation:** MUST-CLOSE before any GDPR-erasure or account-deletion route ships: add a DB-level guard (e.g. trigger or RESTRICT on the sole-admin assignment) or route all user deletions through remove_member(). Flag explicitly to Meridian as a precondition for Phase-2 erasure work.

### [M] Two-pool connection budget under-documented in .env.example (~15 documented vs ~30 actual)
- **Severity:** Medium  ·  **Disposition:** FIX-NOW
- **File:** `.env.example:18; db/engine.py:11; db/control/engine.py:21`
- **Recommendation:** Update .env.example to document that each engine inherits QueuePool defaults (pool_size=5 + max_overflow=10 = 15) so the co-located default is ~30 connections/process; advise sizing Postgres max_connections accordingly to avoid correlated control+data-plane exhaustion.

### [B] logout delete_cookie omits domain/secure flags → stale browser cookie, persistent 401 loop
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `src/.../multitenantauth/routes/auth.py:268`
- **Recommendation:** Pass domain=settings.session_cookie_domain and secure=settings.session_cookie_secure to response.delete_cookie() so the browser honors the deletion (RFC 6265). Server-side session is already deleted, so no hijack risk — this is a UX/loop fix.

### [C] provision_tenant maps bad-charset slug ValueError to 409 instead of 400
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `src/.../multitenantauth/routes/tenants.py:86-88`
- **Recommendation:** Split the ValueError subtypes (charset-validation → 400, slug-collision → generic 409) as the signup route already does.

### [D] DomainMismatchError not caught in grant_role/revoke_role_route → uncaught 500 instead of 400
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `src/.../multitenantauth/routes/roles.py:49-72`
- **Recommendation:** Add except DomainMismatchError → 400 in both grant and revoke routes (it inherits AuthError, not ValueError, so the existing clause misses it). Domain guard fires before any DB write, so this is error-surface only.

### [E] _assert_not_last_admin fails open when admin_role_name resolves to None
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `src/.../multitenantauth/authz/service.py:82`
- **Recommendation:** Fail closed: raise if admin_role_id is None rather than letting the predicate degrade to role_id IS NULL (which matches nothing and silently bypasses the guard). Add a regression test that an unseeded admin role causes remove of the last member to RAISE, not pass.

### [I] tenant_slug_history rows never reaped; resolve_slug correctness depends on undocumented live-before-history ordering
- **Severity:** Low  ·  **Disposition:** PHASE-2
- **File:** `src/.../multitenantauth/tenancy/registry.py:197-214; db/control/repository.py:71-84`
- **Recommendation:** (a) Reap/expire history rows on slug reclaim; (b) add a regression test asserting resolve_slug returns the live owner for a slug that also has an expired stale-tenant history row, making the load-bearing ordering explicit. rename_slug has no Phase-1 route so attacker-driven growth is not reachable.

### [J] effective_permissions() flat-union is unused but invites domain-boundary-collapsing misuse
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `src/.../multitenantauth/authz/resolution.py:55-67`
- **Recommendation:** Delete it, or rename to signal non-enforcement intent (e.g. _debug_all_permissions), so a future caller can't wire a platform grant into a tenant-scoped Perm check.

### [K] Pepper startup guard enforces presence but not minimum entropy/length
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `src/.../config/settings.py:139-154`
- **Recommendation:** Enforce a minimum pepper length (>= 16 bytes) in verify_runtime() for prod/staging so a 1-char pepper is rejected.

### [L] dispose_control_engine can race control_session_factory at shutdown
- **Severity:** Low  ·  **Disposition:** DEFER
- **File:** `src/.../db/control/engine.py:25-42`
- **Recommendation:** Guard the resolve+lock sequence so a factory is never bound to a disposed engine. Only reachable at SIGTERM after traffic stops; not a security boundary, low priority.

### [N] Concurrent duplicate role grant races to IntegrityError → uncaught 500
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `src/.../multitenantauth/authz/service.py:114; routes/roles.py:66`
- **Recommendation:** Catch IntegrityError → 204 (idempotent no-op) or use INSERT...ON CONFLICT DO NOTHING. Data integrity is preserved by the unique constraint; only the error response is wrong (breaks the documented idempotent guarantee under concurrency).

### [O] Allowlisted-domain signup on staging is unbounded (no per-actor/total quota)
- **Severity:** Low  ·  **Disposition:** DEFER
- **File:** `src/.../multitenantauth/routes/auth.py:108-124, 148-150, 184-204`
- **Recommendation:** If operators populate signup_allowlist, document/add a per-actor or total quota. Prod/empty-allowlist fail-closed gates already bound the production surface; correctly filed Low.

### [P] provision_tenant lacks IntegrityError catch on concurrent slug race → 500 instead of 409
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `src/.../multitenantauth/routes/tenants.py:81-89`
- **Recommendation:** Mirror the signup route: add except IntegrityError → 409 so the slug-race loser gets a clean 409 (uq_tenant_slug). Robustness asymmetry, not an isolation breach.

### [Q] remove_member CASCADE drops ResourceRoleAssignment rows with no authz_event revoke (audit gap)
- **Severity:** Low  ·  **Disposition:** PHASE-2
- **File:** `src/.../multitenantauth/authz/service.py:241-247, 260; db/control/models/authz.py:166-168`
- **Recommendation:** Emit revoke events for ResourceRoleAssignment in remove_member(), and add a resource_id column to AuthzEvent so resource grants/revokes are distinguishable. Must close before a consumer wires a resource-grant route (assign_resource_role has no Phase-1 route today).

### [R] Control-env autogenerate catch-all (return True) is a latent DROP vector for app-side schema objects on a co-located DB
- **Severity:** Low  ·  **Disposition:** FIX-NOW
- **File:** `migrations_control/env.py:21`
- **Recommendation:** Replace the catch-all with explicit return False so the control migration chain manages only objects it owns. Inert today (no native enums/sequences), but a future app-side ENUM/sequence on a co-located DB could be DROPped by a control autogenerate.

## Layer-2 independent verification — load-bearing items (added 2026-06-24)

Because triage promoted 0 items to Crit/High, the matrix's default-to-refuted confirmer stage never engaged. To exercise the method's verify mechanism properly, 4 independent Opus confirmers were pointed directly at the load-bearing items (A, E, F, H) **as if Crit/High hypotheses**, default-to-refuted, white-box, with route-reachability facts established first (`remove_member` IS a live `DELETE` route; no user/role/tenant-delete, resource-grant, or rename route exists in Phase-1). **All four refuted as Crit/High** — the gate verdict (0 Crit/High) is now mechanism-verified, not triage-asserted.

- **A — CONFIRMED-MEDIUM (refuted as Crit/High).** Leak is real (`tenants.py:88` `detail=str(exc)` propagates `registry.py:68`'s `live_id`) but the opaque tenant_id is not a security boundary — every tenant route gates on `has_membership` (`deps.py:82,117`); a non-member still gets 404. The stated invariant is non-derivation (uuid4, holds), not non-disclosure. Platform-admin-only. Fix: generic 409 message.
- **E — CONFIRMED-MEDIUM (refuted as Crit/High).** Real fail-OPEN of the sole backstop on the live `remove_member` route. **Correction to the fix:** `_assert_not_last_admin` is never called when `admin_role_id` is None (the call-site `any(a.role_id == admin_role_id)` at service.py:251 short-circuits — all `role_id` are `nullable=False` UUIDs, `uuid == None` always False). Fix at the **resolution site** in `remove_member` (service.py:250) AND the guard (service.py:82): `if admin_role_id is None: raise`. Severity capped at Medium: misconfiguration-gated (`APP_ADMIN_ROLE_NAME` not matching a seeded role), self-inflicted, availability-only.
- **F — REFUTED as Crit/High → Low.** SameSite=Lax (`cookies.py:33`) + Origin exact-match allowlist (`csrf.py:58-64`) cover the real vector; Origin is never absent on a browser cross-origin mutating request (worst case `"null"` → 403). Lenient branch reachable only by non-browser clients without the victim cookie. Cheap tighten: 403 a no-header mutating cookie-auth request rather than waiting for MDN38.
- **H — REFUTED-AS-PHASE1 (valid Phase-2 precondition).** FK CASCADE wiring is real, but no live Phase-1 route deletes a user/role/tenant parent row; the two live removal routes are app-guarded. Phase-2 precondition for Meridian: promote ≥1-admin to a DB-level guard before any erasure/teardown route.

**Net:** merge gate = **0 open Critical/High, mechanism-verified.** A + E are real Mediums to fix now (E with the corrected resolution-site fix). F is a cheap Low tighten (posture call). H/Q/I are Phase-2 preconditions to record for Meridian.

## ALL-OPUS RE-RUN — authoritative (2026-06-24, run wf_7fb96f43-7bc)

The first run put the 3 baseline producers + the triage adjudicator on Sonnet (the matrix cells/verify/synth were Opus). Per maintainer direction, re-ran with **every stage on Opus/high-effort** + triage now promotes invariant-touching borderline items into verify (so the default-to-refuted stage can't be short-circuited to zero). 23 agents, ~1.59M tokens. **This run supersedes the Sonnet-tainted first run.** Triage promoted 5 (incl. a High) → the Opus verify stage actually engaged.

**Merge gate: 0 confirmed Critical/High — mechanism-verified.** The one High the matrix raised (INV-POOL-EXHAUSTION, dual ~15-conn pools on one Postgres) was **refuted to Info** by Opus verify: no amplification (1 cached conn/request, released at request end), bounded by SQLAlchemy's default 30s `pool_timeout` (not the asserted indefinite DoS), and connection capacity is outside the mechanism's named guarantees; already documented (OPS-F4).

**2 CONFIRMED Mediums (code-verified by controller):**
1. **INV-COOKIE-SECURE-GUARD-GAP** *(NEW — Opus caught what Sonnet missed)* — `verify_runtime` (settings.py:139-154) gates only on peppers; it never rejects `session_cookie_secure=false` in prod/staging. Boot prod with `APP_SESSION_COOKIE_SECURE=false` → clean boot → login sets a `Secure`-less session cookie → cleartext token to a passive observer. Operator-misconfig-gated (default True) → Medium, same fail-open class as the pepper guard. **Fix:** extend `verify_runtime` to fail-closed on `not session_cookie_secure` in prod/staging (fold in a pepper min-length floor [first-run K] while there).
2. **INV-AUDIT-SUPPRESS-RESOURCE-REVOKE** *(= first-run Q, now CONFIRMED)* — `remove_member` builds `held_role_ids` from `TenantRoleAssignment` only, but `s.delete(membership)` CASCADEs `ResourceRoleAssignment` rows (authz.py:166-167) with no revoke `AuthzEvent`. Phase-1-capped Medium (no resource-role route yet); **becomes High the moment a consumer ships resource-role routes** (the DELETE path is already live). **Fix:** enumerate resource assignments + emit revoke events before delete (role-level now; the `AuthzEvent.resource_id` column is the Phase-2 precondition).

**Controller code-verifications (resolved 2 synth discrepancies):**
- `_assert_not_last_admin` **DOES use `.with_for_update()`** (service.py:94) — the synth's "lockless, no FOR UPDATE" is WRONG; the ≥1-admin concurrent-removal race is already guarded. (A concurrent-removal *test* is still worth adding as coverage.)
- **First-run finding E (last-admin fail-open) re-confirmed in code:** `remove_member:250-251` gates the locked guard behind `any(a.role_id == admin_role_id)`; `admin_role_id=None` (misconfigured `admin_role_name`) ⇒ always False ⇒ guard skipped ⇒ last admin removable. **Fix:** fail-closed-on-None at the gate (remove_member) and inside `_assert_not_last_admin`.

**Refuted (Opus, default-to-refuted):** CSRF-sibling-tenant (path-based tenancy + 404-before-403 ⇒ no cross-tenant authority; the "sibling = other tenant" premise is fabricated — they're just multiple trusted frontend origins) · role_permission-no-DB-domain-guard (only writer is the fail-closed seed; no Phase-1 write route; raw INSERT presupposes DB creds).

**Pass-through (deduped):** add_member/grant_role 500-on-bad-role (most-reported; catch DomainMismatchError/ValueError→400) · assign_role-family dup-grant→500 (catch IntegrityError→204) · provision_tenant slug-race→500 (→409) · first-run A (tenant_id leak→generic 409), C (charset→400), B (logout cookie domain/secure), R (control autogenerate `return True`→`return False`), M (.env two-pool budget doc), password max_length comment reword.

**Meridian oracle:** 3 fully covered (session/CSRF, 404-before-403, fail-closed), 1 partial (cross-tenant: path-id yes, **slug-desync not probed**), 2 under-covered coverage gaps to add next pass — a **migration data-safety** round-trip cell and an explicit **≥1-admin concurrent-removal race test** (lock is present; lock in the property).

**Phase-2 preconditions for Meridian (record, don't fix):** H (DB-level ≥1-admin before erasure/teardown route) · Q-full (`AuthzEvent.resource_id` + resource-revoke completeness before a resource-grant route) · I (slug-history reaping + ordering test before a rename route).

**Posture calls (maintainer):** F (CSRF lenient no-header branch — cross-tenant thesis refuted; residual defense-in-depth Low; cheap optional tighten to 403) · G (login rate-limit — generic-battery posture gap; document the proxy dependency, defer in-app throttle).
