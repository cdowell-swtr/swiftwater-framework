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
- `runtime: "node20-forced"` was a tracked exception for an action with **no Node-24 release
  yet** — GHA force-runs such actions on Node 24. There are now **none**; the
  `test_no_node20_forced_actions` guard forbids reintroducing one without a conscious choice.

## `task` (go-task) is installed directly, not via an action

The framework's `ci.yml` and `render-matrix.yml` need the `task` binary. They previously
used `arduino/setup-task@v2`, but that action has **no Node-24 release at any ref**
(`action.yml` is `runs.using: "node20"` at `v2`, `v2.0.0`, and `main`; latest release
v2.0.0, Feb 2024) — so on 2026-06-16 it would be force-run on Node 24. It was dropped
(2026-06-11) in favour of the official install script, pinned to a version:

```yaml
- name: Install Task (go-task)
  run: |
    sh -c "$(curl -sSL https://taskfile.dev/install.sh)" -- -b "$HOME/.local/bin" v3.51.1
    echo "$HOME/.local/bin" >> "$GITHUB_PATH"
```

This is a `run:` step (no Node runtime at all), so it is outside the `APPROVED_ACTIONS`
scope. To bump `task`, edit the pinned `v3.x.y` tag in both workflows. The template ships
no workflow that needs `task`, so this change is framework-only.

## When adding or updating a workflow action

1. Pin to a Node-24-capable version.
2. Add/update the entry in `APPROVED_ACTIONS` (with `min_major` for node actions).
3. Run `uv run pytest tests/test_workflow_node24.py` — green means compliant.

## Verified versions (2026-06-11)

checkout@v5 · setup-uv@v7 · setup-node@v6 · upload-artifact@v6 · download-artifact@v7 ·
action-gh-release@v3 · oasdiff/gitleaks (docker). `task` (go-task) v3.51.1 installed via
install.sh — `arduino/setup-task` removed (no Node-24 release).
