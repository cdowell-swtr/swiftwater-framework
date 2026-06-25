# Upgrade notes

Per-release guidance for upgrading an existing generated project across framework versions
(`framework upgrade`). Most upgrades are a clean, reviewable diff; the notes here call out the
cases that need a human in the loop. Newest release first.

The GitHub Release's auto-generated notes list the merged PRs; this file holds the
**upgrader-facing** guidance that the commit log can't convey.

---

## v0.4.1

Surfaced by Meridian's v0.4.0 adoption (the first real de-forking consumer); see
`docs/superpowers/assessments/2026-06-25-meridian-to-framework-v040-adoption-divergences.md`.

### `pi_prefix` now fills in on upgrade (DV-1) — automatic, no action

A project created **before FWK9** (no persisted `pi_prefix` answer) previously upgraded with an
**empty** PI prefix in the managed `AGENTS.md` block. `framework upgrade` / `upskill` now apply the
derived default (`(project_slug | upper …)[:4]`) for any question your project predates, so the
block fills in. If that derived value isn't the prefix you want, set `pi_prefix:` explicitly in
`.copier-answers.yml` before (or after) upgrading — an explicit answer always wins.

### `.pre-commit-config.yaml` duplicate-key warning (DV-4) — may need a one-line edit

v0.4.0 moved `conventional-pre-commit` and `default_install_hook_types` into the
framework-**managed** region of `.pre-commit-config.yaml`. If you had **hand-added** your own copies
of those keys, the upgrade leaves a **duplicate top-level key** → invalid YAML → `check-yaml` fails
your first post-upgrade commit.

`framework upgrade` now **warns** (non-fatal) when it detects a duplicate top-level key in
`.pre-commit-config.yaml`. We don't auto-de-dupe — we can't tell an intentional override from a
redundant copy. **Fix:** delete your hand-added copy (the managed region now provides it), then
commit. The managed region owns `default_install_hook_types` and the `conventional-pre-commit` hook.

### `--with multitenantauth` on a persisted control DB (DV-6) — de-forking consumers only

*Applies only if you are adopting `--with multitenantauth` onto a project that **already ran an
older control-plane migration chain** (e.g. a fork being de-forked). A fresh control DB, or a
generic consumer adding the battery for the first time, is unaffected — skip this.*

The battery's `migrations_control` chain ships revisions `c0001_control_tenant` /
`c0002_auth_model` (reused ids, **different schema** — adds `slug`, `tenant_slug_history`, the
resource-domain CHECK, index drops) under a **new** Alembic version table,
`alembic_version_multitenantauth`. On a **persisted** control DB that already ran an older
`c0001`/`c0002`, the new version table is empty, so `alembic upgrade head` re-runs the
`CREATE TABLE`s against objects that already exist → the migration fails.

Two supported adoption paths:

- **Dev / rebuildable DB (recommended):** rebuild the control DB from the new chain —
  `task dev:reset` (or drop and re-create the control database), then `alembic upgrade head`.
  This is the clean path and what dev-DB-rebuildable consumers should do.
- **Prod / persisted DB you must keep:** **stamp** the new control version table to the revision
  that matches your already-applied schema, then upgrade forward. The control chain has its own
  Alembic config (`alembic_control.ini`, `script_location = migrations_control`) and runs
  independently of the app chain — the rendered project applies it with
  `alembic -c alembic_control.ini upgrade head` (see `scripts/entrypoint.sh`). After verifying your
  existing objects match the `c0001`–`c0003` end-state, `alembic -c alembic_control.ini stamp head`
  (or stamp the specific revision your schema corresponds to and let the remaining revisions apply),
  then `alembic -c alembic_control.ini upgrade head`. Do this under your normal migration review;
  the framework cannot know your prior fork's chain, so this step is manual by necessity.

This is the battery's **persisted-control-DB adoption reference** — the control migration chain is
plane-isolated under its own version table precisely so a co-located app chain and the control
chain never collide.

### By-design changes to expect (DV-2, DV-3) — FYI

- **`stage` → `staging`.** The battery's environment validator allows only
  `{dev, test, staging, prod}` (no `stage`/`ci`). If your `settings.py` used `stage`, rename it to
  `staging` — a required local rename, by design, not a bug.
- **`AGENTS.md` is framework-managed (since FWK9).** Your project content lives under the
  "Project notes" heading; the `FRAMEWORK:BEGIN/END` region is managed and reconciled on upgrade.
  Expected — move any hand-written content outside the managed markers.
