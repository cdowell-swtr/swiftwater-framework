# `framework upgrade` + rollback — design

**Plan 24.** Status: design (this spec) → implementation plan → build.

## Problem

A generated project records the framework version it was scaffolded at (`_commit` in
`.copier-answers.yml`). Today nothing moves a project *forward* onto a newer framework
release: batteries can be added/removed (`upskill --with` / `downskill`), but pulling
template improvements — CI workflows, Compose files, observability config, review agents,
scaffolded code patterns — has no first-class command. The closest path, a bare
`framework upskill <project>`, conflates two unrelated concerns (version movement *and*
battery mutation) in one call, and it carries a latent corruption bug (see below).

This plan adds **`framework upgrade`** as the single, explicit path that moves a project
across framework versions, and cleanly separates that from battery mutation.

### The identity-stripping bug (root cause we are fixing)

`upskill_project` passes `{batteries, alert_channels, **migration_context}` into
`copier.run_update`, but **not** the four identity answers — `project_name`,
`project_slug`, `package_name`, `python_version`. Copier does not round-trip those answers
through the portable source on update, so each update *strips* them from
`.copier-answers.yml`. It is safe for one hop (the rendered files are still correct), but a
later identity-path re-render then renders an empty package name — silent corruption. This
was found via the v0.2.0→v0.2.2 dry-run and is the concrete reason `framework upgrade` must
own version movement and get identity preservation right.

## Principles

- **Each command owns exactly one kind of change.** `upgrade` moves *versions*;
  `upskill --with` / `downskill` move *batteries*. A battery change must never smuggle in a
  template version bump, and vice-versa. Builder predictability over convenience.
- **Two clean snapshots.** A clean working tree *before* (precondition) and an explicit
  "commit (and push) now" instruction *after* give the builder a reviewable before/after
  diff. From there, **git owns history** — including any later downgrade and its conflicts.
- **Fix the cause, prove the invariant.** Identity preservation lives in the one shared
  update core so every path inherits it; a two-hop regression test makes the strip bug
  unreachable. No after-the-fact "healing" of stripped projects — correct core + the test
  mean no project ever reaches the stripped state.

## Command surface

### `framework upgrade <project> [--to <tag>]` — new

The one path that moves a project across framework versions.

1. **Preconditions** (refuse, mutate nothing, exit non-zero on failure):
   - project is git-tracked (existing check), **and**
   - the working tree is **clean** (`git status --porcelain` empty). This is what makes the
     before-snapshot clean and every failure branch recoverable.
2. **Resolve target:** `--to <tag>` if given, else the latest release tag (the same source
   `framework check` uses).
3. **No-op:** if the project is already at the target → print "already up to date (`vX.Y.Z`)"
   and exit 0.
4. **Update:** a single 3-way `copier update` computing the delta `recorded → target`
   directly (Copier-native; not stepped per intermediate tag). Identity is preserved;
   batteries and channels carry through unchanged. Any ordered per-version data migrations
   are handled inside that one update via Copier's `_migrations` keyed on the version range.
5. **Integrity + tests:** regenerate the integrity manifest (guarded on an existing lock),
   then run `task test`.
6. **On success**, the *last thing printed* is the two-snapshot instruction: a pointer to
   review the diff, followed by the explicit commands —
   `git add -A && git commit -m "chore: upgrade framework to vX.Y.Z" && git push` — so the
   builder records a clean after-snapshot immediately.
7. **On conflict markers or red tests** → exit non-zero with guidance (see Error handling).

### `framework upskill <project> --with <battery>` / `--alerts` — battery/alert mutation only

Pins to the project's **currently-recorded** version (no version movement), re-renders to
add the battery / reconfigure channels, runs tests. Identity preserved via the shared core.

### `framework upskill <project>` (bare, no `--with`/`--alerts`) — blocked

Exits non-zero with an **argument-requirement** message (no deprecation/history framing —
no consumer ever used bare upskill to move versions):

> `framework upskill` adds batteries — pass at least one `--with <battery>`. To move the
> framework version, use `framework upgrade <project>`.

### `framework downskill` — unchanged

Battery removal, at the recorded version, via the shared core.

### `framework check` — re-pointed

Its "newer release available" message now ends with "…then run `framework upgrade <project>`"
instead of `upskill`.

## Components & data flow

### New module `upgrade.py`

Owns the `framework upgrade` command logic: clean-tree check, target resolution, no-op
short-circuit, success/commit-after messaging. Thin — delegates the actual update to the
shared helper.

### Shared update helper (the one risky place)

Extract today's `upskill_project` body into a single helper —
`_apply_update(project, *, vcs_ref, batteries, channels)` (in `upskill.py` or a small
`_update.py`). It is the only place that touches the update mechanics, so identity
preservation and the fail-closed guard are inherited by every caller:

- **Read** the four identity answers (`project_name`, `project_slug`, `package_name`,
  `python_version`) from `.copier-answers.yml`.
- **Fail-closed guard:** if any identity answer is missing/empty → raise, refusing the
  update. No reconstruction/inference — convert silent empty-package-name corruption into a
  loud stop. (Expected unreachable in practice; defense-in-depth.)
- **Update:** `copier.run_update(..., data={**identity, "batteries": batteries,
  "alert_channels": channels, **migration_context(batteries)})` — identity now travels with
  every update.
- **Re-record** batteries + channels (as today) **and identity** into `.copier-answers.yml`.
- Regenerate the integrity manifest (guarded on an existing `.framework/integrity.lock`);
  run `task test`; return green/red.

### Callers

- `upgrade.py` → `_apply_update(vcs_ref=target_tag, batteries=recorded, channels=recorded)`
  — version moves; batteries/channels unchanged.
- `upskill --with` → `_apply_update(vcs_ref=recorded_version, batteries=recorded+new,
  channels=...)` — version pinned; batteries change. (Guards decision A: `_commit` unchanged.)
- `downskill` → **unchanged; not a caller.** `remove_battery` removes a battery by surgical
  two-render file-splicing and only touches `.copier-answers.yml` via `record_batteries` — it
  never runs `copier update`, so it neither strips identity nor needs the shared core. Left
  exactly as-is. The two update (re-render) paths are `upgrade` and `upskill --with`.

### Data flow — `framework upgrade`

```
check git-tracked + clean tree
  → resolve target tag (--to or latest)
  → read recorded version; if equal → no-op, exit 0
  → _apply_update(target):
        read identity + fail-closed guard
        → copier.run_update(data={identity, batteries, channels, migrations})
        → re-record identity + batteries + channels
        → regen integrity manifest
        → task test
  → print result + commit-after instruction
```

The key property: **identity preservation and the fail-closed guard live in `_apply_update`
alone**, so both re-render paths (`upgrade` and `upskill --with`) inherit them, and the
two-hop invariant test targets that single helper.

## Error handling, safety & edge cases

**Refusals (exit non-zero, nothing mutated):**

- *Not git-tracked* → existing `UpskillError` message (run `git init` + commit first).
- *Dirty working tree* (new) → "commit or stash your changes before upgrading — the upgrade
  needs a clean tree so its diff is reviewable and reversible." Detected via
  `git status --porcelain`.
- *Missing identity answers* → the fail-closed guard: "`.copier-answers.yml` is missing
  identity answers (`…`); refusing to upgrade rather than render an empty project. Restore
  them and retry."
- *`--to <tag>` not a real release / unreachable remote* → clear error naming the bad tag;
  no partial work.

**Non-refusal outcomes:**

- *Already at target* → no-op, exit 0, "already up to date (`vX.Y.Z`)."
- *Copier conflict markers* (incoming template change vs. a local edit) → update applied;
  tree has standard `<<<<<<<` markers; exit non-zero with "resolve the conflict markers,
  then run `task test`" — consistent with how battery changes already behave.
- *Merge clean but `task test` red* → exit non-zero, "upgrade applied but tests fail —
  review the diff, fix, and re-run tests before committing." Tree left as-is for inspection.

**Key safety property:** because we refuse *before* touching anything on a dirty tree, every
non-no-op upgrade starts from a clean commit. So even the "tests red" and "conflict markers"
outcomes are fully recoverable with `git restore .` / `git reset --hard` — the rollback
story holds in *every* failure branch, not just the happy path. There is no bespoke
framework "undo"; rollback is plain git, exactly as the published `upgrading.md` philosophy
states.

## Testing

TDD throughout. Three buckets.

### 1. The headline invariant — identity survives (the regression guarantee)

- **Two-hop sequential upgrade test:** render a project → `_apply_update` to an intermediate
  tag → `_apply_update` again to a later tag → assert `.copier-answers.yml` *still* contains
  all four identity answers **and** the rendered `src/<package_name>/` directory still exists
  with the right name. Reproduces the exact multi-hop scenario the manual dry-run caught;
  this is the test that makes the strip bug unreachable.
- **Single-upgrade identity test:** one `_apply_update` preserves identity + batteries +
  channels.
- **Fail-closed guard test:** strip an identity answer from `.copier-answers.yml`; assert
  `_apply_update` raises rather than rendering an empty package name.

### 2. Command-surface behavior

- *Clean-tree precondition:* dirty tree → refuses, mutates nothing; clean tree → proceeds.
- *No-op:* project already at target → exits 0, "already up to date," no changes.
- *`--to <tag>`:* targets the named tag; bad/unknown tag → clear error.
- *Bare `upskill` blocked:* no `--with` → the "requires at least one `--with`" error, exit
  non-zero.
- *`upskill --with` pins version:* adds the battery **without** moving the recorded framework
  version (asserts `_commit` unchanged) — guards decision A.
- *Success closing message:* asserts the commit-after instruction is the final output.

### 3. Conflict / red-test outcomes

Conflict markers, and a clean-merge-but-red-`task test`, each exit non-zero with the right
guidance and leave the tree reviewable.

### Test mechanics — throwaway git repos, deleted on teardown

The multi-hop test spins up **two throwaway git repos per test, both torn down**:

1. **A synthetic "framework source" repo** — a *minimal* Copier template (just enough: the
   four identity answers + `.copier-answers` wiring + a `src/{{package_name}}/` path + a
   battery toggle), committed and **tagged** at ≥2 synthetic versions (e.g. `v0.0.1`,
   `v0.0.2`) to upgrade *between*. Deliberately synthetic, not the real repo's release tags,
   so the invariant test is isolated from real-template churn — hermetic, fast, stable.
   `run_update`'s `vcs_ref` points at these throwaway tags.
2. **The rendered project repo** — rendered from that source, `git init` + committed (so it
   satisfies the git-tracked + clean-tree preconditions), then upgraded twice.

Both live under a pytest **`tmp_path`** dir (a fresh dir per test, auto-removed by pytest —
the convention the existing `test_upskill.py` git-repo tests already follow, so no hand-rolled
finalizer). Render-heavy cases route to `TMPDIR=/var/tmp` (the 16 GB `/tmp` tmpfs fills under
full renders, and `/var/tmp` also sidesteps stale `/tmp/pytest-of-chris/*` accumulation).

**No network remotes — ever.** Tests create only **local** git repos; nothing is created on
GitHub or any network remote (no auth dependency, no orphaned-repo leak):

- The `git push` in the success message is asserted as **printed text only** — the test
  checks the commit-after instruction is the final output; it never executes a push.
- `copier update`'s `vcs_ref` resolves against the synthetic source's **local path**, so the
  source needs no remote.
- If a test ever needs a push *target* (to exercise a flow end-to-end), it is a **local bare
  repo** created under the same `tmp_path` and wired via `git remote add … <local-path>`.

"Teardown" therefore means deleting **the remotes too, not just the working clones** — but
because every "remote" is a local bare repo inside `tmp_path`, the single `rmtree` finalizer
removes the synthetic source, the rendered project, **and** any bare push-target together.
Every test leaves no git repos (working or bare/remote) and no temp dirs behind.

## Docs

- `documentation/using/upgrading.md` loses its "Planned — not yet available" banner; the
  "Intended UX" / "Today: check, then upskill" sections become the *actual* `framework
  upgrade` reference (the page already describes this flow as the seed).
- The bare-`upskill` redirect and the `upgrade` vs `upskill --with` / `downskill` split are
  reflected in the CLI reference.

## Out of scope (v1)

- **Dedicated `--dry-run`.** The clean-tree precondition + review-before-commit flow *is* the
  dry run: after `framework upgrade`, `git diff` is the merge result with nothing else mixed
  in, and `git restore .` discards it. A true non-mutating preview is an easy additive
  follow-up if a real need (e.g. CI gating) appears.
- **A `--rollback` command / framework-managed snapshots.** Rollback is plain git; the
  clean-tree + commit-after model is what makes that safe. No bespoke undo.
- **Healing already-stripped projects.** Correct shared core + the two-hop invariant test
  make the stripped state unreachable; reconstruction would be dead code. (Operational note,
  not framework code: before the single existing consumer's next upgrade, eyeball its
  `.copier-answers.yml` once to confirm identity is present.)
- **Stepping through intermediate tags** within one upgrade — single 3-way jump only.
