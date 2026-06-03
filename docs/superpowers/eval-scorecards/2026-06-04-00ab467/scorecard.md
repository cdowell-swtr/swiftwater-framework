# Eval scorecard

## Summary
- Agents: 1
- Calls: 12 (bad: 9, good: 3)
- Total cost (est., USD): $0.00

## Scorecard
| Agent | Recall | FP | Status |
|---|---|---|---|
| review-observability-fe | 1.00 | 0.00 | PASS |

## Cost by agent
| Agent | Model | Calls | In tok | Out tok | Cache reads | Est. cost |
|---|---|---|---|---|---|---|
| review-observability-fe | claude-opus-4-8 | 12 | 0 | 0 | 0 | $0.00 |

## Recall diagnosis (per bad case)
### review-observability-fe
- [caught] `swallowed-error` r0 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `swallowed-error` r1 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `swallowed-error` r2 — seeded=`frontend/src/Items.tsx`, other_findings=0
- [caught] `unbounded-label` r0 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `unbounded-label` r1 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `unbounded-label` r2 — seeded=`src/demo/frontend_rum/metrics.py`, other_findings=0
- [caught] `uninstrumented-view` r0 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0
- [caught] `uninstrumented-view` r1 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0
- [caught] `uninstrumented-view` r2 — seeded=`frontend/src/Dashboard.tsx`, other_findings=0

## FP diagnosis (findings on good fixtures)
### review-observability-fe
- `capped-label` r2 → 1 findings:
  - `src/demo/frontend_rum/metrics.py:203` medium — New RUM signal `app_frontend_device_class_total` is exported but has no corresponding alert rule or Grafana dashboard panel. infra/observability/prometheus/alerts/frontend_alerts.yml covers only LCP and js_errors, and infra/observability/grafana/dashboards/frontend.json only panels web_vitals, js_errors, page_views, and rum_beacons. A new metric with no dashboard panel or alert is operationally invisible until someone manually queries it.

## Agentic behavior
### review-observability-fe
- Calls: 12, avg turns: 1.0, max-cap hits: 0

## Drift check
_(no drift detected — all tool calls within the production sandbox)_

## Acknowledged (covered by decisions)
_(none)_

## Proposed thresholds.yaml
```yaml
observability-fe:
  recall_min: 0.90  # observed 1.00
  fp_max: 0.10  # observed 0.00
```
