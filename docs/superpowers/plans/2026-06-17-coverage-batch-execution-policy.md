# Coverage Batch (FWK19, FWK23–FWK28) — Execution Policy & Index

> **For the overnight runner (laptop):** this is the shared operating policy every per-item
> plan in this batch references. Read it once, then execute each item's plan in order. Each
> per-item plan is a self-contained spec+plan (like `2026-06-17-fwk21-…`). Use
> `superpowers:executing-plans` (or subagent-driven) per item.

## Scope

The remaining med/low half of the FWK18 runtime-coverage inventory
(`docs/superpowers/assessments/2026-06-15-runtime-coverage-gaps.md`). The two standing
highs (FWK20 workers-live, FWK21 battery-runtime) shipped. FWK22 is a dropped tombstone.

## Order (hardest first — settled 2026-06-17)

1. **FWK24** — per-battery live routes through Traefik + react RUM round-trip (M8, M9)
2. **FWK23** — observability live exercise (M7, M10, M11, M12, M13)
3. **FWK26** — dev-loop / service-health (M1, M2, M4, M14)
4. **FWK25** — Taskfile targets through the `task` runner (M5, M6)
5. **FWK19** — non-dev compose overlays config-validated + `test.yml` up live (M3 + H1/H2/H7 validation)
6. **FWK27** — generated-project `.claude` review-gate hook (M15)
7. **FWK28** — seam/script smoke + workflow-graph asserts (L1, L2, L3)

Plan files: `docs/superpowers/plans/2026-06-17-fwk<NN>-<slug>.md`.

## Escape hatch — NEVER block on the human (park-and-continue)

The run is fully unattended overnight. It must **never stop to wait for input or approval.** If
finishing a step would require EITHER:

- **my permission** — an outward-facing or hard-to-reverse action: merging to `master`,
  cutting/pushing a release or tag, publishing anything, deleting/overwriting something I created,
  or any destructive/networked action beyond a test's own scope; OR
- **my input** — a decision that genuinely can't be resolved from the code, the plan, or a sensible
  default: an unanticipated design fork, a real-bug fix that's non-trivial/ambiguous/risky, or a
  pre-chosen fork-default that turns out wrong,

then **do NOT ask and do NOT wait. Park it and keep going:**

1. **Park only the blocked unit** — the single step / sub-test / task that needs me, plus anything
   that strictly depends on it. Mark it `@pytest.mark.xfail(strict=True, reason="PARKED: <what + why>
   — needs <input|permission>")` (or `skip` if it can't even be written), leave any related FWK29
   registry entry KNOWN_GAP, and commit what IS done.
2. **Continue with the rest of the CURRENT item** that does not need me (the independent sub-tasks),
   then move to the next item in the order. Never let one parked unit sink a whole item.
3. **Record every parked unit in the morning report** with enough context to decide in one read: what
   was blocked, the exact decision or permission needed, the options, and where it lives
   (file/test/commit). If it's also a real bug, additionally do the `ACTION_LOG` + new `PLAN.md`
   entry (per the real-bug policy).

This generalizes the real-bug policy below — an ambiguous fix is just one kind of "needs my input."
The ONLY thing that waits for me is the **terminal step: opening the batch PR for review** (the merge
is the single intended permission gate). Never leave the `gate` tier red.

## Transient Claude API / safety-classifier unavailability — RETRY, never fail

**Distinct from the escape hatch.** A Claude API / auto-mode error — e.g. *"auto mode cannot
determine the safety of Bash right now … <model> is temporarily unavailable"* — is **transient
infrastructure**, NOT a test result and NOT a decision point. Do **not** fail, park, skip, xfail, or
abandon anything because of it.

- **Wait ~60s and retry the exact same action. Keep retrying at 1-minute intervals, indefinitely,
  until it succeeds**, then resume exactly where you left off.
- A long or repeated outage is still just "wait longer" — **never** conclude an item or the run
  failed merely because the classifier has been erroring for a while. There is no give-up timeout.
- Applies to every such API/classifier error (Bash gating, tool dispatch, subagent spawn, etc.).
  Read-only work that doesn't need the classifier may continue meanwhile, but the blocked action is
  **not** skipped — come back and complete it once the classifier recovers.
- (Different failure mode: a full multi-hour **quota** outage can kill the session itself. If the run
  must survive that, drive it from a standing cron that self-heals at the next reset — not an
  in-session sleep. For a transient classifier blip, the 1-minute retry above is the whole answer.)

## Operating environment (laptop)

- Requires **docker acceptance parity** — buildx + dind-capable, host-UID-clean. See
  `docs/maintenance/laptop-dev-parity.md`. The acceptance tier is docker-gated
  (`skipif not _docker_available()`) and **CI-ignored / local-only**, so these tests run on
  the laptop, not in GitHub CI.
- **`TMPDIR`:** the full/acceptance tier builds large images; if `/tmp` is a small tmpfs, set
  `TMPDIR=/var/tmp` (or any roomy non-tmpfs dir) for the run. Cf.
  [[full-suite-exhausts-tmp-tmpfs-use-var-tmp]].
- **API keys:** the batch uses **no real API keys by default** (fork 2A asserts reachability +
  the documented no-key error + metric, not a real completion). If a test is later upgraded to a
  real-backend assertion, source keys from the operator's local environment out of band — never
  commit keys, and never echo a key-bearing line.
- Reuse the existing harnesses in `tests/acceptance/test_rendered_project.py`:
  `_run_image_serving` (FWK21), `_compose_env`, `_compose_host_port`, `_free_tcp_port`, the
  `_isolate_compose_project` autouse fixture (ephemeral host ports + per-test compose project),
  and the FWK20 `compose exec -T` query pattern. Through-Traefik routing uses the FWK8 recipe
  (connect `127.0.0.1:443` + `Host: demo.localhost`, `check_hostname=False`, chain-verify the
  mkcert CA). Cf. [[testing-traefik-tls-route-from-python]].

## Branch / commit strategy

- **One batch branch:** `fwk-coverage-batch` (cut from up-to-date `master`).
- **≥ 1 commit per item**, each gate-green; **commit more often when it buys safety**
  (e.g. after the helper, after each sub-test) — the run is long; frequent commits =
  resumability.
- The framework repo's **PreToolUse review gate** (`reviewers-gate-check.sh`) over-fires the
  full app-agent panel on every commit (~600k each) — wasteful for test-only slices. Use the
  **controller skip-marker recipe** per commit ([[controller-skip-marker-recipe]]:
  `framework gate-prepare` → write `.framework/audit/marker.json` {staged_hash, verdict PASS,
  drift false}; `git add` + marker-gen as ONE call, then `git commit` as a SEPARATE call) and do
  **one Opus whole-branch review at the end** ([[gate-cadence-framework-slices]]). The
  framework commit-gate still needs `PLAN.md`/`ACTION_LOG.md` staged on every commit.
- **One PR at the end** for morning review (no autonomous merges to protected `master`).

## Real-bug policy (these tests exist to catch unexercised breakage — expect some)

When a new test goes red, **root-cause it first** (`superpowers:systematic-debugging`); never
patch a symptom. Then:

- **Small + obviously-correct + scoped to the surface under test** (à la FWK20's beat
  `--schedule` one-liner): apply the template fix, add a CI-visible render guard where one fits,
  let the test go green. This is a template-payload change → **defer the release** (no consumers)
  but note it.
- **Non-trivial / ambiguous / risky:** do **not** guess unattended — this is a "needs my input"
  case, so apply the **escape hatch** (park-and-continue) above: `@pytest.mark.xfail(reason="FWK<NN>:
  real bug — <one line>", strict=True)`, leave the FWK29 registry entry **KNOWN_GAP** (do **not**
  falsely flip to EXERCISED), and continue.
- **Every real bug, fixed or deferred, gets ALL of:** (1) an `ACTION_LOG.md` entry; (2) a **new
  `PLAN.md` `Next` entry** (a new `FWK` task ID) capturing the bug + proposed fix; (3) a line in
  the morning report.
- **Never leave the `gate` tier red.** (The acceptance tier is CI-ignored, so a local xfail does
  not block the PR's required checks; but the `gate`-tier render guards must stay green.)

## Release

**None** for the batch (test-only). Any template fix a real bug forces is **deferred** — flag it
for a future batched release; do not cut a tag during the run.

## Review

Per-item: a quick controller self-check + the skip-marker. **Branch-end: one Opus whole-branch
code-quality + spec review** (review-model policy / [[subagent-review-model-pattern]]); address
findings before the PR.

## Non-vacuity (required for every test)

Each test must be **bite-proven** (RED on a regression, GREEN on correct) or non-vacuous by
construction, per FWK8/FWK20/FWK21. Cheap bite-proofs (flip an asserted marker / disable the
surface via env) are preferred over expensive rebuilds; document which was used.

## Morning report (end of run)

A single summary, structured so I can act in one read:
- **Per item:** green / partial / xfail / skipped, and which sub-tasks landed.
- **Bugs found** (with the new `FWK` IDs + `ACTION_LOG` refs).
- **⚠ PARKED — needs my decision/permission** (the escape-hatch list): each with *what* was blocked,
  the *exact* decision or permission needed, the options, and *where* it lives (file/test/commit).
  This is the to-do list for my morning pass.
- The batch PR link; anything that couldn't complete and why.
