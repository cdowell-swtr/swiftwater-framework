---
name: arduino-setup-task-no-node24-release
description: "✅ RESOLVED (PR #9, 2026-06-11): arduino/setup-task (no Node-24 release at any ref) replaced with a direct go-task install before the 2026-06-16 GHA node24 force. Kept as history."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: f0c30aab-012a-4b65-a655-4432ba2eb964
---

`arduino/setup-task` has **no Node-24 release** and cannot be fixed by a version bump. Verified 2026-06-11: `action.yml` is `runs.using: "node20"` at **every** ref — `v2`, `v2.0.0`, and even `main`; the latest release is `v2.0.0` (Feb 2024). So the `test_workflow_node24.py::APPROVED_ACTIONS` entry's "pending a Node-24 release" note and the maintenance doc's "bump once a Node-24 release ships" are a dead end.

It is the **lone `node20-forced`** action left after the NODE24-MIGRATION bulk bump (`v0.1.7`). GHA force-runs the **Node 24** runtime by default on **2026-06-16** (node20 removed 2026-09-16) → its node20 dist gets run under node24 (the v0.2.1 release run already logged the "may not work as expected" warning). Used in **framework workflows only**: `.github/workflows/ci.yml:19` + `render-matrix.yml:48` — NOT the template.

**Why:** spotted in the v0.2.1 release-run logs; the framework claims Node-24 compliance via `APPROVED_ACTIONS`, so this is a real gap with a near deadline.

**How to apply:** ✅ DONE on branch `node24-replace-arduino-setup-task` → **PR #9** (commit `9e78b1a`, 2026-06-11): dropped the action; `task` (go-task) now installed directly via the official `install.sh` **pinned to v3.51.1** (`-b "$HOME/.local/bin"` + `echo >> "$GITHUB_PATH"`) in `ci.yml` + `render-matrix.yml`. A `run:` step has no Node runtime → outside `APPROVED_ACTIONS`. Removed the entry; added a `test_no_node20_forced_actions` guard (fail-closed against any future `node20-forced`); updated the maintenance doc. **All PR checks green** — every render combo (incl. full battery) ran `task ci` on the real runner, and `build` ran the upskill tests' `subprocess.run(["task","test"])`; Opus branch review = no blockers. PATH gotcha confirmed safe: `$GITHUB_PATH` only affects *later* steps, and both `task` consumers are later steps. To bump `task`: edit the pinned `v3.x.y` tag in both workflows. Lesson that held: always confirm a `node20`→`node24` claim by reading `runs.using` in `action.yml` at the exact tag ([[verify-action-node-runtime-from-actionyml]]), not a web summary.
