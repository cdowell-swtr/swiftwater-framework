#!/bin/sh
set -e

# On container start: apply pending migrations + load seed data (both idempotent), then hand
# off to the server command (uvicorn, passed as CMD / compose `command`). Gated by
# APP_RUN_MIGRATIONS (default true) so dev / single-host / test self-migrate on start. A
# multi-host rolling deploy sets APP_RUN_MIGRATIONS=false on the app hosts and migrates ONCE
# before the roll (see infra/deploy/README.md), so N containers don't race the same migration.
if [ "${APP_RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
  python scripts/seed.py
fi
exec "$@"
