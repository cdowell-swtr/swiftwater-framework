#!/bin/sh
set -e

# On container start: apply pending migrations and load seed data (both idempotent),
# then hand off to the server command (uvicorn, passed as CMD / compose `command`).
alembic upgrade head
python scripts/seed.py
exec "$@"
