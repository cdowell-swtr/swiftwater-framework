---
name: framework-eval-no-builtin-resume
description: "`framework eval` has NO built-in resume (the Plan-20b checkpoint is for the audit run_engine only). Resume an interrupted sweep with a self-healing per-agent driver, and gate continuation on findings-COMPLETENESS — not exit code, because `framework eval <agent>` exits non-zero on a THRESHOLD FAILURE (expected), not just a crash."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: e7e23a67-9817-4ea6-8b0e-fbf0bba32de0
---

`framework eval` does **not** resume from `--findings-out` — it re-runs everything. The
Plan-20b `checkpoint.py`/`tree_signature` covers the audit `run_engine`, NOT `eval` (the
Plan 21 plan wrongly assumed otherwise). Findings are written incrementally to
`<dir>/<agent>/<kind>/<case>__r<repeat>.json`, so a crash preserves completed work.

**Resume recipe — a self-healing per-agent driver:** iterate the registered agents; for each,
count `find <dir>/<agent> -name '*__r*.json'` vs expected (`fixtures × repeats`); **skip if
complete**, else `rm -rf` the partial agent dir and re-run `framework eval <agent> --repeat N
--backend subagent --findings-out <dir>`. A reference is `/var/tmp/resume_baseline.sh` from
the Plan-21 0c run.

**CRITICAL gotcha:** gate continuation on findings-**completeness**, NOT the exit code.
`framework eval <agent>` **exits non-zero when the agent FAILS its thresholds** — that is the
expected baseline signal, not a crash. My first resume driver treated the first threshold-fail
as a stop and quit early. Check the findings count after each run; only stop when an agent's
findings come back *incomplete* (a real backend/quota abort).

Backend exhaustion is now graceful (FF `5bb1add`): the `claude -p` "session limit" 429 raises
`BackendExhausted` and `framework eval` exits 4 with findings preserved (see
[[subagent-backend-large-input-via-stdin-not-argv]]). Also a `tee` pipe masks the inner exit
code — read the inner command's status, not the pipeline's. Related:
crossing a full quota outage needs a standing cron (not ScheduleWakeup), and watch for silent subagent drops under quota throttling.
