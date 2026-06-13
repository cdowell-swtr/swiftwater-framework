---
name: new-file-eval-fixtures-empty-diff
description: An eval fixture whose change.patch creates a NEW file realizes to an empty diff (git diff hides untracked files) — only agentic agents detect it.
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: a21de392-d362-4517-b988-848d9a8e4434
---

`realize_fixture`/`realize_cached` (src/framework_cli/review/evals.py) apply the fixture's
`change.patch` with `git apply` then capture `git diff` — which shows only **tracked**
changes. A patch that creates a **new file** leaves it untracked (`?? path`), so the returned
diff is **empty**.

Consequence: a new-file bad fixture carries zero signal in the diff. **Agentic** agents still
detect it (they explore the rendered tree with read/grep/glob, where the file physically
exists) — e.g. `observability-fe/bad/uninstrumented-view` (creates `frontend/src/Dashboard.tsx`)
calibrates 1.00 despite an empty diff. But a **bundle/diff** agent would always miss it.

So: when authoring a fixture for a bundle/diff-strategy agent, make the patch **modify an
existing tracked file**, not create a new one — or the agent gets nothing. (A free
`realize_cached` sweep over all fixtures surfaces these as empty-diff outliers; see the
Plan 18 pre-flight 52/53 sweep.) Discovered during the 2026-06-03 `/reviewers:tune` pre-flight.
Related: [[eval-fixtures-coupled-to-template]], [[template-payload-tdd-loop]].
