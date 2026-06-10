#!/usr/bin/env bash
# PreToolUse hook: on `git commit`, run the in-process review gate
# (`framework gate`). It reviews the affected staged set, writes
# .framework/audit/marker.json, and degrades skip-neutral when no AI review
# backend is enabled — so a backend-less commit is never blocked. Blocks the
# commit (exit 2) only on a real FAIL verdict.
set -euo pipefail
grep -Eq '(^|[^[:alnum:]_])git[[:space:]]+([^[:space:]].*[[:space:]]+)?commit([^[:alnum:]_]|$)' || exit 0
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root"
if ! uv run framework gate >/dev/null 2>&1; then
  summary=$(python3 -c "import json;print(json.load(open('.framework/audit/marker.json')).get('summary',''))" 2>/dev/null || true)
  echo "Pre-commit gate FAILED (framework gate): ${summary:-findings at/above block threshold; see .framework/audit/latest/audit-report.md}. Address the findings, then retry." >&2
  exit 2
fi
exit 0
