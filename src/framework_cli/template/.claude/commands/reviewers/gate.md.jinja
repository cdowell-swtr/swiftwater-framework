---
description: Pre-commit gate. Affected-only review of the staged set, writes the marker the PreToolUse hook reads. Usually invoked automatically by the hook, but can be run manually to pre-warm.
---

You are running `/reviewers:gate`. Your job: evaluate the staged set with the affected review agents, write `.framework/audit/marker.json`.

**Steps:**

1. **Run eval-prepare**:
   ```bash
   uv run framework eval-prepare --mode gate > /tmp/reviewers-gate-prep.json
   ```

2. **Read the prep manifest**.

3. **Branch on mode**:

   **If `mode == "noop"`** (no review-relevant files staged):
   - Run eval-finalize directly (it writes a PASS marker with empty agents_run):
     ```bash
     echo '{"results": [], "meta": '$(cat /tmp/reviewers-gate-prep.json | jq '{mode, staged_hash, agents_set}')'}' > /tmp/reviewers-gate-results.json
     uv run framework eval-finalize --mode gate \
       --results /tmp/reviewers-gate-results.json \
       --out-dir .framework/audit/latest
     ```
   - Print: "Gate noop — no review-relevant changes."
   - DONE.

   **If `mode == "regrade"`** (only thresholds.yaml staged):
   - Run eval-finalize directly (it re-flags existing findings against current thresholds):
     ```bash
     echo '{"results": [], "meta": '$(cat /tmp/reviewers-gate-prep.json | jq '{mode, staged_hash, agents_set}')'}' > /tmp/reviewers-gate-results.json
     uv run framework eval-finalize --mode gate \
       --results /tmp/reviewers-gate-results.json \
       --out-dir .framework/audit/latest
     ```
   - Print: "Gate regrade — re-flagged existing findings against new thresholds."
   - DONE.

   **If `mode == "gate"`** (the normal case):
   - Print a one-line summary: "Gate: N affected agents (<list>). Dispatching..."
   - If N > 30, confirm with the user.

4. **Invoke the Workflow tool** (`name: "reviewers-gate"`, `args:` the prep manifest).

5. **Write the workflow's `{results, meta}` to a temp file** (`/tmp/reviewers-gate-results.json`).

6. **Run eval-finalize**:
   ```bash
   uv run framework eval-finalize --mode gate \
     --results /tmp/reviewers-gate-results.json \
     --out-dir .framework/audit/latest
   ```

7. **Print the verdict** from `.framework/audit/marker.json`:
   - PASS: "Gate PASS — marker written. Commit can proceed."
   - FAIL: "Gate FAIL — see `.framework/audit/latest/audit-report.md` for findings."

**Important notes:**
- This command is usually invoked automatically by the PreToolUse hook when you (Claude) try to commit. You can also invoke it manually to pre-warm the marker before a commit.
- The output is **ephemeral** — `.framework/audit/` is gitignored.
- The hook reads `.framework/audit/marker.json` to decide whether to allow the commit; if you skip running the gate, the hook will block your commit until you run it.
