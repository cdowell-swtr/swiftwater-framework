# Upgrading to a newer framework release

The framework itself evolves: new releases improve the template — CI workflows, Compose
files, observability config, review agents, and scaffolded code patterns. **Upgrading** pulls
an existing project *forward* onto a newer framework release, distinct from
[adding or removing batteries](batteries-add-remove.md) (which change a project's feature set
without changing the framework version).

## The command

```bash
framework check                          # is there a newer release? prints the upgrade command
framework upgrade my-app                 # move my-app onto the latest release
framework upgrade my-app --to v0.3.0    # …or onto a specific release
```

`framework upgrade` requires a **clean git working tree** (commit or stash first) — that
is what makes the upgrade one reviewable, reversible diff. It re-renders the template at
the target release via Copier's three-way merge (your app code is preserved; conflicts
become standard inline markers), regenerates the integrity manifest, and runs `task test`.
On success it prints the result line and, as the last line, the commit-and-push instruction:

```
Upgraded to v0.3.0; tests pass. Review the diff, then snapshot it:
  git add -A && git commit -m "chore: upgrade framework to v0.3.0" && git push
```

On conflict markers or failing tests the command exits non-zero and tells you to resolve
markers and fix failures before committing.

## How it works

Mechanically, `framework upgrade` calls Copier's `copier update`: a three-way merge that
re-renders the template at the new release tag against the project, applying the delta
non-destructively. Your application code is preserved; only framework-owned scaffolding is
updated. Where an incoming template change conflicts with a local edit, Copier leaves
standard inline conflict markers for you to resolve.

Every project records the framework version it was scaffolded at, in its `.copier-answers.yml`.
That recorded version is the anchor: the framework knows where the project started, so it
computes and applies only the delta between the project's version and the target release.
After the merge, `framework upgrade` regenerates the integrity manifest so
`framework integrity` reflects the new version.

## Rolling back

**Rollback is your project's own git history** — there is no special framework "undo."

`framework upgrade` is designed with this in mind:

- It **refuses** to run on a dirty tree. Your pre-upgrade state is therefore
  always in a clean commit.
- On success it tells you to **commit and push immediately**, giving you a clean
  after-upgrade snapshot.

With both snapshots in place, rolling back is a standard git operation:

```bash
git revert HEAD        # or
git reset --hard HEAD~ # if the upgrade commit is the tip and you haven't pushed
```

## Command split: upgrade vs. upskill

| Command | What it changes | Framework version |
|---|---|---|
| `framework upgrade <project>` | Re-renders the template at the new release | Moves to the new version |
| `framework upskill <project> --with <battery>` | Adds a battery | **Pins** the recorded version (no bump) |
| `framework downskill <project> <battery>` | Removes a battery | **Pins** the recorded version (no bump) |

`framework upskill --with` and `framework downskill` re-render at the project's *recorded*
framework version — they change the battery set without bumping the framework release.
`framework upgrade` is the one path that moves the version.

Bare `framework upskill` (no `--with` or `--alerts`) is rejected:

```
framework upskill adds batteries — pass at least one `--with` <battery>.
To move the framework version, use `framework upgrade <project>`.
```

## Checking for updates

`framework check` compares the installed CLI version against the latest published release
and reports what to do:

```
framework check: installed v0.2.2, latest v0.3.0. Upgrade the CLI with
`uv tool install git+https://github.com/cdowell-swtr/swiftwater-framework@v0.3.0`,
then run `framework upgrade <project>`.
```

Update the CLI first (so it ships the new template), then upgrade your projects.
