---
description: Hygiene review — run review agents against current code state via local subagents (no paid API). Auto-detects framework vs project target. Optional positional arg = single agent shortcut; --agents a,b,c for a subset; --snapshot (force all-snapshot) or --since <ref-or-dir> (force all-delta against ref or baseline-dir); --preserve-as <dir> [--force] to snapshot the run as a dated baseline under docs/superpowers/eval-scorecards/audit-…/.
---

You are running the `/reviewers:audit` workflow. Your job: dispatch the subagent-backed audit pipeline and surface what the review agents would flag in the current code state.

**Inputs:**
- Optional positional agent name (single-agent shortcut, e.g. `security`). If `--agents` is also passed, `--agents` wins.
- Optional flag: `--target {framework|project}` (default: auto-detect).
- Optional flag: `--agents a,b,c` — comma-separated list to run a specific subset of agents. Each name is validated against the active roster for the target; unknown agent names cause `audit-prepare` to exit non-zero with the list of valid names. If both `--agents` and the positional argument are passed, `--agents` wins.
- Optional flag: `--preserve-as <dir>` — after finalize, copy `.framework/audit/latest/` into `<dir>` (a dated baseline directory parallel to the tune scorecards under `docs/superpowers/eval-scorecards/`). Refuses to overwrite a non-empty target unless `--force` is also passed.
- Optional flag: `--force` — overwrite a non-empty `--preserve-as` target.
- Optional flag: `--snapshot` — force every agent into snapshot mode (no diff seed; bundled context does the work). Skips per-agent baseline auto-discovery. Mutually exclusive with `--since`.
- Optional flag: `--since <ref-or-dir>` — force delta mode against a chosen anchor. Either a git ref/SHA (every agent diffs HEAD vs that ref) or a baseline directory under `docs/superpowers/eval-scorecards/` (per-agent: agents that were in that baseline diff against its `git_sha`; agents not in that baseline fall back to snapshot). Disambiguation: `audit-prepare` first checks whether the value is an existing path that looks like a baseline dir (a directory containing a readable `meta.json` with a non-empty `git_sha`); if yes, baseline-dir form. Otherwise resolved as a git ref via `git rev-parse --verify`. Mutually exclusive with `--snapshot` — passing both causes `audit-prepare` to exit non-zero with an error message. Examples: `--since 2446de8` (against a SHA), `--since v1.0` (against a tag), `--since docs/superpowers/eval-scorecards/audit-2026-05-30-2446de8` (against a baseline dir; agents not in that baseline silently fall back to snapshot).

Each agent's resolved mode is recorded as `review_mode: "snapshot" | "delta"` in `meta.json`'s `per_agent` block and in each `findings/<agent>.json` record (alongside `base_sha` and `base_baseline` for delta-mode agents).

**Steps:**

1. **Parse the user's arguments**. Extract the optional positional agent name, `--target`, `--agents`, `--preserve-as`, `--force`, `--snapshot`, and `--since`. Bind the parsed values to shell vars `AGENT`, `AGENTS`, `TARGET`, `PRESERVE_AS`, `FORCE`, `SNAPSHOT`, `SINCE` (empty if not supplied) so the snippets below can reference them.

2. **Run audit-prepare** via Bash (writes BOTH a stdout manifest AND a
   split-manifest layout under `/tmp/reviewers-audit-prep-split/` for the
   Workflow-tool args; the split layout exists because the inline manifest can
   exceed the ~1.76MB Workflow-args ceiling for full audits across many
   agents). Build the agent flag list from the `--agents` arg (comma-split)
   and pass each as a separate `--agent` flag. If `--agents` is not set, fall
   back to the positional agent name (if any):
   ```bash
   AGENT_FLAGS=""
   if [ -n "$AGENTS" ]; then
     IFS=',' read -ra ARR <<< "$AGENTS"
     for a in "${ARR[@]}"; do AGENT_FLAGS="$AGENT_FLAGS --agent $a"; done
   elif [ -n "$AGENT" ]; then
     AGENT_FLAGS="--agent $AGENT"
   fi
   rm -rf /tmp/reviewers-audit-prep-split 2>/dev/null
   uv run framework audit-prepare \
     ${TARGET:+--target "$TARGET"} \
     $AGENT_FLAGS \
     ${SNAPSHOT:+--snapshot} \
     ${SINCE:+--since "$SINCE"} \
     --output-dir .framework/audit/latest \
     --split-to /tmp/reviewers-audit-prep-split > /tmp/reviewers-audit-prep.json
   ```
   If audit-prepare errors with "Could not auto-detect target," inform the user and suggest `--target framework` or `--target project`.

3. **Read the prep manifest** and inspect the work-item count.

4. **Print a pre-flight estimate** to the user:
   - Target detected (framework or project).
   - Number of agents being run.
   - Estimated wall time: ~30s-2min per agent.
   - Subagent quota note (scales with subscription tier).

5. **If work item count > 30**, **confirm with the user** before proceeding.

6. **Invoke the Workflow tool** (`name: "reviewers-audit"`). Build the `args`
   object as `{indexPath, itemsDir, meta}` where:
   - `indexPath` is `"/tmp/reviewers-audit-prep-split/index.json"`
   - `itemsDir` is `"/tmp/reviewers-audit-prep-split/items"`
   - `meta` is `{mode, target, agents_set, output_dir}` copied from the
     stdout prep manifest at `/tmp/reviewers-audit-prep.json` (e.g.
     `jq '{mode, target, agents_set, output_dir}' /tmp/reviewers-audit-prep.json`).

   The workflow loads the index from disk and dispatches one subagent per
   item (each subagent reads its own item file). Inline `work_items` is no
   longer passed — the split-manifest layout keeps the Workflow-args payload
   tiny. Wait for the result in the foreground.

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

9. **Clean up transient `/tmp` artifacts** (the prep + results files and the
   per-item split layout all contain the full diff payload AND per-agent
   audit-mode metadata — `review_mode`, `base_sha`, `base_baseline`). After
   step 8 (audit-finalize) completes, that per-agent metadata is durably
   stored in `.framework/audit/latest/meta.json`'s `per_agent` block (and in
   each `findings/<agent>.json` record), so cleaning the `/tmp` layout here
   does not lose traceability. After this step: the `--preserve-as` baseline
   under `docs/superpowers/eval-scorecards/audit-…/` is the only repo-persisted
   output (review it for sensitive findings before committing);
   `.framework/audit/latest/` is gitignored and overwritten on the next run;
   `/tmp/reviewers-audit-*` are gone. `rm -f`/`rm -rf` are silent on missing
   files but will report other errors (permission denied, etc.) so a failed
   cleanup is visible to the user. (If audit-finalize fails before writing
   meta.json, the per-agent metadata in `/tmp/reviewers-audit-prep-split/`
   is the only place it lived — investigate before clearing.)
   ```bash
   rm -rf /tmp/reviewers-audit-prep-split
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
