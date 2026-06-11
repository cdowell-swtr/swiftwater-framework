# Deploy

Deployment in a scaffolded project is a **contract**. The framework owns the *orchestration* — build the image, push it, deploy it, then run four validation phases that gate one another and roll back automatically on any failure. You own only the *strategy*: the handful of hooks that place the image on your chosen target. You configure; you do not architect.

This page describes the deploy model end to end so you can reason about it without opening the project. Your generated project also ships a `DEPLOY.md` and an `infra/deploy/README.md` with the exact hook list and variable tables for your specific setup.

## The shape of a deploy

Two GitHub Actions workflows drive deployment, both wired and ready in every project:

- `deploy-staging.yml` — runs on **merge to `main`** (or manual dispatch).
- `deploy-prod.yml` — runs on **manual approval** (the `production` GitHub Environment gate) or a **`v*` tag** push.

The cardinal rule is **promote, never rebuild**. Staging builds the image once; production deploys the *same* image, byte-for-byte, after it has passed staging's gates. There is no separate prod build that could drift from what was tested.

## Staging: build, deploy, validate

On merge to `main`, `deploy-staging.yml` runs two jobs:

**1. `build-push`** builds the application image from `infra/docker/Dockerfile` and pushes it to the GitHub Container Registry, tagged with the commit SHA:

```text
ghcr.io/<owner>/<repo>:<sha>
```

That fully-qualified tag is the unit of promotion — it flows to the deploy job as `APP_IMAGE` and, later, to production unchanged.

**2. `deploy-staging`** runs in the `staging` GitHub Environment and walks the deploy through your strategy:

1. `bash infra/deploy/strategy.sh deploy` — your configured strategy places `APP_IMAGE` on the target.
2. `strategy.sh await-healthy 120` — polls `/health` and refuses to proceed while any SLO is `breached` (this is the health gate; a wedged or out-of-SLO deploy never goes green).
3. `strategy.sh alert-smoke` — advisory (`continue-on-error`): fires a synthetic alert and checks that delivery works, but never fails a healthy deploy.
4. `strategy.sh endpoints` — resolves the deployed URL the validation phases probe.

Then the **four validation phases** run in order, each gating the next:

| Phase | What runs | Checks |
|---|---|---|
| **1 — smoke** | `SMOKE_TARGET=<url> uv run pytest tests/smoke -q` | Liveness / readiness + no breached SLO |
| **2 — sniff** | `SNIFF_TARGET=<url> uv run pytest tests/sniff -q` | Critical-path probes |
| **3 — E2E** | `E2E_TARGET=<url> uv run pytest tests/e2e -q` | The full end-to-end suite against staging |
| **4 — load** | `K6_TARGET=<url> bash scripts/load.sh` | k6 load test held to the SLO thresholds |

If any step fails, the workflow runs `strategy.sh rollback` automatically, then notifies. A successful staging run is what makes a commit eligible for production.

## Production: promote the validated image

`deploy-prod.yml` does **not** rebuild. It promotes the staging-built image into the `production` Environment after a manual approval (or a `v*` tag), then runs a lighter post-deploy check:

- **smoke** (`tests/smoke`) — liveness/readiness + SLO.
- **sniff, read-only** (`tests/sniff`) — critical-path probes that never write against production.

There is deliberately **no E2E or load phase against prod** — those tiers write data and drive load, which you don't do to a live system. Any failure rolls back automatically.

**Tag discipline:** a `v*` tag deploys `ghcr.io/<repo>:<tagged-sha>`, so only tag a commit whose image already passed staging. To promote a specific image explicitly, dispatch `deploy-prod` manually and pass the staging-validated `image` input; if you leave it blank, the workflow defaults to the image built for that SHA.

## What you implement (the strategy)

The framework already decided the hard parts — release versioning, migration-aware rollback, health-gating, and runtime secret injection — in `infra/deploy/strategy.sh`. You fill in only the target-specific `__target_*` hooks:

| Hook | Responsibility |
|---|---|
| `__target_place_image` | Pull `$APP_IMAGE` and run it from `infra/compose/$DEPLOY_ENV.yml`; don't route traffic until healthy. |
| `__target_migrate` | Run `alembic` against the target's database using *this* checkout's migrations (rollback's downgrade needs the new migration's down-path). |
| `__target_record_release` / `__target_release_history` | Persist and read the `(image, alembic-revision)` history per environment. |
| `__target_teardown` | Remove a failed or rolled-back release. |

These hooks map onto whatever target you choose — compose-over-SSH to a VPS, a PaaS deploy CLI (Fly.io / Render / Railway) pointed at `APP_IMAGE`, or `kubectl set image` / a Helm release for Kubernetes.

### Turnkey: compose-over-SSH

You can skip writing hooks entirely. Set the Environment variable `DEPLOY_TARGET=compose-ssh` to use the framework's shipped reference target (`infra/deploy/targets/compose-ssh.sh`). It rolls your image across one or more app hosts (`DEPLOY_HOSTS`, space-separated IPs), one host at a time, with **no downtime given a health-draining load balancer** and the app's graceful shutdown. Each app host runs `infra/compose/app-host.yml` (app only — no Postgres, no Traefik) against a single **shared external Postgres** (`APP_DATABASE_URL`); your load balancer terminates TLS and drains a host by its `/health` status. TLS at the LB, firewalling the app port, and provisioning the shared Postgres are yours to supply.

## Migrations are reversible (enforced)

Rollback works by reversing migrations, and a rolling deploy runs old and new code against one shared schema. So every per-deploy migration must be both **reversible** and **backward-compatible (expand-only)**: add columns/tables/indexes and ship code that works with and without them. A destructive **contract** change (drop/rename) would break the old code still running mid-roll, so it must be its own later release.

This isn't a guideline — it's enforced. `scripts/check_migrations.py` runs in pre-commit and CI and **fails** any migration whose `downgrade()` is empty/`pass`/`raise` (irreversible) or whose `upgrade()` makes a destructive change (`drop_*`, `rename_table`, column rename) unless the file is explicitly marked `# deploy: contract`. During the roll, migrations run **once** before the new code; the app hosts set `APP_RUN_MIGRATIONS=false` so per-container startup doesn't race the single migrate step. The same discipline applies to every database paradigm you add, not just PostgreSQL.

## Run the validation tiers locally

The same phases work against any reachable environment — point the target env var at it:

```bash
SMOKE_TARGET=https://staging.example.com  task test:smoke   # phase 1
SNIFF_TARGET=https://staging.example.com  task test:sniff   # phase 2
E2E_TARGET=https://staging.example.com    uv run pytest tests/e2e -q   # phase 3
K6_TARGET=https://staging.example.com     task test:load    # phase 4
```

These are the same commands the CD workflows run, so you can reproduce a deploy gate from your own machine before (or after) a real deploy.

## Config and secrets at deploy

The image carries **no** configuration or secrets — everything is injected at runtime from the target's environment (and as GitHub Environment secrets). At minimum you set `DEPLOY_BASE_URL`, `POSTGRES_PASSWORD`, and every variable in `.env.example`, in the target's environment. The naming and layering of those values is covered in [Secrets & environment parity](secrets-and-env-parity.md); which services run where is covered in [Services](services.md).
