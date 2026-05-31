---
description: Template-payload audit — render the bundled template with all batteries, audit the rendered project with the full project roster (snapshot), map findings back to template source, and preserve a dated scorecard under docs/superpowers/eval-scorecards/template-audit-…/. Framework-only (audits the framework's own template). Runs on subscription subagents, no paid API.
---

You are running the `/reviewers:template-audit` workflow. Your job: audit the **template payload** — the app-domain code the framework audit (`FRAMEWORK_AGENTS`) can't see — by rendering it with all batteries and running the full project review roster against the rendered project.

**Steps:**

1. **Capture the framework repo root + SHA** (you start in the framework repo):
   ```bash
   FW_ROOT=$(git rev-parse --show-toplevel)
   FW_SHA=$(git rev-parse --short HEAD)
   DATE=$(date +%Y-%m-%d)
   DEST="$FW_ROOT/docs/superpowers/eval-scorecards/template-audit-$DATE-$FW_SHA"
   ```

2. **Render the all-batteries audit subject**:
   ```bash
   rm -rf /tmp/template-audit-render /tmp/template-audit-split 2>/dev/null
   uv run framework template-render --out /tmp/template-audit-render
   ```

3. **Prepare the audit** (run IN the render dir so `read_batteries(".")` sees that project's all-batteries roster; snapshot ⇒ whole-tree, no baseline lookup). **Use `uv run --project "$FW_ROOT"`** — a bare `uv run framework` inside the render dir resolves to the *rendered project's* venv (which has `demo` installed, not `framework-cli`) and fails with `Failed to spawn: framework`. `--project` keeps cwd at the render dir while running the framework's own CLI:
   ```bash
   cd /tmp/template-audit-render
   uv run --project "$FW_ROOT" framework audit-prepare --target project --snapshot \
     --output-dir /tmp/template-audit-render/.framework/audit/latest \
     --split-to /tmp/template-audit-split > /tmp/template-audit-prep.json
   cd "$FW_ROOT"
   ```

4. **Read the prep manifest** (`/tmp/template-audit-prep.json`); note `agents_set` (the full ~18-agent project roster). Print a pre-flight estimate (agent count, ~30s–2min each, subscription-quota note). If the work-item count > 30, confirm with the user.

5. **Invoke the Workflow tool** (`name: "reviewers-audit"`) with args `{indexPath: "/tmp/template-audit-split/index.json", itemsDir: "/tmp/template-audit-split/items", meta: <{mode,target,agents_set,output_dir} copied from the prep manifest>}`. Wait for the result in the foreground.

6. **Quota-drop guard:** compare the number of returned `results` to `agents_set`. If any agents are missing (silent subagent-quota drops), re-run `audit-prepare` restricted to the missing agents — **from inside the render dir** so the all-batteries project roster is in effect (a battery-gated agent name like `accessibility`/`api-design` is only valid against the rendered project's roster, not `$FW_ROOT`):
   ```bash
   cd /tmp/template-audit-render
   uv run --project "$FW_ROOT" framework audit-prepare --target project --snapshot \
     --agent <MISSING_1> --agent <MISSING_2> \
     --output-dir /tmp/template-audit-render/.framework/audit/latest \
     --split-to /tmp/template-audit-split-retry > /tmp/template-audit-prep-retry.json
   cd "$FW_ROOT"
   ```
   Dispatch the `reviewers-audit` workflow again for that subset, then merge the new results into the full set before finalizing.

7. **Write the merged `{results, meta}`** to `/tmp/template-audit-results.json` (Write tool).

8. **Finalize** (writes findings/ + audit-report.md + meta.json under the render dir). Run from `$FW_ROOT` (NOT the render dir) — `audit-finalize` stamps `meta.json`'s `git_sha` from the cwd's `git rev-parse HEAD`, so running here records the **framework** SHA (the thing actually being audited). Both paths are absolute, so cwd doesn't affect output location:
   ```bash
   uv run framework audit-finalize \
     --results /tmp/template-audit-results.json \
     --out-dir /tmp/template-audit-render/.framework/audit/latest
   ```

9. **Map findings back to template source** (the triage aid):
   ```bash
   uv run framework template-map \
     --findings /tmp/template-audit-render/.framework/audit/latest/findings \
     --template-root "$FW_ROOT/src/framework_cli/template" \
     --package-name demo
   ```
   This writes `path-map.md` next to the findings dir.

10. **Preserve the scorecard back to the framework repo**:
    ```bash
    mkdir -p "$DEST"
    cp -r /tmp/template-audit-render/.framework/audit/latest/findings "$DEST/"
    cp /tmp/template-audit-render/.framework/audit/latest/audit-report.md "$DEST/"
    cp /tmp/template-audit-render/.framework/audit/latest/meta.json "$DEST/"
    cp /tmp/template-audit-render/.framework/audit/latest/path-map.md "$DEST/"
    ```
    `meta.json`'s `git_sha` is the framework HEAD (step 8 ran from `$FW_ROOT`), matching the dated dir's `$FW_SHA`.

11. **Write `triage.md`** (hand-authored, as with the framework audit): for each finding decide fix-now / defer / false-positive, using `path-map.md` to locate the template source. Save it in `$DEST/triage.md`.

12. **Clean up**:
    ```bash
    rm -rf /tmp/template-audit-render /tmp/template-audit-split /tmp/template-audit-split-retry
    rm -f /tmp/template-audit-prep.json /tmp/template-audit-prep-retry.json /tmp/template-audit-results.json
    ```

13. **Print a summary**: findings count by severity per agent, the `$DEST` path, and a note that `path-map.md` is a best-effort aid (line numbers as-rendered).

**Important notes:**
- Framework-only command — it audits the framework's *own* template; it is intentionally NOT shipped into generated projects.
- Runs entirely on CC subagents (subscription quota), not the paid API.
- The scorecard under `docs/superpowers/eval-scorecards/template-audit-…/` is the repo-persisted output — review it for anything sensitive before committing.
