# GitHub Actions Node runtime policy

GitHub forces the **Node 24** actions runtime by default on **2026-06-16** and removes
Node 20 from runners on **2026-09-16**. Every `uses:` reference in this repo — the
framework's own workflows (`.github/workflows/`) **and** the workflows shipped into
generated projects (`src/framework_cli/template/.github/workflows/`) — must be pinned
to a Node-24-capable action version.

## Source of truth

`tests/test_workflow_node24.py::APPROVED_ACTIONS` is the authoritative map. It is enforced
by two tests that raw-scan every `uses:` on both surfaces:

- `runtime: "node"` actions must be pinned at or above their `min_major` (the first
  Node-24 release).
- `runtime: "docker"` actions (oasdiff, gitleaks) run in containers — no Node runtime, no
  version floor — but are still listed (an unrecognized `uses:` fails the test).
- `runtime: "node20-forced"` is a tracked exception for an action with **no Node-24 release
  yet** (currently `arduino/setup-task`). GHA force-runs it on Node 24; revisit before the
  2026-09-16 removal and bump once a Node-24 release ships.

## When adding or updating a workflow action

1. Pin to a Node-24-capable version.
2. Add/update the entry in `APPROVED_ACTIONS` (with `min_major` for node actions).
3. Run `uv run pytest tests/test_workflow_node24.py` — green means compliant.

## Verified versions (2026-06-04)

checkout@v5 · setup-uv@v6 · setup-node@v6 · upload-artifact@v6 · download-artifact@v7 ·
action-gh-release@v3 · arduino/setup-task@v2 (node20-forced) · oasdiff/gitleaks (docker).
