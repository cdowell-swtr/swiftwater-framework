# Upgrading to a newer framework release

!!! warning "Planned — not yet available"
    A dedicated `framework upgrade` command does **not** exist yet. This page describes the *intended* upgrade experience. Do not try to run `framework upgrade` — it is not a real command today. The verified, available path is described in the [Today](#today-check-then-upskill) section at the bottom.

The framework itself evolves: new releases improve the template — CI workflows, Compose files, observability config, review agents, and scaffolded code patterns. "Upgrading" means pulling an existing project *forward* onto a newer framework release, distinct from [adding or removing batteries](batteries-add-remove.md) (which changes a project's feature set without changing the framework version).

## How upgrades work

Every project records the framework version it was scaffolded at, in its `.copier-answers.yml`. That recorded version is the anchor for an upgrade: the framework knows where the project started, so it can compute and apply only the template changes between the project's version and the target release.

Mechanically this is a Copier `copier update`: a three-way merge that re-renders the template at the new release tag against the project, applying the delta non-destructively. Your application code is preserved; only framework-owned scaffolding is updated, and where an incoming template change conflicts with a local edit, Copier leaves standard inline conflict markers for you to resolve.

## Intended UX

The planned `framework upgrade` flow is a thin, explicit front-door over that mechanism:

1. **Check.** `framework check` compares the project's recorded version against the latest release and reports whether a newer one exists (the intent is to surface a changelog with breaking changes clearly marked).
2. **Re-render.** The upgrade re-renders the template at the new release tag via `copier update`, merging the delta into the project.
3. **Verify.** The project's own test suite (`task test`) runs after the merge; the upgrade is only considered successful if the project is green afterward.
4. **Resolve, if needed.** Any conflict markers left by the merge are resolved by hand, exactly as with a battery change.

### Rolling back

Because an upgrade is just a re-render into a git-tracked working tree, **rollback is your project's own git history** — there is no special framework "undo." Commit (or stash) before upgrading, review the merge diff, and if you are not happy with it, discard the changes with ordinary git (`git restore` / `git reset` / checking out the prior commit). Keeping the pre-upgrade state in a commit is what makes the upgrade safe to attempt.

## Today: check, then upskill

Until the dedicated command lands, the same outcome is available through commands that **do** exist:

```bash
# 1. Is there a newer framework release?
framework check

# 2. If the CLI is behind, upgrade the CLI itself (check prints the exact command):
uv tool install git+https://github.com/cdowell-swtr/swiftwater-framework@<latest-tag>

# 3. Bring the project forward onto the newer framework version:
framework upskill my-app
```

`framework upskill` already wraps `copier update`: run with **no** `--with` flag it re-renders the project at the latest framework release without changing its battery set, then runs `task test`. (When you *do* pass `--with`, it adds those batteries during the same re-render — see [Add/remove batteries](batteries-add-remove.md).) `framework check` prints the exact `uv tool install` command for the latest tag and reminds you to follow it with `framework upskill <project>`.

The project must be git-tracked for `upskill` to run, which is also what gives you the rollback path described above.
