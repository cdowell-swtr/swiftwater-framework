# Why this framework

## The problem

Building a Python application is easy. Building one that is maintainable, testable, observable, and deployable — consistently, from day one — is hard. Most projects start without tests, accumulate technical debt early, and reach production without meaningful observability or a real staging environment. The patterns that prevent these problems are well-known, but the activation energy to set them all up from scratch is high enough that they rarely get applied.

The framework exists to eliminate that activation energy. A builder runs one command and receives a project that already has TDD enforced, linting wired, a CI pipeline configured, a full observability stack, and an environment model that matches production — before they write their first line of application logic.

The goal is that any builder, regardless of experience level, can produce solid, observable, testable, deployable Python applications from their first line of code to their ten-millionth.

## The approach: opinionated scaffold

The framework is a [Copier](https://copier.readthedocs.io/) template rendered by the `framework` CLI. Running `framework new "My App"` produces a fully-wired project directory: Docker Compose files, GitHub Actions workflows, `pyproject.toml`, pre-commit configuration, a Taskfile, and all the application skeleton. Nothing is placeholder — the generated project runs, tests pass, and CI is green from the first commit.

This is deliberately opinionated. The framework makes structural decisions so the builder doesn't have to: test layout, coverage strategy, observability stack, environment model, secrets handling. The builder's job is to configure their project's specifics and then write application logic. The principles behind these decisions are laid out in [Design principles](../working/design-principles.md).

The framework is not a library to import. It generates a project that owns its own code. The builder can read every file, understand every decision, and modify anything. If a framework update ships an improved convention, `framework upgrade` merges it non-destructively — or the builder can diverge intentionally and record the drift.

## Antipatterns it prevents

The framework's template and CI agents are designed around a specific list of failure modes that plague projects built without scaffolding:

- Tests written after the fact, or not at all — the TDD contract is enforced before code is considered done
- "Works on my machine" drift — dev, CI, staging, and prod all run the same Docker Compose definitions
- Secrets baked into code — the wizard collects secrets once, writes them to `.env` (gitignored), and emits the exact `gh secret set` commands; committed files never contain secret values
- No CI pipeline — the generated project ships a complete GitHub Actions workflow on day one
- No staging environment — staging is part of the generated CD pipeline, not an afterthought
- No AI-assisted review — a suite of domain-specific AI review agents gate every PR, each covering one concern (security, data integrity, observability, test quality, and more)
- No structured observability — a full Prometheus + Grafana + Loki + Tempo stack is included and runs identically in every environment

## Batteries

Beyond the base application scaffold, the framework provides opt-in feature sets called _batteries_. Each battery adds a coherent capability: async task workers, WebSocket routes, a React frontend, contract testing, additional database paradigms, and so on. Batteries are activated at scaffold time (`framework new my-app --with workers --with react`) and can be added later (`framework upskill my-app --with webhooks`).

Each battery is integrated end-to-end: it adds its services to the Compose stack, its tests to the test suite, its observability surface to Prometheus and Grafana, and activates any additional CI review agents specific to its domain.

## Dogfooding

The framework holds itself to the same standard it imposes on generated projects. The framework repository has its own TDD, linting, and CI pipeline, and the template is validated by rendering it and exercising the generated output — not just inspecting template source. A render matrix runs on every PR across a representative set of battery combinations, because template conditionals interact. The template is never released unless rendered projects are green.

The review agents that run on generated projects also run on the framework itself. The framework cannot credibly enforce a discipline it exempts itself from.
