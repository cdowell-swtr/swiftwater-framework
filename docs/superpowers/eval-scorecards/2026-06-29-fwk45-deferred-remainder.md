# FWK45 — deferred reviewer-tuning remainder, eval-gated — scorecard (2026-06-29)

**Verdict: PASS.** The deferred remainder of FWK43's reviewer-tuning v2 sweep (S1/exp-2) —
**3 fixture rewrites + 8 domain-prompt edits** — is applied and **eval-gated green across all 9
affected agents**, at `--repeat 1` (the batch pass) and confirmed stable at `--repeat 3`. No
regression. Free `subagent` backend (`claude -p`), reviewers at production models. Provenance-frozen
(hand-applied from `.framework/reviewer-audit-v2/changelist-full.json`; no fresh `reviewer-audit` run).

## What was gated

- **Fixtures (FWK124–126):** `application-logic/bad/falsy-none-check` rewritten to a manifesting
  inverted-guard bug (the old `if not item:` was behaviourally inert); `data-integrity/bad/non-atomic-bulk-insert`
  minimized to a single-finding diff vs its good pair; new `compliance/good/pii-in-logs-not-compliance`
  regression fixture (PII-in-logs → privacy's lane, compliance stays clean).
- **Prompt edits (FWK127 — 8, not the scorecard's stated 6; see FWK123 loud finding):** accessibility ×2,
  api-design ×1, architecture ×1, coverage-gap ×1, dependency ×1, documentation ×2.

## Eval gate — `--repeat 1` batch pass (the 9 affected agents)

```
application-logic 1.00/0.00 PASS · data-integrity 1.00/0.00 PASS · compliance 1.00/0.00 PASS
accessibility 1.00/0.00 PASS · api-design 1.00/0.00 PASS · coverage-gap 1.00/0.00 PASS
dependency 1.00/1.00 PASS (advisory) · documentation 1.00/0.00 PASS · architecture 1.00/0.00 PASS
```

All `EXIT=0` (a valid scored verdict — captured eval's **own** `$?`, not a pipe's, per
[[registering-review-agent-gate-completeness]]; no `BackendExhausted`/exit-4, so none is an INVALID
exhaustion masquerading as a result — [[framework-eval-no-builtin-resume]]).

## Confirmation — `--repeat 3` (stability against single-roll non-determinism)

```
application-logic 1.00/0.00 · data-integrity 1.00/0.00 · compliance 1.00/0.00
accessibility 1.00/0.00 · api-design 1.00/0.00 · coverage-gap 1.00/0.00 · architecture 1.00/0.00
dependency 1.00/1.00 (advisory) · documentation 1.00/0.33 (advisory)
```

- The **7 blocking agents** hold at recall 1.00 / **fp 0.00** across all 3 rolls — the fixtures + prompt
  edits gate cleanly and stably.
- `dependency` (advisory, `block_threshold=None`) holds at fp 1.00 — surfacing-by-design on its good
  fixture, within its band, exactly as the v2 scorecard documented; not a regression.
- `documentation` (advisory) shows a single-roll wobble (fp 0.33 = 1 of 3 rolls flagged its good
  fixture) but **PASSes** — the advisory floor accommodates it. The `--repeat 3` confirmation is what
  surfaces this (a single roll showed fp 0.00); recorded, not hidden. The two documentation edits (the
  `/count` worked-example bans + the quote-the-line guard) reduce but don't fully eliminate the
  good-fixture false positive — consistent with the v2 finding that advisory precision is partly met.

## Provenance

Source: the frozen `main/.framework/reviewer-audit-v2/changelist-full.json` (49 KB, 2026-06-19).
Worklist + the 8≠6 reconciliation: `2026-06-29-fwk45-deferred-remainder-worklist.md` (FWK123).
Eval sequencing: a single batch pass (operator-chosen 2026-06-29), not per-edit re-eval — the v2
scorecard's own method.
