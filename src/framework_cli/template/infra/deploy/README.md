# Deploy strategy — what the framework decided, and the little you configure

Deployment is a **contract**. The framework owns the orchestration (build → push → deploy →
smoke → sniff → E2E → load) AND the strategic decisions: release versioning, **migration-aware
rollback**, health-gating, and runtime secrets. `strategy.sh` already implements those. You
implement only the `__target_*` hooks for your target and set a few config env vars — you
configure, you do not architect.

## Pick a target

| Target | `__target_place_image` implements |
|---|---|
| Compose-over-SSH (VPS) | scp `infra/compose/<env>.yml` to the host, then over ssh `docker compose -f <env>.yml up -d` (pulls `APP_IMAGE`) |
| Fly.io / Render / Railway | the platform's deploy CLI pointed at `APP_IMAGE` |
| Kubernetes | `kubectl set image` / a Helm release using `APP_IMAGE` |

A turnkey default (compose-over-SSH + Traefik/ACME blue-green) ships as a follow-up; until
then, implement the hooks below for your target.

## What you implement (the only gaps in `strategy.sh`)

| Hook | Must do |
|---|---|
| `__target_place_image` | Pull `$APP_IMAGE` and run it from `infra/compose/$DEPLOY_ENV.yml`; do not route traffic until healthy. |
| `__target_migrate` | Run `alembic <args>` against the target's relational DB using THIS checkout's migrations (rollback's downgrade needs the new migration's down-path). When you add other DB paradigms (document/graph/…), reverse their migrations here too. Run `alembic` either from the CI runner against the target DB, or on the host with the new image — either way using the new release's migration scripts. |
| `__target_record_release` / `__target_release_history` | Persist + read the `(image, revision)` history per env on the target (durable across runs). |
| `__target_teardown` | Remove a failed/rolled-back release. |

## What the framework already did (do not weaken)

- **Release versioning** — each deploy records `(image, alembic-revision)`; `current-release`/`releases` read it.
- **Migration-aware rollback** — `rollback` reverses migrations to the previous release's revision THEN redeploys its image (the image only ever upgrades, so the explicit downgrade is required).
- **Health-gate** — `await-healthy` polls `/health` and refuses any `breached` SLO (the Phase-1 smoke rule).
- **Guarantees:** versioned/addressable releases (a rollback target always exists), runtime secrets (never baked into images), the same image promoted staging → prod (no rebuild). No-downtime cutover is the target's job (blue-green via Traefik in the turnkey follow-up, or the platform's native rolling deploy) — see the turnkey follow-up.

## Config you set (GitHub Environment + the target)

| Var | Where | Purpose |
|---|---|---|
| `DEPLOY_ENV` | workflow (`staging`/`prod`) | selects `infra/compose/<env>.yml` |
| `DEPLOY_BASE_URL` | Environment variable | the deployment's base URL (endpoints + health-gate) |
| `APP_IMAGE` | set by the workflow | the pushed registry tag |
| `POSTGRES_PASSWORD` | **target env + GitHub Environment secret** | DB credential, injected at runtime |
| every var in `.env.example` | **the target's environment** | the app reads config from the target's env — NEVER baked into the image |

Set application config + secrets **in the target's environment** (or the platform's secret
store) and as GitHub Environment secrets — the image carries none of them.

## Migrations: reversible by discipline, across every paradigm

Rollback can only restore a previous release if its migrations can be reversed, so:

- **Write expand/contract migrations.** A rolling deploy runs old and new code against ONE
  shared schema, so each deploy's migration must be **backward-compatible (expand-only)**: add
  columns/tables/indexes (additive) and ship code that works with and without them; a
  destructive **contract** change (drop/rename) breaks the old code still running during the
  roll. Migrations also run **once** before the roll — set `APP_RUN_MIGRATIONS=false` on the
  app hosts (it is matched exactly as `true`/`false`; the default is `true`, so dev/single-host
  self-migrate on start) so the per-container entrypoint does not race them.
- **Unsafe migrations are blocked, not just discouraged.** The migration guard
  (`scripts/check_migrations.py`, pre-commit + CI) fails any migration whose `downgrade()` is
  empty/`pass`/`raise` (irreversible) **or** whose `upgrade()` does a destructive op
  (`drop_*`, `rename_table`, column rename) — the latter unless the file is marked
  `# deploy: contract`. **Contract changes are their own post-rollout release:** ship the
  expand release, let it fully roll out, remove the old code, then a later `# deploy: contract`
  migration removes the old shape. (Raw-SQL drops via `op.execute` and type-narrowing aren't
  caught structurally — Plan 7's data-integrity agent adds that.) **Never destroy data that
  cannot be reconstructed.**
- **This applies to all database paradigms, not just relational.** PostgreSQL uses Alembic
  here; document/key-value/graph/time-series/vector stores (Plan 8) carry their own reversible
  migration tooling and the same discipline + guard. Reverse each active store in
  `__target_migrate`.

## Antipatterns this seam prevents (don't reintroduce them)

- No rollback target → `rollback` errors if there's no previous release.
- Secrets baked into images → config/secrets come from the target env at runtime.
- Skipping staging → prod only deploys an image that passed staging's four phases.
- Mutating prod during validation → prod runs smoke + **read-only** sniff; never E2E/load writes.
- Big-bang / irreversible migrations → expand/contract + the migration guard above.

## Validate a real deploy (no framework help needed)

1. Implement the `__target_*` hooks; set the config above.
2. Merge to `main` → `deploy-staging.yml` builds+pushes, calls your `deploy`, runs the four
   phases against your `endpoints`, and auto-rolls-back (reversing migrations) on any failure.
3. Locally point the tiers at any environment: `SMOKE_TARGET=… task test:smoke`,
   `SNIFF_TARGET=… task test:sniff`, `E2E_TARGET=… uv run pytest tests/e2e`, `K6_TARGET=… task test:load`.

## Notifications

`notify.sh` logs by default. Wire your channel there (reuse the Alertmanager destination).
