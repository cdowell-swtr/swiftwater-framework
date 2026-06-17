# The review system

This page explains what the review system *is* and *why* it exists. It is intentionally conceptual: the detailed per-agent reference — which agents exist, what each one checks, and the thresholds they apply — is in [Review agents](../reference/review-agents.md). Here we cover the architecture and the reasoning behind it.

## What it is

The review system is a layer of **domain-specific AI review agents** that read a change and report findings. Each agent owns exactly one concern — security, data integrity, observability, test quality, architecture, and so on — and reviews a diff only through that lens. They run at two points:

- **At commit**, locally, as a gate before a change lands.
- **In CI**, on every push and pull request, as Check Runs alongside the deterministic gates.

Findings are aggregated into a single pass/fail picture so you see the whole review in one place rather than hunting through individual checks. Some agents **block** a merge on serious findings; others are **advisory** and surface findings without blocking. This is the framework's answer to one of the antipatterns it sets out to prevent: *no AI-assisted review with separation of concerns.* A single generalist reviewer blurs concerns and misses things; a panel of narrow specialists, each with a sharp remit, does not.

## Why it exists

Deterministic gates — `ruff`, `mypy`, `gitleaks`, the coverage threshold — catch a large class of issues cheaply and run in the inner loop. But they can't reason about *intent*: whether a new code path is observable, whether a test actually asserts behaviour or just exercises lines, whether a data model change is consistent across stores, whether a change leaks PII into logs. That reasoning is what the review agents add. Deep, token-intensive judgement happens here, deliberately separated from the fast pre-commit layer, so the cheap checks stay fast and the expensive ones run where they belong.

## How it's built: one engine, two backends

The architecture's defining property is that there is **one review engine** with a **swappable model backend**. The agents, the prompts, the context assembly, the aggregation, and the gate logic are identical no matter how the model is called. Only the thing that turns a prompt into a model response is swapped, behind a single `messages.create`-shaped seam:

- A **paid API backend** that calls the Anthropic API directly (used in CI, where an API key is configured).
- A **free subagent backend** that shells out to the local headless `claude` CLI (`claude -p`).

Both backends adapt their output into the same response shape, so the review loops are byte-identical across paid and free. This was the explicit goal of the work that introduced the seam (Plan 20): **dev equals prod by construction.** The reviewer you run locally for free is not a different, weaker pipeline that happens to resemble the CI one — it is the same engine with a different way of reaching a model. Any divergence in *outcome* is now purely a matter of model judgement and calibration, not of two pipelines drifting apart.

The system is also **opt-in and cost-safe**: if the key a paid path needs is simply unset, the agents **skip neutral** rather than fail, so no spend happens without an explicit key in place. Consistent with the framework's secrets posture, the eval and runtime paths read **separate, scope-specific** keys (`ANTHROPIC_EVAL_API_KEY` and `ANTHROPIC_RUNTIME_API_KEY`) rather than one shared credential — see [Secrets & environment parity](secrets-and-env-parity.md).

## How they're proven: the eval harness

The agents are themselves software, and software is tested. Because LLM output is non-deterministic, you can't assert exact-match output — so each agent is exercised by an **eval harness** against golden fixtures: known-bad diffs it must flag (true positives) and known-good diffs it must pass without false alarms. The harness **scores** the agents against a pass threshold rather than a literal string, and the scores are how the prompts get tuned over time. This is the framework dogfooding its own discipline: the reviewers that gate your changes are held to a measured quality bar of their own, and the same agents that review generated projects also review the framework itself.

## In short

The review system is a panel of single-concern AI review agents that gate changes at commit and in CI, backed by one engine that can drive a paid API or a free local subagent interchangeably — so the free local review and the paid CI review are the *same* review. An eval harness scores the agents against golden fixtures so their quality is measured, not assumed. It exists to add the intent-level judgement the deterministic gates can't, with separation of concerns built in. See [Review agents](../reference/review-agents.md) for the full per-agent reference.
