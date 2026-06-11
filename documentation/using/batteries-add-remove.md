# Add/remove batteries

You do not have to decide every battery up front. `framework upskill` adds batteries to an existing project, and `framework downskill` removes one. Both operate on a project directory and run the project's own test suite afterward so you immediately know whether the change left the project green.

!!! note "This page is about *batteries*, not framework-version upgrades"
    Adding and removing batteries changes which feature sets a project contains. Pulling a project onto a newer *framework release* is a separate concern covered on [Upgrading](upgrading.md).

## Add a battery — `upskill`

```bash
framework upskill my-app --with websockets
```

`upskill` takes the project path as its argument and adds one or more batteries via repeated `--with` flags:

| Option | Purpose |
|---|---|
| `NAME` (argument) | Path to the project to upskill. |
| `--with` | Add a battery to the project. Repeatable. |
| `--alerts` | Reconfigure alert channels (comma-separated; **replaces** the existing set). |

Under the hood `upskill` re-renders the template over the project as a three-way merge, so the new battery's files are added non-destructively. Your edits are preserved; where an incoming change conflicts with a local edit, Copier leaves standard inline conflict markers for you to resolve. The new battery is added on top of the project's already-recorded set — existing batteries are kept — and the resolved set is re-recorded into `.copier-answers.yml`.

The project must be git-tracked (run `git init` and make a commit first); `upskill` refuses otherwise so the merge is reviewable and reversible through git. After the merge, `upskill` runs `task test`:

- If the tests pass, it reports success.
- If they fail (or Copier left conflict markers), it tells you to resolve the markers and fix the failures before committing, and exits non-zero.

`--alerts` lets you reconfigure where alerts go at the same time; the value you pass *replaces* the current channel set rather than merging into it. Omit it to leave the project's alert channels untouched.

## Remove a battery — `downskill`

```bash
framework downskill my-app webhooks
```

`downskill` takes two arguments — the project path and the battery to remove — plus an optional `--force`:

| Option | Purpose |
|---|---|
| `NAME` (argument) | Path to the project. |
| `BATTERY` (argument) | The battery to remove, e.g. `webhooks`. |
| `--force` | Remove even if the battery appears to still be in use. |

Removing a battery deletes the files that battery contributed while **preserving migrations** (so a removal never orphans your database history). If the battery still appears to be referenced in the project, `downskill` refuses unless you pass `--force`. As with `upskill`, it then runs `task test` and reports whether the project is still green; on failure it tells you to review the removal diff and fix any dangling references before committing.

## Why the test run matters

Both commands end by running the project's real test suite. That is deliberate: a battery change that leaves the project red is surfaced immediately, while your working tree still has the diff staged for review. Because the project is git-tracked, you can always inspect the change and roll it back with ordinary git if you are not happy with it.

See the full battery list and what each one adds on [New project & batteries](new-and-batteries.md).
