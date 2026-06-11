# Install the framework CLI

The `framework` CLI is the entry point to everything: it scaffolds new projects, adds and removes batteries, and keeps existing projects in sync with newer framework releases. This page covers prerequisites and installation, and nothing here requires the framework's own repository checked out.

## Prerequisites

- **Python 3.12 or newer.** The CLI targets `>=3.12`. The projects it generates target Python 3.12 by default (you can override this per-project — see [New project & batteries](new-and-batteries.md)).
- **[uv](https://docs.astral.sh/uv/)** — the package manager used to install the CLI and to run generated projects. Install it first via the instructions on the uv site.
- **Git** — the CLI installs from a git source, and several commands (`upskill`, `integrity`, `restore`) operate on a git-tracked project.

The generated *projects* additionally expect Docker (with Compose) and [go-task](https://taskfile.dev/) at runtime, but you do not need those just to install the CLI.

## Install

Install the CLI as a [uv tool](https://docs.astral.sh/uv/concepts/tools/) directly from the GitHub repository:

```bash
uv tool install git+https://github.com/cdowell-swtr/swiftwater-framework
```

This puts a `framework` executable on your PATH, isolated in its own environment, so it does not interfere with any project's dependencies.

### Pin to a specific release

To install a specific tagged release instead of the default branch, append the tag:

```bash
uv tool install git+https://github.com/cdowell-swtr/swiftwater-framework@v0.1.9
```

The version you install is recorded into every project you scaffold (in its `.copier-answers.yml`), which is what later lets a project be brought forward onto a newer framework release.

## Verify

```bash
framework --help
```

You should see the top-level help, which lists the available commands (`new`, `upskill`, `downskill`, `check`, `integrity`, `restore`, and others). Running `framework` with no arguments prints the same help.

## Upgrading the CLI itself

To pull the CLI onto a newer release later, re-run the install command with the new tag (uv replaces the existing tool), or use uv's upgrade flow:

```bash
uv tool upgrade framework-cli
```

`framework check` will tell you whether a newer release exists and print the exact install command to run — see [The CLI](the-cli.md) and [Upgrading](upgrading.md).
