# Releasing the framework

A release is a git tag `vX.Y.Z` on this repo, equal to the `framework-cli` version in
`pyproject.toml`. Generated projects record `_commit: vX.Y.Z` in `.copier-answers.yml`, and
`framework upskill` / `framework check` / CI step-0 all resolve that tag — so the tag MUST exist
and MUST point at the commit whose bundled template you shipped.

## Procedure

1. Ensure `master` is green (`uv run pytest -q`, `uv run ruff check .`, `uv run mypy src`).
2. Bump `version` in `pyproject.toml` to `X.Y.Z` (semver). Update `CLAUDE.md` + the meta-plan.
3. Commit. **Tag the same commit:** `git tag vX.Y.Z && git push origin master vX.Y.Z`.
4. The invariant holds by construction: CLI `X.Y.Z`'s bundled template == the template at `vX.Y.Z`,
   because they are the same commit. Do not move a tag after release.

## Install / upgrade

- Install: `uv tool install git+https://github.com/cdowell-swtr/swiftwater-framework@vX.Y.Z`
- Check for newer: `framework check`
- Upgrade a project: bump the installed CLI, then `framework upskill <project>` (the project must
  be a clean git working tree; Copier leaves inline conflict markers where a builder edited a
  changed framework line).
