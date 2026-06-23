# FWK58 — `--with multitenantauth`: the Meridian de-fork spine (Phase 1) — design

**Status:** design approved section-by-section (brainstorm complete); written spec pending user review → writing-plans next
**Date:** 2026-06-23
**Task:** FWK58 (committed to Meridian; date de-pressurized 2026-06-23 — single maintainer, no external dependency)
**Inputs:** Meridian's extraction-confirmation + incremental-de-fork responses (2026-06-23); the reference impl on `cdowell-swtr/meridian@origin/main` (pinned `e0cf9cf` as of 2026-06-23).
**Supersedes scope in:** `docs/superpowers/assessments/2026-06-22-framework-response-to-meridian.md` (which committed physical-routing+ops as inseparable — **renegotiated to two-phase** with Meridian, below).

---

## 1. Context & goal

Meridian forked an identity / session / authz / tenant-registry control plane and built it out
(MDN33/34/36/47/53/59). FWK58 extracts the **generic core** into a framework battery, built to
Meridian's validated shape, so Meridian deletes its fork and adopts the battery — and so any other
multitenant consumer gets the same spine. Meridian's impl is both the **extraction reference** and the
**validation oracle** (its ~2,360-line auth/tenancy test suite is the behavioral spec).

The guiding constraint is the **colonization guard**: the battery ships **multitenant-consumer-shaped,
not Meridian-shaped**. Meridian's RBAC *policy* and its epistemic-governance / absolute-seal
compartmentalization stay Meridian-local; only the generic *mechanism* moves.

### Two-phase de-fork (renegotiated with Meridian, 2026-06-23)

Meridian confirmed they adopt **incrementally**, spine-first, and that this is the *lower-risk* path —
the spine runs on the control session only and is routing-independent (the request chain
`current_user → active_tenant → guard` never touches a tenant DB; physical routing appears only at the
data-access boundary, two call sites). So:

- **Phase 1 (this spec):** identity / session / authz mechanism / tenant-registry on `control_session`.
  Meridian validates it in prod and deletes its fork of those.
- **Phase 2 (later spec):** physical routing + ops — `tenant_session`/`resolve_tenant_dsn`, the
  connection-budgeted `TenantEngineRegistry` (MDN47), plane-aware migrate/deploy/rollback (MDN59/46),
  physical tenant-DB provisioning. Adopted once the Phase-1 spine is proven.

Each phase is reviewed before *its* adoption (a real consumer must not run un-reviewed auth in prod).

---

## 2. Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| Q1 | Battery grain | **One battery, `--with multitenantauth`.** Internally `authn`/`authz`/`tenancy` modules mirroring Meridian's split. A single-tenant `--with auth` variant is a **deferred** future item. |
| Q2 | Control-plane placement | **Logically separate always, physically co-located by default, separable by config.** Own `ControlBase` + `control_session_factory` + `migrations_control` chain with a **named version table**; `APP_CONTROL_DATABASE_URL` defaults to `DATABASE_URL`, overridable to a separate control DB. A strict generalization of Meridian's separate-DB shape. |
| Q3 | Phase-1 invasiveness | **Self-contained.** The battery adds its own auth/tenant/authz surface + a guarded example over its *own* control-plane data. The existing `Item` demo is **untouched** (so the future single-tenant `--with auth` can share an unscoped demo). Logical `tenant_id` scoping of business data is a separate deferred item. |
| C | `product` role-domain (Meridian's ask) | **Option 1 — generic resource-scope.** The battery ships a generic `resource` role-domain (`resource_role_assignment`: subject + opaque `resource_id` + role, composite-FK pinned). Meridian collapses `ProductRoleAssignment` onto it (`resource_id = product_id`) → full de-fork. `product` naming + the `product:*` catalog stay Meridian-local. |
| — | Session mechanism | **Opaque server-side sessions** (the row is the credential → revocable), via httpOnly cookie with an `Authorization: Bearer` fallback. (The deferred `--with auth` may additionally offer stateless **JWT** — see §13.) |
| — | Form | **Library over the canonical store** (in-process; no separate auth service). |

---

## 3. Scope

### In (Phase 1)

- **Identity / session** — signup (founder), login, logout, invite + accept/set-password; opaque
  server-side sessions (cookie + bearer).
- **Tenant registry + membership** — `Tenant` (registry, opaque `dsn` routing key — **never connected
  to** in Phase 1), `TenantMembership`; register/activate/get APIs; the provisioning **two-step seam**
  (battery owns the row + `provisioning→active` status lifecycle; physical create is a consumer hook).
- **AuthZ mechanism** — `Role` / `Permission` / `RolePermission`; the three assignment domains
  (`tenant`, `platform`, generic `resource`) with composite-FK + CHECK domain integrity; the recursive
  permission-expression evaluator; domain-split grant resolution; the grant/revoke service with the
  ≥1-admin invariant and append-only `AuthzEvent` audit; the `current_user → active_tenant → guard`
  request chain with **404-before-403**.
- **A minimal generic seed** — ~2 example permissions + ~2 example roles, as a worked starting point.
- Template integration: control plane wiring, `migrations_control` chain, settings, obs, render +
  acceptance, integrity + FWK29 classification, a release.

### Out — deferred to Phase 2

Physical routing (`tenant_session`, `resolve_tenant_dsn`, `TenantEngineRegistry` + connection
budgeting), plane-aware migrate/deploy/rollback, physical tenant-DB provisioning (`create_database` +
fan-out migrate + tenant-DB seed). The `tenant_db` dependency is **not** in Phase 1.

### Out — stays Meridian-local (colonization guard)

Their RBAC *policy* (the EDR/`product:*` permission vocabulary, role bundles), `product_access.py`
(the sealed/hidden resource-tree resolver — see §5), and epistemic-governance / absolute-seal.

---

## 4. The generic/local line (colonization guard, made concrete)

The battery ships the **mechanism + a minimal generic example**; the consumer owns the **policy**.
Drawn from reading the reference impl (`auth/*.py`, `db/control/models/*.py`):

| Generic → battery (LOCKED) | Policy → consumer-editable seed (INTENTIONALLY_UNLOCKED) |
|---|---|
| `PermDef` dataclass + materialize/reconcile mechanism | the **catalog content** — battery ships `tenant:read`, `tenant:manage-members` only; *not* `tenant:manage-products`/`product:*`/`platform-financial:*`/EDR vocabulary |
| `Role`/`Permission`/`RolePermission`, built-in-seeded + custom-DB-role seam + edit/shadow-protection | the **role bundles** — battery ships `tenant.admin`, `tenant.member` only; consumer replaces |
| ≥1-admin invariant (TOCTOU-safe `SELECT … FOR UPDATE` over the admin-assignment set) | the **protected role *name*** — battery setting `admin_role_name` (default `tenant.admin`); Meridian hardcodes it today |
| generic resource-scope: `resource_role_assignment` + `assign/revoke_resource_role` + a **flat** `resource_grant` hook | Meridian's `product` naming + `has_product_permission` |

The mechanism files render **LOCKED**; `permissions.py` / `roles.py` (the policy seed) render
**INTENTIONALLY_UNLOCKED** (like the FWK9 seed files) — this is what makes "consumer owns the policy"
real rather than aspirational.

---

## 5. The authz evaluator seam (the subtle part)

The recursive permission-expression evaluator (`expr.py`) is **generic mechanism — ported in full**,
because its recursion carries real generic *security* value:

- `Perm`/`ALL`/`ANY` nest arbitrarily; `evaluate`/`perm_leaves`/`resource_params`/`_has_wildcard_leaf`
  recurse.
- Construction-time guards: empty `ALL()`/`ANY()` → raise (`all([])` is a silent allow-all); a wildcard
  `Perm` leaf **anywhere** under `ALL` → raise (inert-deny today, would silently flip to grant later).
- Wildcard-ness is a property of the **authored pattern**, never the bound value (so an
  attacker-controlled `*` path segment can't flip a concrete leaf into the subtree branch).
- Domain-split resolution (`resolution.py`): a `platform` grant can never satisfy a `tenant:{id}` leaf
  and vice-versa; pure boolean over precomputed grant sets, no DB access in `evaluate`.

The evaluator exposes **two extension hooks**: `subtree_exists(name, resource)` (wildcard subtrees) and
the resource-grant hook. The **sealed/hidden resource-tree semantics are NOT in the evaluator** — they
live in Meridian's `product_access.py::candidate_grant_nodes`, which is **triply Meridian-local**: it
walks the **EDR** product hierarchy (epistemic-governance), in the **tenant DB** (physical routing,
Phase 2), with **nearest-seal-wins / non-sealed-ancestor** logic (absolute-seal, MDN36).

So the seam: **the battery owns *how expressions evaluate*; Meridian owns *what the resource tree is and
which nodes are sealed/hidden*.**

- **Battery ships:** the recursive evaluator + guards; flat domain-split resolution; a **generic flat
  `resource_grant`** (direct `resource_role_assignment` × `role_permission` match on
  `(membership_id, resource_id, role, perm)` — control-DB only, no tree, no seal, no routing → **live in
  Phase 1**); and `subtree_exists` as an **inert / deny-by-default** hook.
- **Meridian plugs back in (Phase 2):** `candidate_grant_nodes` (hierarchy + sealed/hidden + tenant-DB
  routing) *behind* the generic `resource_grant` / `subtree_exists` hooks.

---

## 6. Architecture & layout

All paths under `src/framework_cli/template/`, battery-conditional on `multitenantauth`.

### Control plane (decision B)

- `src/{{package_name}}/db/control/` — a battery-conditional package: `base.py` (`ControlBase`,
  separate `DeclarativeBase`/metadata) + per-domain models `authn.py` / `authz.py` / `tenant.py`
  (mirroring Meridian's MDN53 split) + `repository.py` (`add_tenant`/`get_tenant`/… thin queries).
- `control_session_factory` — its own engine bound to `APP_CONTROL_DATABASE_URL` (defaults to
  `DATABASE_URL`). Added as a battery-conditional region in `db/engine.py` (or `db/control/engine.py`).
- `migrations_control/` — a second alembic chain (`alembic_control.ini`, `env.py`, `versions/`) whose
  `env.py` targets `ControlBase.metadata` **and sets a named `version_table`
  (`alembic_version_multitenantauth`)** — REQUIRED here (unlike Meridian's reference, whose two chains
  live in separate DBs and use the default table) because the battery co-locates by default and two
  chains in one DB must not share `alembic_version`. The entrypoint runs both `alembic upgrade head`
  chains.

### Battery package

- `src/{{package_name}}/multitenantauth/` with `authn/` (service, passwords, tokens, email-norm),
  `authz/` (service, expr, resolution, permissions [seed], roles [seed]), `tenancy/` (registry service),
  `deps.py` (the single-module request chain — `current_user`/`active_tenant`/`guard` co-located by
  design so 404-before-403 + single cached control session live together), `errors.py`, and a `routes/`
  surface.
- No new `requires` — Postgres is the base store and is always present (the composite-FK/CHECK pattern
  needs it).

---

## 7. Components

- **Models** — `authn`: `AppUser` (email-canonical uniqueness + lowercase CHECK; `born`
  signup/invite/operator; `signed_up_at` xor invariant; password hash + version), `Session` (token_hash
  PK; identity-only, never tenant-bound), `InviteToken`. `authz`: `Role` (UNIQUE(id,domain) target of
  the composite FK; `is_builtin`), `Permission` (`scope:action`, domain), `RolePermission`,
  `TenantRoleAssignment` (CHECK `role_domain='tenant'` + composite FK), `PlatformRoleAssignment`,
  **`ResourceRoleAssignment`** (`membership_id` + opaque `resource_id` + role; CHECK
  `role_domain='resource'` + composite FK), `AuthzEvent` (append-only grant/revoke audit). `tenant`:
  `Tenant` (registry; opaque `dsn`; `status` provisioning→active→suspended; `tenant.status` CHECK —
  MDN48 cheap item), `TenantMembership`. Domain set: `role.domain ∈ {tenant, platform, resource}`.
- **Service layer** — authn: signup-founder, login (verify + rehash-on-login), logout, invite/accept.
  authz: `assign/revoke/change_role`, `add/remove_membership`, `add_platform_role`,
  `assign/revoke_resource_role`; the ≥1-admin invariant; `AuthzEvent` audit with idempotent-no-phantom
  (only a real state change is audited). **Services never commit — the route owns the tx boundary.**
- **Deps + evaluator** — `control_session` (FastAPI-cached per request), `current_user` (cookie/bearer
  → `Session` → `AppUser`; 401), `active_tenant` (URL tenant active + member; 404), `guard(expr)`
  (re-assert membership-404 precondition, then evaluate domain-split grants; 403); `expr.py`
  (recursive `Perm`/`ALL`/`ANY` + guards) + `resolution.py` (domain-split grant sets). `guard` carries
  `__authorized__` for the fitness tests; never serialized to a client.
- **Seed (UNLOCKED policy)** — `permissions.py` (`PermDef` catalog, minimal generic) + `roles.py`
  (built-in bundles + one custom-DB-role proving the seam) + a seed runner with a reconciliation check.
- **Routes** — auth (signup/login/logout/invite-accept), tenants (create/list-members/manage-members),
  roles (grant/revoke). The guarded example: `GET /tenants/{tenant_id}/members` behind
  `guard(Perm("tenant:manage-members", on="tenant:{tenant_id}"))`.
- **Settings (Pydantic)** — `control_database_url` (`APP_CONTROL_DATABASE_URL`, default = app DB);
  `session_cookie_name`; `session_pepper` (SecretStr); `password_pepper` (SecretStr) + argon2 cost
  params (`argon2_time_cost`/`memory_cost`/`parallelism`); `admin_role_name`; session TTL.
- **Passwords / tokens** — argon2id (`argon2-cffi`) over an **HMAC-SHA256 pepper pre-hash**, per-row
  salt in the PHC string, a version column for rotation, `needs_rehash` + rehash-on-login. Tokens:
  `secrets.token_urlsafe(32)`, store only `HMAC-SHA256(token, session_pepper)` (opaque; the hash lookup
  IS the check). **New dependency: `argon2-cffi`.**

---

## 8. Data flow

- **Request auth chain:** `current_user` (resolve cookie or `Authorization: Bearer` → `Session` row →
  `AppUser`; 401 on missing/invalid/expired/disabled) → `active_tenant` (URL `tenant_id` → `Tenant`
  active + membership; 404) → `guard` (for a tenant-scoped expr, re-assert membership-404 *first*, then
  `evaluate` against domain-split grants; 403). All on one cached `control_session`.
- **Signup (founder):** create `AppUser(born='signup')` + register `Tenant` (active) + `TenantMembership`
  + assign `admin_role_name`; mint a `Session`; set the httpOnly cookie.
- **Invite/accept:** an admin invites (create `AppUser` if needed + membership + `InviteToken`); the
  invitee redeems (set password, stamp `accepted_at`, mark `used_at`); then logs in.
- **Grant/revoke:** guarded route → service `assign/revoke_role` → `AuthzEvent` (only on real change).
- **Tenant registration (two-step seam):** `register_tenant(id, name, dsn, status='provisioning')` →
  (consumer/Phase-2: physical create + migrate) → `activate_tenant(id)`. The self-contained Phase-1
  demo registers-then-activates directly (no physical DB; nothing routes to `dsn` in Phase 1). A
  `tenant_id` charset guard (`^[a-z0-9_]+$`) is retained (hygiene now; required by Phase-2 `CREATE
  DATABASE`).

---

## 9. Error handling

- **401** — opaque `"Not authenticated"` for every missing/invalid/expired-session and disabled-user
  case (no oracle).
- **404-before-403** — unknown / inactive / non-member tenant → 404; existence is never leaked; `guard`
  re-checks the membership precondition before any 403, so a policy-leaking 403 can never precede the
  existence check.
- **403** — opaque forbidden detail when the permission expression is unsatisfied.
- **Domain mismatch** — `DomainMismatchError` on assigning a wrong-domain role (also structurally
  blocked by the composite FK — belt and suspenders); `LastAdminError` on the ≥1-admin invariant;
  unknown role/membership → `ValueError`. Mapped to HTTP codes at the route layer.
- **Missing path param in a resource binding** → DENY, never a 500 (`bind_resource` returns `None`).

---

## 10. Testing (the TDD oracle)

Port Meridian's **~2,360-line suite as the behavioral spec** (`tests/unit/{auth,...}`,
`tests/functional/test_auth_*`, `test_authz_*`, `test_tenancy.py`, `test_product_role_*`,
`tests/e2e/test_auth_tenancy_e2e.py`):

- **unit** — email-norm, tokens, permissions, passwords, expr (incl. the construction-time guards +
  wildcard-pattern-property).
- **functional** — models (constraints/CHECKs), service (grant/revoke, ≥1-admin TOCTOU, idempotent
  audit), deps (the 401/404/403 chain + 404-before-403), authz-seed (catalog/role reconciliation),
  **authz-fitness (T1–T4 — the crown jewels: every guarded route has a coherent `__authorized__`
  contract, never serialized)**, routes, signup-security, tenancy (registry + membership), resource-role
  (renamed from product-role; flat grant).
- **e2e** — signup → login → guarded route.

Adaptations: rename `product`→`resource`, strip EDR/product vocabulary, drop routing/`tenant_db` tests
(Phase 2), drop the sealed-tree resolver tests (Meridian-local).

Run via the **template-payload TDD loop** ([[template-payload-tdd-loop]]) in a generated project
(render → uv sync → edit source → mirror → pytest in `/tmp/work`); ruff-format-check the rendered
output. Plus:

- new **render-matrix** combos (multitenantauth baseline + with-other-batteries);
- an **acceptance** test (generated project's auth suite + coverage gate + clean first pre-commit);
- a **live docker** test: signup → login → guarded route against real Postgres, both chains migrated;
- a **two-chain migration** test: both chains `upgrade head` against one DB with distinct version tables
  (the named-version-table wrinkle), and the control chain against a separate control DB (Meridian's
  override).

---

## 11. Integrity / FWK29 / observability

- **Integrity** — mechanism files (models, deps, services, expr/resolution, control engine,
  `migrations_control/*`) → **LOCKED**; policy seeds (`permissions.py`, `roles.py`) →
  **INTENTIONALLY_UNLOCKED**; settings regions → HYBRID where a managed region coexists with
  consumer-edited config. Classify per `integrity/classes.py` (battery-conditional `BATTERY_LOCKED`).
- **FWK29 runtime-coverage** — classify the new operational surface: the control-DB session, the
  `migrations_control` chain, the auth routes, the entrypoint's second `alembic upgrade`. Each gets an
  EXERCISED / EXEMPT / KNOWN_GAP entry or the gate fails ([[fwk29-coverage-registry-gate]]).
- **Obs (in-process)** — metrics: login success/failure, session create/active, authz allow/deny by
  domain, grant/revoke events. Owes alert(s) + a dashboard; extend `test_obs_completeness` keyed on the
  battery's `obs` ([[obs-completeness-guard-already-exists]]).

---

## 12. Release, build approach & reviewer plan

- **Release** — template payload → ships a release; the broad render-matrix is the proof
  ([[release-yml-runs-full-gate-before-publish]]). Pre-cut: baseline + all-batteries + touched-single
  renders with their own mypy/ruff ([[release-readiness-needs-render-not-local-gate]]).
- **Build** — subagent-driven, TDD throughout; Sonnet implementers + spec-compliance review, **Opus**
  code-quality per task + a branch-end whole-branch **Opus** review ([[subagent-review-model-pattern]]).
- **Reviewers (run when Phase 1 is done, *before* Meridian adopts — not post-Phase-2):**
  1. the always-on subagent spec + Opus code-quality + branch-end reviews;
  2. the **framework review agents over the rendered battery** — `security` especially, plus
     privacy / data-integrity / env-parity — **scoped to "Phase 1 as a standalone shippable unit"** so
     the deferred Phase-2 seams (physical routing, inert `subtree_exists`, no `tenant_db`) are framed as
     by-design-deferred and not scored as defects; Phase-2-deferred findings → triaged known-deferred;
  3. an explicit **`/security-review`** pass on the diff (belt-and-suspenders, given the stakes).

---

## 13. Deferred items (→ PLAN stubs)

- **`--with auth`** — single-tenant identity + authz (no tenancy). Shares an unscoped `Item` demo (why
  Q3 kept Phase 1 self-contained). Design consideration: offer cookie + bearer + **stateless JWT** —
  explicitly contrasted with `multitenantauth`'s **revocable opaque server-side sessions**.
- **`tenant-data-model` / `tenant-context-propagation`** — logical `tenant_id` scoping of *business*
  data + fail-closed context propagation. Explicitly **not** Phase 1 (would impose `tenant_id` on every
  consumer's domain model).
- **FWK58 Phase 2** — physical routing + ops (`tenant_session`, `TenantEngineRegistry` + connection
  budgeting, plane-aware migrate/deploy/rollback, physical provisioning, the sealed-tree hook lit by a
  consumer resolver).
- **secrets-backing** — externalize per-tenant DSN creds (immediate-follow; Meridian is on env/settings
  + never-log today, not adoption-blocking).
- **MDN48 hardening (deferred half)** — obs/SLO on the control hot path; `authz_event` FK-ondelete +
  GDPR-erasure + retention indexes. (The cheap half — `tenant.status` CHECK, cross-domain
  `role_permission` enforcement — is folded into Phase 1.)

---

## 14. Risks & open questions

- **Extraction source pinned** — extract from `cdowell-swtr/meridian@e0cf9cf` (origin/main, 2026-06-23),
  not a moving branch ([[verify-master-content-after-pr-merge]]).
- **Password version column naming** — the `AppUser` model uses `hash_version`; `passwords.py`'s
  rotation story references `pepper_version`/`APP_PEPPER_VERSION`. Reconcile to one rotation column +
  setting during the build.
- **The named version table is battery-specific** — not in Meridian's reference (their chains are in
  separate DBs). It is the load-bearing mechanism for co-located two-chain migrations; test it
  explicitly (both the co-located and separate-control-DB cases).
- **Settings split** — the battery adds several auth settings; ensure they land in a battery-conditional
  region and don't leak into non-multitenantauth renders.
- **Surface size** — largest single template addition to date (~1,900 LoC core + ~2,360 LoC oracle to
  port/adapt). Sequence as many small TDD tasks; the date is de-pressurized, so do it properly.

---

## 15. Validation-oracle reference (Meridian, `@e0cf9cf`)

Generic → extract: `db/control/models/{authn,authz,tenant}.py`; `auth/{service,deps,expr,resolution,
permissions,roles,passwords,tokens,email_norm,errors}.py`; the `control_session_factory` half of
`db/engine.py`; `migrations_control/{env.py,versions/c0001,c0002,c0003}`; `alembic_control.ini`. Tests:
`tests/unit/auth/*`, `tests/unit/test_{provisioning,settings_auth}.py`, `tests/functional/test_auth_*`,
`test_authz_*`, `test_tenancy.py`, `test_product_role_*`, `tests/e2e/test_auth_tenancy_e2e.py`.

Meridian-local (do NOT extract): `auth/product_access.py`, `db/control/models/product.py`,
`db/edr/**`, `db/tenancy/provision.py` (physical), the `tenant_session`/`TenantEngineRegistry` half of
`db/engine.py`.
