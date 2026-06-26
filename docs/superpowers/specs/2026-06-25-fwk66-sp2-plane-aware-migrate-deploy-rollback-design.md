# FWK66 (SP2) — Plane-aware migrate / deploy / rollback (design)

> **FWK66 = FWK58 Phase 2, SP2** — the second sub-project of the `multitenantauth`
> Meridian→Framework de-fork's physical-plane half. Phase 2 decomposes into **SP1 / FWK61**
> (the physical routing core — *shipped v0.4.2*), **SP2 / FWK66** (this spec — plane-aware
> migrate/deploy/rollback), and **SP3 / FWK67** (authz-mechanism re-touch + lifecycle hardening +
> the folded FWK63 seam residuals). Build order SP1 → SP2 → SP3. *(SP1/SP2/SP3 are friendly prose
> labels; each sub-project is a flat `FWK<n>` PI ledger row, branch, spec, and PUR — see
> the FWK61-Phase-2 ID map.)*
>
> This is a **promote-up** under the vendored `cross-repo-convention.md` (`CROSS-REPO-convention: v4`):
> generator = **meridian** (validated reference impl), absorber = **swiftwater-framework**. Recorded in
> `docs/superpowers/decisions/DEC-0003-multitenantauth-promote-up.md` (parent) + a new SP2 sub-record
> **`DEC-0005`** once this design is approved.

## 1. Problem & strategy

SP1 (v0.4.2) shipped the physical routing core: per-tenant engine registry, connect-time DSN resolution
(`tenant_session`), idempotent single-tenant provisioning, and a per-tenant **migrate primitive**
(`migrate_tenant(dsn)`, alembic via the Python API). But **nothing fans out**. A multitenant project today has
**three database planes**:

1. **Control plane** — `control_database_url` (the tenant registry + auth + sessions; its own alembic chain,
   `migrations_control/`, version table `alembic_version_multitenantauth`).
2. **Default business DB** — `database_url` (the app/business schema, e.g. `items`). This is **live**: the
   shipped demo routes (`/items`, graphql, webhooks, agents) all bind to `get_session()` → the engine built
   from `database_url`; **no shipped route consumes `tenant_db`** (SP1 left the data plane latent). So
   `database_url` is not a dev artifact — it is a real, served business DB.
3. **Per-tenant DBs** — `{tenant_db_name_prefix}_{tenant_id}`, one per active tenant, each carrying the same
   app/business schema (`migrations/`), reached by routing.

Two failures follow from the missing fan-out:

- **Migrate is single-plane.** `scripts/entrypoint.sh` runs `alembic upgrade head` (the app chain → `database_url`)
  and, under the battery, `alembic -c alembic_control.ini upgrade head` (control). It **never migrates the tenant
  DBs.** Ship a business-schema migration and every tenant DB silently goes stale → routed requests hit a tenant
  DB missing the new column/table.
- **Rollback is plane-blind and destructive.** `infra/deploy/strategy.sh` `rollback()` does
  `__target_migrate "downgrade ${rev}"` then redeploys the prior image. A `downgrade` is `alembic`'s reverse ops —
  it **drops** what the upgrade added. Fanned out across control + N tenant DBs, that is an **irreversible
  data-loss multiplier** (drop a column on tenant 1..N, drop auth tables on control), and partial failure leaves a
  schema-split fleet. This is precisely the MDN46 hazard Meridian documented but never wired.

**Strategy.** Build the fan-out on SP1's Python-API `migrate_tenant` primitive (not Meridian's subprocess shape);
make boot + deploy + rollback plane-aware, **all gated on the `multitenantauth` battery**; and under the battery
make rollback **image-only — no schema downgrade on any plane** — relying on the framework's existing **expand-only
migration contract** (`scripts/check_migrations.py`), with **contract migrations as an explicit rollback floor**.

**Why image-only rollback is safe (and what it costs).** A built image carries *code*, not data; all data lives in
the external Postgres DBs, which persist across deploys. Under the expand-only contract every migration is additive
(new nullable/defaulted columns, new tables/indexes), so the *old* image runs correctly against the *new*
(expanded) schema. Rollback therefore only needs to redeploy the prior image — the databases are untouched, no row
is lost. The accepted cost is **schema cruft**: a rolled-back feature leaves its additive schema behind (N× across
tenant DBs), reclaimed later by a deliberate **forward-only contract migration**. Cruft is cheap and deferrable;
auto-`downgrade` data loss is catastrophic and irreversible — so we trade the former to forbid the latter. The
boundary: image-only rollback is safe *within an expand-only window only* — it is not a data backup, and it cannot
cross or rescue a contract (destructive) migration.

## 2. Scope

**In (SP2):**
- `upgrade_all()` — the plane-aware fan-out runner: control-first → default `database_url` → every active tenant
  DB, returning a per-target result map; control-fail-fast, tenant best-effort, non-zero exit on any failure.
- `active_tenant_dsns(control_session)` — a control-repository enumeration function (none exists today).
- Plane-aware **boot**: `scripts/entrypoint.sh.jinja` runs `upgrade_all` under the battery (replacing the two bare
  `alembic upgrade head` lines), unchanged otherwise.
- Plane-aware **Taskfile**: a battery-gated `db:migrate:all` target; bare `db:migrate` unchanged.
- Plane-aware **deploy/rollback**: `infra/deploy/strategy.sh` → `strategy.sh.jinja` — non-battery render
  **byte-identical to today**; battery render does rollback-by-image + the contract-floor refusal.
- `scripts/check_migrations.py` extended to scan **both** chains (`migrations/versions` *and*
  `migrations_control/versions`) — closes the gap the SP1 scorecard recorded.
- Multi-host discipline documentation: the `APP_RUN_MIGRATIONS=false` pre-roll step, made plane-aware, in
  `infra/deploy/README.md`.
- Conformance: real-Postgres, never-skip-neutral fan-out + isolation tests; a non-battery behavior-identity guard;
  the obs-completeness surface unchanged (no new gauges — the fan-out emits a structured result/log, see §6).
- The Phase-2 Layer-2 adversarial security pass scoped to migrate/deploy/rollback (incl. the SP1-recorded
  migration-data-safety cell).

**Out (deferred, boundary named):**
- **Real secrets backend** (PLAN.md Horizon "Secrets-backing") — SP1's `resolve_dsn` seam is reused as-is.
- **Suspend / teardown / orphan-DB lifecycle** — SP3. The fan-out migrates `active` tenants only; `provisioning`
  and `suspended` are out (a `provisioning` tenant has no committed schema contract yet; `suspended` is an SP3
  lifecycle concern).
- **Tenant data-plane *route* wiring / FWK60 logical scoping** — SP2 makes tenant DBs migratable, not consumed by
  new routes.
- **A per-tenant migration-version dashboard / drift report** — YAGNI; the result map + structured logs suffice.
- **Parallel fan-out** — YAGNI for SP2; sequential is correct and simplest. Recorded as a future concurrency knob
  for large fleets (it does not change the result-map contract, so it is a clean later addition).

## 3. Architecture

```
db/control/
  repository.py        (LOCKED — exists) get_tenant, get_tenant_dsn, …  + active_tenant_dsns  ← SP2 re-touch
migrations_control/    (exists) the control chain (c0001–c0003); env.py → control_database_url
migrations/            (exists) the app/business chain; env.py honors a pre-injected sqlalchemy.url (SP1)
multitenantauth/tenancy/
  provision.py         (LOCKED — exists) migrate_tenant(dsn)  ← reused as the per-tenant primitive
  migrate.py           (LOCKED — SP2 new) upgrade_all() → result map; `python -m …tenancy.migrate` entry
scripts/
  entrypoint.sh        (jinja — battery branch swapped to upgrade_all)
  check_migrations.py  (static — extended to scan both chains)
infra/deploy/
  strategy.sh          → strategy.sh.jinja (non-battery byte-identical; battery branch = rollback-by-image)
  README.md            (plane-aware deploy/rollback + multi-host section)
Taskfile.yml           (jinja — battery-gated db:migrate:all)
```

All planes are **synchronous** SQLAlchemy (matching SP1 + the control plane). Alembic is driven through the
**Python API** (`alembic.command.upgrade` + a programmatic `Config`), reusing SP1's `migrate_tenant` — *not* the
subprocess (`alembic -x dsn=…`) shape Meridian uses. The fan-out adds nothing to the request path; it is a
boot/deploy/CLI concern.

## 4. Components

### 4.1 `upgrade_all()` (`multitenantauth/tenancy/migrate.py`, new, integrity-LOCKED)
The plane-aware fan-out. Signature `upgrade_all(*, control_session_factory=…) -> MigrateReport`. Sequence:

1. **Control plane (fail-fast).** `alembic.command.upgrade` on a programmatic `Config` pointed at
   `alembic_control.ini`/`migrations_control` with `sqlalchemy.url = control_database_url`. If this raises, **abort
   immediately** — the registry that enumerates tenants lives in the control plane; a broken control plane means we
   cannot safely or completely fan out. Record `control: error` and return non-zero; do **not** touch any tenant.
2. **Default business DB.** `alembic.command.upgrade` on the app chain pointed at `database_url`. (Co-located
   default: `control_database_url == database_url`, two version tables in one physical DB — already handled by the
   two chains' distinct `version_table`s. Split-control: a distinct physical DB.) Failure here is recorded but does
   **not** abort the tenant fan-out (the default DB is independent of tenant DBs).
3. **Tenant fan-out (best-effort).** Enumerate `active_tenant_dsns(cs)`; for each, `migrate_tenant(dsn)` (the SP1
   primitive). On a per-tenant failure, **record and continue** — do not abort the rest. Credentials/DSNs never
   logged (reuse SP1's hygiene; the `%`-escape in `migrate_tenant` already guards the alembic ConfigParser path).

Returns a `MigrateReport` — `{"control": "ok"|err, "default": "ok"|err, "tenants": {tenant_id: "ok"|err}}` — and the
`__main__` entry **exits non-zero if any target failed**, so boot/CI halts the rollout. *Rationale for best-effort
on tenants:* under expand-only, a partially-migrated fleet still serves correctly under either code version, so
continuing maximizes the migrated set and gives the operator a complete failure map; fail-fast on tenant *k* of *N*
strands the same split fleet but reports less.

**Idempotent / re-runnable:** every step is `upgrade head` (a no-op when already current), so a re-run after a
partial failure completes the laggards. Sequential, deterministic order (control → default → tenants in a stable
enumeration order) — no parallelism in SP2.

### 4.2 `active_tenant_dsns` (`db/control/repository.py`, LOCKED — deliberate re-touch)
`active_tenant_dsns(session) -> list[tuple[str, str]]` → `(tenant_id, dsn)` for every `status == "active"` tenant.
A read-only `select` mirroring the existing `get_tenant_dsn`/`live_slug_tenant_id` shape. The DSN it returns is the
stored control-row DSN — *not* resolved through the `resolve_dsn` seam, because the fan-out is an operator/boot
context, not a request; a secrets-backed resolver is a request-path concern. (If a future secrets backend stores
*only* a reference in the row, the fan-out resolves through the seam too — recorded as a Secrets-backing
precondition, not built here.) This edit to a Phase-1 LOCKED file regenerates its checksum and is covered by the
branch's Layer-2 review — exactly as SP1's `registry.py`/`deps.py` edits were.

### 4.3 Boot — `scripts/entrypoint.sh.jinja`
Under `{% if "multitenantauth" in batteries %}`, the boot migrate becomes the plane-aware runner. Today's battery
branch runs two bare `alembic upgrade head` lines (app + control); SP2 replaces them with a single
`python -m {{ package_name }}.multitenantauth.tenancy.migrate` call (which does control-first → default → fan-out),
then the existing authz seed, then the consumer seed — order preserved. The non-battery branch (bare
`alembic upgrade head`) is **unchanged**. `APP_RUN_MIGRATIONS` gating is unchanged. Multi-host rolling deploy still
sets `APP_RUN_MIGRATIONS=false` on app hosts and runs the migrate once before the roll — now plane-aware via
`task db:migrate:all`.

### 4.4 Taskfile — `db:migrate:all` (battery-gated)
A new `db:migrate:all` target (rendered only under the battery) running the same
`python -m …tenancy.migrate` entry — the operator-facing handle for the pre-roll migration and local fan-out. Bare
`db:migrate` (single `alembic upgrade head`) is **unchanged** so a non-battery project is untouched and a battery
project still has the single-DB target for the control/default DB when wanted.

### 4.5 Deploy / rollback — `infra/deploy/strategy.sh` → `strategy.sh.jinja`
The file becomes a jinja template; the **non-battery render is byte-for-byte today's `strategy.sh`** (asserted by a
render test). Under `{% if "multitenantauth" in batteries %}`:

- **`deploy()`** is essentially unchanged — it records the release `(image, rev)` and places the image; the image's
  plane-aware entrypoint (§4.3) runs `upgrade_all` on boot. `repo_head_revision()` (the recorded `rev`, from
  `alembic heads` on the app chain) stays meaningful as the business-schema head.
- **`rollback()` becomes image-only.** It finds the prior release and **redeploys that image with no
  `__target_migrate "downgrade"` on any plane**, then records the rollback as the new live release. The prior
  image runs against the current (forward) schema by the expand-only guarantee.
- **Contract-floor refusal.** Before an image-only rollback, the battery branch checks whether a **contract
  (destructive) migration** lies between the rollback-target rev and the current head, in *either* chain. If so it
  **refuses** the one-click rollback with an explicit error: crossing a contract migration means the prior image
  needs schema the contract dropped, so recovery requires a deliberate data-restore plan, never an automated
  downgrade. Detection reuses the existing `# deploy: contract` marker (see §4.6); the exact wiring (a
  `contract-floor` helper invoked by `rollback()`, scanning the revision range across both `versions` dirs for the
  marker) is the implementation seam.

The non-battery `rollback()` keeps today's `downgrade ${rev}` → redeploy contract verbatim — single-DB projects are
deliberately untouched (reopening their rollback posture is out of scope).

### 4.6 `check_migrations.py` — scan both chains
Today the guard scans only `migrations/versions` (the app chain). SP2 generalizes it to scan
`migrations_control/versions` as well (when present), applying the same reversible + expand-only rules. A
destructive control-plane migration is the *most* dangerous (auth/registry data), so the contract marker must be
acknowledged there too; and the contract-floor logic (§4.5) needs both chains' markers to be authoritative. This
closes the SP1-scorecard "`check_migrations.py` does not scan `migrations_control/versions`" latent follow-up.

### 4.7 Integrity-lock impact
`multitenantauth/tenancy/migrate.py` is added to `integrity/classes.py:BATTERY_LOCKED_SRC` (gated on
`multitenantauth`) **in the task that creates it** — it lives under the already-walked `multitenantauth` tree, so a
forgotten lock fails `test_auth_mechanism_lock.py` the moment it renders (fail-safe; cannot be deferred). The
`repository.py` re-touch (§4.2) regenerates its checksum. `strategy.sh`, `entrypoint.sh`, `check_migrations.py`,
`Taskfile.yml` are *shared/operator-owned* deploy infra, not the locked mechanism — their classification under
`integrity/classes.py` is reconciled per the existing rules (the rendered paths are unchanged by the
`strategy.sh` → `.jinja` source rename).

## 5. Data flow

**Boot / deploy migrate (battery):** entrypoint → `upgrade_all` → control `upgrade head` (fail-fast) → default
`database_url` `upgrade head` → enumerate active tenants → per-tenant `migrate_tenant` (best-effort) → result map →
exit code → (authz seed → consumer seed) → exec server.

**Rollback (battery):** `strategy.sh rollback` → find prior release → contract-floor check across both chains
(refuse if crossed) → redeploy prior image, **no downgrade** → record rollback as live.

**Rollback (no battery):** unchanged — `downgrade ${rev}` → redeploy prior image → record.

## 6. Error handling & observability
- **Fail-closed where it matters:** control failure aborts the whole fan-out; the `__main__` entry exits non-zero
  on any failed target so boot/CI does not silently proceed on a partial migration.
- **Best-effort where it is safe:** a single tenant's failure does not abort the rest (expand-only makes a partial
  fleet correct); the result map names every failure.
- **No credential disclosure:** DSNs/passwords are never logged or put in a result value (the result map keys on
  `tenant_id`, values are `"ok"` or a sanitized error class — never the DSN); reuses SP1's never-log hygiene and the
  `migrate_tenant` `%`-escape.
- **Observability:** no new Prometheus gauges (the fan-out is a boot/CLI event, not a request path; SP1's
  per-endpoint pool gauges already cover routing). The runner emits a structured result map to stdout/logs; the
  obs-completeness guard (`battery.obs`) is unchanged.

## 7. Conformance contract (drift-aware)
Gates Meridian's routing/ops fork-deletion (per DEC-0003 / the SP2 PUR). Seeded from **intended behavior**, not
Meridian's current code (their fan-out works *now* but we rebuild on our primitive — see §10).

- **Pure-unit (runs everywhere):** result-map shape; control-first ordering; control-fail-fast (control error ⇒
  no tenant touched, non-zero exit); tenant best-effort continuation + non-zero exit on any failure;
  contract-floor detection across both chains (a `# deploy: contract` revision between target and head ⇒ refuse);
  `active_tenant_dsns` returns only `active` tenants.
- **Real-Postgres tier (`render-complete`, never skip-neutral):** provision 2 tenants → add an expand migration →
  `upgrade_all` brings control + default + both tenant DBs to head, isolation intact (A's write invisible to B);
  a deliberately-broken tenant → result map flags it, the others still migrate, exit non-zero. These need real
  Postgres, so they run in the tier that **cannot skip-degrade to a silent pass** — the exact failure mode that
  hid Meridian's earlier drift.
- **Non-battery render:** `strategy.sh` byte-identical to the pre-SP2 file; `db:migrate`/entrypoint behavior
  identical; `check_migrations.py` behavior on an app-only project unchanged.

## 8. Testing strategy
TDD throughout (red → minimal green), via the template-payload loop (`[[template-payload-tdd-loop]]`: render →
uv sync → mirror → pytest in the generated project; `ruff format --check` the rendered output). Unit tests for every
ordering/failure/contract-floor branch; real-Postgres acceptance for fan-out + isolation; the non-battery
byte-identity guard; `render-complete` exercises the rendered project's own suite. A Phase-2 Layer-2 adversarial
security pass (stance×focus matrix, **all stages Opus** per `[[security-review-workflow-all-opus]]`) gates the
branch, scoped to migrate/deploy/rollback and explicitly including the SP1-recorded **migration-data-safety** cell
(can a crafted migration or fan-out ordering destroy or cross-contaminate tenant data?). Author/verify split: agents
author (no docker), the controller runs the real-Postgres/docker verification.

## 9. Phase-2 preconditions & SP1 carryovers
- **Honored in SP2:** the migration-data-safety Layer-2 cell (§8); closing the `check_migrations.py` control-chain
  gap (§4.6).
- **Still SP3 (not SP2):** the DB-level ≥1-admin guard, `AuthzEvent.resource_id` + resource-grant audit
  completeness, `tenant_slug_history` reaping, the inert `subtree_exists` re-arm, and the folded FWK63 t1–t4 seam
  residuals — all gate *routes/lifecycle*, not the migrate/deploy/rollback surface, so they remain SP3.
- **SP1 data-plane preconditions (sentinel guard, parse-before-cache, lock-hygiene+connect_timeout) land when a
  route first consumes `tenant_db`** — SP2 does not wire such a route, so they remain deferred.

## 10. Promote-up & DEC bookkeeping
- **New PUR `DEC-0005`** (SP2 sub-record) alongside `DEC-0004`: generator = meridian, absorber = framework;
  capability = plane-aware migrate fan-out + boot wiring (validated reference) **+ the CD deploy/rollback semantics
  (designed fresh, informed by Meridian's `DEPLOY.md`/MDN46/MDN59 hazard analysis)**; conformance contract per §7;
  generator confirmation requested async.
- **Correct DEC-0004's stale drift note.** DEC-0004 recorded Meridian's Phase-2 write path as *broken* (missing
  `slug`; `all_tenant_dsns` ImportError). Re-reading Meridian directly (2026-06-25) shows both are **fixed** —
  Meridian now has a working control-first `upgrade_all()`, a plane-aware `entrypoint_tenancy.sh`, and a plane-split
  seed. The drift finding is corrected to bookkeeping: the migrate fan-out is a *validated* reference, not broken;
  the genuinely-unwired part on Meridian's side is the **CD deploy/rollback** (their open MDN46). Per SP1's rule we
  still rebuild on our own primitive and seed conformance from intended behavior, so the design does not depend on
  Meridian's code state — only the PUR framing is corrected.

## 11. PI ledger bookkeeping (rides this branch's first commit)
Master is protected (no standalone doc-only PR), so the FWK61-Phase-2 ID reconciliation rides the FWK66 branch's
first commit (same precedent as the FWK62/FWK64 loose-ends):
1. Re-scope the PLAN `FWK61` row → "Phase 2 SP1 — physical routing core (shipped v0.4.2)"; move the SP2/SP3
   descriptions to their own rows.
2. Renumber the *done* PI-v3 row `FWK64` → **`FWK65`** (with a one-line collision note; the shipped commit message
   `chore(FWK64)` is immutable git history and stays).
3. Add rows: **`FWK66`** (SP2, this work), **`FWK67`** (SP3, folds FWK63 t1–t4 + Phase-1 preconditions),
   **`FWK68`** (convention-lock presence+floor redesign, parked).
4. Tick the already-shipped-but-unticked **`FWK62`** (v0.4.1) and **`FWK64`** (cross-repo adoption) loose-ends per
   their riding-plan note.
5. Keep the "Phase 2 = FWK61 SP1 → FWK66 SP2 → FWK67 SP3" decomposition as linking prose.

## 12. References
- SP1 design: `docs/superpowers/specs/2026-06-25-fwk61-sp1-physical-routing-core-design.md`; SP1 PUR `DEC-0004`.
- SP1 Layer-2 scorecard (Phase-2 preconditions): `docs/superpowers/eval-scorecards/2026-06-25-fwk61-sp1-layer2-security-matrix.md`.
- Parent promote-up: `docs/superpowers/decisions/DEC-0003-multitenantauth-promote-up.md`.
- Meridian reference (read directly, MDN busy): `meridian` `db/tenancy/migrate_all.py`, `scripts/entrypoint_tenancy.sh`,
  `scripts/seed.py`, `_docs/.../2026-06-18-tenancy-data-segregation-design.md` (MDN33),
  `_docs/.../2026-06-21-plane-aware-container-boot-design.md` (MDN59), `DEPLOY.md` (MDN46).
- Cross-repo convention: vendored `cross-repo-convention.md` (`CROSS-REPO-convention: v4`).
