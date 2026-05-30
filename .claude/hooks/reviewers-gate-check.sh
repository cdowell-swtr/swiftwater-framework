#!/usr/bin/env bash
# PreToolUse hook: matches Bash tool calls containing `git commit`. Reads
# .framework/audit/marker.json and decides allow vs block based on:
#   - staged_hash matches the current review-relevant staged set
#   - verdict is PASS
#   - drift_detected is false
# On any failure, blocks with a directive Claude reads and acts on.
#
# Implementation note: the staged_hash / marker fields are read by shelling
# out to `framework eval-prepare --mode gate` (for the current hash) and to
# `python3 -c` reads of the marker JSON (for marker fields). This avoids any
# sys.path hacking and naturally matches the template-shipped version.
# We use `python3` (not bare `python`) for portability — many systems
# (incl. this dev env) ship python3 + uv-managed Pythons but no `python`
# symlink. `uv run python` would also work but adds ~hundreds of ms per
# spawn vs the stdlib-only JSON reads here.

set -euo pipefail

# Only fire on `git commit` invocations.
grep -Eq '(^|[^[:alnum:]_])git[[:space:]]+([^[:space:]].*[[:space:]]+)?commit([^[:alnum:]_]|$)' || exit 0

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root"

marker=".framework/audit/marker.json"
if [ ! -f "$marker" ]; then
  echo "Pre-commit gate not run for current staged set. Invoke /reviewers:gate, then retry this commit." >&2
  exit 2
fi

# Recompute current staged_hash by shelling out to eval-prepare --mode gate
# and parsing the JSON it emits. This is the same code path /reviewers:gate
# uses, so the hashes are guaranteed to compare apples-to-apples.
current_hash=$(uv run framework eval-prepare --mode gate 2>/dev/null | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('staged_hash', ''))
except Exception:
    pass
") || {
  echo "Pre-commit gate: could not compute staged hash (uv run framework eval-prepare failed?). Invoke /reviewers:gate manually, then retry." >&2
  exit 2
}

if [ -z "$current_hash" ]; then
  echo "Pre-commit gate: could not compute staged hash (empty output). Invoke /reviewers:gate manually, then retry." >&2
  exit 2
fi

marker_hash=$(python3 -c "
import json
try:
    m = json.load(open('$marker'))
    print(m.get('staged_hash', ''))
except Exception:
    pass
" 2>/dev/null) || marker_hash=""

if [ "$current_hash" != "$marker_hash" ]; then
  echo "Pre-commit gate stale (staged set changed since last gate). Invoke /reviewers:gate, then retry." >&2
  exit 2
fi

verdict=$(python3 -c "
import json
try:
    m = json.load(open('$marker'))
    print(m.get('verdict', 'FAIL'))
except Exception:
    print('FAIL')
" 2>/dev/null) || verdict="FAIL"

summary=$(python3 -c "
import json
try:
    m = json.load(open('$marker'))
    print(m.get('summary', ''))
except Exception:
    pass
" 2>/dev/null) || summary=""

drift=$(python3 -c "
import json
try:
    m = json.load(open('$marker'))
    print('true' if m.get('drift_detected', False) else 'false')
except Exception:
    print('false')
" 2>/dev/null) || drift="false"

if [ "$verdict" != "PASS" ]; then
  echo "Pre-commit gate FAILED: $summary. Address findings in .framework/audit/latest/audit-report.md and re-evaluate (re-run /reviewers:gate), then retry. To override (rare): git commit --no-verify." >&2
  exit 2
fi

if [ "$drift" = "true" ]; then
  echo "Drift detected during last gate run: subagent used disallowed tools (see .framework/audit/latest/audit-report.md '## Drift check'). Investigate before committing." >&2
  exit 2
fi

# All checks pass — allow the commit.
exit 0
