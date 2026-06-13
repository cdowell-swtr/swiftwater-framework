---
name: docker-as-root-host-uid-gap
description: "✅ RESOLVED by Plan 12 (FF b24806f): worker/beat got `user:`, frontend switched to `npm ci` + a gitignored `node_modules/.gitkeep` (Docker root-owns the named-volume mount point otherwise), live guards added. [Was: Plan 9 fixed only the `app` service.]"
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 3248cc2a-470c-4aa5-9ff1-5d9cf4d914a4
---

Plan 9's "run dev containers as host UID so renders leave no root-owned files" fix was scoped to **one** service. `infra/compose/dev.yml.jinja` has a single `user: "${UID:-1000}:${GID:-1000}"` line (on `app`, ~line 8 — the only `user:` in any compose file). Three other `profiles: ["dev"]` services bind-mount **writable** host paths with no `user:` line, so they run as root and reproduce the root-owned-`/tmp`/residue class Plan 9 claimed to resolve:

- **`worker`** (`workers` battery) — `../../src:/app/src` → root `__pycache__` in host `src/`
- **`beat`** (`workers` battery) — `../../src:/app/src` → root `__pycache__` in host `src/`
- **`frontend`** (`react` battery, `image: node:22`) — `../../frontend:/app/frontend` → root vite/build artifacts in host `frontend/` (`node_modules` is a named volume, but the bind itself is writable)

The guard `test_rendered_project_dev_lite_stack_leaves_no_root_owned_files` is structurally blind to all three: it brings up `--profile lite` (which is `app`-only — worker/beat/frontend never start) and scans only `dest/src` (never `dest/frontend`). So it reads green while covering only the already-fixed path.

**Why:** Plan 9 / CLAUDE.md / meta-plan described the docker-as-root wedging class as fully RESOLVED; it was only resolved for the `app` service. The `workers`/`react` batteries bring it back.

**How to apply:** When scheduling the hygiene slice — add `user:` to `worker`/`beat` (share the app Dockerfile/UID story), handle the `node:22` frontend carefully (node images expect to own `node_modules`), and **widen the guard to the full `dev` profile + scan `frontend/`**. TDD shape: widen guard → watch it fail on worker/beat/frontend → add `user:` → green. Recorded as a CLAUDE.md Known follow-up 2026-06-02. Related: [[verify-parity-not-blocker]] (Plan 9's parent SVC-PROD `/tmp`-wedge context), [[dind-e2e-harness-gotchas]] (the deploy e2e runs root by necessity — different mechanism, not this gap).
