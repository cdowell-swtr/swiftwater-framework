# FWK58 — `--with multitenantauth` de-fork spine (Phase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship `--with multitenantauth` — a generic multitenant identity / session / authz-mechanism /
tenant-registry control-plane spine, extracted from Meridian's validated impl so Meridian de-forks onto it.

**Architecture:** A battery-conditional control plane (`ControlBase` + `control_session_factory` +
its own `migrations_control` alembic chain with a **named version table**) co-located in the app DB by
default and separable via `APP_CONTROL_DATABASE_URL`. The authz core is a recursive permission-expression
evaluator over composite-FK-integrity-enforced role assignments (`tenant`/`platform`/generic `resource`
domains), exposed through a `current_user → active_tenant → guard` request chain with 404-before-403.
Cookie-based sessions are CSRF-defended and multi-host-shaped (configurable cookie `Domain` + CSRF
allowlist, safe single-host defaults).

**Tech Stack:** FastAPI, SQLAlchemy (sync), Alembic (two chains), Pydantic settings, argon2-cffi,
Postgres. Template payload (Copier/Jinja). Subagent-driven TDD.

**Spec:** `docs/superpowers/specs/2026-06-23-fwk58-multitenantauth-defork-spine-design.md`
**Reference impl (pinned):** `cdowell-swtr/meridian@e0cf9cf` — local checkout at
`/home/chris/Claude Code/Projects/meridian` (`git rev-parse e0cf9cf` to confirm; extract from this tree).

## Global Constraints

*(Every task implicitly includes this section. Copy values verbatim.)*

- **Port-vs-novel:** "Port `<path>`" means copy that file from `meridian@e0cf9cf` verbatim, then apply the
  listed transformations — the reference is the content, not a placeholder. Novel code is given in full.
- **The generic/local transformations (apply to every ported file):**
  - `product` → `resource` everywhere (table `product_role_assignment`→`resource_role_assignment`,
    column `product_id`→`resource_id`, `role_domain` value `'product'`→`'resource'`, fns
    `assign/revoke_product_role`→`assign/revoke_resource_role`, ctx key `product_grant`→`resource_grant`).
  - **Drop** (Meridian-local / Phase 2): `auth/product_access.py`, `db/control/models/product.py`,
    `db/edr/**`, the physical `db/tenancy/provision.py` (keep only its control-registry half), the
    `tenant_session`/`TenantEngineRegistry` half of `db/engine.py`, and the `tenant_db` dependency.
  - The evaluator's `subtree_exists` hook ships **inert** (`lambda name, resource: False`); the flat
    `resource_grant` ships **live** (control-DB-only direct match). The sealed/hidden tree resolver is NOT
    ported (Meridian plugs it in behind the hook in Phase 2).
  - Strip Meridian's EDR/product permission vocabulary; ship a **minimal generic** seed (Task 17).
  - `_ADMIN_ROLE_NAME = "tenant.admin"` (hardcoded in the reference) → `settings.admin_role_name`.
  - **Env-token remap (security-critical — sec-review B-F1):** Meridian's env tokens are
    `{dev,test,stage,prod}`; the framework's are `{dev,test,staging,prod}`. EVERY ported env comparison
    maps `stage`→`staging` (the `environment` field-validator set, the signup gates, `verify_runtime`).
    A verbatim port makes `staging` invalid AND fails signup/pepper gates open — never port `{"dev",
    "stage"}` / `{"prod","stage"}` literally.
  - **De-Meridianize the fitness allowlists (security-critical — sec-review A-F3):** the
    `PUBLIC` / `INLINE_AUTHZ` sets in `test_authz_fitness.py` hardcode Meridian routes (`/edr/view`,
    `/edr/assets/{name}`, `/t/{tenant_id}/p/{product_id}`). REBUILD them for the battery's actual route
    surface — strike every `/edr/*` and `/t/.../p/...` entry. A stale allowlist entry = a silently
    unguarded route in shipped consumer code.
- **Signup fail-closed by default (security-critical — sec-review A-F9, operator decision A):** unlike
  the reference (empty `signup_allowlist` = unrestricted), the battery ships **fail-closed**: `prod`
  signup is off (404); an **empty `signup_allowlist` means DENY in `staging`** (and prod stays off);
  signup is open only in `dev`. A consumer opts INTO public signup by setting the allowlist (or an
  explicit flag). Meridian restores its own behavior by setting the allowlist.
- **Pepper guard (security-critical — sec-review B-F2):** peppers (`session_pepper`/`password_pepper`)
  default to `SecretStr("")` (matching the reference) — NOT "required". Safety is the ported
  `verify_runtime(settings)` fail-fast guard, called from `create_app()`: in `prod`/`staging`, empty
  peppers raise at startup. Port `verify_runtime` + its `create_app` wiring as part of Task 2/9 (it is
  NOT in the original plan draft). The `pepper_version`/`hash_version` columns are **forward-compat
  only** — there is NO live pepper rotation in Phase 1 (rotating the single pepper today mass-locks
  every user); do not claim otherwise.
- **Template-payload TDD loop** ([[template-payload-tdd-loop]]): tests run in a GENERATED project (the
  framework venv lacks the template's deps). Cycle per change: render a `multitenantauth` project to
  `/tmp/work` → `uv sync` → write the failing test there → confirm RED → edit the framework template
  source → mirror into `/tmp/work` (cp `.py`; render+cp `.jinja`) → confirm GREEN → `ruff format --check`
  the rendered output → commit the framework source. Use `TMPDIR=/var/tmp` for renders.
- **Template file types:** files with relative imports / no interpolation are plain `.py` under a
  battery-conditional path; files that interpolate (`{{package_name}}`, batteries) are `.jinja`.
  Battery-conditional dirs use `{% if "multitenantauth" in batteries %}name{% endif %}`; conditional
  single files use the `{{ 'name.ext' if 'multitenantauth' in batteries else '' }}.jinja` idiom.
- **SQLAlchemy is sync** throughout (matches both template and reference). Services never commit — the
  route/caller owns the transaction boundary.
- **Tooling:** all via `uv run`. Gate before any commit: `uv run pytest -q`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy src`. Docker/acceptance tier needs the sandbox disabled.
- **No new `requires`** on the battery (Postgres is the always-present base). New dep: `argon2-cffi`,
  declared battery-conditionally in `pyproject.toml.jinja`.
- **Colonization guard:** mechanism files render LOCKED; the policy seed (`permissions.py`/`roles.py`)
  renders INTENTIONALLY_UNLOCKED. The battery ships multitenant-consumer-shaped, never Meridian-shaped.
- **Commit hygiene:** stage then commit as separate calls; keep PLAN.md/ACTION_LOG.md updated per task
  ([[commit-gate-hook-timing]]); the per-task gate cadence follows [[gate-cadence-framework-slices]]
  (light per-task review + controller skip-marker commits + one branch-end full review).

---

## Security-review ledger (two-agent pre-implementation review, 2026-06-23 — applied)

All findings from the authZ/tenant-isolation (A-*) and authN/session/CSRF/crypto (B-*) reviews, with
disposition + where applied. The branch-end review reconciles this against Meridian's own security-review
spec. **Convergent headline:** signup was a fail-open zone from two angles (B-F1 env-token mismatch +
A-F9 empty-allowlist) → resolved by the fail-closed default (Global Constraints + Task 13).

| ID | Finding | Disposition → where |
|----|---------|---------------------|
| B-F1 | `stage`→`staging` env-token mismatch (signup fail-open, pepper guard dark, validator rejects `staging`) | **Fixed** — Global Constraints env remap; Tasks 2, 13 |
| B-F2 | Pepper "required" vs default-empty; `verify_runtime` unported | **Fixed** — default-empty + port `verify_runtime` into `create_app`; Tasks 2, 9, 16 |
| B-F8 | Over-claimed pepper rotation | **Fixed** — version columns forward-compat only, no live rotation; Tasks 2, 9 |
| B-F9 | `session_cookie_secure` no default | **Fixed** — pin `True`; Task 2 |
| B-F10 | argon2 cost-floor validators missing | **Fixed** — port floors `≥3/≥65536/≥4`; Task 2 |
| B-F3 | Parent-domain cookie discloses raw token (session hijack) | **Fixed (doc/guardrail)** — invariant in spec §5.1 + Task 15 |
| B-F4 | CSRF allowlist must be exact-match; "pattern" invites wildcards | **Fixed** — exact netlocs, wildcards forbidden + test; spec §5.1, Task 15 |
| B-F5 | Lenient absent-Origin branch coupled to `SameSite=Lax` | **Fixed (doc)** — spec §5.1 |
| B-F6 | Empty-allowlist same-origin equivalence | **Fixed** — regression test; Task 15 |
| B-F7 | Junk-Bearer-with-cookie CSRF test omitted | **Fixed** — explicit test (c2); Task 15 |
| B-F11 | No logged-in change-password route; document the session-invalidation pattern | **Build-note** — set-password already invalidates all sessions (ported, Task 13); a consumer adding a logged-in change-password/disable flow must replicate `delete Session where user_id`. Document in the seed/README. |
| A-F2 | Fitness paraphrase wrong; real suite is T1/T1b/T2/T3/T4/T4b; T1b load-bearing | **Fixed** — real tests named, T1b `active_tenant`-only w/ Phase-2 seam; Task 16 |
| A-F3 | `PUBLIC`/`INLINE_AUTHZ` hardcode Meridian/EDR paths | **Fixed** — rebuilt for the battery surface; Global Constraints + Task 16 |
| A-F5 | Domain CHECK must REMOVE `'product'`; enumerate `rra` constraint names | **Fixed** — exact names + `('tenant','platform','resource')` + reject-`'product'` test; Tasks 5, 7 |
| A-F1 | Flat `resource_grant` re-parses a concatenated string (opaque `resource_id` mis-slice) | **Fixed (improved on reference)** — pass discrete path params; Tasks 10, 14 |
| A-F4 | `add_platform_role` writes a phantom audit row | **Fixed** — move `_record_event` inside the `if`; flag upstream; Task 11 |
| A-F6 | Evaluator branch order load-bearing | **Fixed** — preserve wildcard→resource→flat + named tests; Task 10 |
| A-F8 | Don't DRY `guard`'s inline 404 re-check | **Fixed** — reviewer note + guard-only-route 404 test; Task 14 |
| A-F10 | Single inert `subtree_exists` construction site | **Fixed** — assert one site; Task 10 |
| A-F7 | No suspended/provisioning-tenant→404 test | **Fixed** — added; Task 14 |
| A-F9 | `signup_allowlist` empty=unrestricted fail-open default | **Fixed (operator decision A)** — fail-closed default; Global Constraints + Task 13 |
| A-F11 | `AuthzEvent` FK ondelete (deferred) | **No action** — confirmed no tenant-delete route in Phase 1 (Task 12 = register/activate/get only) |
| — | Cross-domain `role_permission` guard is seed-time-advisory, not a DB invariant | **Stated** — sufficient in Phase 1 (no runtime bundle-mutation route); Task 5 |

---

## Layer-1 Hardening — design panel (data-model · ops · plan-quality) + MDN registry-shape addendum

> Per Meridian's two-layer adversarial-security-review method, the first review (above) was a *partial*
> Layer-1 panel (security + authZ). This completes Layer 1 with the **data-model/migrations**,
> **operations/deploy**, and **plan-quality** lenses. **This hardening section GOVERNS the task bodies
> where they conflict** (the structural blockers below are already folded into the named tasks; this is
> the authoritative record + the remaining build-notes). Layer 2 (the stance×focus attacker matrix) runs
> pre-merge — see "Layer-2 pre-merge gate" below.

**Blockers (fixed in the named tasks):**
| ID | Finding | Fixed in |
|----|---------|----------|
| PQ-C1/C2 | No `authn/service.py` in the reference — signup/login/etc. are route handlers in `routes/auth.py`; Task 13 mislabeled it a "port", cited a nonexistent test source, and depended on routes built later | Task 13 reframed = authn **routes + `cookies.py`** (run after Task 14); Task 16 narrowed to tenant/role routes + wiring + fitness |
| OPS-F1 | The control vocabulary/role seed is never invoked at boot → fresh container boots healthy but first signup fails | Task 8 adds the control-seed step to the LOCKED `entrypoint.sh` (after both chains); Task 17 `seed.py` gets a `__main__` |
| DM-F1 | Named version table isolates bookkeeping, NOT autogenerate → co-located `alembic --autogenerate` proposes dropping the other chain's tables | Task 7 adds `include_*` scoping to BOTH env files (incl. the previously-untasked `migrations/env.py.jinja`) + a co-located `alembic check` test |
| OPS-F2 | Separate-control-DB cutover unspecified; Meridian's existing control DB collides on the version table | **Operator decision:** ship generic separate-DB support (target DB must pre-exist — documented); the existing-control-DB adoption migration is **deferred to Meridian co-design** (Task 12 ops note) |
| MDN addendum | tenant registry must decouple **opaque immutable `id`** (PK/routing/DB-name key) from **mutable DNS-safe `slug`** (URL label) + slug-history/cooling — don't inherit `id == slug` | Tasks 6 (models) + 12 (registry) |

**Build-notes (fold into the named task during execution):**
- **DM-F2** Task 7 — flip the c0003 `role_domain` `server_default="product"`→`"resource"` explicitly + a positive test (insert without `role_domain` → persists `'resource'`).
- **DM-F3** Tasks 5/7 — the domain-CHECK `'product'`-removal is a **four-site** coupled edit (model `ck_role_domain` + `ck_permission_domain` + migration c0002 ×2); the reject-`'product'` test must run against the **migration-built** schema.
- **DM-F4** Task 19/a framework guard — assert `set(Base.metadata.tables) & set(ControlBase.metadata.tables) == set()` (co-located table-name disjointness).
- **DM-F5** Task 11/16 — map an `IntegrityError` on the idempotent-grant race to 409/idempotent-success (else a concurrent first-time duplicate grant 500s). Non-blocking.
- **DM-F6** Task 7 — preserve the c0002 "NEVER run downgrade with real auth data" docstring warning (irreversible data loss); echo the rollback-by-redeploy guidance in the README.
- **OPS-F4** Tasks 2/3 — the co-located default runs two pools on one Postgres; either add `control_pool_size`/`control_max_overflow` settings (small) or document the connection budget in `.env.example`/README so an operator can size `max_connections`.
- **OPS-F5** Task 8/health — consider a battery-conditional `/ready` control-schema probe (port Meridian's `control_schema_ready` = `SELECT 1 FROM permission LIMIT 1`) so the `APP_RUN_MIGRATIONS=false` multi-host path holds traffic until schema+seed land.
- **OPS-F6** Task 12/README — document that in Phase 1 the tenant `dsn` is forward-compat metadata (never connected to) and `provisioning→active` is registry-state only until Phase-2 routing.
- **OPS-F7** Task 16 — `verify_runtime` must be called at the TOP of `create_app()` (before router includes); a misconfigured prod/staging container crash-loops at boot (correct fail-closed — note in the deploy runbook). (Folded into Task 16.)
- **PQ-P2** Task 13 — the B-F11 change-password/session-invalidation note has a landing home (Task 13 README step). (Folded.)
- **PQ-P3** Task 21 — bring the live stack up with `APP_ENVIRONMENT=dev` for the signup leg (fail-closed default 403s in staging) + add a negative `staging`+empty→403 assertion.
- **PQ-P4** Self-review — `control_session_factory` is consumed only in Task 14 (not "7/14"); Task 7 consumes `control_database_url` + `ControlBase.metadata`. (Corrected in the self-review below.)
- **PQ-P5** Tasks 4–6 — author `models/__init__.py` re-exports incrementally (Task 4 = authn classes only; Tasks 5/6 extend) so no task imports a not-yet-created model.
- **I1** Task 1 — `gates_agents=("security",)` is harmless-redundant (`security` is `active_when="always"`); keep as documentation or drop.

**Confirmed sound by the panel (do not re-open):** FK creation ordering c0001→c0003; Phase-1 migrations are expand-only (rolling-safe); downgrades topologically correct; the ≥1-admin `FOR UPDATE` TOCTOU lock; full index coverage for every authz hot-path query; `AuthzEvent` FK-ondelete deferral (no Phase-1 tenant/user/role delete route); the security-review transformations all verify against the pinned reference; placeholder scan clean.

---

## Phase A — Control-plane foundation & battery skeleton

### Task 1: Register the `multitenantauth` battery + package skeleton

**Files:**
- Modify: `src/framework_cli/batteries.py` (add a `BatterySpec` to `_BATTERIES`)
- Create: `src/framework_cli/template/src/{{package_name}}/{% if "multitenantauth" in batteries %}multitenantauth{% endif %}/__init__.py`
- Test: `tests/test_batteries.py` (or wherever battery specs are asserted) + `tests/test_copier_runner.py`

**Interfaces:**
- Produces: the `multitenantauth` battery token; a conditional `multitenantauth/` package dir in renders.

- [ ] **Step 1: Write the failing test** — assert the battery resolves and renders.

```python
# tests/test_batteries.py
def test_multitenantauth_battery_registered():
    from framework_cli.batteries import get_battery, resolve
    spec = get_battery("multitenantauth")
    assert spec.obs == "in-process"
    assert spec.requires == ()           # postgres is the base, not a battery
    assert resolve(["multitenantauth"]) == ["multitenantauth"]
```

- [ ] **Step 2: Run it — expect FAIL** (`KeyError: unknown battery`).
Run: `uv run pytest tests/test_batteries.py::test_multitenantauth_battery_registered -v`

- [ ] **Step 3: Implement** — add to `_BATTERIES` in `batteries.py`:

```python
    "multitenantauth": BatterySpec(
        "multitenantauth",
        "Multitenant identity + sessions + authz mechanism + tenant registry "
        "(control-plane spine; cookie/bearer auth, CSRF-defended)",
        gates_agents=("security",),
        obs="in-process",
    ),
```

- [ ] **Step 4: Run — expect PASS.** Add a `test_copier_runner` assertion that a `--with multitenantauth`
  render produces `src/<pkg>/multitenantauth/__init__.py`. Render with `TMPDIR=/var/tmp`.

- [ ] **Step 5: Commit** (`feat(multitenantauth): register battery + package skeleton`).

> **Note for reviewers:** confirm `gates_agents=("security",)` is the right hook — it activates the
> `security` review agent whenever the battery is present (verify `security` is a real registered agent
> and not advisory-only for this use). Adjust per [[check-agent-prompt-fit-before-adding-to-target]].

### Task 2: Auth settings region

**Files:**
- Modify: `src/framework_cli/template/src/{{package_name}}/config/settings.py.jinja` (add a
  `{% if "multitenantauth" in batteries %}` region)
- Modify: `.env.example` template (document the new vars, framework region)
- Test: `template/tests/unit/{{ 'test_settings_auth.py' if 'multitenantauth' in batteries else '' }}.jinja`
  (port `meridian tests/unit/test_settings_auth.py`)

**Interfaces:**
- Produces: settings fields — `control_database_url: str` (env `APP_CONTROL_DATABASE_URL`, default =
  `database_url`), `session_cookie_name: str`, `session_cookie_secure: bool = True` (pin the safe
  default — sec-review B-F9), `session_cookie_domain: str | None = None`, `csrf_allowed_origins: set[str]
  = set()`, `session_pepper: SecretStr = SecretStr("")`, `password_pepper: SecretStr = SecretStr("")`,
  `pepper_version: int = 1` (forward-compat only — no live rotation in Phase 1), `argon2_time_cost: int =
  3` / `argon2_memory_cost: int = 65536` / `argon2_parallelism: int = 4` (with floor validators —
  sec-review B-F10), `admin_role_name: str = "tenant.admin"`, `session_ttl_hours: int = 336`,
  `invite_ttl_hours: int = 168`, `signup_allowlist: list[str] = []`. Plus the module function
  `verify_runtime(settings) -> None` and the `environment` field-validator admitting the framework set
  **`{dev,test,staging,prod}`** (sec-review B-F1).

- [ ] **Step 1: Failing test** — port `test_settings_auth.py`; assert defaults (`session_cookie_secure is
  True`, `session_cookie_domain is None`, `csrf_allowed_origins == set()`, `admin_role_name ==
  "tenant.admin"`); the `control_database_url` fallback to `database_url`; the argon2 floor validators
  reject `time<3` / `memory<65536` / `parallelism<4`; the `environment` validator accepts `staging` and
  rejects `stage` / `production`; and `verify_runtime` raises in `prod`/`staging` with an empty pepper
  but passes in `dev` and when peppers are set.
- [ ] **Step 2: Run — FAIL** (fields/validators/`verify_runtime` absent).
- [ ] **Step 3: Implement** the conditional settings region. Control-URL fallback via a
  `model_validator(mode="after")`: if `APP_CONTROL_DATABASE_URL` is unset, `control_database_url =
  database_url`. Peppers are `SecretStr = SecretStr("")` (default-empty — **not** required); safety is
  `verify_runtime(settings)` — port from reference `settings.py:173-183`, remapping `{"prod","stage"}` →
  `{"prod","staging"}` — wired into `create_app()` in Task 16's `main.py` step. Port the three argon2
  floor validators and the `environment`-in-`{dev,test,staging,prod}` validator (sec-review B-F1).
  `signup_allowlist` semantics are enforced fail-closed in Task 13, not here.
- [ ] **Step 4: Run — PASS.** `ruff format --check` the rendered settings.
- [ ] **Step 5: Commit** (`feat(multitenantauth): auth settings region + verify_runtime guard`).

### Task 3: `ControlBase` + `control_session_factory`

**Files:**
- Create: `.../db/{% if "multitenantauth" in batteries %}control{% endif %}/base.py` (plain `.py`)
- Create: `.../db/{% if "multitenantauth" in batteries %}control{% endif %}/engine.py.jinja`
- Test: `template/tests/unit/{{ 'test_control_engine.py' if ... }}.jinja`

**Interfaces:**
- Produces: `ControlBase(DeclarativeBase)` (separate metadata); `control_session_factory() ->
  sessionmaker[Session]` bound to an engine on `get_settings().control_database_url`.

- [ ] **Step 1: Failing test** — `control_session_factory()` returns a sessionmaker; a session opens
  against the control URL; `ControlBase.metadata` is distinct from `Base.metadata`.
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: Implement.** `base.py`:

```python
from sqlalchemy.orm import DeclarativeBase
class ControlBase(DeclarativeBase):
    """Declarative base for control-plane (identity/authz/tenant-registry) models."""
```

`engine.py.jinja` (mirrors `db/engine.py`'s `build_engine`/`build_session_factory`, on the control URL;
lazy singleton so a non-multitenantauth render is unaffected and tests can rebind):

```python
import threading
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from {{package_name}}.config.settings import get_settings
from {{package_name}}.db.engine import build_engine, build_session_factory

_control_engine: Engine | None = None
_control_factory: "sessionmaker[Session] | None" = None
_control_lock = threading.Lock()   # double-checked lock (sec-review OPS-F3): FastAPI runs sync deps in a
                                   # threadpool, so a cold-start burst must not orphan a second engine/pool.

def control_engine() -> Engine:
    global _control_engine
    if _control_engine is None:
        with _control_lock:
            if _control_engine is None:
                _control_engine = build_engine(get_settings().control_database_url)
    return _control_engine

def control_session_factory() -> "sessionmaker[Session]":
    global _control_factory
    if _control_factory is None:
        with _control_lock:
            if _control_factory is None:
                _control_factory = build_session_factory(control_engine())
    return _control_factory

def dispose_control_engine() -> None:
    global _control_engine, _control_factory
    with _control_lock:
        if _control_engine is not None:
            _control_engine.dispose()
        _control_engine = None
        _control_factory = None
```

- [ ] **Step 4: PASS.** `ruff format --check`.
- [ ] **Step 5: Commit** (`feat(multitenantauth): ControlBase + control_session_factory`).

---

## Phase B — Models & migrations

### Task 4: AuthN models

**Files:**
- Create: `.../db/control/models/__init__.py` (re-export all model classes as `m.*`), `authn.py`
- Test: port `meridian tests/functional/test_auth_models.py` → `template/tests/functional/...`

**Port:** `meridian@e0cf9cf:src/meridian/db/control/models/authn.py` verbatim (`AppUser`, `Session`,
`InviteToken`) — relative import `from ...base import ControlBase` stays; no transformations needed (no
product references). Re-export from `models/__init__.py` so call sites use `from ...control import models
as m; m.AppUser`.

- [ ] **Step 1:** Port `test_auth_models.py` (email-canonical uniqueness + lowercase CHECK; `born`
  signup/invite/operator + the `(born='signup') = (signed_up_at IS NOT NULL)` invariant; Session
  identity-only). Confirm RED (no models).
- [ ] **Step 2:** Port the models. Confirm GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): authn models`).

### Task 5: AuthZ models (the composite-FK integrity core — security-critical)

**Files:**
- Create: `.../db/control/models/authz.py`
- Test: port `meridian tests/functional/test_auth_models.py` (authz portion) +
  `test_product_role_assignment_model.py` → resource-role model test.

**Port** `authz.py` with transformations: `Role`, `Permission`, `RolePermission`,
`TenantRoleAssignment`, `PlatformRoleAssignment`, `AuthzEvent` verbatim; **rename**
`ProductRoleAssignment`→`ResourceRoleAssignment`: table `resource_role_assignment`, `product_id`→
`resource_id`, `role_domain` default/CHECK `'product'`→`'resource'`, and the **exact** constraint/index
renames (sec-review A-F5 — disambiguates from `PlatformRoleAssignment`'s `pra` names): `uq_pra_membership_
product_role`→`uq_rra_membership_resource_role`, `ck_pra_product_role_domain`→`ck_rra_resource_role_domain`
(CHECK `role_domain='resource'`), `fk_pra_product_role_domain`→`fk_rra_resource_role_domain`,
`ix_pra_membership`→`ix_rra_membership`, `ix_pra_product`→`ix_rra_resource`. The composite FK
`(role_id, role_domain) → role(id, domain)` + per-table `CHECK(role_domain='<domain>')` is the
**load-bearing integrity mechanism** — preserve exactly. **Set `ck_role_domain`/`ck_permission_domain` to
`IN ('tenant','platform','resource')` — REMOVE `'product'`, not just add `'resource'` (sec-review A-F5):
a residual `'product'` silently re-admits a Meridian-policy role-domain into a generic battery.**

**MDN48 cheap-in-window items, add here:**
- `Tenant.status` CHECK (Task 6, the tenant model) — `CHECK(status IN ('provisioning','active','suspended'))`.
- Cross-domain `role_permission` enforcement: a `tenant`-domain role must not bundle a `platform` perm.
  Enforced as a **seed-time reconciliation assertion** (Task 17). **Sec-review note:** this is
  seed-time-ADVISORY, not a DB invariant — it is sufficient in Phase 1 because **no runtime
  bundle-mutation route ships** (bundles are seeded, not API-mutable); a consumer that later adds a
  `RolePermission`-writing route must add a DB-level guard. State this explicitly; don't imply a DB invariant.

- [ ] **Step 1:** Port the resource-role model test — assert (a) a `tenant`-domain role **cannot** be
  inserted into `resource_role_assignment`, (b) a `platform`-domain role cannot either (composite-FK +
  CHECK reject both), (c) **`'product'` is rejected by the `role`/`permission` domain CHECK**, and (d) a
  flat resource grant round-trips. Confirm RED.
- [ ] **Step 2:** Port + transform the models. Confirm GREEN. Verify the domain CHECK is exactly
  `('tenant','platform','resource')`.
- [ ] **Step 3:** Commit (`feat(multitenantauth): authz models + generic resource-scope`).

> **Reviewers:** this is the integrity spine. Verify the rename preserved every composite FK + the **exact**
> renamed constraint set; that the domain CHECK is `('tenant','platform','resource')` with `'product'`
> **removed** (not merely `'resource'` added); and that no `product`/EDR reference leaked in (A-F5).

### Task 6: Tenant models (opaque id + mutable slug — MDN registry-shape addendum)

**Files:** Create `.../db/control/models/tenant.py`; test ports `test_tenancy.py` (model portion).
**Port** `tenant.py` (`Tenant`, `TenantMembership`) + the `Tenant.status` CHECK (MDN48), **with the
MDN de-fork registry-shape addendum (2026-06-23) — do NOT inherit Meridian's `id == slug` smell:**

- **`Tenant.id`** = **opaque, immutable** — PK, routing key, and the **per-tenant DB-name key** (Phase 2).
  Generate it (uuid-hex or an opaque token), NOT from the slug. Keep the `String(64)` + `^[a-z0-9_]+$`
  charset (it must be a safe DB-identifier component for Phase-2 `CREATE DATABASE`).
- **`Tenant.slug`** = **mutable, unique, DNS-label-safe** — the URL/subdomain label ONLY. Add a CHECK for
  an RFC-1123 label (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, ≤63 chars) + a UNIQUE constraint. NEVER used as a
  routing/DB key.
- New `TenantSlugHistory` model — `(slug PK or unique, tenant_id FK, retired_at, reserved_until)`: maps a
  retired slug → its tenant (for 301 redirects) and holds it in a **cooling/reserved** state so a rename
  can't be immediately squatted. A slug is claimable only if it is neither a live `tenant.slug` nor a
  history row whose `reserved_until` is in the future.
- `TenantMembership.tenant_id` FKs the **opaque `tenant.id`** (unchanged — grants key on the immutable id).

Rationale: a workspace rebrand (common) must never touch the physical DB or break links; changing a
PK + DB-naming scheme after tenants exist is the irreversible migration this exercise targets. (The
URL-uses-slug + subdomain resolution behavior pairs with the multi-host work and is Phase 2; Phase 1
ships the *decoupled model* + registry mechanism so the irreversible decision is correct from row #1.)

- [ ] **Step 1:** Test: `tenant.id` is opaque (not derived from slug); `slug` UNIQUE + the DNS-label CHECK
  rejects `Bad_Slug`/`-x`/uppercase; `status` rejects a junk value; membership uniqueness
  `(user_id, tenant_id)`; a `TenantSlugHistory` row maps an old slug → tenant. RED.
- [ ] **Step 2:** Port + add the slug/history models + CHECKs. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): tenant registry models — opaque id + mutable slug`).

> **Reviewers:** confirm `tenant.id` is never derived from or coupled to `slug` anywhere (grep), the slug
> CHECK is a strict DNS label, and `TenantMembership`/grants key on the opaque `id`, not the slug.

### Task 7: `migrations_control` chain with a NAMED version table (novel — load-bearing)

**Files:**
- Create: `template/{{ 'alembic_control.ini' if 'multitenantauth' in batteries else '' }}.jinja`
- Create: `template/{% if "multitenantauth" in batteries %}migrations_control{% endif %}/env.py.jinja`,
  `script.py.mako`, `versions/c0001_*.py`, `c0002_*.py`, `c0003_*.py`
- **Modify (sec-review DM-F1): `template/migrations/env.py.jinja`** — the APP chain's env. It is in NO
  other task and is the other half of the autogenerate fix below.
- Test: `template/tests/unit/{{ 'test_control_migrations.py' if ... }}.jinja`

> **Sec-review DM-F1 (PLAN-BLOCKER, fixed here): the named version table isolates version *bookkeeping*,
> NOT autogenerate.** In the co-located default (one DB, both chains), the consumer's documented `alembic
> revision --autogenerate` reflects the WHOLE database — so the app chain (`Base.metadata`) sees the
> control tables and emits `op.drop_table()` for each, and the control chain symmetrically proposes
> dropping `item`/battery tables. A data-destroying footgun the framework's own `upgrade head` tests stay
> green through. **Fix:** add an `include_name`/`include_object` to BOTH env files so each chain's
> autogenerate/`check` sees only its OWN metadata's tables — the control `env.py` filters to
> `ControlBase.metadata.tables` (and ignores the app's `version_table`), and the app
> `migrations/env.py.jinja` filters OUT the control tables (battery-conditional: when `multitenantauth`
> is active, exclude `ControlBase.metadata.tables` + `alembic_version_multitenantauth`).

**Novel — the named version table.** Meridian's `migrations_control/env.py` uses the default
`alembic_version` because its chains live in separate DBs. The battery co-locates by default → the
control chain MUST use a distinct version table. `env.py.jinja`:

```python
from sqlalchemy import engine_from_config, pool
from alembic import context
from {{package_name}}.config.settings import get_settings
from {{package_name}}.db.control.base import ControlBase
from {{package_name}}.db.control import models  # noqa: F401  (register tables on ControlBase.metadata)

config = context.config
_x = context.get_x_argument(as_dictionary=True)
config.set_main_option("sqlalchemy.url", _x.get("dsn") or get_settings().control_database_url)
target_metadata = ControlBase.metadata
_VERSION_TABLE = "alembic_version_multitenantauth"   # <-- distinct from the app chain's alembic_version

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata,
            version_table=_VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()

def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"}, version_table=_VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Port** the three version files from `meridian@e0cf9cf:migrations_control/versions/` (`c0001_control_tenant`,
`c0002_auth_model`, `c0003_product_role_assignment`) — transform `product`→`resource` in c0003 (table +
columns + the exact `rra` constraint names per Task 5); add the `Tenant.status` CHECK to c0001; and set
the role/permission domain CHECK in c0002 to **`IN ('tenant','platform','resource')` — `'product'`
removed** (sec-review A-F5; must match the models in Task 5, else resource inserts fail at runtime or a
`'product'` role-domain silently survives). `alembic_control.ini` mirrors `template/alembic.ini` with
`script_location = migrations_control`.

- [ ] **Step 1:** Test — (a) apply BOTH chains against ONE Postgres URL and assert two distinct version
  tables exist (`alembic_version` and `alembic_version_multitenantauth`), all control tables created, no
  collision; (b) apply the control chain against a SEPARATE `control_database_url` and assert the app DB
  has no control tables (Meridian's override); (c) **autogenerate guard (DM-F1): with both chains applied
  co-located, `alembic check` on the app chain AND on the control chain each report "no changes" — i.e.
  neither proposes dropping the other's tables.** RED (without `include_*`, (c) emits spurious drops).
- [ ] **Step 2:** Author env/ini (incl. the `include_*` scoping on both env files) + port migrations. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): migrations_control chain + named version table + autogen scoping`).

> **Reviewers:** verify the named version table isolates version bookkeeping AND the `include_*` scoping
> isolates autogenerate (the co-located `alembic check` reports no changes for either chain); a downgrade
> of one chain can't touch the other's table.

### Task 8: Entrypoint runs both chains + seeds the control vocabulary + control-engine lifespan

> **Sec-review OPS-F1 (PLAN-BLOCKER, fixed here): the control seed MUST be wired into boot.** Task 17
> *builds* `authz/seed.py` but nothing invokes it at startup, and the rendered consumer-owned `seed.py`
> seeds `Item`s, not the control vocabulary — so a fresh `--with multitenantauth` container boots healthy
> but with an empty `permission`/`role` catalog and **the first founder signup fails at runtime** (it
> needs the seeded `admin_role_name`). The LOCKED `entrypoint.sh` is the correct injection vector
> (the consumer `seed.py` can't be relied on). This also makes Task 21's live e2e passable.

**Files:** Modify `template/scripts/entrypoint.sh` (`.jinja`) — a battery-conditional region that, after
**both** `alembic upgrade head` chains, runs the control seed `python -m
{{package_name}}.multitenantauth.authz.seed` (so `authz/seed.py` needs a `__main__` / idempotent
`seed()` entry — note this in Task 17); modify `main.py.jinja` lifespan to `dispose_control_engine()` on
shutdown. Test: render assertions + the live docker test (Task 21) covers runtime.

- [ ] **Step 1:** Render-guard test: with `multitenantauth`, `entrypoint.sh` contains BOTH the control
  `alembic upgrade head` AND the control-seed invocation (ordered after both chains); without the battery,
  neither appears. RED.
- [ ] **Step 2:** Add the conditional region — run the control chain, then the app chain, then the
  control seed; all gated on `APP_RUN_MIGRATIONS` (idempotent re-run safe). Wire `dispose_control_engine()`
  into the existing shutdown path. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): run control migrations + seed vocabulary + dispose engine`).

---

## Phase C — Auth mechanism (pure)

### Task 9: Passwords + tokens + email-norm (security-critical)

**Files:** Create `.../multitenantauth/authn/{passwords,tokens,email_norm}.py`; modify
`pyproject.toml.jinja` (conditional `argon2-cffi>=23` dep). Tests: port
`meridian tests/unit/auth/{test_passwords,test_tokens,test_email_norm}.py`.

**Port** `passwords.py` (argon2id over HMAC-SHA256 pepper pre-hash; `hash_password`/`verify_password`/
`needs_rehash`), `tokens.py` (`mint`/`hash_token` = `HMAC-SHA256(raw, session_pepper)`), `email_norm.py`
verbatim. **Version columns are forward-compat ONLY (sec-review B-F8):** keep `settings.pepper_version`
and the model `AppUser.hash_version`, but there is NO live pepper rotation in Phase 1 — `_peppered`
reads only the single current pepper, so rotating it would mass-lock every user. Do NOT add rotation
logic; the columns reserve the seam. (The argon2 cost params + floor validators land in Task 2;
`verify_runtime` is wired in Task 16.)

- [ ] **Step 1:** Port the three unit tests (hash≠plaintext; verify round-trips; wrong-pepper fails;
  `needs_rehash` on cost change; token hash is HMAC, not the raw). RED.
- [ ] **Step 2:** Add the dep (conditional), port the modules. `uv sync` in `/tmp/work`. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): argon2id passwords + opaque tokens`).

> **Reviewers:** confirm the pepper is settings-only (never DB) and every `verify_password` failure mode
> returns False (only `VerifyMismatchError`/`VerificationError`/`InvalidHashError` are caught — a genuine
> config error still raises). NOTE: Phase 1 ships **no live pepper rotation** (the version column is a
> forward-compat seam only) — do not assert rotation-without-lockout.

### Task 10: Expr evaluator + resolution (security-critical — the evaluator seam)

**Files:** Create `.../multitenantauth/authz/{expr,resolution}.py`. Tests: port
`meridian tests/unit/auth/test_expr.py` + `test_expr_product.py` (→ `test_expr_resource.py`).

**Port** `expr.py` verbatim — recursive `Perm`/`ALL`/`ANY`, `_has_wildcard_leaf` (recursive),
construction-time guards (empty `ALL`/`ANY` raise; wildcard leaf anywhere under `ALL` raises),
`bind_resource`, `evaluate`, `Authorized`. **Transform:** `_is_product_resource`→`_is_resource_scoped`
(`"/resource:" in pattern`), the `product_grant` ctx key → `resource_grant`. **Port** `resolution.py`
verbatim (`platform_permissions`, `tenant_permissions`, `has_membership`, domain-split). Keep
`subtree_exists` as a ctx hook (the inert default is supplied by `guard` in Task 14). **Preserve the
exact `evaluate` branch order (sec-review A-F6): wildcard → resource-scoped → flat tenant_perms** — so an
authored `…/resource:*` leaf always hits the inert `subtree_exists` (deny) and never the live flat
`resource_grant`. Do not collapse the resource-scoped branch above the wildcard check.

- [ ] **Step 1:** Port the expr unit tests — incl. the security cases: `ALL()` empty raises; wildcard leaf
  under `ALL` raises (even nested `ALL(ANY(Perm(wild)))`); **a bound `*` path segment does NOT flip a
  concrete leaf to the subtree branch** (`test_path_value_star_does_not_flip…`); **a wildcard `resource:*`
  leaf still routes to `subtree_exists`, not the flat grant** (port `test_expr_product.py`'s
  wildcard-subtree case, renamed); platform grant can't satisfy a tenant leaf; missing path param → deny
  (not 500). RED.
- [ ] **Step 2:** Port + transform. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): recursive permission-expression evaluator`).

> **Reviewers:** this is the decision core. Verify the wildcard-is-a-property-of-the-pattern rule, the
> recursive ALL-guard, AND the wildcard→resource-scoped→flat branch order survived the port intact;
> confirm `subtree_exists` defaults to deny everywhere it's consumed (sec-review A-F10: assert exactly ONE
> inert construction site — a grep/unit guard — so it can't be locally overridden to allow); confirm no
> sealed/hidden tree logic was ported (stays Meridian-local).

---

## Phase D — Services

### Task 11: AuthZ service (grant/revoke + ≥1-admin TOCTOU — security-critical)

**Files:** Create `.../multitenantauth/authz/service.py`, `.../multitenantauth/errors.py`. Tests: port
`meridian tests/functional/test_auth_service.py` + `test_product_role_service.py` (→ resource-role).

**Port** `service.py` with transformations: `assign/revoke/change_role`, `add/remove_membership`,
`add_platform_role`, `assign/revoke_product_role`→`assign/revoke_resource_role` (`product_id`→
`resource_id`); the `_assert_not_last_admin` TOCTOU guard (`SELECT … FOR UPDATE` over the admin-assignment
set); the idempotent-no-phantom-audit rule; `AuthzEvent` recording. **Transform:** `_ADMIN_ROLE_NAME =
"tenant.admin"` → `get_settings().admin_role_name`. Port `errors.py` (`DomainMismatchError`,
`LastAdminError`, `AUTHZ_FORBIDDEN_DETAIL`). **De-fork fix (sec-review A-F4):** the reference's
`add_platform_role` records its `AuthzEvent` UNCONDITIONALLY (outside the `if existing is None` block —
`service.py:361`), so a repeated platform grant writes a phantom audit row — unlike the other four
grant/revoke fns. Move its `_record_event` INSIDE the `if existing is None` block to match them (and flag
this upstream to Meridian as a bug).

- [ ] **Step 1:** Port the service tests — incl. the ≥1-admin invariant (can't revoke/remove the last
  admin), idempotent grant records no phantom audit (**including a repeated `add_platform_role` → no
  second event**), domain-mismatch raises, resource-role flat grant/revoke. RED.
- [ ] **Step 2:** Port + transform (incl. the A-F4 fix). GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): authz grant/revoke service + ≥1-admin invariant`).

> **Reviewers:** verify the `FOR UPDATE` lock covers the whole admin set (TOCTOU-safe under concurrent
> demotions); `admin_role_name` is read from settings everywhere the reference hardcoded it; and audit
> fires only on real state changes for **all five** grant/revoke fns (the `add_platform_role` phantom-audit
> fix landed — sec-review A-F4).

### Task 12: Tenancy registry service (routing-agnostic)

**Files:** Create `.../multitenantauth/tenancy/registry.py` + `.../db/control/repository.py`. Tests: port
the control-registry portion of `meridian tests/unit/test_provisioning.py` + `test_tenancy.py`.

**Port** ONLY the control-registry half of `db/tenancy/provision.py`, **adapted to the opaque-id +
mutable-slug shape (Task 6):** `register_tenant(name, *, slug, dsn, status="provisioning")` — **generates
the opaque `tenant_id`** (does NOT take it from the slug), validates the slug is DNS-safe + claimable
(not a live slug, not a cooling history row), inserts via `control_repo.add_tenant`; `activate_tenant(id)`
(status→active); `get_tenant(id)`/`get_tenant_dsn(id)`; plus the slug mechanism: `rename_slug(id,
new_slug)` (validate DNS-safe + claimable, move the old slug to `TenantSlugHistory` with a
`reserved_until` cooling window, set the new slug) and `resolve_slug(slug) → (tenant_id, redirect: bool)`
(a live slug → its id; a retired history slug → its id + `redirect=True` for a 301; reserved/unknown →
None). **Keep** the `^[a-z0-9_]+$` charset guard for the opaque id (it's a Phase-2 DB-identifier
component). **Drop** `create_database`, `_migrate_tenant`, `seed_base_vocabulary`, `invalidate_dsn_cache`,
`build_engine(dsn)` — physical/EDR/Phase-2. The registry **never connects to `dsn`** (routing-agnostic —
Meridian's load-bearing assumption).

- [ ] **Step 1:** Test — `register_tenant` mints an opaque id **not equal to / not derived from** the
  slug, writes a `provisioning` row, **opens no connection to the dsn**; `activate_tenant` flips to
  `active`; an invalid opaque-id charset and a non-DNS-safe slug both raise; `rename_slug` moves the old
  slug to history with a future `reserved_until` and rejects a still-cooling slug; `resolve_slug` returns
  the live id, returns `(id, redirect=True)` for a retired slug, and `None` for a reserved/unknown one;
  `get_tenant_dsn` returns the stored opaque string. RED.
- [ ] **Step 2:** Implement the registry + repository. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): routing-agnostic tenant registry + slug lifecycle`).

> **Reviewers:** confirm no code path connects to a tenant `dsn` (grep `create_engine`/`tenant_session`
> in the battery → none); the opaque `id` is minted independent of `slug`; the two-step seam
> (register→activate) leaves physical provisioning to the consumer; a rename can't squat a cooling slug.

> **Ops note (sec-review OPS-F2, operator-decided):** the battery ships generic separate-control-DB
> *support* (set `APP_CONTROL_DATABASE_URL`; the target DB must already exist — document in
> `.env.example`/README + the cutover note). Adopting an **existing populated** control DB (Meridian's
> fork → battery schema: `product`→`resource`, `id`/`slug` split, `alembic stamp` onto the named version
> table) is a Meridian-specific data migration → **deferred to Meridian co-design**, not the battery.

### Task 13: AuthN routes + session helpers (signup / login / logout / set-password / me)

> **Plan-quality fix (sec-review PQ-C1/C2): there is NO `authn/service.py` in the reference.** The authn
> flows are **route handlers inline in `meridian routes/auth.py`** (signup L116, login, logout,
> set-password, `/auth/me`) plus the private helpers `_issue_session`, `_set_session_cookie`,
> `_allowlisted`, `_dummy_hash`. This task extracts those **routes + helpers** — a *novel extraction from
> route handlers*, not a port of a service module. **Sequencing: execute AFTER Task 14 (the deps chain) —
> login/logout/me consume `current_user`/`control_session`; signup consumes Tasks 9/11/12.**

**Files:** Create `.../multitenantauth/routes/auth.py` + `.../multitenantauth/cookies.py` (the
`set_session_cookie` helper, promoted from the reference's private `_set_session_cookie` — this is the
ONE home for it; Task 15 no longer creates it). Tests: port `meridian tests/functional/test_auth_routes.py`
(authn routes) + `test_auth_signup_security.py`.

**Extract** the authn route handlers + helpers: signup-founder (create `AppUser(born='signup')` +
`register_tenant`(slug)+`activate` + `add_membership` with `admin_role_name` + `_issue_session`), login
(`verify_password` + rehash-on-login + **a FRESH `mint()` session** — no pre-auth session ⇒ fixation
structurally prevented), logout (delete session), set-password / invite-accept (`InviteToken` redemption
— set password, stamp `accepted_at`, mark `used_at`, **delete all of the user's sessions**), `/auth/me`
(authenticated-self via `current_user`). `set_session_cookie` lands in `cookies.py` (httponly + secure +
samesite=lax + `domain=session_cookie_domain`). **Signup gating — TWO security-critical transformations
(sec-review B-F1 + A-F9, operator decision A):** (1) remap env tokens — `environment == "prod"` → 404
(off); the gate becomes `environment in {"dev","staging"}` (NOT Meridian's `{"dev","stage"}`); (2)
**fail-closed default** — flip the reference's "empty allowlist = unrestricted": `prod` off, **`staging`
+ empty allowlist = DENY (403)**, open only in `dev`. Document loudly in the rendered `.env.example` +
README — **and add the B-F11 note** there: a consumer adding a logged-in change-password/disable flow
must replicate `delete Session where user_id` (set-password already does).

- [ ] **Step 1:** Port the route + signup-security tests (TestClient, real mounted routes), ADAPTED to the
  new defaults: founder gets admin; duplicate email/slug → generic 409 (no enumeration); disabled user
  can't login; login mints a fresh token (fixation); set-password invalidates all sessions; invite
  single-use; **signup in `prod` → 404**; **`staging` + empty allowlist → 403 (fail-closed)**; `staging`
  + matching allowlist → 201; `dev` → 201. RED.
- [ ] **Step 2:** Extract routes + helpers + apply both transformations. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): fail-closed authn routes + session helpers`).

---

## Phase E — Deps, CSRF, routes

### Task 14: Request auth chain (deps — security-critical, 404-before-403)

**Files:** Create `.../multitenantauth/deps.py`. Tests: port `meridian tests/functional/test_auth_deps.py`.

**Port** `deps.py` with transformations: `control_session`, `current_user` (cookie→bearer→`Session`→
`AppUser`; 401), `active_tenant` (404-before-leak), `guard(expr)`. **Drop** `tenant_db` (Phase 2).
**Transform** the `guard` ctx: `subtree_exists` → inert `lambda name, resource: False`; `product_grant` →
a **flat** `resource_grant`. **Sec-review A-F1 — pass discrete args, do NOT re-parse a concatenated
string.** The reference splits `tenant:{tid}/product:{pid}` back apart in the resolver; a consumer's
opaque `resource_id` containing the literal `tenant:` or `/resource:` would mis-slice. Instead, read the
bound path params directly (they are already discrete keys in `ctx["path"]`): the evaluator's
resource-scoped branch calls `ctx["resource_grant"](node.name, ctx["path"])`, and the closure reads
`path["tenant_id"]` / `path["resource_id"]` verbatim — no substring surgery:

```python
def _resource_grant(name: str, path: dict[str, str]) -> bool:
    # Flat, control-DB only: does the user (via their (user, tenant) membership) hold a resource-role
    # granting `name` on this exact resource_id? tenant_id/resource_id come straight from the bound
    # path params — never parsed out of a concatenated resource string (A-F1).
    tid, rid = path.get("tenant_id"), path.get("resource_id")
    if tid is None or rid is None:
        return False
    membership_id = cs.scalar(select(m.TenantMembership.id).where(
        m.TenantMembership.user_id == user.id, m.TenantMembership.tenant_id == tid))
    if membership_id is None:                       # resolve membership by (user, tenant) FIRST
        return False
    hit = cs.scalar(
        select(m.ResourceRoleAssignment.id)
        .join(m.RolePermission, m.RolePermission.role_id == m.ResourceRoleAssignment.role_id)
        .where(m.ResourceRoleAssignment.membership_id == membership_id,   # (membership, resource) TOGETHER
               m.ResourceRoleAssignment.resource_id == rid,
               m.RolePermission.permission_name == name)
        .limit(1))
    return hit is not None
```

(No tree walk, no seal — Meridian overrides this hook with `candidate_grant_nodes` in Phase 2. Mirror the
`name, path` hook signature in the evaluator's resource-scoped branch, Task 10.)

- [ ] **Step 1:** Port the deps tests — 401 (no/expired/disabled), **404-before-403** (non-member of an
  existing tenant gets 404, never a 403 that leaks existence), **a guard-only route (binds `{tenant_id}`
  but does NOT depend on `active_tenant`) still returns 404 to a non-member** (sec-review A-F8 — the
  inline re-check is load-bearing), **a member of a `suspended`/`provisioning` tenant gets 404**
  (sec-review A-F7), 403 (valid member, missing perm), the single cached `control_session`. RED.
- [ ] **Step 2:** Port + transform. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): request auth chain + flat resource_grant`).

> **Reviewers:** the 404-before-403 ordering is the highest-stakes property — verify `guard` re-asserts
> membership before any 403 for tenant-scoped exprs, and that its **inline membership-404 re-check is NOT
> refactored to depend on `active_tenant`** (a guard-only route relies on it — sec-review A-F8). Verify the
> flat `resource_grant` resolves membership by `(user, tenant)` FIRST and matches on `(membership_id,
> resource_id)` together, from discrete path params, never `resource_id` alone or a parsed substring.

### Task 15: CSRF middleware + cookie delivery (security-critical, MDN multi-host shape)

**Files:** Create `.../multitenantauth/csrf.py` (the CSRF middleware ONLY — `cookies.py` with
`set_session_cookie` is created in Task 13; sec-review PQ-C2). Tests: port `meridian` CSRF tests (find
via `git grep -l CSRF tests/`, e.g. `test_csrf.py`) + new shape tests.

**Port** `middleware/csrf.py` with the **MDN §5.1 transformation** — replace the hardcoded single-host
comparison with the configurable allowlist:

```python
# was: if source and urlsplit(source).netloc != request.headers.get("host", ""):
host = request.headers.get("host", "")
netloc = urlsplit(source).netloc
# EXACT-MATCH ONLY (sec-review B-F4): csrf_allowed_origins holds exact netlocs; NO wildcards/patterns.
allowed = (netloc == host) or (netloc in settings.csrf_allowed_origins)
if source and not allowed:
    return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
```

(The cookie helper itself — `set_session_cookie`, `httponly=True`, `secure=session_cookie_secure` default
True, `samesite="lax"`, **`domain=session_cookie_domain`** None=host-only — lives in Task 13's
`cookies.py`.) **Sec-review B-F3/B-F4 — the multi-host knobs widen the trust boundary; the battery ships
exact-match + safe defaults and DOCUMENTS the risk, it does not implement subdomain support.** Add the
§5.1 invariants to the `csrf.py` + `cookies.py` module docstrings: a parent-domain session cookie
discloses the raw token to every subdomain's server (only enable where every subdomain is equally
trusted); `SameSite=Lax` gives no cross-tenant protection between sibling subdomains, so the exact-match
allowlist is the only cross-tenant CSRF defense — wildcards are forbidden.

- [ ] **Step 1:** Tests — (a) same-origin POST passes; (b) cross-origin cookie-auth POST → 403; (c)
  Bearer-only (no cookie) cross-origin → passes (exempt); **(c2) a junk `Authorization: Bearer …` header
  on a cookie-bearing cross-origin POST → 403 (cookie presence triggers the check; sec-review B-F7)**; (d)
  unauthenticated → passes; (e) absent Origin+Referer → passes (lenient); **(e2) with an EMPTY allowlist a
  cross-origin cookie POST still 403s (locks the same-origin equivalence; sec-review B-F6)**; (f)
  **shape:** an exact origin in `csrf_allowed_origins` passes; **(f2) a `*`/wildcard entry never
  substring-matches — a cross-origin POST still 403s (sec-review B-F4)**; (g) **shape:**
  `session_cookie_domain` set → the `Set-Cookie` carries `Domain=`; default unset → no `Domain=`. RED.
- [ ] **Step 2:** Port + transform. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): CSRF defence + multi-host cookie shape`).

> **Reviewers:** verify the default (empty allowlist) preserves strict same-origin (B-F6); the allowlist is
> **exact-match, wildcards inert/rejected** (B-F4); cookie presence (not a Bearer header) triggers the
> check — a junk `Authorization` must not exempt a cookie-bearing request (B-F7); `samesite="lax"` +
> `secure=True` + `httponly` defaults are retained; and the parent-domain-cookie + sibling-subdomain-Lax
> risks are documented in §5.1 (B-F3/B-F4).

### Task 16: Tenant/role routes + main.py wiring + authz-fitness (security-critical)

> **Sequencing/scope (sec-review PQ-C1/P1): the AUTHN routes are Task 13** — this task is the
> tenants/roles routes + app wiring + the fitness suite. Execute after Tasks 13/14/15.

**Files:** Create `.../multitenantauth/routes/{tenants,roles}.py`; modify `main.py.jinja` (conditional
router includes for ALL of auth[Task13]/tenants/roles + `app.add_middleware(CSRFMiddleware)` + **wire
`verify_runtime(settings)` at the TOP of `create_app()`, before any router include** — Task 2/9,
sec-review OPS-F7). Tests: port `meridian tests/functional/test_auth_routes.py` (tenant/role portions) +
**`test_authz_fitness.py`**.

**Port** the tenant/role route handlers (tenants: `POST /tenants`, `GET /tenants/{tenant_id}/members`,
manage-members; roles: grant/revoke) — each guarded with the appropriate `guard(Perm(...))`.

**Port the authz-fitness suite by its REAL tests (sec-review A-F2) — there are six, not "T1–T4":**
- `test_T1_no_unguarded_route` — deny-by-default allowlist;
- **`test_T1b_tenant_data_routes_must_be_guarded`** — the load-bearing "authenticated ≠ authorized" guard.
  `tenant_db` is dropped (Phase 2), so its predicate is `active_tenant`-only **with an explicit comment
  that the `tenant_db` arm re-arms in Phase 2** (so the dead arm is a documented seam, not an accident);
- `test_T2_tenant_routes_bind_tenant_id` — every `{tenant_id}` route binds it in its expression;
- `test_T3_response_models_never_carry_policy` — no `Authorized`/`Perm`/`ALL`/`ANY` in any response model;
- `test_T4_policy_vocabulary_absent_from_openapi` — the permission/role vocab never appears in OpenAPI;
- `test_T4b_403_body_is_the_generic_constant` — a real 403 carries only `AUTHZ_FORBIDDEN_DETAIL`.
**DROP** Meridian's `test_T2_product_id_bound_routes_are_the_expected_set` (its exact product-route set is
Meridian-specific) — replace with a `{resource_id}`-binding assertion only if a resource-grain route ships
in Phase 1 (none does → omit).

**De-Meridianize the allowlists (sec-review A-F3 / Global Constraints):** rebuild `PUBLIC` for the
battery's surface — `/auth/signup`, `/auth/login`, `/auth/logout`, `/auth/set-password`, `/auth/me`,
`/heartbeat`, `/health`, `/ready`, `/metrics`, `/openapi.json`, `/docs`, `/docs/oauth2-redirect`,
`/redoc` — with **every `/edr/*` entry struck**. Set `INLINE_AUTHZ = set()` (Meridian's only inline-authz
route was the product visibility route, which doesn't ship). A stale Meridian path left in either set = a
silently unguarded route.

- [ ] **Step 1:** Port route + the six fitness tests + the rebuilt allowlists. RED (routes absent → fitness fails).
- [ ] **Step 2:** Port routes; wire `main.py.jinja` (conditional includes + CSRF middleware + `verify_runtime`). GREEN.
- [ ] **Step 3:** `ruff format --check` rendered. Commit (`feat(multitenantauth): auth/tenant/role routes
  + authz-fitness`).

> **Reviewers:** authz-fitness is the structural guarantee no route ships unguarded — verify all six hold,
> that `PUBLIC`/`INLINE_AUTHZ` contain ZERO Meridian/EDR/product paths (A-F3), and that T1b's
> `active_tenant`-only predicate is a documented Phase-2 seam (A-F2).

---

## Phase F — Seed (policy — UNLOCKED)

### Task 17: Minimal generic seed catalog + reconciliation

**Files:** Create `.../multitenantauth/authz/permissions.py`, `roles.py`, `seed.py`. Tests: port
`meridian tests/functional/test_authz_seed.py` + `test_product_vocabulary.py` (→ minimal generic).

**Novel (minimal generic policy).** `permissions.py` ships ONLY a worked-example catalog (NOT Meridian's
EDR vocab):

```python
CATALOG = (
    PermDef("tenant:read", "tenant", "Read tenant resources", True),
    PermDef("tenant:manage-members", "tenant", "Invite/grant/revoke tenant members", True),
)
```

`roles.py` ships `tenant.admin` (`{tenant:read, tenant:manage-members}`) + `tenant.member` (`{tenant:read}`)
+ one custom-DB-role proving the seam. `seed.py` materializes catalog + roles + bundles and runs the
**reconciliation check** (every bundled perm exists + is live; **cross-domain guard:** a `tenant` role
bundles only `tenant` perms — MDN48). These two files render **INTENTIONALLY_UNLOCKED**.

- [ ] **Step 1:** Test — seed is idempotent; reconciliation rejects a bundle referencing an unknown/
  cross-domain perm; built-ins are edit/shadow-protected. RED.
- [ ] **Step 2:** Implement. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): minimal generic seed catalog + reconciliation`).

> **Reviewers:** confirm NO Meridian/EDR/product vocabulary leaked into the shipped catalog; the
> cross-domain bundle guard is enforced at seed time.

---

## Phase G — Integration: obs, integrity, FWK29

### Task 18: Observability (in-process)

**Files:** Create the metric definitions (in `multitenantauth/` — login/session/authz/grant-revoke
counters+gauges on the app `/metrics`); `infra/observability/prometheus/alerts/{{ '...' }}.jinja`;
`infra/observability/grafana/dashboards/{{ '...' }}.jinja`. Test: extend `tests/test_obs_completeness.py`
keyed on `battery.obs` ([[obs-completeness-guard-already-exists]]).

- [ ] **Step 1:** Extend `test_obs_completeness` — `multitenantauth` (obs="in-process") owes an alert +
  a dashboard; assert they exist + the metrics appear on a rendered `/metrics`. RED.
- [ ] **Step 2:** Add metrics (auth success/failure, session create/active gauge, authz allow/deny by
  domain, grant/revoke), an alert (e.g. authz-deny-rate spike, login-failure spike), a dashboard. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): in-process auth observability`).

### Task 19: Integrity classification

**Files:** Modify `src/framework_cli/integrity/classes.py`. Test: `tests/integrity/test_classes.py` /
`test_coverage.py` (the FWK7 reverse check).

- [ ] **Step 1:** Test — render all-batteries; assert every new `multitenantauth` file is classified;
  `permissions.py`/`roles.py` are INTENTIONALLY_UNLOCKED; mechanism files are BATTERY_LOCKED (gated on
  `multitenantauth`). RED (unclassified → `AuthoringError`).
- [ ] **Step 2:** Add `BATTERY_LOCKED` entries (mechanism, models, migrations, deps, services, csrf,
  control engine) gated on `multitenantauth`; add the two seed files to INTENTIONALLY_UNLOCKED; settings
  region → HYBRID. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): integrity classification`).

### Task 20: FWK29 runtime-coverage classification

**Files:** Modify `tests/runtime_coverage/registry.py`. Test: `test_completeness.py` (the gate-tier guard).

- [ ] **Step 1:** Run the completeness check — new surfaces (control session, `migrations_control` chain,
  auth/tenant/role routes, CSRF middleware, entrypoint's 2nd alembic) are unclassified → RED.
- [ ] **Step 2:** Classify each EXERCISED (Task 21 live test covers them) / EXEMPT / KNOWN_GAP. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): FWK29 runtime-coverage classification`).

---

## Phase H — Acceptance & release readiness

### Task 21: Acceptance — generated project + live docker

**Files:** Modify `tests/acceptance/test_rendered_project.py` (new `multitenantauth` cases) + port
`meridian tests/e2e/test_auth_tenancy_e2e.py`.

- [ ] **Step 1:** Acceptance tests — (a) a `--with multitenantauth` project's own auth suite passes +
  meets the coverage gate; (b) its **first pre-commit runs clean**; (c) **live docker**: bring up
  Postgres, run both alembic chains, then signup → login → `GET /tenants/{tid}/members` (200) and an
  unauthenticated/cross-tenant request (401/404). RED.
- [ ] **Step 2:** Resolve whatever the live run surfaces (this is where real integration bugs appear —
  [[meridian-is-the-de-facto-integration-test]]). GREEN.
- [ ] **Step 3:** Commit (`test(multitenantauth): acceptance + live docker e2e`).

### Task 22: Render-matrix combos + release readiness

**Files:** Modify `.github/workflows/render-matrix.yml` (add `multitenantauth` baseline + a
with-other-batteries combo); run the release-readiness renders locally.

- [ ] **Step 1:** Add the matrix combos. Locally render baseline + all-batteries + `multitenantauth`-single
  and run each rendered project's `mypy`/`ruff`/tests ([[release-readiness-needs-render-not-local-gate]]).
- [ ] **Step 2:** Fix any render/format/dep-drift. Full framework gate green (`pytest -q`, `ruff check`,
  `ruff format --check`, `mypy src`).
- [ ] **Step 3:** Commit (`ci(multitenantauth): render-matrix combos`). **Release cut is post-merge** per
  [[release-cut-procedure]] (bump pyproject + lock + DOGFOOD_COMMIT, tag → release.yml).

---

## Layer-2 pre-merge gate — stance × focus matrix (Meridian method, white-box)

Run against the **implemented, green, pushed branch**, before merge — the attacker-oriented half of the
two-layer method (Layer 1 was the design panels above). Per the method:

**Baseline first:** `/code-review` + the framework `security` agent + an explicit `/security-review` over
the rendered battery (scoped "Phase-1 standalone"; Phase-2 seams = by-design) + the Sonnet spec-compliance
+ Opus whole-branch reviews. Fold their findings into the synthesis.

**Then the matrix.** Populate only the relevant cells (~10–14), each a white-box agent with a concrete
brief; offence findings (Break-in/Damage) carry a **concrete repro or downgrade**; every Critical/High is
**independently verified, default-to-refuted**; fix-loop (repro → failing test → fix → re-run the
affected stance) **until K rounds are dry**. Stances × focus (F1 authn/sessions · F2 authz/RBAC · F3
tenant isolation · F4 data/migrations/concurrency · F5 cutover/ops):

```
              F1 authn/session   F2 authz/RBAC     F3 isolation        F4 data/concur        F5 cutover/ops
Break-in      session forge/      404→403 leak;     cross-tenant via    —                     —
              fixate/replay;      guard bypass;     opaque-id/slug
              CSRF multi-host     wildcard/subtree  desync; resolve_slug
              (parent-domain,     allow-leak        history→wrong tenant
              sibling-Lax)
Harden        pepper/verify_      seed cross-domain  —                  CHECK/composite-FK    verify_runtime gate;
              runtime gate;       bundle; default-                      domain integrity;     entrypoint seed/order;
              fail-closed signup  deny completeness                     autogen include_*     /ready; conn-budget
Disrupt       signup→tenant       —                 —                   ≥1-admin lock          two-pool exhaustion;
              creation DoS                                              contention; slug-     idempotent-grant race
              (fail-closed)                                             cooling growth
Damage        —                   —                 cross-tenant        audit-trail tamper;   control-chain
                                                     bleed; slug-squat   migration drop/      downgrade data loss;
                                                     after rename        rollback             autogen drop_table
```

**Merge gate: zero open Critical/High** — each fixed-with-a-regression-test or explicitly
refuted-with-reason. Record the run + confirmed findings in `ACTION_LOG.md`. Orchestrate as a
fan-out → verify → synthesise → fix-loop workflow (a deterministic multi-agent runner is ideal). Also
reconcile against Meridian's own prior security-review of this code (their threat-model oracle).

---

## Self-review (controller, against the spec)

- **Spec coverage:** §3 in-scope items → Tasks 1–17; §5/§5.1 evaluator+CSRF shape → Tasks 10/14/15;
  §6 architecture → Tasks 1–8; §7 components → Tasks 2–17; §8 data flow → Tasks 13/14/16; §9 errors →
  Tasks 14/15; §10 testing → every task + 21/22; §11 integrity/FWK29/obs → Tasks 18–20; §12 release/review
  → Task 22 + branch-end; §13 deferrals → PLAN stubs FWK59/60 (out of this plan, correctly). **No gaps.**
- **Placeholder scan:** port-instructions name exact source files + transformations (not placeholders);
  novel code is shown in full. The one open reconcile (`hash_version`/`pepper_version`) is a *decide-one*
  in Task 9, not a placeholder.
- **Type consistency:** `resource_role_assignment`/`resource_id`/`resource_grant` used consistently from
  Task 5 through Task 14; `control_session_factory` (Task 3) consumed in **Task 14** (Task 7's `env.py`
  consumes `control_database_url` + `ControlBase.metadata`, not the factory — PQ-P4); `admin_role_name`
  (Task 2) consumed in Tasks 11/13; `csrf_allowed_origins`/`session_cookie_domain` (Task 2) consumed in
  Task 15; `set_session_cookie`/`cookies.py` (Task 13) consumed by Task 13's authn routes.
- **Layer-1 hardening applied (2026-06-23):** the two-agent security review + the 3-lens design panel
  (data-model/ops/plan-quality) per Meridian's method; see the "Security-review ledger" + "Layer-1
  Hardening" sections. Pre-merge = the Layer-2 stance×focus matrix.
