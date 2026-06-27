# FWK66 SP2 — Plane-aware migrate / deploy / rollback — Layer-2 adversarial security matrix

**Date:** 2026-06-27
**Subject:** FWK58 Phase 2, SP2 (`--with multitenantauth`): control-first migrate fan-out + plane-aware
boot/`task db:migrate:all` wiring + **image-only rollback floor** (`rollback_guard.py`, `check_migrations.py`
two-chain scan), all battery-gated; a non-battery render is byte-identical to pre-SP2.
**Reviewed render:** clean `framework new --with multitenantauth` (package `demo`) at branch HEAD `2f36159`
(`fwk66-plane-aware-migrate-deploy-rollback`); pre-rendered at `/var/tmp/fwk66-sp2-l2/mt`.
**Method:** all-Opus (`claude-opus-4-8`, effort high) stance×focus matrix — 3 baseline producers → 12 cells
(stances `operator / chaos / dataloss` × focuses `F-ISO / F-CRED / F-ORDER / F-ROLLBACK`) → triage adjudication
(promote invariant-touching borderline items) → default-to-refuted verify (one skeptic per promoted finding) →
synthesis. 34 agents, ~1.91M subagent tokens, 365 tool calls, ~36 min wall-clock.
**Gate rule:** count CONFIRMED findings (`refuted=false` AND `mechanism_verified=true`) at Critical/High; **PASS iff that count is 0.**

---

## Merge-gate verdict: **GREEN — 0 confirmed Critical/High**

18 raw cell findings → 17 promoted → verified. The script's gate-of-record count of confirmed Critical/High
is **0**. No promoted hypothesis verified to a reachable Critical/High break of a crown-jewel invariant on a
shipped entrypoint (boot `entrypoint.sh`, `task db:migrate:all`, or the CD `strategy.sh rollback`).

**But the gate earned its keep below the Crit/High line.** Reading *every* confirmed disposition (not just the
Crit/High band) surfaced **three confirmed Medium findings** (`refuted=false`, `mechanism_verified=true`) — one
of which is a genuine **fail-OPEN** of the headline I-ROLLBACK invariant that an independent Opus verifier
flagged **FIX-NOW**:

| ID | Confirmed Medium | Invariant | Disposition |
|----|------------------|-----------|-------------|
| **P15** | **Merge-topology rollback fail-OPEN** — `_app_contract_in_range` used `walk_revisions(target, "heads")`, which on a merge topology omits a `# deploy: contract` on a **merged side-branch**, so an image-only rollback to a merge parent silently crosses it | I-ROLLBACK | **FIXED IN-BRANCH (post-matrix)** |
| P11 | **Marker-evasion** — raw-SQL `op.execute("DROP …")` / type-narrowing `alter_column(type_=…)` carry no marker → evade both `check_migrations.py` and `rollback_guard.py` | I-ROLLBACK | DOCUMENTED-LIMITATION |
| P16 | **Control floor over-refusal** — `_control_contract_any` walks `base→heads` unconditionally → once any control contract ships, every later control rollback refuses (no per-release lower bound) | I-ROLLBACK | DOCUMENTED-LIMITATION (fail-**closed**) |

P11 and P16 are by-design, disclosed, and fail in the **safe** direction (P11 = the pre-SP2 single-DB blind spot
backstopped by the data-integrity review agent; P16 = over-refusal on the most sensitive plane). P15 was none of
those — an **unintended fail-open** contradicting the code's own docstring intent — so it was fixed before merge.

---

## P15 — the fail-open, and the fix (headline)

**Mechanism (reproduced, both by the verifier and independently here).** `rollback_guard.py:_app_contract_in_range`
detected contract migrations via `script.walk_revisions(target_rev, "heads")`. On a merge topology — chain
`0001→0002→(0003a, 0003b)→0004merge` with a `# deploy: contract` on side-branch `0003b` — `walk_revisions("0003a","heads")`
yields only `['0004merge','0003a']` and **omits `0003b`**. But a real `alembic downgrade 0003a` from the merge head
unapplies `{0004merge, 0003b}` (= ancestors-of-head − ancestors-of-target), so `0003b`'s contract **is** crossed — yet
the guard returned no offenders and **allowed** the image-only rollback. Reachable on the shipped CD path: `strategy.sh`
refuses to *deploy* with multiple heads, but the standard remedy `alembic merge heads` places a former sole head (the
recorded `rev`) as a merge parent; rollback then targets exactly that parent while a marked contract sits on the sibling.

**Verifier's suggested fix was itself wrong — caught by empirical check.** The verify agent proposed
`iterate_revisions("heads", target, select_for_downgrade=True)`. Run against the same chain (alembic 1.18.5) it returns
**`['0004merge']`** — *also* missing `0003b`. The advisor's "prove the API before trusting the method name" discipline
caught this; shipping it would have left the floor fail-open.

**The correct fix (verified across all cases):** compute the true downgrade set as the **ancestor-set difference** —
`ancestors(heads) − (ancestors(target) ∪ {target})`:

| target | downgrade set | side-branch `0003b` flagged? |
|--------|---------------|------------------------------|
| `0003a` (merge parent) | `{0003b, 0004merge}` | **yes** (the P15 case — now refuses) |
| `0002` (below the branch) | `{0003a, 0003b, 0004merge}` | yes (linear-in-range still refuses) |
| `0003b` (land ON contract) | `{0003a, 0004merge}` | no — correct, we land on it, don't cross |
| `0004merge` (head) | `{}` | no — nothing to roll back, allow |
| bogus/ambiguous | raises `ResolutionError` | — fail-**closed** preserved |

Implemented in `_app_contract_in_range` (uses `iterate_revisions("heads","base")` for head ancestors and
`iterate_revisions(target,"base")` ∪ the resolved target for the exclusion set). `_control_contract_any` walks
`base→heads` so it was already complete and is unchanged.

**TDD (in a real rendered battery project, alembic synced):**
- **RED:** with the old `walk_revisions` impl, `test_merge_topology_marked_contract_on_side_branch_is_refused`
  fails with `AssertionError: []` (the side-branch contract is missed).
- **GREEN:** with the fix, the full guard suite is **12 passed** (8 unit + 2 pre-existing functional + 2 new merge tests).
- Regression tests added to `tests/functional/test_rollback_guard.py` (a hand-built synthetic merge chain;
  the project's real chain is linear so cannot exercise this). Rendered guard + tests are `ruff format --check`
  clean at the rendered project's 88-col default.

**Why fixed in-branch, not deferred (advisor-confirmed):** it's a strict *tightening* (fail-open → correct) of the
exact invariant SP2 delivers, in unlocked framework code built on this branch, with a one-idiom fix in hand. The TDD
regression test *is* the verification (it ships and re-derives the mechanism) — no full matrix re-run and no 47-min
gate re-run is warranted for a strict tightening.

---

## Crown-jewel invariants — independently re-verified on the shipped surface

- **I-ISO (cross-tenant isolation across the fan-out) — HOLDS.** `migrate_tenant` builds a **fresh per-DSN** alembic
  `Config` per call; `env.py::run_migrations_online` builds a **fresh `NullPool` engine** every `command.upgrade` — no
  module-level/cached engine or pooled connection survives across iterations, and a mid-loop exception carries no state
  forward (per-iteration `except`). Verified on the migrate path, not merely inherited from SP1. (P1/P2/P3/P5 refuted.)
- **I-CRED (credential non-disclosure) — HOLDS.** Every `migrate.py` `except` records/logs only `type(exc).__name__`;
  the result map values are class names or `"ok"`; `main()` prints only class names + `^[a-z0-9_]+$` tenant ids. The
  SP1 alembic `%`-interpolation leak class is **not reintroduced** (control/default never `set_main_option` a raw DSN;
  `migrate_tenant` keeps the `%%`-escape at `provision.py:60`). (P4/P5/P6 refuted.) *Pre-existing latent residual,
  out of SP2 scope:* `env.py` `set_main_option` is not `%%`-escaped like `provision.py`, so a `%`-bearing DSN run
  directly via `task db:migrate` / raw `alembic upgrade` could leak in the operator's own terminal — shielded on every
  SP2 fan-out/boot path (class-name-only `except`), unchanged by SP2; carried to the SP1 data-plane preconditions.
- **I-FAILFAST (control-first ordering) — HOLDS.** A control-plane `upgrade` failure returns **before** any default/tenant
  mutation; a tenant-enumeration read failure is recorded and **also** returns before the fan-out; `report_failed` flags
  any non-`ok` plane/tenant and `main()` exits non-zero — best-effort tenant continuation cannot exit green on a real
  failure or mask a partial migration. (P7/P8/P9/P10 refuted.)
- **I-ROLLBACK (image-only rollback floor) — HOLDS after the P15 fix.** Battery `strategy.sh rollback()` performs **no
  `alembic downgrade` on any plane** (P11 confirmed no `__target_migrate "downgrade"`; image-only redeploy + record);
  the guard fails **closed** on any resolution error (P8/P14 — `ALLOW_CONTRACT_ROLLBACK=1` override only), receives the
  **full** recorded revision (P12 — abbreviated/unknown revs over-refuse safely or raise), and — with the P15 fix — now
  detects a marked contract on a merged side-branch.

---

## Promoted findings — full disposition (gate-of-record verify verdicts)

`refuted`/`mech` = the verify agent's `refuted` / `mechanism_verified`. Confirmed = `refuted=false` AND `mech=true`.

| ID | Finding (abbrev.) | Inv | Sev | refuted | mech | Disposition |
|----|-------------------|-----|-----|---------|------|-------------|
| P1 | Shared/cached engine misroutes `migrate_tenant` | I-ISO | High | yes | no | NO-ACTION |
| P2 | Process-wide DSN cache misroute | I-ISO | High | yes | no | NO-ACTION |
| P3 | Mid-loop exception carries state to next tenant | I-ISO | High | yes | no | NO-ACTION |
| P4 | alembic `%`-interpolation DSN leak (SP1 carry-over) | I-CRED | High | yes | no | NO-ACTION |
| P5 | DSN disclosure via log/result/stdout | I-CRED | High | yes | **yes** | NO-ACTION |
| P6 | DSN leak via exception/log | I-CRED | High | yes | no | NO-ACTION |
| P7 | Best-effort masks partial / exits green | I-FAILFAST | High | yes | no | NO-ACTION |
| P8 | Control/enum read failure permits tenant mutation | I-FAILFAST | High | yes | **yes** | NO-ACTION |
| P9 | Default-DB failure proceeds to fan-out | I-FAILFAST | Low | yes | no | NO-ACTION (recorded + flagged) |
| P10 | Concurrent `upgrade head` race | I-FAILFAST | Low | yes | no | NO-ACTION |
| **P11** | **Marker-evasion (raw-SQL / type-narrowing)** | I-ROLLBACK | Medium | **no** | **yes** | **DOCUMENTED-LIMITATION** |
| P12 | Abbreviated/wrong rev mis-resolves range | I-ROLLBACK | Low | yes | yes | NO-ACTION (full rev passed; partial over-refuses) |
| P13 | `ALLOW_CONTRACT_ROLLBACK=1` allows on resolution-error path | I-ROLLBACK | Low | yes | yes | DOCUMENTED-LIMITATION (intended break-glass) |
| P14 | cwd-relative config paths drop a floor | I-ROLLBACK | Low | yes | no | DECISION (missing ini → fail-closed) |
| **P15** | **Merge-topology rollback fail-OPEN** | I-ROLLBACK | Medium | **no** | **yes** | **FIX-NOW → FIXED IN-BRANCH** |
| **P16** | **Control floor always-in-range over-refusal** | I-ROLLBACK | Medium | **no** | **yes** | **DOCUMENTED-LIMITATION** (fail-closed) |
| P17 | Override crosses floor with offenders present | I-ROLLBACK | Low | yes | yes | NO-ACTION (documented override) |

---

## Documented limitations / maintainer decisions (recorded, non-blocking)

- **P11 — marker-evasion (Medium).** `check_migrations.py` + `rollback_guard.py` key on the AST op-set + the explicit
  `# deploy: contract` marker; raw-SQL / type-narrowing destructive migrations carry no marker and evade both. Disclosed
  in `check_migrations.py`, `infra/deploy/README.md`, and the guard docstring; identical to the pre-SP2 single-DB blind
  spot. The primary backstop is commit/CI-time **semantic review** (the data-integrity review agent), not the rollback
  floor — the data is destroyed at deploy/migrate time, before any rollback. Reaching the sink requires a *trusted*
  operator to author the destructive migration. → SP3 carry-over (wire the semantic agent as the authoritative backstop).
- **P16 — control-floor over-refusal (Medium, fail-closed).** The control rev is not tracked per release, so
  `_control_contract_any` treats any control contract as always-in-range. Over-enforcement on the most sensitive plane —
  cannot mask an under-block. Disclosed in the docstring. → SP3 carry-over (per-release control-rev tracking for a precise floor).
- **P13/P17 — `ALLOW_CONTRACT_ROLLBACK=1` (Low).** The deliberate operator break-glass (warns + demands a data-restore
  plan), reachable only by an operator who exports the flag. Keep explicit + warning-loud. → SP3 carry-over: emit an audit-log line when exercised.

---

## Provenance caveat (read before citing the workflow's own synthesis output)

The workflow's Phase-5 **synthesis agent received the verify-stage verdicts as `[object]`** (a script data-passing bug;
per-stage verdicts were held in-memory, not persisted), so its narrative `scorecard_markdown` is a *reconstruction* from
the rendered code — it **independently re-numbered findings** and under-reported P15 ("Confirmed findings to fix now:
None"). **This scorecard is NOT built from that narrative.** It is built from the **gate-of-record**: the script's
`confirmed_crit_high_precomputed` + `refuted_high_severity` (computed from the real verify outputs) and the per-agent
verify verdicts extracted directly from the workflow agent transcripts (`agent-*.jsonl`). The 15 matrix cells, triage,
and 17 verify skeptics all ran on Opus and produced real verdicts; only the final narrative-assembly step was degraded.

**Action item before the next Layer-2 run:** fix the workflow script (`scratchpad/fwk66-sp2-layer2.mjs`) to pass the
verify verdicts to the synthesis agent as a serialized array (and/or persist per-stage verdicts to disk), so the next
run's synthesis is an assembly of the real verdicts rather than a reconstruction, and the controller need not
hand-extract verdicts from transcripts.

---

## SP3 / Phase-3 carry-overs (record, do not fix in SP2)

1. **Semantic destructive-migration detection** (P11) — wire the data-integrity review agent as the authoritative
   contract-floor backstop alongside the structural marker.
2. **Per-release control-revision tracking** (P16) — record the control chain head per release for a precise control
   `(target, head]` floor instead of always-in-range.
3. **Override audit trail** (P13/P17) — emit an audit-log line whenever `ALLOW_CONTRACT_ROLLBACK=1` is exercised.
4. **SP1 data-plane preconditions remain deferred** — placeholder-DSN **sentinel guard** (an empty/blank tenant DSN
   makes `env.py`'s settings-fallback re-migrate the **default** DB and report the tenant green — a fail-open the matrix
   re-surfaced; reinforces the SP1-recorded sentinel precondition), parse-before-cache, lock-hygiene + `connect_timeout`,
   and the `env.py` `%%`-escape for credential symmetry. SP2 wires no `tenant_db` *request* route, so these stay untriggered.

## Net

**Gate GREEN: 0 confirmed Critical/High.** All four crown-jewel invariants re-verified on the shipped surface. The
matrix's value this run was catching **P15** — a confirmed fail-open of the rollback floor that both the precomputed
Crit/High count (it's Medium) and the degraded synthesis narrative missed — now **fixed in-branch** with a non-vacuous
TDD regression test (and a corrected fix the verifier's own suggestion would have gotten wrong). P11/P16 are confirmed
but by-design/fail-safe documented limitations; the rest refuted. (The branch's one acceptance red,
`test_rendered_project_integrity_verifies_tamper_and_restore`, is the pre-existing FWK70 `_commit` skew-guard fixture
bug — unrelated to the SP2 security surface.)
