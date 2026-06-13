---
name: release-cut-procedure
description: "How to cut a swiftwater-framework release (vX.Y.Z) — files to bump, the render-matrix proof, lightweight tag → release.yml."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 8ee32788-65d6-4cce-ba1d-2d370eb00620
---

The repeatable release-cut sequence for this repo (done identically for v0.1.5/v0.1.6/v0.1.7/v0.1.8/v0.1.9). **Trigger:** cut a release whenever something that reaches builders ships — NOT only template-payload changes. Framework-CLI features ship in the wheel too: e.g. **v0.1.9 was a framework-side-only change** (the new `review-env-parity` reviewer — a prompt + registry entry, zero template files touched) and still warranted a release because the reviewer reaches builders' CI via the installed `framework-cli` wheel. When in doubt, release.

1. **Bump version** in `pyproject.toml` (`version = "X.Y.Z"`).
2. `uv lock` (updates `framework-cli` to X.Y.Z in `uv.lock`).
3. **`DOGFOOD_COMMIT`** in `src/framework_cli/dogfood.py` → `"vX.Y.Z"` (the tag the generated integrity step-0 installs).
4. Update the **meta-plan** status row (mark the plan done + FF SHA + `vX.Y.Z`) and the **CLAUDE.md** Current State pointer.
5. Validate metadata: `uv run ruff check src/framework_cli/dogfood.py`, `uv run mypy src/framework_cli/dogfood.py`, `uv lock --check`, `uv build` (must build `framework_cli-X.Y.Z.{whl,tar.gz}`).
6. Commit `chore(release): vX.Y.Z — …` (commit-gate dance applies: separate `git add` then commit; CLAUDE.md staged; write the `.framework/audit/marker.json` PASS skip-marker via `framework gate-prepare`).
7. **Push `master`** — this push's `render-matrix.yml` run is the framework-side proof; watch it green (`gh run watch <id> --exit-status`). A prior failing render-matrix (e.g. the packagecloud flake) shows up here.
8. **Lightweight tag** (`git tag vX.Y.Z <sha>`, NOT annotated — prior tags are lightweight) and `git push origin vX.Y.Z` → triggers `release.yml` (tag==version guard → reusable ci + render-matrix → `uv build` → GitHub Release). The `arduino/setup-task@v2` Node-20 deprecation warning in this run is the known tracked exception, not a failure.
9. Watch `release.yml` to a green published Release (`gh release view vX.Y.Z`, confirm `isDraft: false` + **exactly 2 assets: `framework_cli-X.Y.Z-py3-none-any.whl` + `framework_cli-X.Y.Z.tar.gz`** — verified v0.1.8/v0.1.9/v0.2.0; there is NO `default.gitignore` release asset despite earlier notes), then a final CLAUDE.md state bump to "published".

**Why:** the local gate misses ruff-FORMAT, template-payload mypy, and generated-project dep drift ([[release-readiness-needs-render-not-local-gate]]) — the render-matrix on the pushed release commit is the real proof, and `release.yml` re-runs it on the tag. **How to apply:** follow steps in order; the tag must equal `pyproject` version or `release.py`'s guard fails. Beware the [[commit-gate-hook-timing]] gotcha and keep "commit" out of Bash descriptions on the push step.
