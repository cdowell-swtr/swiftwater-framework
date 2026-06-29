#!/usr/bin/env bash
# GFS-lite retention for $BACKUP_DEST. Filled in by the prune task; no-op until then.
set -euo pipefail
: "${BACKUP_DEST:=./backups}"
exit 0
