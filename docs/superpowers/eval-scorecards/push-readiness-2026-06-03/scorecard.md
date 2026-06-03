# Push-readiness scorecard — 2026-06-03 (Plan 14)

**Result: GREEN** ✅ — a **vanilla `framework new`-shaped project** (only `uv lock` generated at scaffold time + the self-seeding `contract` job; **NO manual `uv sync`/`task openapi:export` prep**) runs its shipped `ci.yml` green on **real GitHub Actions** for baseline + all-batteries × push/PR, first try (no flake re-run).

This is Plan 14's acceptance test: the regression Plan 13 found (a fresh project isn't push-ready) is now fixed, and the dogfood — with its old `prepare_project` manual prep **removed** — still goes green.

| Config | push run | PR run | result |
| --- | --- | --- | --- |
| baseline | [run](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26893962922) | [run](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26894133080) | ✅ green |
| all-batteries | [run](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26894329755) | [run](https://github.com/cdowell-swtr/swiftwater-dogfood/actions/runs/26894673111) | ✅ green |

## What this proves

- **`uv.lock` at `new`** — the 5 `uv sync --frozen` jobs + the Dockerfile `COPY uv.lock` pass with only the lock that `render()`/`framework new` generated (`framework_cli.lockfile.write_lockfile`). No committed-by-hand lock.
- **`contract` job self-seed** — with no committed `openapi.json`/`schema.graphql`, the job generates them for the run, emits a `::notice::`, and passes (the oasdiff / graphql-breaking-change gates are skipped because the spec is untracked). First push + first PR both green.
- **The dogfood harness no longer pre-generates artifacts** (`prepare_project` removed) — so green here means the *project itself* is push-ready, not that the harness papered over it.

## Notes

- Pinned `_commit: v0.1.4` for the integrity step-0 install (branch validation); `DOGFOOD_COMMIT` bumps to `v0.1.5` when this plan's release ships.
- Bonus (closed): `test_rendered_react_battery_passes` now calls `write_lockfile(dest)` before its multi-stage docker build, so the full `--with react` image build is validated in-session — closing the long-standing 8g "react image build never run end-to-end" residual.
- Known edge (deferred, pre-existing): oasdiff hard-fails on the first PR that commits `openapi.json` (base branch lacks it) — mirror the graphql `|| skip` base-missing guard in a follow-up.
