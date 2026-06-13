---
name: verify-action-node-runtime-from-actionyml
description: "To learn a GitHub Action's Node runtime, read its action.yml `runs.using` — not a web-search summary. setup-uv@v6 is node20; node24 only at v7."
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8ee32788-65d6-4cce-ba1d-2d370eb00620
---

When migrating GitHub Actions off a deprecated Node runtime (e.g. the Node 20 → Node 24 forced default on 2026-06-16), determine each action's actual runtime by fetching its `action.yml` and reading `runs.using` (`node16`/`node20`/`node24`) at the specific tag — **do not trust a WebSearch summary**.

During `NODE24-MIGRATION` (shipped `v0.1.7`, FF `7618ce4`), my WebSearch claimed `astral-sh/setup-uv@v6 = Node 24`. It was wrong: `v6` (and the floating `v6` tag) declare `runs.using: node20`; setup-uv only moved to `node24` at **`v7.0.0`**. I bumped to `@v6` and the allowlist guard went green anyway because the guard's `min_major` floor itself encoded the wrong version — false confidence. The branch-end Opus review caught it by fetching `raw.githubusercontent.com/astral-sh/setup-uv/v6/action.yml` (node20) vs `/v7/action.yml` (node24). Verified set for the migration: checkout@v5, setup-uv@**v7**, setup-node@v6, upload-artifact@v6, download-artifact@v7, action-gh-release@v3; `arduino/setup-task` had no Node-24 release → tracked `node20-forced` exception.

**Why:** version-number intuition and search summaries lag/misreport action runtimes; the action.yml `runs.using` is authoritative. A guard test keyed on a hand-entered version floor amplifies the error (it green-lights the wrong version) rather than catching it.

**How to apply:** for any action-runtime claim, `WebFetch` the action's `action.yml` at the exact tag and read `runs.using` before pinning. The source of truth for this repo's policy is `tests/test_workflow_node24.py::APPROVED_ACTIONS` + `docs/maintenance/github-actions-node-runtime.md`; revisit `arduino/setup-task` before the 2026-09-16 Node-20 removal. Reinforces [[verify-parity-not-blocker]] (verify empirically) and why the independent branch-end review earns its cost.
