# Applying these threshold updates

To apply the proposed values from `thresholds.proposal.yaml`:

1. Diff `tests/eval/fixtures/thresholds.yaml` against `thresholds.proposal.yaml`.
2. For each changed agent, sanity-check the new values against the observed
   `recall` / `fp` columns in `scorecard.md`. If a number looks borderline,
   prefer the more conservative side (lower recall_min, higher fp_max).
3. Copy approved entries into `tests/eval/fixtures/thresholds.yaml`.
4. Commit referencing this scorecard dir.

See `scorecard.md` for the source observations and `findings/` for raw records.
