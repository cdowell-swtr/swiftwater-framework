# Local Reviewers Design

**Status:** DRAFT — 2026-05-29 (PDT)
**Branch (anticipated):** `plan-local-reviewers` (decomposes into two implementation plans, Slice E1 and Slice E2)
**Supersedes:** the "single paid run" calibration framing in Slice D's status. Slice D's paid run becomes future work (Slice E3, the production-floor anchor); local subagent-driven calibration moves to the center of the workflow.

---

## Goal

Move the *substantive work* of the review-agent system — tuning, hygiene review, pre-commit gating — out of the paid Anthropic API path and onto Claude Code subagents (which run on the conversation's subscription, not metered API rates). The paid API path remains as a periodic anchor and as the universal CI safety net; it stops being the cost-center for every iteration.

Two slices:

1. **Slice E1 — Local review infrastructure.** Build the subagent-backed dispatch once. Expose it as `/reviewers:tune` (calibration against fixtures) and `/reviewers:audit` (hygiene review against current code).
2. **Slice E2 — Local gating safety net.** Wire the audit machinery into `/reviewers:gate` plus a `PreToolUse` hook that auto-dispatches the gate on AI-driven commits. Ship the same surface into generated projects via the template.

---

## Why this matters

The current state, after Slice D's harness work:
- One full `framework eval --repeat 3` against fixtures costs ~$3.75 in API spend.
- Every iteration on prompts, fixtures, or thresholds re-incurs that cost.
- The dogfooding `framework review --target framework` path costs real API money on every PR.
- Calibration iteration is the *most frequent* of these activities and the one that compounds.

After this slice:
- Tuning and hygiene review cost ~$0 per iteration (subagent quota, bounded by subscription tier).
- Pre-commit gating catches problems before they would have triggered a paid PR review.
- The paid API path becomes a periodic anchor (verify the production-floor numbers haven't drifted) and the universal CI safety net (runs on GHA via `agent-evals.yml` and `review.yml`, where subagent runtime is unavailable).
- Generated projects inherit the same local-first economics via template-shipped commands and hooks.

---

## Architecture

### Slice scope and decomposition

The two slices share infrastructure but have distinct shapes and acceptance criteria.

**Slice E1** delivers the subagent-dispatch machinery plus two user-facing commands that wrap it. The dispatch is built once; both commands reuse it with different inputs (fixtures vs. current code).

**Slice E2** is mostly wiring: the existing audit machinery from E1, plus marker-file semantics, plus a `PreToolUse` hook, plus template-side replication for generated projects.

E1 has no dependency on E2. E2 depends on E1.

### Three commands, one family

All three commands live under the `/reviewers:` namespace to (a) avoid plugin/built-in conflicts on generic names like `/audit`, (b) make the family discoverable via tab-completion, and (c) signal "this is about the review system, not general framework operations."

| Command | Purpose | Inputs | Output dir | Lifecycle |
|---|---|---|---|---|
| `/reviewers:tune [<reviewer>]` | Threshold calibration. Runs agents against rendered fixtures, scores recall/fp, proposes thresholds. | `<reviewer>` optional positional (default: all 18); `--repeat N` (default 3); `--slug <name>` (default: short git ref) | `docs/superpowers/eval-scorecards/YYYY-MM-DD-<slug>/` | Committed — calibration history |
| `/reviewers:audit [<reviewer>]` | Hygiene review. Runs agents against current code state, returns findings. Auto-detects framework vs project target. | `<reviewer>` optional positional; `--target {framework\|project}` override; `--affected` (gate-internal) | `.framework/audit/latest/` | Ephemeral, gitignored, overwritten each run |
| `/reviewers:gate` | Pre-commit gate. Affected-only audit, writes marker, exit code drives the PreToolUse hook. | None (always operates on staged set) | `.framework/audit/latest/` + `.framework/audit/marker.json` | Ephemeral, gitignored |

The slash command files live in `.claude/commands/` in the framework repo, and (for `audit` + `gate`) in `src/framework_cli/template/.claude/commands/` so they ship to generated projects.

### Shared infrastructure: the dispatch

All three commands invoke the `Workflow` tool with a saved JS script. The framework repo carries:

- `.claude/workflows/reviewers-tune.js` — fans out per (agent × fixture × repeat). Wraps each call's response as the per-call JSON record schema established in the prior harness work.
- `.claude/workflows/reviewers-audit.js` — fans out per agent (one call each, no fixture/repeat dimension).
- `.claude/workflows/reviewers-gate.js` — same as audit but scoped to affected agents and writes the marker.

Each workflow:
- Uses the `Workflow` tool's built-in parallelism (capped at `min(16, cpu_count - 2)` concurrent agent calls automatically).
- Uses `schema:` on each `agent()` call to enforce JSON-findings shape (validated at the tool layer; no DIY parsing required).
- Captures the same `report` dict shape the prior harness work standardized: `findings`, `usage`, `latency_ms`, `stop_reason`, `turns`, `tool_calls`, `raw_text`.
- Writes one JSON record per call to the appropriate `findings/` subdirectory.

Generated projects ship `audit` and `gate` workflows via the template; `tune` ships only in the framework repo (projects don't tune because they don't own the fixtures).

### Subagent type and fidelity constraint

The 11 bundle-tier agents are single-call. The 7 agentic-tier agents drive a multi-turn tool-use loop. The production sandbox for agentic agents exposes exactly three tools: `read_file`, `grep`, `glob`, root-confined.

For local dispatch, the agentic tier uses the **`Explore` subagent type** — CC's read-only agent that has `Read`, `Grep`, `Glob` (plus `Bash`, `WebFetch`, `WebSearch`, etc.). The first three mirror production; the others are wider than the production sandbox.

The fidelity constraint is enforced in two layers:

1. **Soft constraint (prompt):** the subagent prompt explicitly instructs use of only `Read`, `Grep`, `Glob` and forbids `Bash`, `WebFetch`, `WebSearch`, etc.
2. **Hard constraint (drift detection in `eval-analyze`):** a whitelist of `{"Read", "Grep", "Glob"}` is checked against every record's `tool_calls`. Any call using a tool outside the whitelist is surfaced in a `## Drift check` section of the analyze report. A new `--strict` flag on `eval-analyze` exits with code 2 on any drift (used in the gate context to fail-on-drift; interactive use just warns).

The escalation path — if drift turns out to be a real problem — is to define a custom CC subagent type with only `Read`, `Grep`, `Glob` available. That's deferred (it requires custom-agent-type setup and is premature without evidence of drift).

The bundle tier uses the `general-purpose` subagent type for single-call dispatch (the agent prompt does not request tools; the response is the JSON findings array). No drift surface for bundle agents — no tool use to monitor.

---

## Slice E1 — `/reviewers:tune [<reviewer>]`

### Behavior

1. Resolve target agents: one if `<reviewer>` arg supplied, all 18 from `agent_names()` otherwise.
2. Load fixtures via the existing `load_fixtures(Path("tests/eval/fixtures"))`.
3. Compute the slug: `--slug` arg if given, else `git rev-parse --short HEAD`.
4. Create the dated output dir: `docs/superpowers/eval-scorecards/$(date +%Y-%m-%d)-<slug>/findings/`.
5. Pre-flight estimate: print `N calls × ~M sec/call ≈ K min wall time` and a subagent-quota note. If N > 30, confirm with the user before invoking the Workflow tool.
6. Invoke `reviewers-tune.js` workflow with args: agent set, fixtures (loaded), repeat count, output dir.
7. Workflow fans out subagent calls in parallel, writes each call's record to `<output>/findings/<agent>/<kind>/<case>__r<i>.json`.
8. After workflow completion: run `framework eval-analyze <output>/findings --out <output>/scorecard.md`.
9. Extract the `## Proposed thresholds.yaml` block from `scorecard.md` into `<output>/thresholds.proposal.yaml`.
10. Write `<output>/apply.md` — instructions for Claude on how to apply the proposal (review the diff against `tests/eval/fixtures/thresholds.yaml`, sanity-check against observed values in `scorecard.md`, copy approved entries, commit referencing this dir).
11. Write `<output>/meta.json` — `{git_ref, model_used, fixture_set_hash, repeat, agent_count, subagent_call_count, run_duration_seconds, drift_detected: bool}`.
12. Print the dir path and scorecard summary to the conversation.

### Inputs

- `<reviewer>` positional (optional): single agent name (e.g., `security`). No arg means all 18.
- `--repeat N` (default `3`): number of repeats per fixture. `--repeat 1` for cheap shape-only passes.
- `--slug <name>` (default short git ref): directory suffix for human readability.

### Output artifacts

```
docs/superpowers/eval-scorecards/YYYY-MM-DD-<slug>/
├── findings/
│   └── <agent>/<kind>/<case>__r<i>.json     # raw per-call records
├── scorecard.md                              # eval-analyze output
├── thresholds.proposal.yaml                  # extracted, ready to apply
├── apply.md                                  # CC instructions for applying
└── meta.json                                 # run metadata
```

The dir is committed to git. Threshold application to `tests/eval/fixtures/thresholds.yaml` is a separate manual step (the user invokes `apply.md`'s instructions through Claude).

### Cost shape

A full `/reviewers:tune --repeat 3` is ~44 fixtures × 3 repeats = 132 subagent calls (~135 with margin). Per-agent invocation (`/reviewers:tune security`) is typically 2-3 fixtures × 3 repeats = 6-9 calls. The Workflow tool runs up to `min(16, cpu-2)` concurrently, so wall time is roughly 10-30 minutes for a full run and 1-3 minutes for a single-agent run.

### Out of scope

- Auto-applying the threshold proposal to `tests/eval/fixtures/thresholds.yaml` (intentional — calibration changes must be reviewed, not snuck in).
- Tuning in generated projects (projects don't own fixtures; advanced users who fork agents would need separate tooling, deferred as future work).

---

## Slice E1 — `/reviewers:audit [<reviewer>]`

### Behavior

1. Auto-detect target: `--target` flag if explicit; otherwise auto-detect from cwd:
   - `src/framework_cli/` present AND `pyproject.toml` declares `name = "swiftwater-framework"` → **framework target**, agent set = `FRAMEWORK_AGENTS`.
   - `.copier-answers.yml` present referencing this framework as `_src_path` → **project target**, agent set = `active_agents("pull_request", read_batteries(...))`.
   - Neither matches → error, instruct user to pass `--target` explicitly or run from inside a relevant repo.
2. Resolve agent set; narrow to single agent if `<reviewer>` arg supplied.
3. Compute the review input the agents see — same shape production `framework review` uses: the diff (`git diff HEAD` by default, or `git diff --cached` when `--affected` is set) plus the assembled context bundle / agentic-loop seed.
4. Output dir: `.framework/audit/latest/`. Overwrite existing contents.
5. Pre-flight estimate: count agents, print N calls and the quota note. If N > 30, confirm.
6. Invoke `reviewers-audit.js` workflow: one subagent call per agent (no fixture/repeat dimension). Each call writes its record to `<output>/findings/<agent>.json`.
7. Generate `<output>/audit-report.md` — a hygiene-focused markdown derived from the records: findings grouped by agent, severity-ordered; the drift-check section; an agentic tool-call summary; a cost-estimate note (since these are subagent calls, the cost report shows ~$0 with a "subagent-dispatched" annotation).
8. Print summary to the conversation: count by severity per agent, link to the full report path.

### Render-then-audit workflow (critical framework-dev pattern)

This pattern must work natively for framework development to be viable without paid runs:

```
cd /tmp
framework new test-app --with workers --with mongodb
cd test-app
/reviewers:audit
```

The audit detects the rendered project via `.copier-answers.yml`, runs project-active agents against the rendered project's source, returns findings. This is how a framework developer asks "did my template change break what the rendered project's review agents catch?" — the closest local proxy for "what happens when a user adopts this framework version." Auto-detection must remain reliable for this loop; regressing it breaks the dogfooding cycle.

### Output artifacts

```
.framework/audit/latest/
├── findings/
│   └── <agent>.json              # one record per agent (no fixture/repeat dimension)
└── audit-report.md               # human-readable findings + drift check
```

Lifecycle: overwritten each run, gitignored. Path is stable so the gate (E2) knows where to look.

### Why one record per agent

There are no fixtures in audit — agents review the current code once, not against known-truth seeded defects. The record schema is the same as tune's records (same `report` dict shape), but the `kind` / `case` / `repeat` dimensions don't apply; they default to `kind="current"`, `case="<agent>"`, `repeat=0`. The `eval-analyze` module's `recall_diagnosis` and `fp_diagnosis` sections are no-ops on audit records (no ground truth to compare against); the `cost_report`, `agentic_behavior`, `drift_check`, and `scorecard`-equivalent sections still produce useful output.

### Preservation of audit evidence (rare case)

Audit output is ephemeral by default — committing every audit produces a graveyard of stale per-developer snapshots. The rare case where an audit finding warrants preservation (e.g., it caught a real bug; you want the original finding committed alongside the fix as discovery-evidence) is handled by **manual excerpt**: the developer copies the relevant snippet from `audit-report.md` into the commit message or PR description. The file path is stable, so excerpting is easy. No tooling needed.

---

## Slice E1 — `eval-analyze` enhancements

The existing `framework eval-analyze` command needs three additions to support local dispatch:

### Drift detection

A new `drift_check(records)` function in `src/framework_cli/review/analyze.py`:
- Whitelist: `_ALLOWED_LOCAL_TOOLS = {"Read", "Grep", "Glob"}`.
- For each record, examine `tool_calls`. Any entry whose `tool` field is outside the whitelist is a drift record.
- Returns `list[dict]` with `{agent, case, repeat, disallowed_tools: list[str], counts: dict[str, int]}`.

`render_markdown` adds a `## Drift check` section listing every drifted call. If empty: `_(no drift detected — all tool calls within the production sandbox)_`.

### `--strict` flag

A new flag on `eval-analyze`:
- Default (interactive): drift warnings are printed but exit code is 0.
- `--strict`: any drift causes exit code 2. Used by `/reviewers:gate` to fail-on-drift.

### Schema tolerance for audit records

`load_records` becomes tolerant of records without `kind` / `case` / `repeat`:
- Missing `kind` → defaults to `"current"`.
- Missing `case` → defaults to the agent name.
- Missing `repeat` → defaults to `0`.

The diagnosis functions (`recall_diagnosis`, `fp_diagnosis`) gracefully skip records where `seeded_file` is absent or `kind == "current"`. The scorecard regenerator (`scorecard`) similarly skips agents with no fixture-shaped records. Practical effect: `eval-analyze` works on tune dirs (fixture-shaped) and audit dirs (current-state) without flags; it just shows different sections depending on what data is present.

---

## Slice E2 — `/reviewers:gate`

### Behavior

1. Compute affected agents from staged files (`git diff --cached`) using the mapping below.
2. Auto-detect target (framework vs project), same as audit.
3. **Special case: thresholds-only change.** If the staged set is exactly `tests/eval/fixtures/thresholds.yaml` and nothing else, do a **regrade**: re-flag the most recent `.framework/audit/latest/findings/` records under the new thresholds (pure recomputation, no subagent dispatch). Verdict is PASS if all agents still meet their new thresholds, FAIL otherwise. Fast, deterministic, no LLM calls.
4. Otherwise: dispatch the gate workflow (`reviewers-gate.js`) — same as audit, but scoped to affected agents only.
5. Run `eval-analyze --strict` against `.framework/audit/latest/findings/` — fail the gate if drift is detected.
6. Compute `staged_hash`: sha256 of the concatenated contents of all review-relevant staged files (deterministic; reverts and whitespace-only changes invalidate; ordering is stable).
7. Write `.framework/audit/marker.json`:
   ```json
   {
     "staged_hash": "sha256:abc123...",
     "agents_run": ["security", "architecture"],
     "verdict": "PASS",
     "drift_detected": false,
     "timestamp": "2026-05-29T18:30:00Z",
     "summary": "2 agents · 0 findings above block threshold"
   }
   ```
8. Exit code: 0 on PASS, 1 on FAIL (findings above block threshold OR drift detected).

### Affected mapping (gating)

The map fires only for gating; calibration is always full-sweep by default.

| Changed in staged set | Effect on gate scope |
|---|---|
| `src/framework_cli/review/agents/<name>.md` | re-eval just `<name>` |
| `tests/eval/fixtures/<agent>/...` | re-eval just `<agent>` |
| `src/framework_cli/review/runner.py` | re-eval **all 11 bundle agents** |
| `src/framework_cli/review/agentic.py` | re-eval **all 7 agentic agents** |
| `src/framework_cli/review/context.py` | re-eval **all 18** (assembly affects everything) |
| `src/framework_cli/review/findings.py` | re-eval **all 18** (parse/severity) |
| `src/framework_cli/review/registry.py` | re-eval **all 18** (model/policy spec) |
| `src/framework_cli/template/**` | re-eval **all 18** (fixtures render from template) |
| `tests/eval/fixtures/thresholds.yaml` | **regrade-only**, no subagent dispatch |
| Anything else | **no agents** → gate trivially PASSes (no review-relevant changes) |

For generated projects (the template-shipped gate), the equivalent mapping is computed from the project's own structure:
- `<project>/src/<package>/**` and `<project>/tests/**` → no review-eval gate fires (project source is what the review agents review *for*, not what affects how they review).
- Generated `.github/workflows/review.yml` and the project's own slash command files → re-eval all project-active agents.

### Output

```
.framework/audit/latest/
├── findings/<agent>.json
├── audit-report.md
└── ../marker.json                    # at .framework/audit/marker.json
```

Marker is the single source of truth the PreToolUse hook reads.

---

## Slice E2 — `PreToolUse` hook

### What it intercepts

A new entry in `.claude/settings.json` (alongside the existing CLAUDE.md commit-gate hook):

- Trigger: `Bash` tool calls where the command contains `git commit` (matches via regex similar to the existing hook).
- Fires only when Claude (or another AI assistant in CC) invokes the Bash tool. Manual human `git commit` in the terminal does NOT fire this hook — those commits are gated by CI on the GHA side.

### What it does

A small shell script (lives at `.claude/hooks/reviewers-gate-check.sh` in framework, shipped to template):

1. Read `.framework/audit/marker.json`. If absent → block with directive.
2. Compute the current `staged_hash` from `git diff --cached` over review-relevant staged files.
3. Compare to marker's `staged_hash`. If mismatch → block with directive.
4. Check marker's `verdict`. If FAIL → block with the marker's `summary`.
5. If PASS and `drift_detected: false` and hashes match → allow.
6. If `drift_detected: true` → block with drift warning.

### Block directives

When the hook blocks, the message is a directive Claude reads and acts on autonomously (mirrors how the existing CLAUDE.md commit-gate hook works):

- **Stale/missing marker:**
  `"Pre-commit gate not run for current staged set. Invoke /reviewers:gate, then retry this commit."`
- **FAIL verdict:**
  `"Pre-commit gate FAILED: <marker.summary>. Address findings in .framework/audit/latest/audit-report.md and re-evaluate, then retry. To override (rare): commit with --no-verify."`
- **Drift detected:**
  `"Drift detected during last gate run: subagent used disallowed tools (see .framework/audit/latest/audit-report.md '## Drift check'). Investigate before committing."`

Claude reads the directive, invokes `/reviewers:gate` (which dispatches subagents, writes the new marker), and retries the Bash commit. If the new marker is PASS, the hook allows on retry. If FAIL, the hook blocks again with the new findings, and Claude either addresses them or surfaces them to the user.

### From the user's perspective

The user says "commit this change." Claude does the rest:
1. Invokes Bash to commit.
2. Hook blocks with directive.
3. Claude invokes `/reviewers:gate`.
4. Gate dispatches subagents, writes marker.
5. Claude retries Bash commit.
6. Hook allows, commit succeeds.

One user action, transparent gate. The slash command remains manually invokable for pre-warming or debugging.

### Why this works (and what it doesn't cover)

CC `PreToolUse` hooks fire only on tool calls Claude makes. They are *not* a universal pre-commit gate. Specifically:

- Manual human commits typed in the terminal: not gated locally. CI is the gate.
- Commits in non-CC environments: not gated locally. CI is the gate.
- AI/agent commits in CC: gated.

This asymmetry is intentional. Most undisciplined commits come from AI agents that don't pause to think; humans typing `git commit` have explicit intent. The hook gates the high-risk path; CI gates everyone else. No marker-staleness drama for non-CC users (they never produce or read markers).

---

## Slice E2 — Template shipping

### What ships to generated projects

In `src/framework_cli/template/`:

```
.claude/
├── commands/
│   ├── reviewers:audit.md.jinja
│   └── reviewers:gate.md.jinja
├── workflows/
│   ├── reviewers-audit.js.jinja
│   └── reviewers-gate.js.jinja
├── hooks/
│   └── reviewers-gate-check.sh.jinja
└── settings.json.jinja                # includes the PreToolUse hook entry
```

Plus `.gitignore.jinja` adds:
```
.framework/audit/
```

### What does NOT ship

- `/reviewers:tune` and its workflow — projects don't own fixtures, so tuning is framework-only.
- `tests/eval/fixtures/` — same reason.
- `docs/superpowers/eval-scorecards/` — same reason.

### Project-side defaults

Generated projects' `/reviewers:audit` and `/reviewers:gate` default to `--target project` (auto-detected via `.copier-answers.yml`). The agent set is computed from the project's recorded batteries (existing `read_batteries(Path("."))` + `active_agents("pull_request", batteries)` machinery).

### Verification

The slice is "done for templates" only after a freshly-rendered project's `/reviewers:audit` and `/reviewers:gate` run successfully against the project's source. The render-then-audit workflow described in the audit section verifies this.

---

## Constraints

### Subagent quota varies by CC subscription tier

CC does not expose the builder's subscription tier to slash commands or workflows. Concrete numbers:

- A full `/reviewers:tune --repeat 3`: ~135 subagent calls.
- A full `/reviewers:audit` (framework target): 6 calls.
- A full `/reviewers:audit` (project target, baseline): typically 10-15 calls.
- Single-agent invocations: 1-9 calls.

The 5-hour quota window resets to its tier-specific allowance. On generous tiers (Max), full tune runs are near-free. On constrained tiers (Pro), a full tune may consume a substantial fraction of the window; on Free, it may exceed it.

### Mitigations

Without detection, we provide transparency and graceful chunking:

1. **Pre-flight estimate** in every slash command (before invoking the Workflow tool):
   ```
   /reviewers:tune all 18 agents × ~2.5 fixtures × 3 repeats = ~135 subagent calls
   Estimated wall time: 10-30 min.
   Subagent quota note: scales with your CC subscription tier; on
   constrained tiers this may consume significant 5-hour quota.
   /reviewers:tune <reviewer> runs one agent (~6-9 calls) for iteration.
   ```
2. **Confirmation prompt for large runs:** slash command instructions tell Claude to confirm with the user before dispatching if N > 30.
3. **Per-agent invocation** as a built-in chunking primitive (the `<reviewer>` positional arg).
4. **`--repeat 1`** for cheap shape-only passes (lose averaging stability, get the recall/fp shape).
5. **`--dry-run` flag** prints the plan and exits without dispatching (safety check).
6. **Documentation** in each slash command's `.md` file explicitly explains the quota tradeoff.

### What `budget.total` is NOT for

The Workflow tool's `budget` global tracks per-turn output-token targets (set by user prompts like "+500k"). It is not a subscription-quota signal and is not used here.

---

## Acceptance criteria

### Slice E1

1. `/reviewers:tune` runs successfully against a single agent (`/reviewers:tune security`) end-to-end: dispatch, record write, eval-analyze, scorecard, thresholds proposal, apply.md, meta.json.
2. `/reviewers:tune` (no arg, full sweep, `--repeat 3`) runs successfully against all 18 agents and commits the dated scorecard dir.
3. Drift check passes on the full run (`drift_detected: false` in meta.json).
4. The user follows `apply.md`'s instructions to produce a calibrated `tests/eval/fixtures/thresholds.yaml`, committed alongside the scorecard dir.
5. `/reviewers:audit` works in the framework repo: detects framework target, runs FRAMEWORK_AGENTS subset, produces audit-report.md.
6. `/reviewers:audit` works in a freshly-rendered test project: detects project target, runs project-active agents, produces audit-report.md.
7. `eval-analyze` produces useful output when pointed at either a tune dir or an audit dir (handles missing fixture dimensions gracefully).
8. `eval-analyze --strict` exits 2 when drift is present in the records.
9. All existing tests still pass (`uv run pytest -q --ignore=tests/acceptance`, ruff/format/mypy clean).

### Slice E2

1. `/reviewers:gate` correctly identifies affected agents from the staged set per the mapping.
2. `/reviewers:gate` writes `.framework/audit/marker.json` with the correct `staged_hash`, `verdict`, and `drift_detected`.
3. `/reviewers:gate` performs a regrade (no subagent dispatch) when the staged set is exactly `tests/eval/fixtures/thresholds.yaml`.
4. The `PreToolUse` hook blocks an AI-invoked `git commit` when the marker is missing or stale, with the correct directive message.
5. Claude responds to the block by invoking `/reviewers:gate`, then retrying the commit; the hook allows on the retry if PASS.
6. The hook blocks on a FAIL marker with the findings summary; Claude relays this to the user.
7. The template-shipped versions of `audit`, `gate`, the hook, and the workflows produce a fresh project that has working local gating from first commit.
8. `.framework/audit/` is in both the framework's `.gitignore` and the template-shipped `.gitignore.jinja`.

---

## Out of scope (future work)

- **Slice E3 — Paid API anchor.** Periodic real-API runs to verify the local subagent results haven't drifted from production-model behavior on the agentic tier (which uses `claude-opus-4-8` in production, vs. the subagent's session model). This is what the original Slice D "key-gated tail" intended; it becomes optional periodic verification rather than the primary calibration mechanism.
- **Custom subagent type for the agentic tier.** If drift detection consistently finds disallowed tool usage, escalate from soft-prompt constraint to a custom CC subagent type with exactly `Read`, `Grep`, `Glob`. Deferred until evidence shows the soft constraint is insufficient.
- **Project-side tuning.** Generated projects don't own fixtures. Advanced users who fork agent prompts in their projects might want to recalibrate locally. Tooling for that case is deferred — likely a "bring your own fixtures" extension to `/reviewers:tune` shipped to templates.
- **Automated `--apply` for threshold proposals.** Intentionally manual — calibration changes must be reviewed, not auto-merged.
- **Git-level `pre-commit` hooks** (universal across CC and non-CC commits). Deferred; CC PreToolUse + CI is the chosen design. Adding a git hook would re-introduce the marker-staleness friction for non-CC users that the current design avoids.

---

## Open risks

1. **Subagent fidelity vs production model.** Even with drift check passing, the subagent's session model differs from production's per-agent model (`claude-opus-4-8` for agentic, `claude-sonnet-4-6` for bundle). Local recall/fp is a *shape signal* — the right way to detect regressions and tune iteratively — but is not authoritative for production-floor numbers on the agentic tier. The paid API anchor (E3 future work) is the only way to close that gap fully.
2. **Quota exhaustion mid-run on constrained tiers.** If a builder on Free or low-tier Pro starts a full tune and hits quota, the Workflow tool will error on subsequent calls. Currently the workflow has no resume-from-where-it-stopped support; a partial run leaves a partial scorecard dir that the builder would have to either complete later (re-dispatching the remaining work manually) or discard. Resume support is plausible follow-up; not in scope here.
3. **Hook ordering with the existing CLAUDE.md commit-gate.** Both hooks intercept the same `Bash git commit` calls. They must compose cleanly: CLAUDE.md staging check first (so the gate isn't run against a commit that's missing the state-pointer update), then reviewers-gate check. Hook ordering in `.claude/settings.json` needs to be deterministic; if not, this design needs revision.
4. **Auto-detection failure for unusual repos.** If a builder is in a repo that's neither the framework nor a copier-rendered project (e.g., a fork that's been renamed or restructured), audit/gate will error and require `--target`. Acceptable, but worth a clear error message.
5. **Marker staleness across branch switches.** Switching branches changes the staged hash; the marker becomes stale. The hook correctly blocks on this. Annoying for branch-switchers but correct behavior.

---

## Implementation notes (informational; details belong in the plan)

- Workflow scripts use `agent()` with `schema:` for structured findings output (validated at the tool layer).
- Workflow scripts use `phase()` for progress grouping in the `/workflows` view.
- The per-call JSON record schema is already defined and tested as part of Slice D's instrumentation work — no schema migration needed; just additional records flowing through.
- `eval-analyze`'s schema tolerance changes need tests covering both fixture-shaped and current-state-shaped records.
- The `PreToolUse` hook shell script must be lightweight (sub-100ms) to not feel like a delay.
