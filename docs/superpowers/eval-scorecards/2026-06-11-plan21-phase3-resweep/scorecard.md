# Plan 21 Phase 3 — whole-set re-sweep (--repeat 3, free subagent backend)

20/20 agents. Raw findings: .framework/plan21/final-findings/ → eval-analyze.

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
| observability-fe | 1.00 | 0.00 | PASS |
| observability-infra | 0.50 | 1.00 | FAIL |
| performance | 1.00 | 0.00 | PASS |
| privacy | 1.00 | 0.00 | PASS |
| security | 1.00 | 0.00 | PASS |
| test-quality | 1.00 | 0.00 | PASS |
| usability | 1.00 | 0.00 | PASS |

**16 PASS / 4 FAIL** vs the CURRENT (pre-re-derivation) thresholds. FAILs: architecture, compliance, env-parity, observability-infra
