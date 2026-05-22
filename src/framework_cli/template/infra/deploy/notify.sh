#!/usr/bin/env bash
# Deploy notification seam (spec §8 alert routing). The CD workflows call:
#   bash infra/deploy/notify.sh "<message>"
# By default this logs to the workflow output. Wire your channel (Slack webhook / email /
# PagerDuty) here — reuse the same destination Alertmanager uses
# (infra/observability/alertmanager/alertmanager.yml) so alerts and deploy notices share one
# place. Keep it non-fatal: a notification failure must not fail the deploy.
set -euo pipefail

message="${1:-deploy notification}"
echo "[deploy notify] ${message}"

# Example (uncomment + set SLACK_WEBHOOK_URL as a secret):
# if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
#   curl -sf -X POST -H 'Content-Type: application/json' \
#     --data "{\"text\": \"${message}\"}" "${SLACK_WEBHOOK_URL}" || true
# fi
