---
name: eval-fixture-patch-truncation
description: "An eval fixture's change.patch with wrong hunk-header line counts makes `git apply` silently TRUNCATE the realized code → broken rendered file → agents correctly flag it (looks like a false positive but is a real fixture bug). Plan 21 added a STATIC guard (validate_patch_hunks + test_fixtures_are_wellformed) that catches it without rendering."
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: a21de392-d362-4517-b988-848d9a8e4434
---

A `tests/eval/fixtures/<agent>/<kind>/<case>/change.patch` whose **hunk-header line counts
are wrong** (`@@ -a,b +c,d @@` where d undercounts the added lines) makes `git apply`
**silently drop the trailing lines** on realize — the rendered file is genuinely truncated
(e.g. `data-integrity/good/atomic-bulk-insert` realized a function ending mid-`for`-loop
with no `return`, even though the raw patch text contained them). The capable paid agent
then *correctly* flags the broken code; the weaker free path scored it clean. It **looks
like a false positive but is a real fixture bug.**

**Plan 21 (FF 828aaed) built the static guard** `validate_patch_hunks(patch) -> list[str]`
in `evals.py` + a parametrized `test_fixtures_are_wellformed` over every
`tests/eval/fixtures/*/*/*/change.patch`. It checks each `@@ -a,b +c,d @@` body: `b` must ==
(context+removed), `d` == (context+added). No render needed — fast, permanent.

**Two gotchas learned building it (both verified against ground truth):**
1. **A naive body-counter false-positives on MULTI-FILE diffs:** the `diff --git`/`index`
   separators between files get miscounted as context lines of the *preceding* hunk (+2 per
   extra file). Fix: a hunk body line is one starting with `' '`,`'+'`,`'-'`,`'\'`, or empty;
   ANY other leading char (`@@`,`diff`,`index`,`new file mode`,`Binary`…) ENDS the body. Of
   16 first-pass "malformed", 10 were this false positive — trusting it blindly would have
   corrupted 10 good fixtures.
2. **Count-mismatch ≠ truncation.** Only a mismatch where the NEW count undercounts *added*
   lines truncates; an extra *context* line (off-by-N in both old&new) is tolerated by
   `git apply` (applies correctly). In the corpus only **3** fixtures genuinely truncated
   (accessibility/{bad,good}, data-integrity/bad/non-atomic-bulk-insert); 2 were harmless
   count-mismatches. Ground-truth check: render, apply with default `git apply` vs
   `git apply --recount`, compare trees — differ ⇒ truncates.

**Fix recipe (faithful, no-drift):** render the combo → `git apply --recount <patch>`
(applies the FULL body, ignoring wrong counts) → `git add -A` → `git diff --staged`
(includes NEW files; plain `git diff` DROPS untracked new files — that silently deleted a
seeded defect once) → overwrite `change.patch`; assert `validate_patch_hunks([])` and that it
realizes the identical tree to `--recount` of the original. Related:
[[eval-fixtures-coupled-to-template]], [[template-payload-tdd-loop]],
[[new-file-eval-fixtures-empty-diff]], [[reviewer-dev-prod-parity-gap]].
