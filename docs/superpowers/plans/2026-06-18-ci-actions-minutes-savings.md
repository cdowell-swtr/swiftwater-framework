# FWK38 — CI Actions-minutes savings (concurrency + paths) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `concurrency` (and documented opt-in `paths`) to the framework's generated workflows so every consumer's CI stops piling up redundant runs — and produce a brief for Meridian to apply the same now for immediate private-repo budget relief.

**Architecture:** Template-payload edit to four generated workflow files: `ci.yml.jinja` gets a cancel-in-progress concurrency group (the dominant-cost PR-iteration workflow); `deploy-staging.yml`, `deploy-prod.yml`, and the tag-triggered `docs.yml` get serialized (never-cancel) groups. Lever 3 (`paths`) ships only as a documented opt-in comment on the template (no safe-by-default home: `ci.yml` paths-ignore would wedge required checks; `docs.yml` is tag-only; `deploy-staging` paths-ignore is a behavior change) — the concrete `paths` saving is delivered to Meridian via a separate brief. No app/runtime behavior changes; defaults only *cancel redundant* runs.

**Tech Stack:** GitHub Actions YAML (`concurrency`, `paths`); Copier `.jinja` templates (note: `.jinja` files are rendered — GHA `${{ }}` must be `{% raw %}`-wrapped; the non-`.jinja` `deploy-*.yml` are copied verbatim); pytest render guards in `tests/test_copier_runner.py` (PyYAML).

**Review-model policy (CLAUDE.md / [[subagent-review-model-pattern]]):** implementers → Sonnet (Haiku ok — these are tiny mechanical YAML edits); per-task spec review → Sonnet; code-quality → **Opus**; branch-end → **Opus**. Pass `model` explicitly.

**Commit-gate / cadence:** the `PreToolUse` hook needs `PLAN.md`/`ACTION_LOG.md` staged; `git add` then `git commit` as **separate** calls ([[commit-gate-hook-timing]]); keep "commit" out of Bash descriptions. Light per-task review (template/CI files — not the 18-agent app gate, [[gate-cadence-framework-slices]]).

**Quality gate before merge:** `uv run pytest tests/test_copier_runner.py tests/test_workflow_node24.py -q` · `uv run ruff check .` · `uv run ruff format --check .`. (No `mypy`/runtime impact — workflow YAML only.)

**Release:** template payload, release-deferred — batches with FWK6/FWK36/FWK37 into one release (per maintainer). Framework repo is **public (free CI)**, so this PR costs 0 minutes; the saving is the *consumer's*. Meridian's relief comes from the brief, not the release.

---

## File Structure

**Template payload (rendered into generated projects — NOT framework source; do not lint as framework code):**
- `src/framework_cli/template/.github/workflows/ci.yml.jinja` — *modify:* add a `cancel-in-progress: true` concurrency group (the `${{ … }}` group must be `{% raw %}`-wrapped) + an opt-in `paths-ignore` comment block.
- `src/framework_cli/template/.github/workflows/deploy-staging.yml` — *modify (verbatim file, no Jinja):* add a serialized `deploy-staging` concurrency group (`cancel-in-progress: false`) + an opt-in `paths-ignore` comment block.
- `src/framework_cli/template/.github/workflows/deploy-prod.yml` — *modify (verbatim):* add a serialized `deploy-prod` concurrency group (`cancel-in-progress: false`).
- `src/framework_cli/template/.github/workflows/{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja` — *modify:* add a serialized `docs` concurrency group (`cancel-in-progress: false`). (Tag-triggered; this only prevents two release publishes racing `gh-pages`.)

**Tests (framework source):**
- `tests/test_copier_runner.py` — *add* `test_generated_workflows_have_concurrency` (render guard).

**Deliverable B — handoff artifact (NOT committed to this public repo):**
- `/home/chris/meridian-ci-savings-brief.md` — *create:* the Meridian brief. Written outside the repo so Meridian's private workflow layout isn't published here; handed to the maintainer.

---

## Task 1: `concurrency` (cancel-in-progress) + opt-in `paths` comment on `ci.yml.jinja`

**Files:**
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py` (the file already imports `Path`, `yaml`; `render_project`/`DATA` exist — match the existing `test_render_includes_ci_pipeline` style):

```python
def test_generated_workflows_have_concurrency(tmp_path: Path):
    """FWK38: ci.yml cancels superseded PR runs; deploys + docs serialize (never cancel).
    Caps the redundant-run pile-up that drives a private consumer's Actions-minute spend."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})
    wf = dest / ".github" / "workflows"

    ci = yaml.safe_load((wf / "ci.yml").read_text())
    assert ci["concurrency"]["group"] == "${{ github.workflow }}-${{ github.ref }}"
    assert ci["concurrency"]["cancel-in-progress"] is True
    # opt-in paths guidance is present (commented, so read raw text)
    assert "paths-ignore" in (wf / "ci.yml").read_text()

    for name, group in (
        ("deploy-staging.yml", "deploy-staging"),
        ("deploy-prod.yml", "deploy-prod"),
        ("docs.yml", "docs"),
    ):
        w = yaml.safe_load((wf / name).read_text())
        assert w["concurrency"]["group"] == group, f"{name} concurrency group"
        assert w["concurrency"]["cancel-in-progress"] is False, f"{name} must not cancel"
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_copier_runner.py::test_generated_workflows_have_concurrency -q`
Expected: FAIL (`KeyError: 'concurrency'` on `ci.yml`).

- [ ] **Step 3: Implement — edit `ci.yml.jinja`**

In `src/framework_cli/template/.github/workflows/ci.yml.jinja`, insert the concurrency block + opt-in comment **between the `permissions:` block and `jobs:`**. The `${{ … }}` MUST be `{% raw %}`-wrapped (this is a rendered `.jinja` file). Current text:

```yaml
permissions:
  contents: read

jobs:
```

becomes:

```yaml
permissions:
  contents: read

# Cancel a superseded run when you push again to the same branch/PR — the latest commit is
# the only one that matters, and this stops redundant CI from piling up (the dominant Actions
# cost for an active repo: this workflow's jobs are billed per-job, rounded up to the minute).
concurrency:
  group: {% raw %}${{ github.workflow }}-${{ github.ref }}{% endraw %}
  cancel-in-progress: true

# Optional: skip CI on docs-only changes by adding `paths-ignore` under the triggers above, e.g.
#   pull_request:
#     paths-ignore: ["**.md", "docs/**"]
# CAVEAT: only do this if these CI jobs are NOT branch-protection-"required" — a required check
# that is skipped by a paths filter wedges the PR at "Expected — waiting for status". (A
# wedge-safe variant needs an always-running aggregate "ci-complete" sentinel; not shipped.)

jobs:
```

- [ ] **Step 4: Run it — `ci.yml` assertions pass (deploys/docs still fail)**

Run: `uv run pytest tests/test_copier_runner.py::test_generated_workflows_have_concurrency -q`
Expected: still FAIL, now on the `deploy-staging.yml` assertion (Task 2 adds those). Confirm the failure moved past the `ci` asserts.

- [ ] **Step 5: Stage (controller commits)**

Do NOT run `git commit` (commit-gate + ACTION_LOG handled by the controller). Stage the two files:
```bash
git add src/framework_cli/template/.github/workflows/ci.yml.jinja tests/test_copier_runner.py
```
Report DONE.

---

## Task 2: serialized `concurrency` on `deploy-staging.yml`, `deploy-prod.yml`, `docs.yml`

**Files:**
- Modify: `src/framework_cli/template/.github/workflows/deploy-staging.yml`
- Modify: `src/framework_cli/template/.github/workflows/deploy-prod.yml`
- Modify: `src/framework_cli/template/.github/workflows/{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja`
- Test: `tests/test_copier_runner.py` (the Task-1 test now fully passes)

Note: `deploy-*.yml` are **verbatim** (non-`.jinja`) — use literal group names, NO `{% raw %}`. The docs file IS `.jinja`, but its group is the literal `docs` (no `${{ }}`), so no `{% raw %}` needed either.

- [ ] **Step 1: Edit `deploy-staging.yml`**

Insert between its `permissions:` block (`contents: read` / `packages: write`) and `jobs:`:

```yaml
# Serialize staging deploys — never cancel an in-flight deploy (that could leave a half-applied
# release); a deploy triggered while one is running queues behind it.
concurrency:
  group: deploy-staging
  cancel-in-progress: false

# Optional: skip the staging deploy on docs-only merges by adding `paths-ignore` under the
# `push:` trigger above, e.g.  paths-ignore: ["**.md", "docs/**"]  — safe here (a push event has
# no PR-merge gate to wedge), but it IS a behavior change (docs-only merges won't redeploy), so
# it's left opt-in.

jobs:
```

- [ ] **Step 2: Edit `deploy-prod.yml`**

Insert between its `permissions:` block (`contents: read` / `packages: read`) and `jobs:`:

```yaml
# Serialize prod deploys — never cancel an in-flight deploy.
concurrency:
  group: deploy-prod
  cancel-in-progress: false

jobs:
```

- [ ] **Step 3: Edit the docs workflow** (`{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja`)

Insert between its `permissions:` block (`contents: write`) and `jobs:`:

```yaml
# Serialize release publishes — never cancel a publish, and don't let two tag publishes race
# the gh-pages branch.
concurrency:
  group: docs
  cancel-in-progress: false

jobs:
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `uv run pytest tests/test_copier_runner.py::test_generated_workflows_have_concurrency -q`
Expected: PASS (all four workflows now carry their concurrency group).

- [ ] **Step 5: Regression — workflow guards + format**

Run: `uv run pytest tests/test_copier_runner.py -q -k "workflow or ci_pipeline or render_includes or deploy" && uv run pytest tests/test_workflow_node24.py -q`
Expected: PASS (concurrency/paths are valid GHA keys; no action versions changed). Then `uv run ruff format --check tests/test_copier_runner.py` + `uv run ruff check tests/test_copier_runner.py` — clean.

- [ ] **Step 6: Stage (controller commits)**

```bash
git add "src/framework_cli/template/.github/workflows/deploy-staging.yml" "src/framework_cli/template/.github/workflows/deploy-prod.yml" "src/framework_cli/template/.github/workflows/{{ 'docs.yml' if 'docs' in batteries else '' }}.jinja"
```
Report DONE.

---

## Task 3: Produce the Meridian brief (handoff artifact — not committed to this repo)

**Files:**
- Create: `/home/chris/meridian-ci-savings-brief.md` (outside the repo — names Meridian's private workflow layout; do NOT add it to the public framework repo)

This is a writing task, not TDD. Meridian's `main` has **no required status checks** (verified), so it can safely take the full lever 3. The brief must give exact, paste-ready edits for Meridian's actual four workflows (`ci.yml`, `docs-layout.yml`, `deploy-staging.yml`, `deploy-prod.yml`) and the integrity-drift note.

- [ ] **Step 1: Write the brief** with these sections (use the concrete YAML below):

**`ci.yml`** — add after `permissions:` / before `jobs:` (Meridian's `ci.yml` is integrity-locked; this is the deliberate, self-healing edit):
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```
…and under the `pull_request:` trigger (SAFE in Meridian — no required checks):
```yaml
  pull_request:
    paths-ignore: ["**.md", "docs/**"]
```

**`docs-layout.yml`** (Meridian-owned, edit freely) — serialized concurrency + run only on docs changes:
```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```
and narrow its triggers to docs paths:
```yaml
  push:
    branches: ["main"]
    paths: ["docs/**", "**.md", "mkdocs.yml"]
  pull_request:
    paths: ["docs/**", "**.md", "mkdocs.yml"]
```

**`deploy-staging.yml`** — serialized, never cancel:
```yaml
concurrency:
  group: deploy-staging
  cancel-in-progress: false
```

**`deploy-prod.yml`** — serialized, never cancel:
```yaml
concurrency:
  group: deploy-prod
  cancel-in-progress: false
```

**Integrity-drift note (verbatim in the brief):** "`ci.yml`/`deploy-*.yml` are framework-locked (`LOCKED_TRACKED`). These hand-edits make `framework integrity` report drift until the next `framework upgrade` onto the FWK38-released template — at which point the rendered content matches and the drift self-heals. `docs-layout.yml` is Meridian-owned, no drift. Expect `framework integrity` to warn (non-fatal) in the interim; it does not block `task dev`."

**Verification steps (in the brief):** after editing, `git diff` shows only the concurrency/paths additions; push a no-op second commit to an open PR and confirm in the Actions tab that the prior CI run is **cancelled** (not left running) — that's the saving, live.

- [ ] **Step 2: Self-check the brief against Meridian's real files**

Read `/home/chris/Claude Code/Projects/meridian/.github/workflows/{ci.yml,docs-layout.yml,deploy-staging.yml,deploy-prod.yml}` and confirm each insertion point exists as described (a `permissions:` block before `jobs:`; the trigger keys named). Adjust the brief's anchors to match Meridian's exact text. Do NOT edit Meridian's files.

- [ ] **Step 3: Report** the brief path + a one-paragraph summary the maintainer can act on. (No commit — it's outside the repo.)

---

## Branch-end (controller)

- [ ] **Gate:** `uv run pytest tests/test_copier_runner.py tests/test_workflow_node24.py -q` + `uv run ruff check .` + `uv run ruff format --check .` — all green.
- [ ] **Reviews:** per-task spec (Sonnet) + code-quality (Opus); branch-end whole-branch (Opus). For Task 1/2 the review checks: `{% raw %}` correctly wraps the `ci.yml` group (and is ABSENT from the verbatim `deploy-*.yml`); deploy/docs are `cancel-in-progress: false`; the rendered YAML parses; no unrelated workflow edits. For Task 3 the review fact-checks the brief's anchors against Meridian's real workflows.
- [ ] **State + PR:** tick FWK38 in `PLAN.md`; final `ACTION_LOG.md` entry. Open the PR against `master` (or fold into the batched FWK6/36/37 release branch per the maintainer). Hand the brief to the maintainer for Meridian.

---

## Self-Review (completed during authoring)

**Spec coverage:** A1 concurrency (ci cancel-true; deploys+docs serialized-false) → Tasks 1–2. A2 paths opt-in comment (no default) → Task 1 (ci) + Task 2 (deploy-staging). Deliverable B Meridian brief (not applied, not committed here) → Task 3. Testing (render guard) → Task 1 test. Deferred items (lever 2; ci sentinel) → not tasked, by design. **No gaps.**

**Placeholder scan:** every step has concrete YAML/commands. Task 3 Step 2's "adjust anchors to match" is a deliberate fact-check against a live external repo, not a TODO — the YAML to insert is fully specified.

**Consistency:** concurrency group strings (`${{ github.workflow }}-${{ github.ref }}` for cancel-true; literal `deploy-staging`/`deploy-prod`/`docs` for serialized), the `{% raw %}`-only-in-`.jinja` rule, and `cancel-in-progress` true/false values are consistent across tasks and match the test assertions.
