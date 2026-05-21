#!/usr/bin/env bash
# Run the named test suites, each tagged with its own coverage context, then enforce a
# combined line-coverage threshold. The contexts (unit / functional / e2e) let CI tell a
# genuinely-uncovered line from one covered only at the integration level.
#
# Usage: scripts/coverage.sh <min_pct> <suite>...
#   pre-commit (fast):  scripts/coverage.sh 70 unit functional
#   CI (full picture):  scripts/coverage.sh 85 unit functional e2e
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <min_pct> <suite>..." >&2
  exit 2
fi

min_pct="$1"
shift

uv run coverage erase
append=""
for suite in "$@"; do
  # $append is intentionally empty on the first suite, "--append" afterwards.
  # shellcheck disable=SC2086
  uv run coverage run --context="$suite" $append -m pytest "tests/$suite" -q
  append="--append"
done
uv run coverage report --fail-under="$min_pct"
