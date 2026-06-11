# Secrets & environment parity

This is the canonical home for two related ideas the framework takes a firm stance on: how configuration stays consistent across every environment (the **parity chain**), and how secrets are **named and handled** so they're auditable and never committed. Your generated project also ships a `SECRETS.md` listing its specific secrets and values; everything you need to understand the model is here.

## The parity chain: same definitions, environment-specific values

A scaffolded project runs in a chain of environments — **dev → ci → staging → prod** — that share one set of *definitions* and differ only in *values*. Nothing is bespoke to production. The mechanisms that hold the line:

- **One config surface.** Every configuration value is read through `config/settings.py` (a `pydantic-settings` `Settings` class). There are no hardcoded values scattered through the code and no `os.getenv` calls in business logic — config has exactly one door.
- **One contract file.** `.env.example` is committed and documents *every* variable the app reads. Each environment supplies its own values against that same contract; staging and prod don't invent new variables, they fill in the documented ones with environment-appropriate values.
- **One image, layered overlays.** The same registry image runs in staging and prod (promoted, not rebuilt — see [Deploy](deploy.md)), and the same Compose overlays compose each environment (see [Services](services.md)). The environment is selected by `APP_ENVIRONMENT` (`dev | test | staging | prod`), which in turn drives derived behaviour — log level, the GraphQL IDE toggle, and so on — rather than separate code paths.

Because dev brings up the *same* observability stack and the *same* service topology as production, the behaviour you see locally is the behaviour you get deployed. The chain is "same definitions, different values" all the way through.

### How config is layered

A value's source depends on where it runs, but the *name* and the *reader* never change:

| Environment | Where values come from |
|---|---|
| **dev** | `.env` (gitignored), with the dev Compose overlay injecting in-network URLs (e.g. `APP_DATABASE_URL` pointing at the `postgres` service) |
| **test / ci** | environment variables / CI secrets; an ephemeral test database the tiers spin up |
| **staging / prod** | the target's environment + GitHub Environment secrets, injected at runtime; **never baked into the image** |

`settings.py` reads them all the same way, because every setting is `APP_`-prefixed and `pydantic-settings` resolves it from the process environment (falling back to `.env` locally).

## The `APP_` prefix

The `Settings` class is configured with `env_prefix="APP_"`, so a field named `database_url` is read from the environment variable `APP_DATABASE_URL`, `environment` from `APP_ENVIRONMENT`, and so on. This namespacing is deliberate: it keeps the application's configuration cleanly separated from the dozens of unrelated variables present in any shell or CI runner, and it makes "is this ours?" answerable at a glance. A representative slice:

| Setting field | Env var | Notes |
|---|---|---|
| `environment` | `APP_ENVIRONMENT` | `dev` / `test` / `staging` / `prod` — drives derived config |
| `database_url` | `APP_DATABASE_URL` | SQLAlchemy URL; in-network in Compose, localhost for host tooling |
| `slo_request_latency_p99_ms` | `APP_SLO_REQUEST_LATENCY_P99_MS` | SLO threshold feeding `/health` |
| `redis_url` | `APP_REDIS_URL` | present with the redis/workers battery |
| `mongo_url` | `APP_MONGO_URL` | present with the mongodb battery |
| `webhook_signing_secret` | `APP_WEBHOOK_SIGNING_SECRET` | present with the webhooks battery |

Battery-specific settings appear only when the battery is active, but they all follow the same `APP_`-prefixed rule.

## Secrets: never committed, injected at the edge

The framework's secrets posture is simple and enforced:

- **`.env.example` is committed; `.env` is not.** `.env` is gitignored. You copy the example, fill in real values locally, and that file never leaves your machine.
- **Deploy-time secrets live in the platform.** Staging and prod read secrets from the target's environment and from **GitHub Environment secrets**, injected at runtime. The image carries none of them.
- **Two guards stop accidents.** `gitleaks` runs in pre-commit *and* in CI (full-history scan) to catch a credential before it's committed; CI secrets are referenced as `${{ secrets.* }}` and never echoed into logs or env output.
- **Set CI/deploy secrets via the platform.** Use `gh secret set <NAME>` (or **Settings → Secrets and variables → Actions**) to register them; map each into the boring env var its consumer reads, in the workflow.

## The secret naming convention

This is where the framework is opinionated, and it's the canonical statement of the rule. Two principles:

### Scope-specific keys, never one shared key

The framework does **not** use a single catch-all `ANTHROPIC_API_KEY`. It uses **separate, scope-specific** environment variables so each consumer holds the narrowest credential it needs, and a leak or rotation is contained to one path. The review system is the worked example — two distinct keys for two distinct paths:

| Env var the code reads | Path | Source |
|---|---|---|
| `ANTHROPIC_EVAL_API_KEY` | the eval / scoring path (measuring the review agents) | `src/framework_cli/review/runner.py` |
| `ANTHROPIC_RUNTIME_API_KEY` | the runtime review path (agents reviewing your diff) | `src/framework_cli/review/runner.py` |

These are the real, verified names — defined as `EVAL_KEY_ENV = "ANTHROPIC_EVAL_API_KEY"` and `RUNTIME_KEY_ENV = "ANTHROPIC_RUNTIME_API_KEY"` in the review runner. The principle generalizes: give each scope (`runtime`, `eval`, read-only, read-write, …) its own variable rather than overloading one.

### Two-tier naming: a descriptive label vs. a boring consumed name

Every secret effectively has **two** names, serving two different audiences:

1. A **descriptive label** in the provider console (Anthropic, GitHub, …) — rich metadata for audit and rotation, encoding things like service, owner, environment, scope, and issue date. It identifies *who owns this and why it exists*; it is never the token value.
2. A **stable, boring name** where the secret is *consumed* — the environment variable the code reads (e.g. `ANTHROPIC_RUNTIME_API_KEY`), and, in GitHub Actions, a GH-legal secret name (uppercase, underscores) that the workflow maps into that env var. The consuming name stays stable as the underlying token rotates in place.

The framework's own CI demonstrates the mapping exactly:

| GitHub secret (the slot) | Mapped into (the consumed env var) | Path |
|---|---|---|
| `ANTHROPIC_FRAMEWORK_CI_RUNTIME` | `ANTHROPIC_RUNTIME_API_KEY` | runtime review |
| `ANTHROPIC_FRAMEWORK_CI_EVAL` | `ANTHROPIC_EVAL_API_KEY` | eval scoring |

A generated project follows the same shape: its review job maps the GitHub secret `ANTHROPIC_<PKG>_CI_RUNTIME` (where `<PKG>` is your uppercased package name) into the `ANTHROPIC_RUNTIME_API_KEY` env var the CLI reads. The console label says everything an auditor wants; the consumed name stays boring and stable so code and workflows never churn when a key rotates.

If a consumer's key is simply unset, the review agents **skip neutral** rather than fail — opt-in by design, so no spend happens without an explicit key in place.

## In short

Configuration has one door (`settings.py`, `APP_`-prefixed), one contract (`.env.example`), and one image promoted across environments — that's the parity chain. Secrets stay out of the repo (gitignored `.env`, gitleaks, GitHub Environment secrets) and follow a two-tier, scope-specific naming convention: a descriptive console label for humans, a boring stable env var for the code. See [Deploy](deploy.md) for where deploy-time secrets are injected and [Services](services.md) for which services consume which `APP_*` URLs.
