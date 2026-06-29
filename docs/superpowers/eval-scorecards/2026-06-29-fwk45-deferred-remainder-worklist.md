# FWK45 deferred-remainder worklist (S1/exp-2) — reconciled 2026-06-29

**Sub-PLAN FWK123.** The authoritative hand-apply worklist for the deferred remainder of
the FWK43 reviewer-tuning v2 sweep, reconciled against **what FWK43 (`0055bc9`) actually
shipped** (the commit diff is ground truth — *not* `apply-preview.notes.txt`, which is the
pre-re-anchoring preview that lists all 22 survivors as "not renderable"). Source of the
proposed edits: the frozen `main/.framework/reviewer-audit-v2/changelist-full.json` (49 KB,
2026-06-19; **provenance-frozen** — no fresh `reviewer-audit` run in this experiment).

## Loud finding — the deferred domain count is **8, not 6**

The v2 scorecard (`2026-06-20-reviewer-tuning-v2.md`) and the FWK43 commit message both state
the deferred remainder is "**6** paraphrased-`before` domain edits." The arithmetic is
unambiguous: **19 prompt-edit survivors − 11 applied hunks = 8 deferred.** All 8 are genuinely
absent from the current files (each verified against the FWK43 diff + current HEAD). The
scorecard **undercounts by 2** — the two un-counted extras are the `accessibility` scope
cross-reference list and one of the `coverage-gap`/`accessibility` rewords (both low-stakes
"hardening" edits the author plausibly treated as non-essential). Recorded, not absorbed.

Survivor accounting: 22 vetted (`verdict.refuted == false`) = **18 `domain_prompt` + 1 `rubric`
+ 3 fixtures**. FWK43 shipped 11 of the 19 prompt edits. `architecture.md` and
`documentation.md` were **never touched by FWK43** → 3 of the 8 deferred; the other 5 are the
unapplied tail of files FWK43 *did* touch (accessibility ×2, api-design ×1, coverage-gap ×1,
dependency ×1).

## The 3 fixture rewrites (→ FWK124 / FWK125 / FWK126)

| Sub-PLAN | Fixture | Action | Eval-gate |
|---|---|---|---|
| FWK124 | `application-logic/bad/falsy-none-check` (`src/demo/routes/items.py`) | Replace the inert `if not item:` seed (identical to `is None` on an ORM row) with a correctness bug that manifests today; keep a clean minimal pair vs the `is None` good fixture | `application-logic` |
| FWK125 | `data-integrity/bad/non-atomic-bulk-insert` | Reduce to a single-finding diff vs its good pair (drop the manufactured strip/length/dedup/cap deltas) so the only catchable defect is the in-loop-commit atomicity bug | `data-integrity` |
| FWK126 | `compliance/good/pii-in-logs-not-compliance` (**new**) | Seed PII-in-logs as a modification to the already-tracked `items.py` (a new-file diff realizes empty — [[new-file-eval-fixtures-empty-diff]]); expect `compliance` to stay clean (PII-in-logs is privacy's lane) | `compliance` |

## The 8 deferred domain/prompt edits (→ FWK127)

Each verified absent from the current file; full `after` text lives in
`changelist-full.json` (grounding kept here so FWK127 need not re-open it). Eval-gate the
affected agent after applying.

1. **accessibility.md — keyboard-rule de-dup.** Keyboard rule defers to the
   non-semantic-interactive rule on the overlapping `<div onClick>` case (report-once). Replace
   the keyboard-inaccessibility bullet with the `after` adding "**De-dup with the
   non-semantic-interactive rule above:**…".
2. **accessibility.md — scope cross-reference list.** Add the "do NOT flag X — agent Y owns it"
   list (usability / observability-fe / code-quality) to the final scope line.
3. **api-design.md — third breaking-change category.** Add "adding a new required (non-null,
   no-default) argument to an existing field/mutation" to the Uncompensated-breaking-schema
   bullet (severity stays high).
4. **architecture.md — folding note** (file untouched by FWK43). Fold in-route
   `commit()/refresh()/session` as a layer-PLACEMENT symptom into the one root finding at the
   same high; bar standalone import findings (code-quality's); cede txn *correctness* to
   data-integrity.
5. **coverage-gap.md — gap-2 reword.** "worker/beat tracing" → "a worker/beat startup or
   task-execution path" (name the runtime path, not its instrumentation — observability owns
   spans).
6. **dependency.md — async/usage-site terminal drop-rule.** Append an imperative "Before
   returning, DELETE any finding mentioning async/event-loop/blocking-IO/throughput/client-swap
   … likewise DELETE unused/usage-site-speculation findings" to the Scope paragraph.
7. **documentation.md — concrete `/count` worked examples** (file untouched by FWK43). Replace
   the "Do NOT flag" paragraph with one naming the exact recurring false positives (page-size
   cap, `response_model`/`summary`/`tags`, `Field(description=…)`, openapi regen) + banning the
   "this behaviour is undocumented" framing.
8. **documentation.md — quote-the-line guard + stale-doc severity.** Replace the advisory-cap
   paragraph with the "quote the exact implementation line you READ before claiming
   inaccurate/stale" guard + the `session.query(Item).count()` aggregate worked example + pin
   doc-completeness/stale-doc at low.

## Eval-gate plan — ONE batch pass at the end (operator-chosen 2026-06-29)

The edits are authored + committed **eval-pending**, then gated in a **single eval-campaign
pass** (the method the v2 scorecard used — whole-roster `--repeat 1` over the affected agents,
then `--repeat 3` confirmation on each edited agent), not a re-eval after every hunk. Rationale:
the `subagent` backend is slow + non-deterministic, so 9+ per-edit re-evals are wasteful and a
single pass is how the sweep was originally gated. Target recall 1.00 / fp 0.00 (`dependency` is
advisory → its fp floor is accommodated per the v2 scorecard). A gate miss in the batch pass
sends the specific edit back for a fix; the final FWK45 commit records the campaign results.

**Eval-backend hygiene** ([[framework-eval-no-builtin-resume]]): a
`BackendExhausted`/exit-4/truncated-`repeat` eval is INVALID (indistinguishable from a threshold
FAIL in CI) → capture eval's **own** `$?` ([[registering-review-agent-gate-completeness]]),
re-run; never treat exhaustion as a verdict. Single-roll scoring is non-deterministic (baseline
smoke run showed `application-logic` wobble) → the `--repeat 3` confirmation is load-bearing.
Agents touched across FWK45 (the experiment's only live-eval load): `application-logic`,
`data-integrity`, `compliance`, `accessibility`, `api-design`, `coverage-gap`, `dependency`,
`documentation`, `architecture` (9 agents).
