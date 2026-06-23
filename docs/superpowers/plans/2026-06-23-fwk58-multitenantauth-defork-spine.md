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
  `database_url`), `session_cookie_name: str`, `session_cookie_secure: bool`,
  `session_cookie_domain: str | None = None`, `csrf_allowed_origins: set[str] = set()`,
  `session_pepper: SecretStr`, `password_pepper: SecretStr`, `argon2_time_cost/memory_cost/parallelism:
  int`, `admin_role_name: str = "tenant.admin"`, `session_ttl_hours: int`.

- [ ] **Step 1: Failing test** — port `test_settings_auth.py`; assert defaults (`session_cookie_domain is
  None`, `csrf_allowed_origins == set()`, `admin_role_name == "tenant.admin"`) and that
  `control_database_url` falls back to `database_url` when `APP_CONTROL_DATABASE_URL` is unset.
- [ ] **Step 2: Run — FAIL** (fields absent).
- [ ] **Step 3: Implement** the conditional settings region. The control-URL fallback (a Pydantic
  `model_validator(mode="after")` or a computed default): if `APP_CONTROL_DATABASE_URL` is unset,
  `control_database_url = database_url`. `session_pepper`/`password_pepper` are `SecretStr` (required, no
  default → fail-fast). Document the [[app-environment-tokens-never-production]] posture for any env gating.
- [ ] **Step 4: Run — PASS.** `ruff format --check` the rendered settings.
- [ ] **Step 5: Commit** (`feat(multitenantauth): auth settings region`).

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
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from {{package_name}}.config.settings import get_settings
from {{package_name}}.db.engine import build_engine, build_session_factory

_control_engine: Engine | None = None
_control_factory: "sessionmaker[Session] | None" = None

def control_engine() -> Engine:
    global _control_engine
    if _control_engine is None:
        _control_engine = build_engine(get_settings().control_database_url)
    return _control_engine

def control_session_factory() -> "sessionmaker[Session]":
    global _control_factory
    if _control_factory is None:
        _control_factory = build_session_factory(control_engine())
    return _control_factory

def dispose_control_engine() -> None:
    global _control_engine, _control_factory
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
`ProductRoleAssignment`→`ResourceRoleAssignment` (table `resource_role_assignment`, `product_id`→
`resource_id`, `role_domain` default/CHECK `'product'`→`'resource'`, constraint/index names
`*_pra_product_*`→`*_rra_*`). The composite FK `(role_id, role_domain) → role(id, domain)` + per-table
`CHECK(role_domain = '<domain>')` is the **load-bearing integrity mechanism** — preserve exactly. Update
`ck_role_domain` / `ck_permission_domain` to `IN ('tenant','platform','resource')`.

**MDN48 cheap-in-window items, add here:**
- `Tenant.status` CHECK (Task 6, the tenant model) — `CHECK(status IN ('provisioning','active','suspended'))`.
- Cross-domain `role_permission` enforcement: a `tenant`-domain role must not bundle a `platform` perm.
  Implement as a **seed-time reconciliation assertion** (Task 17) AND document the DB-level option
  (composite FK `(role_id) → role` is domain-agnostic; a trigger/loader check is the pragmatic guard).
  → reviewers: confirm the chosen enforcement point is sufficient.

- [ ] **Step 1:** Port the resource-role model test — assert a `tenant`-domain role **cannot** be inserted
  into `resource_role_assignment` (composite-FK + CHECK rejects it), and a flat resource grant round-trips.
  Confirm RED.
- [ ] **Step 2:** Port + transform the models. Confirm GREEN. Verify `role.domain` CHECK includes `resource`.
- [ ] **Step 3:** Commit (`feat(multitenantauth): authz models + generic resource-scope`).

> **Reviewers:** this is the integrity spine. Verify the rename preserved every composite FK + CHECK; that
> `resource` is in the `role`/`permission` domain CHECKs; that no `product`/EDR reference leaked in.

### Task 6: Tenant models

**Files:** Create `.../db/control/models/tenant.py`; test ports `test_tenancy.py` (model portion).
**Port** `tenant.py` verbatim (`Tenant`, `TenantMembership`) + **add** the `Tenant.status` CHECK (MDN48).

- [ ] **Step 1:** Test: membership uniqueness `(user_id, tenant_id)`; `Tenant.status` rejects a junk value.
  RED.
- [ ] **Step 2:** Port + add CHECK. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): tenant registry models`).

### Task 7: `migrations_control` chain with a NAMED version table (novel — load-bearing)

**Files:**
- Create: `template/{{ 'alembic_control.ini' if 'multitenantauth' in batteries else '' }}.jinja`
- Create: `template/{% if "multitenantauth" in batteries %}migrations_control{% endif %}/env.py.jinja`,
  `script.py.mako`, `versions/c0001_*.py`, `c0002_*.py`, `c0003_*.py`
- Test: `template/tests/unit/{{ 'test_control_migrations.py' if ... }}.jinja`

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
`c0002_auth_model`, `c0003_product_role_assignment`) — transform `product`→`resource` in c0003; add the
`Tenant.status` CHECK to c0001 and the `resource` value to the role/permission domain CHECKs in c0002.
`alembic_control.ini` mirrors `template/alembic.ini` with `script_location = migrations_control`.

- [ ] **Step 1:** Test — apply BOTH chains against ONE Postgres URL and assert two distinct version
  tables exist (`alembic_version` and `alembic_version_multitenantauth`), all control tables created, no
  collision. Then a second test: apply the control chain against a SEPARATE `control_database_url` and
  assert the app DB has no control tables (Meridian's override). RED.
- [ ] **Step 2:** Author env/ini + port migrations. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): migrations_control chain + named version table`).

> **Reviewers:** verify the named version table truly isolates the chains in the co-located case, and that
> a downgrade of one chain can't touch the other's table.

### Task 8: Entrypoint runs both chains + control-engine lifespan

**Files:** Modify `template/scripts/entrypoint.sh` (or `.jinja`) — conditional second `alembic -c
alembic_control.ini upgrade head`; modify `main.py.jinja` lifespan to `dispose_control_engine()` on
shutdown. Test: a render assertion + the live docker test (Task 21) covers runtime.

- [ ] **Step 1:** Render-guard test: with `multitenantauth`, `entrypoint.sh` contains the control
  `alembic upgrade head`; without it, it doesn't. RED.
- [ ] **Step 2:** Add the conditional region (run the control chain BEFORE the app chain; both gated on
  `APP_RUN_MIGRATIONS`). Wire `dispose_control_engine()` into the existing shutdown path. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): run control migrations + dispose control engine`).

---

## Phase C — Auth mechanism (pure)

### Task 9: Passwords + tokens + email-norm (security-critical)

**Files:** Create `.../multitenantauth/authn/{passwords,tokens,email_norm}.py`; modify
`pyproject.toml.jinja` (conditional `argon2-cffi>=23` dep). Tests: port
`meridian tests/unit/auth/{test_passwords,test_tokens,test_email_norm}.py`.

**Port** `passwords.py` (argon2id over HMAC-SHA256 pepper pre-hash; `hash_password`/`verify_password`/
`needs_rehash`), `tokens.py` (`mint`/`hash_token` = `HMAC-SHA256(raw, session_pepper)`), `email_norm.py`
verbatim. **Reconcile** the version column: the model uses `hash_version`; align `passwords.py`'s rotation
story to a single column + setting (decide `hash_version` + `APP_HASH_VERSION`, or keep Meridian's
`pepper_version`/`APP_PEPPER_VERSION` and rename the model column — pick ONE; spec §14).

- [ ] **Step 1:** Port the three unit tests (hash≠plaintext; verify round-trips; wrong-pepper fails;
  `needs_rehash` on cost change; token hash is HMAC, not the raw). RED.
- [ ] **Step 2:** Add the dep (conditional), port the modules, reconcile the version column. `uv sync` in
  `/tmp/work`. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): argon2id passwords + opaque tokens`).

> **Reviewers:** confirm the pepper is settings-only (never DB), failure modes all → False (no exception
> leak), and the chosen version-column reconciliation supports rotation without mass lockout.

### Task 10: Expr evaluator + resolution (security-critical — the evaluator seam)

**Files:** Create `.../multitenantauth/authz/{expr,resolution}.py`. Tests: port
`meridian tests/unit/auth/test_expr.py` + `test_expr_product.py` (→ `test_expr_resource.py`).

**Port** `expr.py` verbatim — recursive `Perm`/`ALL`/`ANY`, `_has_wildcard_leaf` (recursive),
construction-time guards (empty `ALL`/`ANY` raise; wildcard leaf anywhere under `ALL` raises),
`bind_resource`, `evaluate`, `Authorized`. **Transform:** `_is_product_resource`→`_is_resource_scoped`
(`"/resource:" in pattern`), the `product_grant` ctx key → `resource_grant`. **Port** `resolution.py`
verbatim (`platform_permissions`, `tenant_permissions`, `has_membership`, domain-split). Keep
`subtree_exists` as a ctx hook (the inert default is supplied by `guard` in Task 14).

- [ ] **Step 1:** Port the expr unit tests — incl. the security cases: `ALL()` empty raises; wildcard leaf
  under `ALL` raises (even nested `ALL(ANY(Perm(wild)))`); a bound `*` path segment does NOT flip a
  concrete leaf to the subtree branch; platform grant can't satisfy a tenant leaf; missing path param →
  deny (not 500). RED.
- [ ] **Step 2:** Port + transform. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): recursive permission-expression evaluator`).

> **Reviewers:** this is the decision core. Verify the wildcard-is-a-property-of-the-pattern rule and the
> recursive ALL-guard survived the port intact; confirm `subtree_exists` defaults to deny everywhere it's
> consumed; confirm no sealed/hidden tree logic was ported (that stays Meridian-local).

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
`LastAdminError`, `AUTHZ_FORBIDDEN_DETAIL`).

- [ ] **Step 1:** Port the service tests — incl. the ≥1-admin invariant (can't revoke/remove the last
  admin), idempotent grant records no phantom audit, domain-mismatch raises, resource-role flat
  grant/revoke. RED.
- [ ] **Step 2:** Port + transform. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): authz grant/revoke service + ≥1-admin invariant`).

> **Reviewers:** verify the `FOR UPDATE` lock covers the whole admin set (TOCTOU-safe under concurrent
> demotions); `admin_role_name` is read from settings everywhere the reference hardcoded it; audit fires
> only on real state changes.

### Task 12: Tenancy registry service (routing-agnostic)

**Files:** Create `.../multitenantauth/tenancy/registry.py` + `.../db/control/repository.py`. Tests: port
the control-registry portion of `meridian tests/unit/test_provisioning.py` + `test_tenancy.py`.

**Port** ONLY the control-registry half of `db/tenancy/provision.py`: `register_tenant(name, *, tenant_id,
dsn, status="provisioning")` (row insert via `control_repo.add_tenant`), `activate_tenant(tenant_id)`
(status→active), `get_tenant`/`get_tenant_dsn`. **Keep** the `_TENANT_ID_RE = ^[a-z0-9_]+$` charset guard.
**Drop** `create_database`, `_migrate_tenant`, `seed_base_vocabulary`, `invalidate_dsn_cache`,
`build_engine(dsn)` — all physical/EDR/Phase-2. The registry **never connects to `dsn`** (routing-agnostic
— Meridian's load-bearing assumption).

- [ ] **Step 1:** Test — `register_tenant` writes a `provisioning` row with an opaque dsn and **opens no
  connection to it**; `activate_tenant` flips to `active`; invalid tenant_id charset raises;
  `get_tenant_dsn` returns the stored opaque string. RED.
- [ ] **Step 2:** Implement the registry + repository. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): routing-agnostic tenant registry`).

> **Reviewers:** confirm no code path connects to a tenant `dsn` (grep for `create_engine`/`tenant_session`
> in the battery → none); the two-step seam (register→activate) leaves physical provisioning to the consumer.

### Task 13: AuthN service (signup / login / logout / invite)

**Files:** Create `.../multitenantauth/authn/service.py`. Tests: port
`meridian tests/functional/test_auth_service.py` (authn portion) + `test_auth_signup_security.py`.

**Port** the authn flows: signup-founder (create `AppUser(born='signup')` + `register_tenant`+`activate`
+ `add_membership` with `admin_role_name` + mint session), login (`verify_password` + rehash-on-login +
mint session), logout (delete session), invite/accept (`InviteToken` redemption — set password, stamp
`accepted_at`, mark `used_at`). The `signup_allowlist` gating ([[app-environment-tokens-never-production]]
posture — fail-closed allowlist semantics: empty = unrestricted is the reference's choice; keep it).

- [ ] **Step 1:** Port the authn + signup-security tests (founder gets admin; duplicate email rejected;
  disabled user can't login; invite single-use; allowlist enforced). RED.
- [ ] **Step 2:** Port. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): authn signup/login/invite service`).

---

## Phase E — Deps, CSRF, routes

### Task 14: Request auth chain (deps — security-critical, 404-before-403)

**Files:** Create `.../multitenantauth/deps.py`. Tests: port `meridian tests/functional/test_auth_deps.py`.

**Port** `deps.py` with transformations: `control_session`, `current_user` (cookie→bearer→`Session`→
`AppUser`; 401), `active_tenant` (404-before-leak), `guard(expr)`. **Drop** `tenant_db` (Phase 2).
**Transform** the `guard` ctx: `subtree_exists` → inert `lambda name, resource: False`; `product_grant` →
a **flat** `resource_grant` closure that queries `resource_role_assignment × role_permission` directly:

```python
def _resource_grant(name: str, resource: str) -> bool:
    # resource == "tenant:{tid}/resource:{rid}" (bound by the evaluator). Flat, control-DB only:
    # does the user (via their tenant membership) hold a resource-role granting `name` on `rid`?
    try:
        tid = resource.split("tenant:", 1)[1].split("/resource:", 1)[0]
        rid = resource.split("/resource:", 1)[1]
    except (IndexError, ValueError):
        return False
    membership_id = cs.scalar(select(m.TenantMembership.id).where(
        m.TenantMembership.user_id == user.id, m.TenantMembership.tenant_id == tid))
    if membership_id is None:
        return False
    hit = cs.scalar(
        select(m.ResourceRoleAssignment.id)
        .join(m.RolePermission, m.RolePermission.role_id == m.ResourceRoleAssignment.role_id)
        .where(m.ResourceRoleAssignment.membership_id == membership_id,
               m.ResourceRoleAssignment.resource_id == rid,
               m.RolePermission.permission_name == name)
        .limit(1))
    return hit is not None
```

(No tree walk, no seal — Meridian overrides this hook with `candidate_grant_nodes` in Phase 2.)

- [ ] **Step 1:** Port the deps tests — 401 (no/expired/disabled), **404-before-403** (non-member of an
  existing tenant gets 404, never a 403 that leaks existence), 403 (valid member, missing perm), the
  single cached `control_session`. RED.
- [ ] **Step 2:** Port + transform. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): request auth chain + flat resource_grant`).

> **Reviewers:** the 404-before-403 ordering is the highest-stakes property — verify `guard` re-asserts
> membership before any 403 for tenant-scoped exprs; verify the flat `resource_grant` resolves membership
> by `(user, tenant)` first and matches on `resource_id` (never `resource_id` alone).

### Task 15: CSRF middleware + cookie delivery (security-critical, MDN multi-host shape)

**Files:** Create `.../multitenantauth/csrf.py`; create `.../multitenantauth/cookies.py` (the
`set_session_cookie` helper). Tests: port `meridian` CSRF tests (find via `git grep -l CSRF tests/`) +
new shape tests.

**Port** `middleware/csrf.py` with the **MDN §5.1 transformation** — replace the hardcoded single-host
comparison with the configurable allowlist:

```python
# was: if source and urlsplit(source).netloc != request.headers.get("host", ""):
host = request.headers.get("host", "")
netloc = urlsplit(source).netloc
allowed = (netloc == host) or (netloc in settings.csrf_allowed_origins)
if source and not allowed:
    return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
```

`cookies.py` `set_session_cookie(response, raw)` — `httponly=True`, `secure=session_cookie_secure`,
`samesite="lax"`, **`domain=session_cookie_domain`** (None = host-only).

- [ ] **Step 1:** Tests — (a) same-origin POST passes; (b) cross-origin cookie-auth POST → 403; (c)
  Bearer-only (no cookie) cross-origin → passes (exempt); (d) unauthenticated → passes; (e) absent
  Origin+Referer → passes (lenient); (f) **shape:** an origin in `csrf_allowed_origins` passes; (g)
  **shape:** `session_cookie_domain` set → the `Set-Cookie` carries `Domain=`. RED.
- [ ] **Step 2:** Port + transform. GREEN.
- [ ] **Step 3:** Commit (`feat(multitenantauth): CSRF defence + multi-host cookie shape`).

> **Reviewers:** verify the default (empty allowlist) preserves strict same-origin; that the cookie
> presence (not a Bearer header) triggers the check (a junk `Authorization` header must not exempt a
> cookie-bearing request); that `samesite="lax"` + `secure` defaults are retained.

### Task 16: Routes + main.py wiring + authz-fitness (security-critical)

**Files:** Create `.../multitenantauth/routes/{auth,tenants,roles}.py`; modify `main.py.jinja`
(conditional router includes + `app.add_middleware(CSRFMiddleware)`). Tests: port
`meridian tests/functional/test_auth_routes.py` + **`test_authz_fitness.py`** (the T1–T4 crown jewels).

**Port** the route handlers (auth: `POST /auth/signup|login|logout`, invite-accept; tenants: `POST
/tenants`, `GET /tenants/{tenant_id}/members`, manage-members; roles: grant/revoke) — each guarded with
the appropriate `guard(Perm(...))`. The routes set the session cookie via `set_session_cookie`. Port the
**authz-fitness** tests verbatim (T1: every mutating tenant route is guarded; T2: every guard's resource
params are bound from the path; T3: `__authorized__` is never serialized; T4: coherent domain usage).

- [ ] **Step 1:** Port route + fitness tests. RED (routes absent → fitness fails).
- [ ] **Step 2:** Port routes; wire `main.py.jinja` (conditional includes + CSRF middleware). GREEN.
- [ ] **Step 3:** `ruff format --check` rendered. Commit (`feat(multitenantauth): auth/tenant/role routes
  + authz-fitness`).

> **Reviewers:** the authz-fitness suite is the structural guarantee that no route ships unguarded or
> with an incoherent contract — verify all four hold for the battery's full route set.

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

## Branch-end review (before merge)

1. **Spec-compliance review** (Sonnet) — every spec §1–§15 requirement has a landing task.
2. **Code-quality review** (Opus) — whole branch.
3. **Framework `security` agent over the rendered battery** — scoped to "Phase 1 standalone"
   (deferred Phase-2 seams = by-design, not defects); triage Phase-2 findings as known-deferred.
4. **Explicit `/security-review`** on the full diff.
5. Reconcile against Meridian's original security-review spec (provided separately) — confirm every
   threat it covers maps to a battery test or an explicit deferral.

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
  Task 5 through Task 14; `control_session_factory` (Task 3) consumed in Tasks 7/14; `admin_role_name`
  (Task 2) consumed in Task 11; `csrf_allowed_origins`/`session_cookie_domain` (Task 2) consumed in Task 15.
