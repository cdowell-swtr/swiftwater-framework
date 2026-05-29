# Secrets — swiftwater-framework (this repo's own)

How **this framework repo's** CI secrets are named and where they live. We dogfood the very
convention we ship to generated projects (`src/framework_cli/template/SECRETS.md.jinja`): when
you generate keys for the framework's own reviewers, follow the schema below.

## The two-tier naming convention (recap)

Every secret has **two** names:

1. A **descriptive label** in the *provider console* (Anthropic / GitHub) — metadata for audit
   and rotation, never the token value:

   ```
   <service>_<package>_<owner>_<env>_<host>_<scope>_<created>_<rand>
   # e.g. anthropic_framework_chris_ci_gha_eval_20260529_3f8d0c1e
   ```

   `service` = provider · `package` = `framework` · `owner` = accountable person ·
   `env` = `ci` · `host` = `gha` · `scope` = `runtime | eval | ro | rw` ·
   `created` = `YYYYMMDD` · `rand` = 8 hex chars.

2. A **stable boring name** where it's consumed: a GH-legal secret (uppercase, underscores, no
   date/rand — the slot rotates in place) mapped into the env var the code reads.

## This repo's secrets

The framework has **two distinct LLM uses**, so — per the `scope` dimension — **two** keys
(separate audit / rotation / blast-radius). Both map to the `ANTHROPIC_API_KEY` env var in
their respective workflow.

| Purpose | Recommended console label | GitHub secret | Consumed as | Used by |
|---|---|---|---|---|
| Review-agent **eval** scoring (golden-fixture recall/precision) | `anthropic_framework_<owner>_ci_gha_eval_<YYYYMMDD>_<rand>` | `ANTHROPIC_FRAMEWORK_CI_EVAL` | `ANTHROPIC_API_KEY` | `.github/workflows/agent-evals.yml` |
| Review agents at **runtime** (the framework reviewing its own diffs — dogfooding) | `anthropic_framework_<owner>_ci_gha_runtime_<YYYYMMDD>_<rand>` | `ANTHROPIC_FRAMEWORK_CI_RUNTIME` | `ANTHROPIC_API_KEY` | `.github/workflows/review.yml` |
| Gitleaks license (full-history scan, if enabled) | n/a (vendor-issued) | `GITLEAKS_LICENSE` | `GITLEAKS_LICENSE` | the generated project's `ci.yml` |

Set them under **Settings → Secrets and variables → Actions**. Both Anthropic keys are
generated in the Anthropic console with the descriptive label above; the GitHub secret name is
the boring slot the workflow reads. Until each is set, its workflow **skips neutral** (never
red) — `agent-evals.yml` additionally uses `--require-key` so a *scheduled* eval fails loudly
rather than silently skipping.

> The eval key (`…_CI_EVAL`) and the runtime key (`…_CI_RUNTIME`) are deliberately **separate**
> — the convention's `scope` dimension. The runtime key mirrors what a generated project names
> its review key (`ANTHROPIC_<PKG>_CI_RUNTIME`); the eval key is framework-internal.
