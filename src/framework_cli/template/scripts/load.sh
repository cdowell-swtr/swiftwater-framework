#!/usr/bin/env bash
# CD Phase 4 — SLO load validation via Grafana k6 (official Docker image; no local install).
# k6 thresholds map 1:1 to the SLO definitions, passed in as env vars (defaults match the
# scaffold's settings). Usage: K6_TARGET=https://staging.example.com bash scripts/load.sh
set -euo pipefail

target="${K6_TARGET:-http://localhost:8000}"
p99_ms="${SLO_P99_MS:-200}"
error_rate_pct="${SLO_ERROR_RATE_PCT:-1}"

# --network host lets the container reach a localhost target (e.g. the local `lite` stack).
docker run --rm -i --network host \
  -e "K6_TARGET=${target}" \
  -e "SLO_P99_MS=${p99_ms}" \
  -e "SLO_ERROR_RATE_PCT=${error_rate_pct}" \
  -e "K6_VUS=${K6_VUS:-10}" \
  -e "K6_DURATION=${K6_DURATION:-30s}" \
  grafana/k6:latest run - < tests/non_functional/load.js
