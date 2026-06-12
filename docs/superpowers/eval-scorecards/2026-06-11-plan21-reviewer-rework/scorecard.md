# Plan 21 — reviewer rework (compliance, obs-infra, env-parity, api-design)

Branch `plan21-reviewer-rework`. Closes the two **REQUIRES-REWORK** agents the Plan-21
audit refuted (`compliance`, `observability-infra`) plus two prompt follow-ups
(`env-parity`, `api-design`), using the audit→fix→adversarial-refute→verify discipline.
All verification on the free `claude -p` **subagent** backend at `--repeat 3`
([[verify-reviewer-evals-at-repeat-3]]). Fixtures authored via render→edit→`git diff`
([[render-edit-gitdiff-eval-fixtures]]). **No `thresholds.yaml` mask** — values are unchanged
([[eval-analyze-threshold-judgment]]).

## Results (`--repeat 3`, subagent backend, 2026-06-11)

| Agent | Before (baseline) | After | Verdict |
|---|---|---|---|
| compliance | recall 1.00 / **fp 1.00** | recall 1.00 / **fp 0.00** | **PASS** |
| api-design | 1.00 / 0.00 (intermittent `severity` omission) | 1.00 / 0.00 | **PASS** |
| env-parity | **0.78** / 0.00 | **1.00 / 0.00** | **PASS** |
| observability-infra | **0.50 / 1.00** | recall **1.00** (2 runs) / fp **0.00 then 0.33** | **PASS** |

obs-infra was verified twice post-backend-fix: recall **1.00 / fp 0.00**, then recall **1.00 /
fp 0.33** — both PASS (`recall_min 0.90`, `fp_max 0.43` unchanged). Recall is now rock-solid; the
fp oscillation (0.00↔0.33) is one good-fixture repeat that engages tools but still misjudges the
*complete* surface (a single broad `glob` it misreads as "alerts dir empty", though the diff adds
`redis_alerts.yml`/`redis.json`). That residual is a diff-awareness *judgment* stochasticity — not
a protocol failure (so the backend recovery loop can't catch it) and not the original `fp 1.00`
defect (which is fixed). `fp_max` stays 0.43 because fp genuinely reaches 0.33; tightening to 0.10
would re-introduce flakiness. Tracked as a residual below.

## Root causes & fixes

### compliance — fp 1.00 (over-flagging) — fixtures were mis-authored
The Phase-1 fix was refuted because the *fixtures* were wrong, not just the prompt:
- **good `audit-logged-action`** baited compliance with a PII free-text filter log
  (`name_filter` → **privacy**'s lane) and an unbounded `list_items` read (→
  **performance**'s lane). All 3 baseline repeats flagged those as `high`.
- the only **bad `logs-pii-in-handler`** was *itself a privacy case* (logs an email) — a
  correctly-scoped compliance agent returns `[]` on it, so it could never test compliance.

Fix (prompt **and** fixtures):
- **prompt** narrowed to compliance's true lane — audit-gap / retention-path / erasure —
  with explicit deferrals (PII-logged/over-collected → privacy; unbounded reads →
  performance; non-atomic writes → data-integrity), a codebase-bar clause, grounding, and a
  hardened JSON-only output contract.
- **good fixture redesigned**: the *same* privileged destructive delete but properly
  **audit-logged** with an opaque `actor_id` — the discriminator is purely the audit trail;
  no PII/unbounded bait. → fp 0.00 (3/3 `[]`).
- **bad fixture replaced**: `logs-pii-in-handler` → **`delete-without-audit-log`**, a
  destructive admin delete with no audit entry (opaque id, atomic — stays out of
  privacy/performance/data-integrity). → recall 1.00 (3/3 `high`).

### observability-infra — recall 0.50 / fp 1.00 — a real fixture bug + a backend flake
- **fp**: the good `complete-obs-surface` fixture had the `redis` block mis-indented under
  `volumes:` (a sibling of `pgdata`) instead of `services:` — a genuine malformed-YAML
  defect baseline reviewers correctly flagged. **Repaired** (redis under `services:`); the
  surface is now structurally complete (service + exporter + scrape + alert + dashboard).
- **prompt** rewritten: pins a broken prod monitoring path (scrape→no-exporter,
  exporter→no-scrape, prod surface→no-alert+no-dashboard) = `high`; "do not flag a complete
  surface"; diff-awareness that a new surface's **alert/dashboard arrive AS NEW FILES in the
  diff** (the exact diff-awareness hallucination the audit named).
- **recall** was capped by a **subagent-backend tool-protocol flake** (see below), not a
  detection defect: when the agent engaged its tools it scored 3/3 `high` on the bad
  fixtures; ~1/3 of invocations failed the protocol and returned garbage. Fixed at the
  backend (below).

### env-parity — recall 0.78 — a tool-leak + a mis-typed fixture
- `service-dev-only` r0 leaked a `{"tool_calls": …}` block as its final text (truncated /
  protocol confusion); `compose-var-not-declared` had an intermittent `[]` miss → both
  addressed by a hardened output-contract + tool/answer-discipline clause **and** the backend
  fix.
- `env-var-consumed-not-declared` used a **defaulted** var (`widget_timeout_s: float = 5.0`)
  — which reaches every env via its default, so a reviewer rating it *medium* was MORE correct
  than the prompt's blanket "high". Re-authored as a **required** var (`widget_api_url: str`,
  no default, absent from `.env.example` → app can't boot) = an unambiguous `high` break.

### api-design — intermittent `severity` omission
The breaking-rename finding was correct but one repeat omitted `severity`, and a single
malformed object makes `parse_findings` discard the **whole** array. Hardened the output
contract: every element MUST carry `severity` (exactly `high|medium|low|info`); preventive.

## Backend fix — the real lever for the file-heavy reviewers

The agentic loop (`review/agentic.py`) treated **any** no-tool-call turn as the final
answer. On the subagent backend the model intermittently (~1/3) ends a turn with neither a
tool call nor a valid findings array — it gives up ("I don't have tools"), echoes the system
prompt, cites the framework template path, or truncates a `{"tool_calls": …}` object whose
outer brace never closes (`backend._decode_tool_turn` then can't decode it → it's treated as
a final answer → `parse_findings` fails). This tanked recall/fp on the file-heavy reviewers
(obs-infra worst; env-parity next), which depend on reading **sibling** files; the
diff-anchored reviewers (compliance, api-design) barely noticed.

Fix (`agentic.py`): a non-parseable "final" turn is a **protocol failure, not a genuine
empty result** (genuine empty is `[]`, which parses). The loop now **nudges and retries**
(`_RECOVERY_INSTRUCTION`, bounded by `_MAX_RECOVERIES = 2`) instead of returning garbage; a
valid `[]` is preserved untouched. The subagent `_TOOL_PROTOCOL` text was also strengthened
("you DO have working tools", "close every brace"). TDD: 3 new tests in
`tests/review/test_agentic.py` (recovers-from-unparseable-final; preserves-genuine-empty;
recovery-is-bounded). This stabilized obs-infra 0.67/1.00→1.00 and env-parity to 1.00 across
consecutive runs.

## thresholds.yaml — no value changes

- **compliance** — recall_min 0.90 / fp_max 0.10; comments updated from "REQUIRES REWORK" to
  the now-observed 1.00 / 0.00.
- **observability-infra** — recall_min 0.90 / fp_max 0.43 **kept**. fp is genuinely fixed
  (1.00 → 0.00–0.33) but still reaches 0.33 on the good-fixture diff-awareness wobble, so
  tightening `fp_max` to 0.10 would re-introduce flakiness; comments updated to the observed
  range. This is NOT a mask of the original defect (which is fixed); it is honest headroom for
  a documented residual.
- **env-parity / api-design** — unchanged (1.00 / 0.00).

## Residual (tracked, non-blocking)

- **obs-infra good-fixture fp wobble (≤0.33).** ~1/3 of repeats, when the agent engages tools,
  still misjudge the complete `complete-obs-surface` as un-alerted/un-dashboarded after a single
  broad `glob` it misreads — despite the diff adding the alert/dashboard files. Passes the gate
  (`fp_max 0.43`) but is a real diff-awareness judgment-stochasticity. Candidate next steps: a
  fixture/prompt nudge forcing a per-directory read of `alerts/`+`dashboards/` before any
  "missing alert/dashboard" finding, or a 2nd clean good fixture to widen the fp denominator.
  Good fit for Plan 23 (agent self-improvement tooling).

## Files

- prompts: `review/agents/{compliance,observability-infra,env-parity,api-design}.md`
- fixtures: `compliance/good/audit-logged-action` (redesigned),
  `compliance/bad/delete-without-audit-log` (new, replaces `logs-pii-in-handler`),
  `observability-infra/good/complete-obs-surface` (repaired),
  `env-parity/bad/env-var-consumed-not-declared` (re-typed required)
- backend: `review/agentic.py`, `review/backend.py` (`_TOOL_PROTOCOL`),
  `tests/review/test_agentic.py`
