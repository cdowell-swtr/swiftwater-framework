---
description: Hygiene review — run review agents against current code state via local subagents (no paid API). Auto-detects framework vs project target. Optional positional arg = single agent shortcut; --agents a,b,c for a subset; --preserve-as <dir> [--force] to snapshot the run as a dated baseline under docs/superpowers/eval-scorecards/audit-…/.
---

You are running the `/reviewers:audit` workflow. Your job: dispatch the subagent-backed audit pipeline and surface what the review agents would flag in the current code state.

**Inputs:**
- Optional positional agent name (single-agent shortcut, e.g. `security`). If `--agents` is also passed, `--agents` wins.
- Optional flag: `--target {framework|project}` (default: auto-detect).
- Optional flag: `--agents a,b,c` — comma-separated list to run a specific subset of agents. Each name is validated against the active roster for the target; unknown agent names cause `audit-prepare` to exit non-zero with the list of valid names. If both `--agents` and the positional argument are passed, `--agents` wins.
- Optional flag: `--preserve-as <dir>` — after finalize, copy `.framework/audit/latest/` into `<dir>` (a dated baseline directory parallel to the tune scorecards under `docs/superpowers/eval-scorecards/`). Refuses to overwrite a non-empty target unless `--force` is also passed.
- Optional flag: `--force` — overwrite a non-empty `--preserve-as` target.

**Steps:**

1. **Parse the user's arguments**. Extract the optional positional agent name, `--target`, `--agents`, `--preserve-as`, and `--force`. Bind the parsed values to shell vars `AGENT`, `AGENTS`, `TARGET`, `PRESERVE_AS`, `FORCE` (empty if not supplied) so the snippets below can reference them.

2. **Run audit-prepare** via Bash. Build the agent flag list from the `--agents` arg (comma-split) and pass each as a separate `--agent` flag. If `--agents` is not set, fall back to the positional agent name (if any):
   ```bash
   AGENT_FLAGS=""
   if [ -n "$AGENTS" ]; then
     IFS=',' read -ra ARR <<< "$AGENTS"
     for a in "${ARR[@]}"; do AGENT_FLAGS="$AGENT_FLAGS --agent $a"; done
   elif [ -n "$AGENT" ]; then
     AGENT_FLAGS="--agent $AGENT"
   fi
   uv run framework audit-prepare \
     ${TARGET:+--target "$TARGET"} \
     $AGENT_FLAGS \
     --output-dir .framework/audit/latest > /tmp/reviewers-audit-prep.json
   ```
   If audit-prepare errors with "Could not auto-detect target," inform the user and suggest `--target framework` or `--target project`.

3. **Read the prep manifest** and inspect the work-item count.

4. **Print a pre-flight estimate** to the user:
   - Target detected (framework or project).
   - Number of agents being run.
   - Estimated wall time: ~30s-2min per agent.
   - Subagent quota note (scales with subscription tier).

5. **If work item count > 30**, **confirm with the user** before proceeding.

6. **Invoke the Workflow tool**:
   - `name`: `"reviewers-audit"`
   - `args`: the JSON loaded from the prep manifest
   - Wait for the result in the foreground.

7. **Write the workflow's returned `{results, meta}` to a temp file**:
   ```bash
   # Claude writes /tmp/reviewers-audit-results.json via Write tool.
   ```

8. **Run audit-finalize**:
   ```bash
   uv run framework audit-finalize \
     --results /tmp/reviewers-audit-results.json \
     --out-dir .framework/audit/latest \
     ${PRESERVE_AS:+--preserve-as "$PRESERVE_AS"} \
     ${FORCE:+--force}
   ```

9. **Clean up transient `/tmp` artifacts** (the prep + results files contain the full diff payload). After this step: the `--preserve-as` baseline under `docs/superpowers/eval-scorecards/audit-…/` is the only repo-persisted output (review it for sensitive findings before committing); `.framework/audit/latest/` is gitignored and overwritten on the next run; `/tmp/reviewers-audit-*.json` are gone. `rm -f` is silent on missing files but will report other errors (permission denied, etc.) so a failed cleanup is visible to the user.
   ```bash
   rm -f /tmp/reviewers-audit-prep.json /tmp/reviewers-audit-results.json
   ```

10. **Print a summary** to the user:
   - Findings count by severity per agent (e.g., "review-security: 2 high, 1 medium").
   - Drift check result.
   - Link: `.framework/audit/latest/audit-report.md` for the full report.

**Important notes:**
- This command runs entirely on CC subagents (subscription quota), NOT the paid Anthropic API.
- Output is **ephemeral** — `.framework/audit/latest/` is overwritten each run and gitignored. The path is stable so `/reviewers:gate` (Slice E2) knows where to look.
- For the rare case where an audit finding warrants preservation as discovery-evidence (caught a real bug being fixed), manually excerpt the relevant snippet from `audit-report.md` into the commit message or PR description.
- Auto-detection: framework target requires `src/framework_cli/` + `pyproject.toml` with `[project].name = "framework-cli"` (parsed via tomllib, tolerant of whitespace variations). Project target requires `.copier-answers.yml`. Neither matches → error, pass `--target` explicitly.
