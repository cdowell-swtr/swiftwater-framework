---
name: flags-is-dual-use-gate-skips-advisory
description: framework_cli.review.evals.flags() is dual-use — for eval scoring it returns True on ANY finding when block_threshold is None (surfacing metric); for gate verdict that would block advisory agents in production. _finalize_gate now skips block_threshold=None agents.
scope: project
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0576f127-c936-4be4-8ea0-a38356f39443
---

`framework_cli.review.evals.flags(findings, spec)` returns `True` on ANY finding when `spec.block_threshold is None` — this is intentional for eval-scoring's advisory-mode metrics (advisory agents "surface" findings; recall/fp measures count surfacing). The function's own docstring says *"Advisory agent — never blocks in production"*, but the function-as-implemented does flag advisory agents because it's reused by both eval scoring and gate-verdict computation.

`_finalize_gate` in `src/framework_cli/cli.py` now explicitly skips advisory agents (`spec.block_threshold is None`) when computing the FAIL/PASS verdict — so advisory findings still surface in `audit-report.md` and gain visibility, but they no longer cause the gate to block. The three advisory agents in the registry are `documentation`, `dependency`, `usability`.

**Why:** During the audit-semantics branch we burned 3× `--no-verify` commits + 5 gate iterations chasing what looked like "documentation@info block_threshold is too tight." My first diagnosis was wrong — documentation's threshold was already `None`. The actual bug was `_finalize_gate` reusing `flags()` for verdict without honoring the docstring's "advisory never blocks" rule. Spent significant subagent quota before finding the root cause.

**How to apply:**
1. If you see a gate FAIL on findings from `documentation`/`dependency`/`usability`, the fix is NOT to lower their threshold (it's already None) — verify `_finalize_gate` is honoring the `spec.block_threshold is None` skip.
2. If adding a new advisory agent (block_threshold=None), it WILL surface findings into reports but WON'T block production gate — by design.
3. Regression guard: `test_gate_finalize_advisory_agent_findings_dont_block_gate` in `tests/test_cli.py` asserts advisory findings → PASS verdict.
4. `flags()` itself stays as-is — eval scoring still needs the "any finding" semantic for advisory agents.
