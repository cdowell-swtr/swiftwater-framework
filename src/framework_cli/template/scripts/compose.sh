#!/usr/bin/env bash
# Thin `docker compose` wrapper: shift every published host port by ${PORT_OFFSET:-0} so a
# second stack can run alongside this one (FWK31). Each port also has its own override; this
# only sets a var when it is not already set in the environment. Then exec the compose
# command passed as arguments.
set -euo pipefail
off="${PORT_OFFSET:-0}"
# Note: if PORT_OFFSET pushes any port past 65535 the bind will fail at runtime.
_p() {  # _p VAR DEFAULT  -> export VAR=$((DEFAULT+off)) unless already set
  local var="$1" default="$2"
  if [ -z "${!var:-}" ]; then export "$var"="$((default + off))"; fi
}
_p HTTP_HOST_PORT 8000
_p POSTGRES_HOST_PORT 5432
_p TRAEFIK_HTTPS_PORT 443
_p TRAEFIK_HTTP_PORT 80
_p MONGO_HOST_PORT 27017
_p REDIS_HOST_PORT 6379
_p FRONTEND_HOST_PORT 5173
_p PROMETHEUS_HOST_PORT 9090
_p GRAFANA_HOST_PORT 3000
_p ALERTMANAGER_HOST_PORT 9093
_p LOKI_HOST_PORT 3100
_p TEMPO_HOST_PORT 3200
_p POSTGRES_EXPORTER_HOST_PORT 9187
_p MONGODB_EXPORTER_HOST_PORT 9216
_p CELERY_EXPORTER_HOST_PORT 9808
_p REDIS_EXPORTER_HOST_PORT 9121
exec docker compose "$@"
