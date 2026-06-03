# GitHub Actions Node 24 Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin every GitHub Actions `uses:` reference — across the framework's 5 workflows and the generated template's 3 — to a Node-24-capable version, guarded by an allowlist regression test, before the 2026-06-16 forced-Node-24 default.

**Architecture:** Mechanical version bumps on both workflow surfaces, fronted by a single TDD'd allowlist guard (`tests/test_workflow_node24.py`) that raw-scans every `uses:` on both surfaces against an `APPROVED_ACTIONS` source-of-truth map. Docker-container actions (oasdiff, gitleaks) are exempt-but-listed; one action with no Node-24 release yet (`arduino/setup-task`) is a tracked `node20-forced` exception. A maintenance doc records the policy. Ships as `v0.1.7` (template workflows are builder-facing).

**Tech Stack:** Python 3.12, pytest, Copier/Jinja templates, GitHub Actions YAML, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-04-node24-actions-migration-design.md`

**Verified action versions (2026-06-04 — re-confirm if executing later):**

| Action | From | To | Runtime |
|---|---|---|---|
| `actions/checkout` | `@v4` | `@v5` | node24 |
| `astral-sh/setup-uv` | `@v5` | `@v6` | node24 |
| `actions/setup-node` | `@v4` | `@v6` | node24 |
| `actions/upload-artifact` | `@v4` | `@v6` | node24 |
| `actions/download-artifact` | `@v4` | `@v7` | node24 |
| `softprops/action-gh-release` | `@v2` | `@v3` | node24 (v3.0.0 "Move the action runtime… to Node 24") |
| `arduino/setup-task` | `@v2` | **`@v2` (unchanged)** | node20 — **no Node-24 release exists**; `node20-forced` exception |
| `oasdiff/oasdiff-action/breaking` | `@v0.0.21` | unchanged | docker (exempt) |
| `gitleaks/gitleaks-action` | `@v2` | unchanged | docker (exempt) |

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tests/test_workflow_node24.py` | **New.** The allowlist guard: `APPROVED_ACTIONS` map + two per-surface tests + a dynamic-ref guard. The executable policy. | T1 |
| `.github/workflows/{ci,release,render-matrix,review,agent-evals}.yml` | Framework's own workflows — bump Node-20 actions. | T2 |
| `src/framework_cli/template/.github/workflows/{ci.yml.jinja,deploy-prod.yml,deploy-staging.yml}` | Template (builder-inherited) workflows — same bumps. | T3 |
| `docs/maintenance/github-actions-node-runtime.md` | **New.** Maintenance policy note. | T4 |
| `CLAUDE.md` | One-line conventions pointer (+ per-commit state bumps). | T4 / all |
| `pyproject.toml`, `uv.lock`, `src/framework_cli/dogfood.py` | `v0.1.7` release bump. | T5 |

**Exact current `uses:` locations** (for the bump tasks):
- **Framework:** `ci.yml`:16,17,19 · `release.yml`:14,15,34,35,38 · `render-matrix.yml`:25,26,46,47,48,54 · `review.yml`:23,24,41,44,53,67,68,70 · `agent-evals.yml`:29,30. (`release.yml`:22,26 are `uses: ./.github/...` reusable-workflow refs — **not** marketplace actions, left alone.)
- **Template:** `ci.yml.jinja`:21,22,35,36,52,55,60(gitleaks),70,71,78,90,105,106,131,132,149,152,176(oasdiff),228,229,249,252,264,281,282,287 · `deploy-prod.yml`:32,33 · `deploy-staging.yml`:22,45,46.

---

## Task 1: Allowlist guard test (TDD — red against current workflows)

**Files:**
- Create: `tests/test_workflow_node24.py`

- [ ] **Step 1: Write the guard test**

Create `tests/test_workflow_node24.py` with exactly this content:

```python
"""Guard: every GitHub Actions `uses:` ref (framework + generated template) is pinned
to a Node-24-capable action version.

GitHub forces the Node 24 actions runtime by default on 2026-06-16 and removes Node 20
from runners on 2026-09-16. This test is the source of truth for the migration policy;
see docs/maintenance/github-actions-node-runtime.md.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source of truth for the Node-24 action policy. `runtime`:
#   "node"          — JS action; the pinned major must be >= min_major (Node-24-capable).
#   "docker"        — container action; no Node runtime, version floor not checked.
#   "node20-forced" — JS action with no Node-24 release yet; GHA force-runs it on Node 24.
#                     Tracked exception — revisit before the 2026-09-16 Node-20 removal.
APPROVED_ACTIONS: dict[str, dict] = {
    "actions/checkout": {"runtime": "node", "min_major": 5},
    "astral-sh/setup-uv": {"runtime": "node", "min_major": 6},
    "actions/setup-node": {"runtime": "node", "min_major": 6},
    "actions/upload-artifact": {"runtime": "node", "min_major": 6},
    "actions/download-artifact": {"runtime": "node", "min_major": 7},
    "softprops/action-gh-release": {"runtime": "node", "min_major": 3},
    "arduino/setup-task": {"runtime": "node20-forced"},  # no Node-24 release as of 2026-06-04
    "oasdiff/oasdiff-action/breaking": {"runtime": "docker"},
    "gitleaks/gitleaks-action": {"runtime": "docker"},
}

FRAMEWORK_WORKFLOWS = REPO_ROOT / ".github" / "workflows"
TEMPLATE_WORKFLOWS = (
    REPO_ROOT / "src" / "framework_cli" / "template" / ".github" / "workflows"
)

# Anchored: an optional leading "- " then "uses:" at the start of the (stripped) line.
# Avoids matching "uses:" inside a run: script or a comment.
_USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>\S+)")


def _collect_uses(directory: Path) -> list[tuple[Path, int, str]]:
    """(file, lineno, ref) for every marketplace `uses:` under directory.

    Raw-source scan — the template `.jinja` `uses:` values are static strings, never
    Copier-interpolated, so no render is needed. Local reusable-workflow refs
    (`uses: ./...`) are files, not marketplace actions, and are skipped.
    """
    found: list[tuple[Path, int, str]] = []
    files = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yml.jinja"))
    for path in files:
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            m = _USES_RE.match(line)
            if not m:
                continue
            ref = m.group("ref").strip().strip("\"'")
            if ref.startswith("./"):
                continue
            found.append((path, i, ref))
    return found


def _major(version: str) -> int | None:
    m = re.match(r"v?(\d+)", version)
    return int(m.group(1)) if m else None


def _check(directory: Path) -> None:
    refs = _collect_uses(directory)
    assert refs, f"no `uses:` refs found under {directory} — the scan is broken"
    violations: list[str] = []
    for path, lineno, ref in refs:
        where = f"{path.relative_to(REPO_ROOT)}:{lineno}"
        if "{{" in ref or "{%" in ref:
            violations.append(f"{where} dynamic action ref {ref!r} — raw-scan assumption broken")
            continue
        if "@" not in ref:
            violations.append(f"{where} unpinned action {ref!r} (no @version)")
            continue
        action, _, version = ref.partition("@")
        policy = APPROVED_ACTIONS.get(action)
        if policy is None:
            violations.append(
                f"{where} action {action!r} not in APPROVED_ACTIONS — add it with its "
                "Node-24 min_major (or fix the ref)"
            )
            continue
        if policy["runtime"] == "node":
            major = _major(version)
            if major is None or major < policy["min_major"]:
                violations.append(
                    f"{where} {ref} is below the Node-24 floor v{policy['min_major']} (got {version!r})"
                )
    assert not violations, "Node-24 action policy violations:\n" + "\n".join(violations)


def test_framework_workflows_use_node24_actions() -> None:
    _check(FRAMEWORK_WORKFLOWS)


def test_template_workflows_use_node24_actions() -> None:
    _check(TEMPLATE_WORKFLOWS)
```

- [ ] **Step 2: Run the test — verify it FAILS (red) on both surfaces**

Run: `uv run pytest tests/test_workflow_node24.py -v`
Expected: **both** tests FAIL — violations listing `actions/checkout@v4 … below the Node-24 floor v5`, `astral-sh/setup-uv@v5 … below v6`, etc. for the framework and template files respectively. This proves the guard catches the current Node-20 pins.

- [ ] **Step 3: Confirm ruff/format clean**

Run: `uv run ruff check tests/test_workflow_node24.py && uv run ruff format --check tests/test_workflow_node24.py`
Expected: clean. (Do **not** commit yet — the test is red; it goes green as T2/T3 land. Stage it now; the controller commits after T2 greens the framework surface, per this repo's commit-gate flow. If executing inline, commit at the end of T3 when both are green.)

---

## Task 2: Bump the framework's 5 workflows

**Files:**
- Modify: `.github/workflows/ci.yml`, `release.yml`, `render-matrix.yml`, `review.yml`, `agent-evals.yml`

- [ ] **Step 1: Apply the version bumps**

Run (from repo root) — each substitution is keyed on the full action path, so order is irrelevant and no `arduino/setup-task`, `oasdiff`, or `gitleaks` ref is touched:

```bash
cd "$(git rev-parse --show-toplevel)"
sed -i -E \
  -e 's#(actions/checkout)@v4#\1@v5#g' \
  -e 's#(astral-sh/setup-uv)@v5#\1@v6#g' \
  -e 's#(actions/setup-node)@v4#\1@v6#g' \
  -e 's#(actions/upload-artifact)@v4#\1@v6#g' \
  -e 's#(actions/download-artifact)@v4#\1@v7#g' \
  -e 's#(softprops/action-gh-release)@v2#\1@v3#g' \
  .github/workflows/ci.yml .github/workflows/release.yml \
  .github/workflows/render-matrix.yml .github/workflows/review.yml \
  .github/workflows/agent-evals.yml
```

- [ ] **Step 2: Verify the framework guard test passes**

Run: `uv run pytest tests/test_workflow_node24.py::test_framework_workflows_use_node24_actions -v`
Expected: PASS. (The `test_template_workflows_*` test still FAILS — that's T3.)

- [ ] **Step 3: Confirm no stray refs remain & YAML still parses**

Run:
```bash
grep -rnE '(checkout|setup-uv|setup-node|upload-artifact|download-artifact|action-gh-release)@v[0-9]' .github/workflows/
uv run python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('yaml ok')"
```
Expected: every match shows the new version (checkout@v5, setup-uv@v6, setup-node@v6, upload-artifact@v6, download-artifact@v7, action-gh-release@v3); `yaml ok` printed.

- [ ] **Step 4: Commit** (controller, per the commit-gate flow — stage T1's test + these workflows + a CLAUDE.md state bump)

```bash
git add tests/test_workflow_node24.py .github/workflows/ CLAUDE.md
git commit -m "ci(node24): bump framework workflows to Node-24 actions + add allowlist guard"
```

---

## Task 3: Bump the template's 3 workflows

**Files:**
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja`, `deploy-prod.yml`, `deploy-staging.yml`

- [ ] **Step 1: Apply the same bumps to the template surface**

```bash
cd "$(git rev-parse --show-toplevel)"
sed -i -E \
  -e 's#(actions/checkout)@v4#\1@v5#g' \
  -e 's#(astral-sh/setup-uv)@v5#\1@v6#g' \
  -e 's#(actions/setup-node)@v4#\1@v6#g' \
  -e 's#(actions/upload-artifact)@v4#\1@v6#g' \
  -e 's#(actions/download-artifact)@v4#\1@v7#g' \
  -e 's#(softprops/action-gh-release)@v2#\1@v3#g' \
  src/framework_cli/template/.github/workflows/ci.yml.jinja \
  src/framework_cli/template/.github/workflows/deploy-prod.yml \
  src/framework_cli/template/.github/workflows/deploy-staging.yml
```
(The template has no `action-gh-release`; the rule is harmless. `gitleaks@v2`/`oasdiff@v0.0.21` are untouched — docker.)

- [ ] **Step 2: Verify the template guard test passes**

Run: `uv run pytest tests/test_workflow_node24.py -v`
Expected: **both** tests PASS now.

- [ ] **Step 3: Render a project and actionlint the generated ci.yml**

```bash
WORK=$(mktemp -d)
uv run python -c "
from pathlib import Path
from framework_cli.copier_runner import render_project
render_project(Path('$WORK/base'), {'project_name':'Demo','author_name':'A','author_email':'a@b.co','batteries':[]})
render_project(Path('$WORK/react'), {'project_name':'Demo','author_name':'A','author_email':'a@b.co','batteries':['react']})
print('rendered')
"
grep -nE '@v[0-9]' "$WORK"/base/.github/workflows/ci.yml | grep -iE 'checkout|setup-uv|upload-artifact'
shellcheck --version >/dev/null 2>&1 && command -v actionlint >/dev/null 2>&1 && actionlint "$WORK"/react/.github/workflows/ci.yml || echo "actionlint not installed — rely on the render-matrix actionlint step (T5)"
```
Expected: the rendered `ci.yml` shows `checkout@v5`/`setup-uv@v6`/`upload-artifact@v6`; actionlint (if present) reports no errors. (The render uses the **actual** `render_project` signature — if the kwargs differ, mirror `tests/test_copier_runner.py`'s `DATA` dict.)

- [ ] **Step 4: Confirm the existing workflow + content tests still pass**

Run: `uv run pytest tests/test_workflows.py tests/test_copier_runner.py -q`
Expected: PASS. (`tests/test_workflows.py` asserts `"action-gh-release" in rel_uses` — version-agnostic, unaffected by `@v2→@v3`.)

- [ ] **Step 5: Verify the integrity manifest is self-consistent (baseline shift is expected)**

The three template workflows are integrity-**tracked** (`src/framework_cli/integrity/classes.py`), so their hashes change — an expected one-time shift. No test pins a golden hash; confirm round-trip integrity still passes:

Run: `uv run pytest tests/integrity -q`
Expected: PASS (manifest is generated from the rendered files and verified against the same — self-consistent at the new hashes).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/.github/workflows/ CLAUDE.md
git commit -m "ci(node24): bump generated template workflows to Node-24 actions"
```

---

## Task 4: Maintenance documentation

**Files:**
- Create: `docs/maintenance/github-actions-node-runtime.md`
- Modify: `CLAUDE.md` (critical conventions)

- [ ] **Step 1: Write the maintenance note**

Create `docs/maintenance/github-actions-node-runtime.md`:

```markdown
# GitHub Actions Node runtime policy

GitHub forces the **Node 24** actions runtime by default on **2026-06-16** and removes
Node 20 from runners on **2026-09-16**. Every `uses:` reference in this repo — the
framework's own workflows (`.github/workflows/`) **and** the workflows shipped into
generated projects (`src/framework_cli/template/.github/workflows/`) — must be pinned
to a Node-24-capable action version.

## Source of truth

`tests/test_workflow_node24.py::APPROVED_ACTIONS` is the authoritative map. It is enforced
by two tests that raw-scan every `uses:` on both surfaces:

- `runtime: "node"` actions must be pinned at or above their `min_major` (the first
  Node-24 release).
- `runtime: "docker"` actions (oasdiff, gitleaks) run in containers — no Node runtime, no
  version floor — but are still listed (an unrecognized `uses:` fails the test).
- `runtime: "node20-forced"` is a tracked exception for an action with **no Node-24 release
  yet** (currently `arduino/setup-task`). GHA force-runs it on Node 24; revisit before the
  2026-09-16 removal and bump once a Node-24 release ships.

## When adding or updating a workflow action

1. Pin to a Node-24-capable version.
2. Add/update the entry in `APPROVED_ACTIONS` (with `min_major` for node actions).
3. Run `uv run pytest tests/test_workflow_node24.py` — green means compliant.

## Verified versions (2026-06-04)

checkout@v5 · setup-uv@v6 · setup-node@v6 · upload-artifact@v6 · download-artifact@v7 ·
action-gh-release@v3 · arduino/setup-task@v2 (node20-forced) · oasdiff/gitleaks (docker).
```

- [ ] **Step 2: Add the CLAUDE.md conventions pointer**

In `CLAUDE.md`, under "## Critical conventions", add one bullet:

```markdown
- **Workflow actions are pinned to Node-24-capable versions** (GHA forces Node 24 on 2026-06-16). `tests/test_workflow_node24.py::APPROVED_ACTIONS` is the source of truth across the framework's own + the template's workflows; see `docs/maintenance/github-actions-node-runtime.md`.
```

- [ ] **Step 3: Confirm the guard still green + commit**

Run: `uv run pytest tests/test_workflow_node24.py -q`
Expected: PASS.

```bash
git add docs/maintenance/github-actions-node-runtime.md CLAUDE.md
git commit -m "docs(node24): maintenance policy note + conventions pointer"
```

---

## Task 5: Validation + release (controller)

**Files:**
- Modify: `pyproject.toml` (version `0.1.6`→`0.1.7`), `uv.lock`, `src/framework_cli/dogfood.py` (`DOGFOOD_COMMIT`→`v0.1.7`)

- [ ] **Step 1: Full local gate**

Run: `uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all green (incl. both new `test_workflow_node24` tests).

- [ ] **Step 2: Branch-end review**

Dispatch an Opus code-quality + spec-compliance review over `git diff master...HEAD` (the guard test, both workflow surfaces, the doc). Address any must-fix findings.

- [ ] **Step 3: Merge FF to master + push (live framework-CI proof)**

```bash
git checkout master && git merge --ff-only node24-actions-migration && git push origin master
```
The push triggers the framework's own `ci.yml` + `render-matrix.yml` **on the bumped actions** — a green run is the live proof that checkout@v5/setup-uv@v6/etc. work. Watch them to completion (`gh run watch`); the render-matrix also exercises the bumped **template** `ci.yml` via the generated projects.

- [ ] **Step 4: Cut `v0.1.7`**

Bump `pyproject.toml` `version` to `0.1.7`, run `uv lock`, set `DOGFOOD_COMMIT = "v0.1.7"` in `src/framework_cli/dogfood.py`, update the meta-plan row + CLAUDE.md state, commit `chore(release): v0.1.7 …`, push, then `git tag v0.1.7 <sha> && git push origin v0.1.7`. Watch `release.yml` to a green GitHub Release.

- [ ] **Step 5: State updates**

Mark `NODE24-MIGRATION` done in the meta-plan status table (FF SHA + `v0.1.7`); advance the "next" pointer to **Plan 16**; update CLAUDE.md Current State.

---

## Notes for the executor

- **Commit-gate flow (this repo):** every commit needs `CLAUDE.md` staged with a real Current-State change, and a `.framework/audit/marker.json` PASS marker matching the staged set (`uv run framework gate-prepare`). Do `git add` and `git commit` as **separate** Bash calls, and keep the literal word "commit" out of Bash *descriptions* (the gate hook greps the whole tool input). Subagent implementers stage but do not commit; the controller commits.
- **Template payload:** `src/framework_cli/template/` is rendered payload, not framework source — don't lint the `.jinja` as framework code; it's validated by render + content/acceptance tests.
- **No new dependencies.** No template behavior change beyond action versions.
