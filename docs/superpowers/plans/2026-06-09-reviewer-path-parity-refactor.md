# Plan 20 — Reviewer path parity refactor (STUB — pre-brainstorm)

**Date:** 2026-06-09
**Status:** ⬜ Not started — stub capturing the rationale. Brainstorm + spec before implementing.

> This is a **rationale-bearing stub**, written deliberately before the context that
> produced it is cleared. It records *why* this plan exists. The actual design comes
> from a fresh brainstorm (see "Open questions").

## The problem this fixes

The review system has **two separate code paths** that are supposed to be equivalent
but are not:

- **Paid path** (what builders actually run): `framework review` / `framework eval` →
  `run_agent` / `run_agent_agentic` (`src/framework_cli/review/runner.py`,
  `agentic.py`) → real Anthropic API client → **raw model text** → `parse_findings`.
- **Free path** (a dev-time cost cheat we use via `/reviewers:tune`, `/reviewers:audit`,
  `/reviewers:gate`): a **different dispatch** — CC subagents driven by the Workflow
  tool's `agent()` with a **forced StructuredOutput schema** (always-well-formed JSON),
  not `run_agent` with a swapped client.

They run the **same models**, so capability is not the difference. The difference is
**scaffolding**, and it runs the wrong way: our **dev path is more constrained/robust
than production**, so it *hides* the bugs builders hit. We spent a week (Plan 18 paid
anchor) calibrating against the free path and it **did not predict the paid path at all**.

## Evidence (from the Plan 18 paid-anchor attempt, 2026-06-09)

1. **The free path's forced-JSON guard masked real paid-path crashes.** The paid path
   crashed twice on malformed model output the free path can never produce:
   - trailing prose after the JSON array → `_extract_array` "Extra data" (fixed `0527d07`);
   - a code snippet in the `line` field → `int(...)` `ValueError` (fixed `bdfb647`).
   Both are on the `framework review` builder path. The free path never exercised them.
2. **Rate-limit reality only exists on the paid path** → the loud-abort/backoff work
   (`88eb3cd`) — irrelevant to free subagents.
3. **A malformed-patch eval fixture realized into truncated code** (`data-integrity`'s
   `atomic-bulk-insert` good fixture: wrong hunk-header line counts → `git apply`
   silently dropped the last lines → broken function). The paid agent correctly flagged
   it; the free path scored it clean. The structural `test_fixtures_are_wellformed`
   gate does not catch this (it checks the patch is non-empty, not that it *applies
   completely*). → see Plan 21 / a well-formedness guard.
4. **Net divergence:** the full paid run (`27222994607`) had **8/20 agents fail** their
   free-path-calibrated thresholds — dominated by good-fixture over-flagging — which the
   free path had reported as 1.00/0.00.

See `[[paid-path-operative-for-builders]]`, `[[reviewer-dev-prod-parity-gap]]`.

## The goal

**One review code path; the only swappable piece is the model-call backend.** A single
`run_agent` / `run_agent_agentic` exercised by both dev and prod, where dev swaps in a
**subagent-backed client** implementing the same `messages.create` interface and prod
uses the Anthropic client. Then:

- Dev testing (free) faithfully predicts production (paid) **by construction**.
- Every fix — parse robustness, retries, prompt changes, hallucination handling — lands
  **once** and benefits both.
- The prompt/threshold tuning (Plan 21) can then be done **locally and cheaply** against a
  representative path, with paid confirmation only at the very end.

This must land **before** Plan 21 — there is no point tuning prompts against a path that
doesn't match production.

## Decision still open (brainstorm)

- **Which robustness do BOTH paths get?** Builders run the paid path, so arguably the
  *robust* free-path behavior (structured/tool-forced output → well-formed JSON) should be
  on the paid path too, with the `parse_findings` hardening as a backstop rather than the
  front line. The point is the two paths **match**, not which guardrail wins.
- **Backend abstraction shape** — what's the minimal `messages.create`-compatible seam,
  and how does the subagent backend satisfy it (it must produce the same raw model text
  the paid client returns, or both must use the same structured-output contract).
- **Fate of the current free-path dispatch** (`/reviewers:*` Workflow scripts,
  split-manifest) — re-target onto the unified path vs. retire.
- Keep the Plan 18 hardening (`0527d07`/`bdfb647`/`88eb3cd`) — it belongs on the unified
  path; verify it isn't a band-aid the new architecture obviates.

## Decomposition (per the user: "one refactor on the architecture, then tuning")

- **Plan 20 (this):** the parity refactor — unify the path, swappable backend.
- **Plan 21:** prompt + threshold re-tuning + fixture quality, on the now-representative path.
