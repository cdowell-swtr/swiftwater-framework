# The CLI

The `framework` CLI is a thin shell over [Copier](https://copier.readthedocs.io/). Copier is the template engine that does the actual rendering and merging; the CLI's job is to give you a small, task-shaped set of commands over it — deriving names, resolving batteries, recording the framework version and battery/alert sets, and running the project's tests after a change. Logic stays minimal and focused so the CLI stays a predictable front-door rather than a place where surprising behavior accumulates.

## What the commands are for

The commands fall into a few groups:

- **Scaffold a project** — `new` renders a fresh project from the template. Covered in [New project & batteries](new-and-batteries.md).
- **Change a project's batteries** — `upskill` adds batteries (and can reconfigure alert channels); `downskill` removes a battery. Covered in [Add/remove batteries](batteries-add-remove.md).
- **Stay current with the framework** — `check` reports whether a newer framework release exists and prints the command to upgrade. Bringing a project forward onto a newer release is covered in [Upgrading](upgrading.md).
- **Keep scaffolding intact** — `integrity` verifies that the framework-managed files in a project have not been moved, deleted, or altered, and `restore` re-fetches a canonical framework file, discarding local edits to it.

There are additional commands used by the framework's own development and CI (template rendering, the review/audit gate, eval scoring, and matrix dogfooding) — you generally will not run those by hand when *using* the framework.

## The full command list

Every command, argument, option, and default is generated directly from the CLI source on the [CLI reference](../reference/cli.md) page. When in doubt, that page — or `framework --help` (and `framework <command> --help`) — is authoritative.
