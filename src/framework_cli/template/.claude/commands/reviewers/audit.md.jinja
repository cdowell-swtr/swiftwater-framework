---
description: Hygiene review — run review agents against current code state via local subagents (no paid API). Auto-detects framework vs project target. Optional positional arg = single agent name.
---

You are running the `/reviewers:audit` workflow. Your job: dispatch the subagent-backed audit pipeline and surface what the review agents would flag in the current code state.

**Inputs:**
- Optional positional arg: single agent name (e.g., `security`).
- Optional flag: `--target {framework|project}` (default: auto-detect).

**Steps:**

1. **Parse the user's arguments**. Extract the optional agent name and optional `--target`.

2. **Run audit-prepare** via Bash:
   ```bash
   uv run framework audit-prepare \
     ${AGENT:+--agent "$AGENT"} \
     ${TARGET:+--target "$TARGET"} \
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

8. **Run eval-finalize**:
   ```bash
   uv run framework eval-finalize --mode audit \
     --results /tmp/reviewers-audit-results.json \
     --out-dir .framework/audit/latest
   ```

9. **Print a summary** to the user:
   - Findings count by severity per agent (e.g., "review-security: 2 high, 1 medium").
   - Drift check result.
   - Link: `.framework/audit/latest/audit-report.md` for the full report.

**Important notes:**
- This command runs entirely on CC subagents (subscription quota), NOT the paid Anthropic API.
- Output is **ephemeral** — `.framework/audit/latest/` is overwritten each run and gitignored. The path is stable so `/reviewers:gate` (Slice E2) knows where to look.
- For the rare case where an audit finding warrants preservation as discovery-evidence (caught a real bug being fixed), manually excerpt the relevant snippet from `audit-report.md` into the commit message or PR description.
- Auto-detection: framework target requires `src/framework_cli/` + `pyproject.toml` with `[project].name = "framework-cli"` (parsed via tomllib, tolerant of whitespace variations). Project target requires `.copier-answers.yml`. Neither matches → error, pass `--target` explicitly.
