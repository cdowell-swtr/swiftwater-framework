#!/usr/bin/env bash
# Turnkey deploy target: compose-over-SSH across 1..N app hosts (Plan 5c-2).
# Sourced by ../strategy.sh when DEPLOY_TARGET=compose-ssh. Implements the __target_* hooks.
#
# Topology: each app host runs infra/compose/app-host.yml (app-only, no Postgres, no Traefik).
# A single SHARED external Postgres is referenced by APP_DATABASE_URL. TLS + health-draining is
# the builder-provided load balancer's job (it routes only to hosts whose /health returns 200).
# The expand migration runs ONCE against the shared DB (hosts run APP_RUN_MIGRATIONS=false).
#
# Config (in addition to strategy.sh's APP_IMAGE / DEPLOY_ENV / DEPLOY_BASE_URL):
#   DEPLOY_HOSTS      space-separated app host list, e.g. "10.0.0.1 10.0.0.2"  (required)
#   APP_DATABASE_URL  the shared Postgres URL                                   (required)
#   DEPLOY_SSH_USER   ssh user                                   (default: deploy)
#   DEPLOY_PATH       dir on each host for compose + release state(default: /opt/app)
#   DEPLOY_SSH_PORT   ssh port                                   (default: 22)
#   DEPLOY_HOST_PORT  app port each host exposes to the LB       (default: 8000)
#   DEPLOY_AWAIT_TIMEOUT  per-host health wait, seconds          (default: 120)

: "${DEPLOY_SSH_USER:=deploy}"
: "${DEPLOY_PATH:=/opt/app}"
: "${DEPLOY_SSH_PORT:=22}"
: "${DEPLOY_HOST_PORT:=8000}"
: "${DEPLOY_AWAIT_TIMEOUT:=120}"

# shellcheck disable=SC2086  # intentional word-splitting of the space-separated host list
_hosts() { require_var DEPLOY_HOSTS; printf '%s\n' ${DEPLOY_HOSTS}; }
_first_host() { _hosts | head -n 1; }

_ssh() {
  local host="$1"; shift
  ssh -p "${DEPLOY_SSH_PORT}" -o StrictHostKeyChecking=accept-new -o BatchMode=yes \
    "${DEPLOY_SSH_USER}@${host}" "$@"
}

_push_compose() {
  local host="$1"
  _ssh "${host}" "mkdir -p '${DEPLOY_PATH}'"
  # No quotes around the remote path: modern OpenSSH (>=9) scp uses the SFTP protocol and does
  # NOT run a remote shell over the destination, so embedded quotes are taken literally (the
  # open fails). DEPLOY_PATH is an operator-set path without spaces, so an unquoted target is
  # correct here (a remote path with spaces would need backslash-escaping, not quoting).
  scp -P "${DEPLOY_SSH_PORT}" -o StrictHostKeyChecking=accept-new \
    infra/compose/app-host.yml "${DEPLOY_SSH_USER}@${host}:${DEPLOY_PATH}/app-host.yml"
}

# Run an alembic command ONCE against the shared DB via a one-shot, no-deps container on the
# first host (which can reach APP_DATABASE_URL). $1=image, rest=alembic args.
_migrate_once() {
  local host img; host="$(_first_host)"; img="$1"; shift
  _push_compose "${host}"
  _ssh "${host}" "cd '${DEPLOY_PATH}' && APP_IMAGE='${img}' APP_DATABASE_URL='${APP_DATABASE_URL}' \
    docker compose -f app-host.yml run --rm --no-deps app alembic $*"
}

# Bring up APP_IMAGE on one host (app-only, no self-migrate) and wait for ITS /health.
_roll_host() {
  local host="$1"
  _push_compose "${host}"
  _ssh "${host}" "cd '${DEPLOY_PATH}' && APP_IMAGE='${APP_IMAGE}' APP_RUN_MIGRATIONS=false \
    APP_DATABASE_URL='${APP_DATABASE_URL}' DEPLOY_ENV='${DEPLOY_ENV}' DEPLOY_HOST_PORT='${DEPLOY_HOST_PORT}' \
    docker compose -f app-host.yml up -d"
  _await_host "${host}"
}

_await_host() {
  local host="$1" deadline body
  deadline=$(( $(date +%s) + DEPLOY_AWAIT_TIMEOUT ))
  while [ "$(date +%s)" -lt "${deadline}" ]; do
    if body="$(_ssh "${host}" "curl -fsS http://localhost:${DEPLOY_HOST_PORT}/health" 2>/dev/null)"; then
      case "${body}" in *'"breached"'*) ;; *) return 0 ;; esac
    fi
    sleep 3
  done
  echo "::error::host ${host} did not become healthy within ${DEPLOY_AWAIT_TIMEOUT}s." >&2
  return 1
}

# === hooks ===========================================================================
__target_place_image() {
  require_var APP_IMAGE
  # _migrated is set to 1 by __target_migrate (the rollback path) so a rollback's
  # subsequent __target_place_image does NOT re-run the forward upgrade. On a plain
  # forward deploy the flag is unset (defaults 0), so the expand migration runs once.
  if [ "${_migrated:-0}" = "0" ]; then
    _migrate_once "${APP_IMAGE}" upgrade head   # expand-only; schema leads (forward deploy)
  fi
  local host
  for host in $(_hosts); do
    _roll_host "${host}"
  done
}

__target_migrate() {
  # Rollback: reverse migrations once against the shared DB using the CURRENT head image
  # (it contains the down-path for the migration being reverted). $* e.g. "downgrade <rev>".
  local head_img; head_img="$(__target_release_history | tail -n 1 | cut -f1)"
  _migrate_once "${head_img}" "$@"
  _migrated=1
}

__target_record_release() {
  require_var DEPLOY_ENV
  local host
  for host in $(_hosts); do
    _ssh "${host}" "mkdir -p '${DEPLOY_PATH}' && printf '%s\t%s\n' '$1' '$2' >> '${DEPLOY_PATH}/releases-${DEPLOY_ENV}.tsv'"
  done
}

__target_release_history() {
  require_var DEPLOY_ENV
  _ssh "$(_first_host)" "cat '${DEPLOY_PATH}/releases-${DEPLOY_ENV}.tsv' 2>/dev/null" || true
}

__target_teardown() {
  local host
  for host in $(_hosts); do
    _ssh "${host}" "cd '${DEPLOY_PATH}' && docker compose -f app-host.yml down --remove-orphans" || true
  done
}
