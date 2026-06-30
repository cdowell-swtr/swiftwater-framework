# Quickstart

This page walks through the shortest real path: install the `framework` CLI, scaffold a project, and see it running. All commands are complete — you don't need to look anything up elsewhere.

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker (with Compose), Git.

---

## 1. Install the framework CLI

The `framework` CLI is installed as a `uv` tool from the GitHub repository:

```bash
uv tool install git+https://github.com/cdowell-swtr/swiftwater-framework
```

Verify the install:

```bash
framework --help
```

You should see the `framework` help output listing available commands (`new`, `upskill`, `integrity`, etc.).

---

## 2. Scaffold a new project

```bash
framework new "My App"
```

The wizard runs interactively. It will ask:

- **Batteries** — which optional feature sets to include (workers, webhooks, websockets, graphql, react, etc.). You can press Enter to skip all and add them later.
- **Alert channels** — where to send SLO breach alerts (webhook, Slack, email, PagerDuty). Defaults to a generic webhook; you can configure real channels now or leave the placeholder.

You can also pass batteries directly without the interactive prompt:

```bash
framework new "My App" --with workers --with webhooks
```

When the command completes, a directory named `my-app` exists in your current directory. It contains a fully-wired project: `pyproject.toml`, `Taskfile.yml`, Docker Compose files for every environment, a GitHub Actions CI/CD pipeline, pre-commit configuration, and the complete test suite layout.

---

## 3. Enter the project, set up git, and install dependencies

`framework new` renders files but does not initialise a git repository, so do that first (the later `task push` step needs it):

```bash
cd my-app
git init
git add -A          # includes the generated uv.lock
git commit -m "Initial scaffold from swiftwater-framework"
uv sync
```

---

## 4. Start the local stack

```bash
task dev
```

On the first run, the pre-flight check installs `mkcert` if it is absent, generates local HTTPS certificates for `localhost` and `*.localhost`, and installs them into your system trust store. This takes about 30 seconds the first time.

After pre-flight, Docker Compose brings up the full local stack: all application services, the observability stack (Prometheus, Grafana, Loki, Alertmanager), and Traefik as a local HTTPS reverse proxy. On subsequent runs this is immediate.

Once up, the application is available at `https://localhost`. The Grafana dashboard is at `https://grafana.localhost`.

If you are on a resource-constrained machine and want to skip the observability stack:

```bash
task dev:lite
```

This starts the application and its database (plus any datastores your selected batteries add, such as Redis).

---

## 5. Run the test suite

```bash
task test
```

This runs the full test suite (unit, functional, and end-to-end) in-process via `pytest`. All tests pass on a freshly generated project.

To run only unit tests without Docker:

```bash
task test:unit
```

---

## 6. Run the local CI pre-flight

Before pushing to GitHub, run the local CI suite to catch issues early:

```bash
task ci
```

This runs lint, type checks, unit + functional + E2E tests with coverage, pip-audit, and exports the OpenAPI schema. This is a fast pre-flight — not a substitute for the Actions run, but it makes the Actions run more likely to pass on the first attempt.

---

## 7. Push to GitHub

```bash
task push
```

This runs `git push` and triggers the authoritative GitHub Actions pipeline. The pipeline runs the full test matrix, the render matrix (template validation), and the AI review agents on your PR.

---

## Key commands

| Command | What it does |
|---|---|
| `task dev` | Start the full local stack (app + observability + HTTPS) |
| `task dev:lite` | Start app services only (no observability) |
| `task dev:reset` | Tear down and rebuild with fresh seed data |
| `task test` | Full test suite in isolated test environment |
| `task test:unit` | Unit tests only |
| `task ci` | Full local CI pre-flight |
| `task push` | Push to GitHub and trigger Actions |
| `task lint` | Run all linters (ruff, mypy, actionlint, shellcheck) |
| `task db:migrate` | Run pending database migrations |
| `task integrity` | Verify framework scaffolding is intact |

---

## Adding a battery later

If you want to add a feature set after the initial scaffold:

```bash
framework upskill my-app --with websockets
```

This merges the battery's files into the existing project non-destructively. Conflict markers appear only where a generated file was edited in ways that conflict with the incoming changes.

---

## Checking for framework updates

```bash
framework upgrade my-app --dry-run
```

This reports whether `my-app`'s pinned version is behind the latest release, without applying anything. To apply it, run `framework upgrade my-app` — it re-execs the target release automatically (self-dispatch), moving the CLI and the template together in one step.
