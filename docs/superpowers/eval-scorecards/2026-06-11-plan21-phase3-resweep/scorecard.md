# Plan 21 Phase 3 — whole-set re-sweep (--repeat 3, free subagent backend)

13/20 agents recorded (resume-aware; raw findings in .framework/plan21/final-findings/ for eval-analyze).

| agent | recall | fp | verdict |
|---|---|---|---|
| accessibility | 1.00 | 0.00 | PASS |
| api-design | 0.83 | 0.00 | PASS |
| application-logic | 1.00 | 0.00 | PASS |
| architecture | 0.67 | 0.00 | FAIL |
| compliance | 1.00 | 1.00 | FAIL |
| contracts | 0.83 | 0.00 | PASS |
| data-integrity | 1.00 | 0.00 | PASS |
| data-lineage | 1.00 | 0.00 | PASS |
| dependency | 1.00 | 1.00 | PASS |
| documentation | 1.00 | 0.67 | PASS |
| env-parity | 0.89 | 0.33 | FAIL |
| observability | 1.00 | 0.00 | PASS |
| observability-db | 1.00 | 0.00 | PASS |

**10 PASS / 3 FAIL** so far. FAILs: architecture, compliance, env-parity
