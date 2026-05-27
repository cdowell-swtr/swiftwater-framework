#!/usr/bin/env bash
# Deploy strategy (framework spec §14) — OPINIONATED SKELETON.
#
# The framework decides the hard parts (release versioning, MIGRATION-AWARE rollback,
# health-gating, runtime secrets) — implemented below. You implement ONLY the __target_*
# hooks for YOUR target (compose-over-SSH, Fly.io, Render, k8s, ...) and set the config env
# vars. See infra/deploy/README.md for the contract, the required env vars, the migration
# discipline, and antipattern guidance. CD workflows call:
#   bash infra/deploy/strategy.sh <operation> [args...]
set -euo pipefail

require_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "::error::deploy config '${name}' is not set — see infra/deploy/README.md." >&2
    exit 1
  fi
}

_todo() {
  echo "::error::deploy hook '$1' is not implemented for your target." >&2
  echo "Implement $1() in infra/deploy/strategy.sh — it must: $2 (see infra/deploy/README.md)." >&2
  exit 1
}

# === TARGET HOOKS — the only code you write ==========================================
# Pull APP_IMAGE and run it from infra/compose/${DEPLOY_ENV}.yml on the target. The image
# self-migrates UP on start (its entrypoint runs `alembic upgrade head`); do NOT route traffic
# until healthy. Merge the observability overlay (`-f infra/compose/observability.yml`) so
# staging/prod run the full monitoring stack (the framework's observability contract); provide
# `GRAFANA_ADMIN_PASSWORD` and the alertmanager webhook file as target secrets (see infra/deploy/README.md).
# Merge `services.yml` so a battery-using project's data stores + worker/beat run in staging/prod
# (set `APP_IMAGE`/`POSTGRES_PASSWORD`). For a managed data store instead, point
# `APP_MONGO_URL`/`APP_REDIS_URL`/`APP_CELERY_*` at it and omit the data-store services — see README.
# (compose-over-SSH e.g.: scp the compose files, then over ssh
# `APP_IMAGE=$APP_IMAGE POSTGRES_PASSWORD=$POSTGRES_PASSWORD docker compose -f <env>.yml -f infra/compose/services.yml -f infra/compose/observability.yml up -d`.)
# When an extension battery (pgvector/timescaledb) is active, the Postgres service uses the custom
# image (extensions baked in). Build+push it alongside APP_IMAGE and set POSTGRES_IMAGE, e.g.:
#   docker build -f infra/docker/postgres.Dockerfile -t $POSTGRES_IMAGE . && docker push $POSTGRES_IMAGE
# Managed alternative: point APP_DATABASE_URL at a managed Postgres that provides the extensions
# (RDS/Cloud SQL/Timescale Cloud/Supabase) and leave POSTGRES_IMAGE unset / the service unused.
__target_place_image() { _todo __target_place_image "pull \$APP_IMAGE and start it from infra/compose/\$DEPLOY_ENV.yml without routing traffic until healthy"; }

# Reverse/apply migrations against the target's stores. \$* is the migration command; the
# relational store runs `alembic \$*` using THIS checkout's migrations (so a downgrade has the
# new migration's down-path). When other DB paradigms are added (Plan 8), reverse each store's
# migrations to the recorded state here too — the SAME reversibility discipline applies to all.
__target_migrate() { _todo __target_migrate "run 'alembic \$*' against the target relational DB (and reverse other paradigms' migrations when present)"; }

# Append "\$1<TAB>\$2" (image, alembic revision) to durable per-DEPLOY_ENV release state ON THE
# TARGET, so a later workflow run can roll back.
__target_record_release() { _todo __target_record_release "append \"\$1<TAB>\$2\" to durable release state for \$DEPLOY_ENV on the target"; }

# Print recorded "image<TAB>revision" lines for DEPLOY_ENV, oldest first.
__target_release_history() { _todo __target_release_history "print recorded 'image<TAB>revision' lines (oldest first) for \$DEPLOY_ENV"; }

# Remove a failed/rolled-back release on the target.
__target_teardown() { _todo __target_teardown "remove a failed or rolled-back release on the target"; }

# === PRESCRIBED LOGIC — the framework owns this; configure, don't weaken it ==========
repo_head_revision() {
  local heads count
  heads="$(uv run alembic heads | awk '{print $1}')"
  count="$(printf '%s\n' "${heads}" | grep -c .)"
  if [ "${count}" -gt 1 ]; then
    echo "::error::multiple Alembic heads — merge them before deploying ('alembic merge heads')." >&2
    return 1
  fi
  printf '%s\n' "${heads}" | head -n 1
}

endpoints() { require_var DEPLOY_BASE_URL; printf '%s\n' "${DEPLOY_BASE_URL}"; }

await_healthy() {
  require_var DEPLOY_BASE_URL
  local timeout="${1:-120}" deadline body
  deadline=$(( $(date +%s) + timeout ))
  while [ "$(date +%s)" -lt "${deadline}" ]; do
    if body="$(curl -fsS "${DEPLOY_BASE_URL%/}/health" 2>/dev/null)"; then
      # Health-gate: serving AND no breached SLO (the Phase-1 smoke rule).
      case "${body}" in
        *'"breached"'*) ;;     # an SLO is breached — keep waiting
        *) return 0 ;;
      esac
    fi
    sleep 3
  done
  echo "::error::release at ${DEPLOY_BASE_URL} did not become healthy within ${timeout}s." >&2
  exit 1
}

deploy() {
  require_var APP_IMAGE
  require_var DEPLOY_ENV
  # Record BEFORE placing so a rollback target is tracked even if this deploy fails midway.
  local rev
  rev="$(repo_head_revision)"
  __target_record_release "${APP_IMAGE}" "${rev}"
  # shellcheck disable=SC2317  # reached once __target_record_release is implemented (not the _todo stub)
  __target_place_image   # the image entrypoint runs `alembic upgrade head` on start
}

rollback() {
  require_var DEPLOY_ENV
  # Roll back to the release before the current head: REVERSE migrations to ITS revision, THEN
  # redeploy ITS image. The downgrade is essential — the image only ever upgrades, so without it
  # the old code would run against the new schema. (Irreversible migrations cannot be restored;
  # the framework blocks them — see the migration guard + infra/deploy/README.md.)
  local history prev image rev
  history="$(__target_release_history)"
  # A rollback target must exist: need at least the current release + one prior.
  if [ "$(printf '%s\n' "${history}" | grep -c .)" -lt 2 ]; then
    echo "::error::no previous release to roll back to (rollback target missing)." >&2
    exit 1
  fi
  prev="$(printf '%s\n' "${history}" | tail -n 2 | head -n 1)"
  image="$(printf '%s' "${prev}" | cut -f1)"
  rev="$(printf '%s' "${prev}" | cut -f2)"
  __target_migrate "downgrade ${rev}"
  # shellcheck disable=SC2317  # reached once __target_migrate is implemented (not the _todo stub)
  APP_IMAGE="${image}" __target_place_image
}

operation="${1:-}"
case "${operation}" in
  deploy)          deploy ;;
  await-healthy)   await_healthy "${2:-120}" ;;
  endpoints)       endpoints ;;
  rollback)        rollback ;;
  releases)        __target_release_history ;;
  current-release) __target_release_history | tail -n 1 | cut -f1 ;;
  teardown)        __target_teardown ;;
  *)
    echo "::error::unknown deploy operation '${operation}'." >&2
    echo "Valid: deploy await-healthy endpoints rollback releases current-release teardown." >&2
    exit 2
    ;;
esac
