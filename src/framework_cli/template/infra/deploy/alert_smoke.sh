#!/usr/bin/env bash
# Alert delivery smoke (8f-w / #3). Fires a synthetic, auto-resolved test alert into Alertmanager,
# then checks Alertmanager's own notification-failure counter. ADVISORY: it ALWAYS exits 0 — a
# third-party blip must never fail your deploy or trigger a rollback. Point ALERTMANAGER_URL at
# your deploy's Alertmanager (default localhost:9093). Called from the CD workflows (advisory step).
set -uo pipefail

AM_URL="${ALERTMANAGER_URL:-http://localhost:9093}"
WAIT="${SMOKE_WAIT:-5}"

failed_total() {
  curl -fsS "${AM_URL}/metrics" 2>/dev/null \
    | awk '/^alertmanager_notifications_failed_total/ {s+=$NF} END {printf "%d", s+0}'
}

# Fire a synthetic, clearly-labeled alert that ends 2s out (auto-resolves; never pages).
end="$(date -u -d '+2 seconds' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
curl -fsS -X POST "${AM_URL}/api/v2/alerts" -H 'Content-Type: application/json' \
  --data "[{\"labels\":{\"alertname\":\"DeploySmokeTest\",\"severity\":\"info\"},\"endsAt\":\"${end}\"}]" \
  >/dev/null 2>&1 || { echo "[alert-smoke] could not reach Alertmanager at ${AM_URL} — skipping (advisory)."; exit 0; }

sleep "${WAIT}"
after="$(failed_total)"

if [ "${after}" -gt 0 ]; then
  echo "::warning::[alert-smoke] Alertmanager reports ${after} failed notification(s) — a configured channel may be misconfigured (delivery may be broken). Advisory only." >&2
else
  echo "[alert-smoke] ok — no notification failures reported."
fi
exit 0
