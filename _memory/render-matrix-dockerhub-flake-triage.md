---
name: render-matrix-dockerhub-flake-triage
description: "render-matrix failures are often Docker Hub registry timeouts, not your change — a no-docs/unrelated combo failing identically is the tell; rerun --failed"
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 04998c6e-0f19-4f7d-953b-9d21e01f9a6f
---

The `render-matrix` workflow runs `task ci` per battery combo, and `task ci` →
`test:cov:ci` brings up a **testcontainers Postgres** (pulls from Docker Hub). On real
GHA this intermittently times out:

```
Get "https://registry-1.docker.io/v2/": net/http: request canceled
(Client.Timeout exceeded while awaiting headers)
```

→ `task: Failed to run task "test:cov:ci": exit status 1`, before later `task ci` steps
(`audit`, `openapi:export`, `docs:build`) even run.

**Triage heuristic:** when render-matrix goes red right after a *battery* change, check
**which combos failed**. If a combo that does NOT include your battery (e.g. a no-docs
`mongodb+pgvector` combo failed identically while you were shipping the `docs` battery)
fails at the same `test:cov:ci` Docker-pull step, it's a **transient Docker Hub infra
flake, not your change**. (`conftest.py` even notes "flake CI — only a persistent failure
actually fails", but a registry timeout still surfaces as a job failure.)

**Fix:** `gh run rerun <run-id> --failed` (re-runs only the failed combos). Confirm green;
then look for positive proof your change actually exercised — e.g. for the docs battery,
grep the rerun log for `task: [docs:build] ... mkdocs build --strict` + `Documentation
built in …s`, since on the flaked run `docs:build` never ran (it's after `test:cov:ci` in
the `ci` task order). Related: [[dogfood-e2e-harness-and-task-ci-coverage-gap]], and the local full-suite
`/tmp` tmpfs exhaustion fix (set `TMPDIR=/var/tmp`).
