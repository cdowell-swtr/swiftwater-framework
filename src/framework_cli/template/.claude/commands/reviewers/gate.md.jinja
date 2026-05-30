---
description: Pre-commit gate. Affected-only review of the staged set, writes the marker the PreToolUse hook reads. Usually invoked automatically by the hook, but can be run manually to pre-warm.
---

You are running `/reviewers:gate`. Your job: evaluate the staged set with the affected review agents, write `.framework/audit/marker.json`.

**Steps:**

1. **Run gate-prepare** (writes BOTH a stdout manifest AND a split-manifest layout
   under `/tmp/reviewers-gate-prep-split/` for the Workflow-tool args; the split
   layout exists because the inline manifest can exceed the ~1.76MB Workflow-args
   ceiling for large staged sets):
   ```bash
   rm -rf /tmp/reviewers-gate-prep-split 2>/dev/null
   uv run framework gate-prepare --split-to /tmp/reviewers-gate-prep-split > /tmp/reviewers-gate-prep.json
   ```

2. **Read the prep manifest** (from `/tmp/reviewers-gate-prep.json` — the stdout
   manifest is still the source of truth for branching on `mode`).

3. **Branch on mode**:

   **If `mode == "noop"`** (no review-relevant files staged):
   - Run gate-finalize directly (it writes a PASS marker with empty agents_run):
     ```bash
     echo '{"results": [], "meta": '$(cat /tmp/reviewers-gate-prep.json | jq '{mode, staged_hash, agents_set}')'}' > /tmp/reviewers-gate-results.json
     uv run framework gate-finalize \
       --results /tmp/reviewers-gate-results.json \
       --out-dir .framework/audit/latest
     ```
   - Print: "Gate noop — no review-relevant changes."
   - DONE.

   **If `mode == "regrade"`** (only thresholds.yaml staged):
   - Run gate-finalize directly (it re-flags existing findings against current thresholds):
     ```bash
     echo '{"results": [], "meta": '$(cat /tmp/reviewers-gate-prep.json | jq '{mode, staged_hash, agents_set}')'}' > /tmp/reviewers-gate-results.json
     uv run framework gate-finalize \
       --results /tmp/reviewers-gate-results.json \
       --out-dir .framework/audit/latest
     ```
   - Print: "Gate regrade — re-flagged existing findings against new thresholds."
   - DONE.

   **If `mode == "gate"`** (the normal case):
   - Print a one-line summary: "Gate: N affected agents (<list>). Dispatching..."
   - If N > 30, confirm with the user.

4. **Invoke the Workflow tool** (`name: "reviewers-gate"`). Build the `args`
   object as `{indexPath, itemsDir, meta}` where:
   - `indexPath` is `"/tmp/reviewers-gate-prep-split/index.json"`
   - `itemsDir` is `"/tmp/reviewers-gate-prep-split/items"`
   - `meta` is `{mode, staged_hash, agents_set}` copied from the stdout prep
     manifest at `/tmp/reviewers-gate-prep.json` (use `jq` or read the JSON
     directly, e.g. `jq '{mode, staged_hash, agents_set}' /tmp/reviewers-gate-prep.json`).

   The workflow loads the index from disk and dispatches one subagent per item
   (each subagent reads its own item file). Inline `work_items` is no longer
   passed — the split-manifest layout keeps the Workflow-args payload tiny.

5. **Write the workflow's `{results, meta}` to a temp file** (`/tmp/reviewers-gate-results.json`).

6. **Run gate-finalize**:
   ```bash
   uv run framework gate-finalize \
     --results /tmp/reviewers-gate-results.json \
     --out-dir .framework/audit/latest
   ```

7. **Clean up the transient `/tmp` split-manifest and results** (item files contain the full unified diff; remove them after finalize so they don't linger between runs):
   ```bash
   rm -rf /tmp/reviewers-gate-prep-split /tmp/reviewers-gate-prep.json /tmp/reviewers-gate-results.json 2>/dev/null || true
   ```

8. **Print the verdict** from `.framework/audit/marker.json`:
   - PASS: "Gate PASS — marker written. Commit can proceed."
   - FAIL: "Gate FAIL — see `.framework/audit/latest/audit-report.md` for findings."

**Important notes:**
- This command is usually invoked automatically by the PreToolUse hook when you (Claude) try to commit. You can also invoke it manually to pre-warm the marker before a commit.
- The output is **ephemeral** — `.framework/audit/` is gitignored.
- The hook reads `.framework/audit/marker.json` to decide whether to allow the commit; if you skip running the gate, the hook will block your commit until you run it.
