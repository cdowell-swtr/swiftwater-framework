# Reviewer tuning pass (tooled, via `framework reviewer-audit`) — scorecard (2026-06-20)

**Verdict: PASS.** The first apply of `framework reviewer-audit`'s vetted changelist —
22 adversarially-vetted edits from the v2 sweep — landed as **11 prompt + rubric edits
across 7 reviewers + the shared rubric**, eval-gated. Every agent that can be scored
PASSes at recall 1.00 / fp 0.00; no regression.

This is "Plan 21 redux", now produced by tooling instead of a hand-driven Workflow: the
audit→reconcile→adversarial-refute pipeline proposed the changes, the adversarial spine
culled 5 of 27, and `framework eval` is the empirical gate on what shipped.

## What was applied (the 11 auto-applyable hunks)

| Agent | Edit (rationale, abbreviated) |
| --- | --- |
| accessibility | Split the over-broad `ARIA/contrast → info` bucket into invalid-aria (medium/high) + low-contrast (low), with a fg+bg grounding guard. |
| api-design | Make the bounded-list exclusion explicit so a `tags() -> []` clean verdict is grounded in the prompt, not an inline comment. |
| application-logic | Add the explicit "do NOT flag X — agent Y owns it" scope list + a behaviourally-identical-conditional clarifier. |
| compliance (×2) | Close the PII-in-logs loophole (→ privacy, NOT compliance) and scope retention/erasure to personal data **persisted in stored records**, not transient log lines. |
| coverage-gap | Add the test-quality ownership boundary (ordinary unit-coverage is test-quality's, not coverage-gap's). |
| data-integrity (×2) | **Factual fix:** the prompt wrongly credited `expire_on_commit=False` for populating `created_at`; name the real mechanism (RETURNING / `eager_defaults`) and foreclose the dialect-rationalization. + reinforce the input-validation/size-cap scope boundary. |
| dependency (×2) | Strengthen the no-fabricated-CVE grounding (the baseline emitted a fabricated `CVE-2024-35195`) with a terminal drop-rule; redefine "justification" as manifest-local; codify dev→prod promotion as not-redundancy. |
| rubric (roster-wide) | Extend the canonical one-owner-per-class line (input/resource caps → performance; GraphQL list shape → api-design; PII-in-logs → privacy; standalone import findings folded into code-quality) — assigns ownership, **not** a uniform severity. |

## Eval gate (free `subagent` backend, reviewers at production models)

**`--repeat 1` over the whole roster — 18/18 scorable agents PASS, all recall 1.00 / fp
0.00**, including all 7 edited agents and both rubric-ownership *gainers* (performance,
privacy):

```
accessibility api-design application-logic architecture compliance contracts
coverage-gap data-integrity data-lineage dependency observability observability-db
observability-fe performance privacy security test-quality usability   → all PASS 1.00/0.00
```

**`--repeat 3` confirmation on the 7 edited agents — all PASS, stable across 3 rolls:**

```
accessibility 1.00/0.00 · api-design 1.00/0.00 · application-logic 1.00/0.00
compliance 1.00/0.00 · coverage-gap 1.00/0.00 · data-integrity 1.00/0.00
dependency 1.00/1.00 (advisory)
```

- `data-integrity` holds at fp 0.00 across all 3 rolls — the factual `RETURNING`/`eager_defaults`
  correction held; the stale-dialect rationalization that produced the baseline false-HIGHs did
  not resurface.
- `dependency` lands at **fp 1.00** (PASS) vs. 0.00 on the single-roll gate — not a regression:
  `dependency` is **advisory** (`block_threshold=None`), so a low/info observation on its good
  fixture is surfacing-by-design, within its threshold band. The edit's precision goal (keep the
  good fixture fully clean) is only partly met; the advisory floor accommodates the remainder.

3 agents (`documentation`, `env-parity`, `observability-infra`) could **not** be scored —
their golden fixtures fail `git apply` (pre-existing template drift, unrelated to this
tuning; none were edited). Tracked separately — see Surfaced gaps.

## Deferred (NOT applied — documented manual follow-ups)

The vetted changelist also contained edits this pass deliberately did **not** apply:

- **Fixture edits** (3, in `apply-preview.notes.txt`) — changing an eval *fixture* changes
  the gate itself, so these warrant a separate deliberate pass, not riding the prompt
  tuning.
- **Paraphrased-`before` domain edits** (6) — the model's `before` is a prose paraphrase,
  not a verbatim file slice, so they don't anchor to an applyable hunk; readable in
  `changelist.json`, apply by hand if desired.

## Surfaced gaps (process findings — the value of running it end-to-end)

1. **eval fixture-suite drift** — at least 3 agents' `change.patch` fixtures no longer
   apply to the current template render; `test_fixtures_are_wellformed` evidently does not
   catch this. (task #19)
2. **eval aborts the whole run on one bad fixture** — a single un-realizable fixture raises
   out of `realize_cached` and kills the sweep; needs record-and-continue. (task #19)
3. **eval has no `--concurrency`** — fully serial (~10 min/agentic-agent); the FWK41 H2
   ThreadPoolExecutor treatment applies. (task #19)
4. **reviewer-audit follow-up still open** — retry-once on an unparseable adversarial
   skeptic before counting it a refutation (env-parity was dropped on 2/3 parse failures).

## Provenance

Vetted changelist: `.framework/reviewer-audit-v2/changelist.json` (sweep 2026-06-19,
free subagent backend, baseline `.framework/plan21/baseline-findings`). Apply-preview +
notes: `.framework/reviewer-audit-v2/apply-preview.{patch,notes.txt}` (regenerated against
master with the FWK42 anchored-diff renderer → 11 clean hunks, `git apply --check` green).
