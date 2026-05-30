---
description: Tune review-agent thresholds by running them against rendered fixtures via local subagents (no paid API). Optional positional arg = single agent name.
---

You are running the `/reviewers:tune` workflow. Your job: dispatch the subagent-backed tune pipeline and produce a calibration scorecard.

**Inputs:**
- Optional positional arg: single agent name (e.g., `security`). No arg = all 18 agents.
- Optional flags: `--repeat N` (default 3), `--slug <name>` (default short git ref).

**Steps:**

1. **Parse the user's arguments** from the slash command invocation. Extract the optional agent name and any flags. Default `--repeat 3`, `--slug <git rev-parse --short HEAD>`.

2. **Compute the output dir:**
   ```bash
   DATE=$(date +%Y-%m-%d)
   SLUG=<from --slug or short git ref>
   OUT="docs/superpowers/eval-scorecards/${DATE}-${SLUG}"
   mkdir -p "${OUT}"
   ```

3. **Cleanup any prior split-manifest dir** (explicit clean slate; `--split-to` also does an idempotent rewrite, but be explicit):
   ```bash
   rm -rf /tmp/reviewers-tune-items/
   ```

4. **Run eval-prepare with `--split-to`** via Bash. The split-manifest write is what makes the full-sweep workflow callable — a full ~132-item manifest is ~1.76MB which is too large to pass inline as `args` to the Workflow tool. With `--split-to`, eval-prepare writes a tiny per-item index + one file per work item; the Workflow takes just the two paths as args.
   ```bash
   uv run framework eval-prepare --mode tune \
     ${AGENT:+--agent "$AGENT"} \
     --fixtures tests/eval/fixtures \
     --repeat "$REPEAT" \
     --output-dir "$OUT" \
     --split-to /tmp/reviewers-tune-items/ > /tmp/reviewers-tune-prep.json
   ```

5. **Read the small index** (`/tmp/reviewers-tune-items/index.json`) to count items + print the pre-flight estimate. Do NOT load the full `/tmp/reviewers-tune-prep.json` (it's the bulky manifest; only `eval-prepare` itself needs to write that — the Workflow won't see it).

6. **Print a pre-flight estimate** to the user:
   - Number of work items (from `index.items.length`).
   - Estimated wall time: 10-30 min for full sweep; 1-3 min for single-agent.
   - **Subagent quota note**: scales with CC subscription tier; on constrained tiers this run may consume significant 5-hour quota. Single-agent invocation (`/reviewers:tune <reviewer>`) is much cheaper.

7. **If work item count > 30**, **confirm with the user** before proceeding. ("This will dispatch N subagent calls — proceed?")

8. **Invoke the Workflow tool**:
   - `name`: `"reviewers-tune"` (resolves to `.claude/workflows/reviewers-tune.js`)
   - `args`: a small JSON object pointing at the split layout:
     ```json
     {
       "indexPath": "/tmp/reviewers-tune-items/index.json",
       "itemsDir": "/tmp/reviewers-tune-items/items",
       "meta": {"slug": "<slug>", "repeat": <repeat>}
     }
     ```
   - This runs in the foreground; wait for the result.

9. **Write the Workflow's returned `{results, meta}` to a temp file**:
   ```bash
   # Claude writes the workflow result JSON to /tmp/reviewers-tune-results.json via Write tool.
   ```

10. **Run eval-finalize**:
    ```bash
    uv run framework eval-finalize --mode tune \
      --results /tmp/reviewers-tune-results.json \
      --out-dir "$OUT"
    ```

11. **Print a summary** to the user: the output dir path, the number of agents that PASS/FAIL, and pointers to:
    - `<OUT>/scorecard.md` for the full report.
    - `<OUT>/thresholds.proposal.yaml` for the proposed threshold values.
    - `<OUT>/apply.md` for instructions on how to apply the proposal.

12. **Suggest the next step** to the user: "Review `<OUT>/scorecard.md` (especially `## Drift check`), then say 'apply the thresholds from `<OUT>`' to update `tests/eval/fixtures/thresholds.yaml`."

**Important notes:**
- This command runs entirely on CC subagents (subscription quota), NOT the paid Anthropic API.
- If any subagent calls fail mid-workflow, the workflow still returns partial results — eval-finalize handles missing data gracefully but the scorecard will be incomplete. Re-run if needed.
- Do NOT auto-apply the proposal to `tests/eval/fixtures/thresholds.yaml`. Threshold changes are deliberate; the user invokes `apply.md`'s instructions.
- The output dir is committed to git as part of the calibration history.
- The `/tmp/reviewers-tune-items/` split-manifest dir is ephemeral — safe to delete after the run.
