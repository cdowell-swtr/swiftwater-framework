---
name: never-batch-dependent-pipeline-steps
description: The render→audit-prepare→Workflow→finalize chain is strictly sequential; never put dependent steps in one parallel tool block.
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f8907a45-ce5e-4aeb-8200-b311b671859b
---

In this repo's reviewer pipelines (`/reviewers:audit`, `/reviewers:gate`, `/reviewers:tune`, `/reviewers:template-audit`) the steps have hard data dependencies: `template-render` writes the render dir → `audit-prepare` reads it and writes the split-manifest + prep JSON → the `reviewers-audit` Workflow reads the split-manifest → `audit-finalize` reads the workflow results. Each step consumes the prior step's files.

**Why:** Twice in the 2026-05-31 template-audit session I batched these into a single tool block. Parallel calls run concurrently, so the downstream call read an empty/missing prep JSON (`json.decoder.JSONDecodeError: Expecting value: line 1 column 1`) and the whole block cascaded to cancellation. The system prompt already says to only parallelize calls with no dependencies — this is me failing to apply it under "make independent calls parallel" momentum.

**How to apply:** Run pipeline steps one tool block at a time, reading each result before issuing the next. Only fan out genuinely independent work (e.g. reading several unrelated files). When a `cd <render-dir>` is involved, also recall [[template-audit-uv-run-project-gotcha]]. Watch for silent agent drops per [[reviewers-tune-quota-throttling]] after each Workflow returns.
