---
name: contracts-agent-pact-v4-false-positive
description: "The contracts review agent misreads pact-v4's body-encoding wrapper and false-positives that the example pact mismatches the provider — discount it; the provider-pact test is the ground truth."
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: 49f13a1d-7e1e-4c24-8e52-b50a128128c4
---

The `contracts` review agent doesn't understand **pact specification v4 body encoding** and reliably false-positives on the shipped example pact (`pacts/examplewebapp-app.json`). In the 2026-05-31 template audit it raised 3 findings (2× high "incompatible response shape" + 1 info "pact not regenerated") claiming the pact's response body `{"content": [...], "contentType": "application/json", "encoded": false}` is incompatible with the provider's `GET /items` returning a bare `list[ItemRead]`.

**That is wrong.** `{content, contentType, encoded}` is pact-v4's **body-encoding wrapper** — not a literal expected response shape. The interaction's `matchingRules` are anchored at `$[*].id` / `$[*].name` with `match: type`, i.e. the body is matched as an **array**, and a `type` matcher matches **N** elements from a single example — so seeding two provider items still verifies against the one-element example. Ground truth: `tests/contract/test_provider_pact.py` runs the real app over testcontainers Postgres and verifies this exact pact **green** in the acceptance tier.

**How to apply:** when triaging `contracts`-agent output about the example pact's response shape / "regenerate the pact", discount it unless the provider-pact verification test actually fails. **This is a concrete PROMPT-level defect** (the agent doesn't understand pact-v4 body encoding) — i.e. a worked example for **Plan 21** (reviewer prompt tuning): the real fix is teaching the agent pact-v4 in its **prompt** (`agents/contracts.md`), not a threshold or a fixture band-aid. See [[reviewer-tuning-is-prompts-not-thresholds]]. Cross-ref [[check-agent-prompt-fit-before-adding-to-target]] (the `contracts` agent = Pact, not generic API contracts).
