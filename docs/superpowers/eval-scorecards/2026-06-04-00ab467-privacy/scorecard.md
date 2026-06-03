# Eval scorecard

## Summary
- Agents: 1
- Calls: 12 (bad: 9, good: 3)
- Total cost (est., USD): $0.00

## Scorecard
| Agent | Recall | FP | Status |
|---|---|---|---|
| review-privacy | 1.00 | 0.00 | PASS |

## Cost by agent
| Agent | Model | Calls | In tok | Out tok | Cache reads | Est. cost |
|---|---|---|---|---|---|---|
| review-privacy | claude-opus-4-8 | 12 | 0 | 0 | 0 | $0.00 |

## Recall diagnosis (per bad case)
### review-privacy
- [caught] `pii-in-response` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-in-response` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-in-response` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-logged` r0 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-logged` r1 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `pii-logged` r2 — seeded=`src/demo/routes/items.py`, other_findings=0
- [caught] `rum-allowlists-pii` r0 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `rum-allowlists-pii` r1 — seeded=`src/demo/config/settings.py`, other_findings=0
- [caught] `rum-allowlists-pii` r2 — seeded=`src/demo/config/settings.py`, other_findings=0

## FP diagnosis (findings on good fixtures)
_(no fp findings — all good fixtures clean)_
## Agentic behavior
### review-privacy
- Calls: 12, avg turns: 1.0, max-cap hits: 0

## Drift check
_(no drift detected — all tool calls within the production sandbox)_

## Acknowledged (covered by decisions)
_(none)_

## Proposed thresholds.yaml
```yaml
privacy:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
```
