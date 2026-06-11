# Plan 21 Phase 3 — whole-set re-sweep (--repeat 3, free subagent backend)

Results recorded per-agent as they complete (resume-aware; survives quota exhaustion).
Raw per-call findings: `.framework/plan21/final-findings/` (gitignored) → feeds `eval-analyze`.

| agent | recall | fp | verdict |
|---|---|---|---|
| accessibility | 1.00 | 0.00 | PASS |
| api-design | 0.83 | 0.00 | PASS |
| application-logic | 1.00 | 0.00 | PASS |
| architecture | 0.67
0.67 | 0.00 | FAIL |
| compliance | 1.00 | 1.00
1.00 | FAIL |
| contracts | 0.83 | 0.00 | PASS |
| data-integrity | 1.00 | 0.00 | PASS |
| data-lineage | 1.00 | 0.00 | PASS |
| dependency | 1.00 | 1.00 | PASS |
| documentation | 1.00 | 0.67 | PASS |
