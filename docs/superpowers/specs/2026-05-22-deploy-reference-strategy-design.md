# Deploy Reference Strategy (Plan 5c) — Design Spec

**Date:** 2026-05-22
**Status:** Approved (brainstorm) — not yet planned/implemented
**Builds on:** Plan 5b deploy seam (`docs/superpowers/plans/2026-05-21-deploy-seam.md`) and the deploy contract in the generated `infra/deploy/README.md`. Roadmap row: Plan 5c in `docs/superpowers/plans/2026-05-20-meta-plan.md`.

---

## 1. Purpose

Plan 5b shipped the deploy *contract* and an opinionated *skeleton* (`infra/deploy/strategy.sh`) whose `__target_*` hooks the builder must implement for their target. Plan 5c fills those hooks with **one concrete, host-validated reference strategy** so a builder gets a working, no-downtime deploy without writing the mechanism themselves — the natural completion of "offload architectural decisions, don't delegate them" ([[offload-architecture-not-delegate]]).

The reference target is **compose-over-SSH across 1..N application hosts** behind a builder-provided load balancer, with an external/managed shared PostgreSQL.

## 2. Scope & non-goals

**In scope:**
- A complete compose-over-SSH strategy for **1..N app hosts** (N=1 is a degenerate single-host roll). Implements the deploy contract's operations (`deploy`, `await-healthy`, `endpoints`, `rollback`, `releases`, `current-release`, `teardown`).
- **Rolling, no-downtime** updates given a health-draining LB + the app's graceful shutdown.
- **Migrate-once** orchestration against the shared DB with the correct expand/rollback ordering, and a small entrypoint change to gate per-host auto-migration.
- A **contract-direction migration detector** (backward-compatibility guard) extending the 5b reversibility guard.
- An **app-only host compose** for the hosts.
- A **local multi-container e2e** that proves no-downtime + migration-aware rollback.
- `DEPLOY.md` guidance: single-host (5b bundled-Postgres) vs. multi-host (5c, external DB), the expand/contract-across-releases workflow, and the required builder config.

**Non-goals (deliberate):**
- **No prod Traefik / ACME / TLS** — TLS termination and health-based draining are the **builder-provided LB**'s job. App hosts serve plain HTTP on a private, LB-reachable port.
- **No managed-Postgres provisioning** — the builder brings a shared DB (managed service or a host they run); HA/backups/failover are out of scope.
- **No cloud-provider LB automation** — the builder configures *their* LB to the documented host/health contract. We do not drive a specific LB's API.
- **No multi-region / no data-tier blue-green** (two DBs with sync) — out of scope.
- **No second concrete target** (Fly/Render/k8s) — those remain builder-implemented against the 5b seam; 5c makes only compose-over-SSH turnkey.

## 3. Topology & the host/LB contract

- **App hosts (1..N):** each runs an **app-only** compose (the app container; no Postgres) and serves `/health` + the app on a private port (default 8000) reachable by the LB.
- **Load balancer (builder-provided):** terminates TLS and **drains a host by health** — the documented contract: *route only to hosts whose `/health` returns 200 on the configured port; drain a host promptly when it goes unhealthy; the deploy is rolling.* Cloud LB, the builder's own nginx/Traefik, etc.
- **Database:** a **single shared PostgreSQL** referenced by `APP_DATABASE_URL` (managed service or a DB host the builder runs). Never per-app-host.
- **Builder responsibilities (documented, not shipped):** TLS at the LB; firewalling the app port to the LB only; provisioning + backing up the shared DB.

## 4. Deploy orchestration

The strategy operates over a host list (`DEPLOY_HOSTS`). The order of schema vs. code changes is the load-bearing correctness property (one shared DB, mixed old/new code during any transition):

**`deploy` (forward — schema leads):**
1. Run `alembic upgrade head` **once** against the shared DB (expand-only — see §5).
2. Record the release `(image, alembic-revision)` to durable per-host state under `DEPLOY_PATH`.
3. **Roll** each host in turn: `docker compose -f <app-only>.yml up -d` the new image → the old container receives **SIGTERM** and shuts down gracefully (Plan 4: finishes in-flight requests, closes the DB) → its `/health` fails → the LB drains it → **await** the new container's `/health` 200 → proceed to the next host. With ≥2 hosts the LB always has a healthy target.

**`rollback` (backward — code retreats first):**
1. **Roll the code back** to the previous release's image on **all** hosts (same rolling mechanism), so nothing is still running the new code.
2. **Then** `alembic downgrade` to the previous release's revision **once** against the shared DB.

This is the symmetric inverse of forward (up: schema→code; down: code→schema), and it is why a partial roll can be unwound safely.

**Integration with the 5b skeleton:** 5c refines the skeleton's `deploy()`/`rollback()` to add the explicit migrate-once step and the rolling, host-list-aware placement. The app container entrypoint gains an `APP_RUN_MIGRATIONS` flag (**default `true`** so dev / single-host / `test` are unchanged); the multi-host deploy sets it `false` on the hosts so they do **not** each race `alembic upgrade head` on start.

**Honest claim:** no-downtime **given** a health-draining LB **and** the app's graceful shutdown — not zero-downtime independent of the LB. This is exactly what the §7 e2e proves (a stand-in health-draining proxy + a continuous poller).

## 5. Migration safety (the core correctness model)

With one shared DB and >1 host (or even blue-green at the cutover instant), **old and new code coexist against a single schema**. This is inherent to no-downtime on a shared DB; the only escape is stop-the-world (downtime). Therefore:

- **Every per-deploy migration must be backward-compatible (expand-only):** additive changes the *old* code tolerates (new columns/tables/indexes, nullable or defaulted additions). The expand migration is applied first; old hosts ignore the additions; new hosts may use them.
- **Destructive (contract) changes are a separate, later release** — run only after the code that used the old shape is fully rolled out and gone. Examples: dropping a column/table, narrowing a type, renaming.

**Reversibility ≠ backward-compatibility.** The 5b guard (`scripts/check_migrations.py`) enforces that a migration *has a real `downgrade()`* — necessary but **not** sufficient: a reversible migration can still drop a column the old code reads. 5c adds a second, complementary check:

- **Contract-direction detector** (extends `check_migrations.py`, runs in pre-commit + CI): scans each migration's **`upgrade()`** (AST) for destructive operations — `op.drop_column`, `op.drop_table`, `op.rename_table`, column renames, and type-narrowing `op.alter_column` (heuristic). If found, the migration **fails** unless it carries an explicit opt-in marker (e.g. a `# deploy: contract` comment) acknowledging it is destructive and must be deployed as its own post-rollout release.
  - The marker is the escape hatch (static detection is imperfect — a contract migration in a dedicated release is legitimate).
  - The scaffold's `0001_initial.py` is clean (its `upgrade()` is `create_table`, not a drop).
  - **Plan 7's data-integrity review agent** adds semantic judgement (e.g. "is this drop actually safe given current code?") later; 5c's detector is the deterministic deploy-time guard.
- **Documentation:** `DEPLOY.md` + the strategy README spell out the expand/contract-across-releases workflow as the builder's discipline.

## 6. Configuration, secrets, release state, compose

**Builder config** (GitHub Environment vars/secrets + the target environment):
- `DEPLOY_HOSTS` — the app host list. `DEPLOY_SSH_USER` + an SSH key (secret). `DEPLOY_PATH` — where the compose file + release state live on each host.
- `APP_DATABASE_URL` — the shared DB. `POSTGRES_PASSWORD` and **every var in `.env.example`** — delivered to each host as a runtime env file; **never baked into the image**.
- `DEPLOY_BASE_URL` — for `endpoints`/health-gating (the LB's URL).

**Release state:** a small `(image⇥revision)` history file kept under `DEPLOY_PATH` **on each host** (identical for one logical release). `rollback`/`releases`/`current-release` read from the first reachable host. (Durable across workflow runs without a central store.)

**Compose model:** 5c **adds** an app-only host compose (app container only, points at the external DB) and the 1..N rolling strategy. 5b's bundled-Postgres `staging.yml`/`prod.yml` **remain** the simpler single-host option. `DEPLOY.md` guides the choice:
- **Single host / solo project:** 5b's bundled-Postgres compose (batteries-included, accepts a brief restart window).
- **Scaling / multi-host:** 5c's app-only host compose + external DB + rolling no-downtime.

## 7. Validation (the proof)

A **Docker-gated acceptance test** (skips without Docker, like the existing live-stack tests):
1. Bring up **≥2 `sshd`+docker "host" containers** (each able to run `docker compose`), a **shared Postgres** container, and a minimal **health-draining stand-in proxy** that plays the builder's LB (routes only to `/health`-passing hosts, drains on unhealthy).
2. Run the **real strategy** over SSH-to-localhost: scp the app-only compose, migrate-once, rolling drain→update→await→rejoin across the hosts.
3. A **continuous poller** hits the app *through the proxy* during the entire roll and asserts **zero failed requests** (proves no-downtime given a draining LB + graceful shutdown).
4. Then exercise **rollback** (code-back-then-downgrade) and assert the service returns to the prior release with the schema reverted.

This is the only thing that genuinely proves the headline claim and the SSH/compose plumbing. The contract-direction detector is unit-tested separately (crafted migrations: a `drop_column` upgrade fails without the marker, passes with it; an additive upgrade passes).

## 8. Deferred to plan-writing time

These are implementation details to settle when the plan is written (not open *design* questions):
- Exact `sshd`+docker "host" container image / how each runs `docker compose` (docker-socket mount vs. dind) in the e2e harness.
- The precise AST signatures the contract-direction detector matches (the destructive-op list above is the intent; the exact `op.*` patterns + the marker syntax are plan-level).
- Whether the 1..N strategy lives as a refined `strategy.sh` in the template or a documented drop-in; and how it coexists with the 5b skeleton's hook seam.
- The app-only host compose's exact services/healthcheck (mirrors the app service from `base.yml` minus Postgres, plus `APP_RUN_MIGRATIONS=false`).

## 9. Self-review

- **Placeholders:** none — every decision (target, LB model, DB, migration timing + safety, ordering, validation, config, compose) is settled; §8 lists only implementation-level details deferred to the plan, by design.
- **Internal consistency:** the migrate-once direction (expand, up-first) and the rollback ordering (code-back-then-downgrade) are consistent with the §5 expand/contract model and the §3 rolling mechanism. The no-downtime claim is qualified consistently (given a draining LB + graceful shutdown) in §3 and proven by the §7 e2e.
- **Scope:** focused on one reference target; the contract-direction guard and the entrypoint flag are the only changes that touch existing scaffold files; everything else is additive.
- **Ambiguity:** the host/LB contract (§3) and the expand/contract discipline (§5) are stated explicitly so the builder's responsibilities are unambiguous.

---

*End of design. Next step (when ready): `superpowers:writing-plans` to produce the Plan 5c implementation plan. Not started — this brainstorm is the deliverable.*
