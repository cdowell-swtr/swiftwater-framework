# Quality gates

A scaffolded project enforces quality automatically, in two places: a fast **pre-commit** gate that runs on every commit, and a stricter **CI** gate that runs on every push. The two share the same tools but apply different coverage thresholds — the commit gate stays fast, CI is thorough. Nothing about either is something you have to remember to run; the hooks and the pipeline run them for you.

## The pre-commit gate

The local gate is configured in `.pre-commit-config.yaml` and runs on every commit. Install it once:

```bash
task hooks            # uv run pre-commit install
task hooks:run        # run every hook against all files, on demand
```

The hooks are:

| Hook | What it checks |
|---|---|
| **ruff check** | Lint (with `--fix`) on changed Python |
| **ruff format** | Formatting on changed Python |
| **mypy** | Static type-check of `src` |
| **gitleaks** | Secret scanning — blocks committing credentials |
| **actionlint** | GitHub Actions workflow linting |
| **shellcheck** | Shell script linting |
| **migrations-reversible** | Migrations are reversible + backward-compatible (rolling-safe) — runs `scripts/check_migrations.py` against changed `migrations/versions/` files |
| **coverage-threshold** | Runs the unit + functional suites and enforces **≥ 70%** line coverage |
| standard hygiene hooks | end-of-file-fixer, trailing-whitespace, mixed-line-ending (→ LF), check-yaml, check-toml, check-merge-conflict |

That's the complete set — the gate is deliberately kept lean and fast. (There is no taplo, yamllint, hadolint, or prettier; the standard hooks and the type/lint/secret/coverage checks are the whole gate.)

## Coverage: 70% at commit, 85% in CI

Coverage runs through `scripts/coverage.sh <min_pct> <suite>...`, which runs each named test suite under its own coverage *context* and then enforces a combined line-coverage threshold. There are two thresholds:

- **70%** at commit time — unit + functional only, so the gate stays fast. This is the `coverage-threshold` pre-commit hook, and also `task test:cov`:

  ```bash
  task test:cov         # bash scripts/coverage.sh 70 unit functional
  ```

- **85%** in CI — unit + functional + **e2e**, the full picture, via `task test:cov:ci`:

  ```bash
  task test:cov:ci      # bash scripts/coverage.sh 85 unit functional e2e
  ```

The per-suite contexts let coverage tell a genuinely-uncovered line from one that's only covered at the integration level — so the 85% gate is a meaningful measure, not a number gamed by counting e2e walk-throughs as unit coverage.

## The CI pipeline

Pushing the branch triggers the authoritative GitHub Actions pipeline:

```bash
task push             # git push → triggers CI
```

CI runs lint and type-checking, then `scripts/coverage.sh 85 unit functional e2e` — the 85% combined gate — so the stricter coverage bar lives on the server side and can't be skipped locally. Before you push, you can run the same checks locally as a pre-flight:

```bash
task ci               # lint, the 85% gate, dependency audit, OpenAPI export
```

`task ci` chains `task lint` (ruff check, mypy on `src`, actionlint, shellcheck), `task test:cov:ci`, `task audit` (a `pip-audit` CVE scan of dependencies), and an OpenAPI schema export. It's the same work the server-side pipeline does, so a green `task ci` locally means a green pipeline.

## Why two thresholds

The split is intentional. The commit gate has to be fast enough that you run it on every commit without resentment, so it stops at the in-process unit + functional tiers and a 70% bar. CI can afford to be thorough — it pulls in the e2e tier and holds the line at 85%. You get quick feedback while you work and a real bar before anything merges, without either one getting in the other's way.
