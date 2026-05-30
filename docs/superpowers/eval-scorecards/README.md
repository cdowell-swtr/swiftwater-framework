# Eval scorecards

Each paid `framework eval` run leaves a dated, self-contained directory here so the result is reproducible from artifacts and we have a *trail* of calibration decisions (instead of one current `thresholds.yaml` with no provenance).

## Layout

```
docs/superpowers/eval-scorecards/YYYY-MM-DD-<slug>/
├── findings/              # raw per-(agent,fixture,repeat) JSON records
│   └── <agent>/<kind>/<case>__r<i>.json
├── scorecard.md           # rendered analyze report (committed)
├── thresholds.proposal.yaml  # the calibration helper's suggestion
└── meta.json              # run metadata: model versions, fixture hash, --repeat, $ spent, key last-4
```

## How to produce one

```bash
DATE=$(date +%Y-%m-%d)
DIR=docs/superpowers/eval-scorecards/${DATE}-slice-d-initial
mkdir -p "$DIR/findings"

# 1. Load scoped keys.
set -a; . ~/.swiftwater-framework-keys.env; set +a

# 2. Score (writes records to findings/).
uv run framework eval --repeat 3 \
  --fixtures tests/eval/fixtures \
  --findings-out "$DIR/findings"

# 3. Analyze (writes scorecard.md).
uv run framework eval-analyze "$DIR/findings" --out "$DIR/scorecard.md"

# 4. Capture the threshold proposal as a separate artifact.
sed -n '/^## Proposed thresholds.yaml/,/^## /p' "$DIR/scorecard.md" \
  | sed -n '/^```yaml/,/^```/p' \
  | sed '1d;$d' > "$DIR/thresholds.proposal.yaml"

# 5. Hand-write meta.json (model versions, $ spent, key last-4 from the analyze output).
```

## Why

- **Reproducible:** `findings/` is the source of truth; `eval-analyze` can re-derive the scorecard or apply a different margin at any time without a re-run.
- **Auditable:** every threshold value in `tests/eval/fixtures/thresholds.yaml` should map back to the scorecard that justified it.
- **Drift visible:** prompt edits or fixture changes can be re-scored and compared against the prior dated dir.
