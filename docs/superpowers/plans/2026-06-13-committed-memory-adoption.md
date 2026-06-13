# Plan 26 — Adopt the Committed Memory Convention — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a committed, project-scoped agent memory store for the framework (root `MEMORY.md` + `_memory/` autoloaded via CLAUDE.md `@`-import), seeded with the public-safe subset of the native store, with gitleaks wired in the framework's own repo first.

**Architecture:** Committed Memory (`MEMORY-convention: v1`, from the sibling `patterns` repo) is a copy-by-hand markdown convention — git + markdown + Claude Code's `CLAUDE.md` `@`-import, no tool/validator. The framework is a *consumer*. This is a content + config migration, not feature code, so tasks use concrete file content + explicit verification rather than failing-test-first TDD — EXCEPT the gitleaks CI wiring, which is real config validated by running it. Decisions are from the approved spec `docs/superpowers/specs/2026-06-13-committed-memory-adoption-design.md`: conservative curation (clearly-safe framework memories only, no rewording); copy-not-move (native store untouched); gitleaks wired properly (local pre-commit + framework CI).

**Tech Stack:** Markdown, `.pre-commit-config.yaml` (gitleaks `v8.21.2`), GitHub Actions (`ci.yml`), Python (copy/index scripts), git (two repos: swiftwater-framework + the sibling patterns repo).

---

## Bootstrap / gate notes (read before executing)

- **The commit-gate PreToolUse hook (now live on master) blocks `git commit` unless `PLAN.md` or `ACTION_LOG.md` is staged**, and it checks the *session cwd's* repo, firing *before* any `cd`. So: (a) every framework commit here stages an `ACTION_LOG.md` entry (PI task-grain logging covers this naturally); (b) the cross-repo patterns commit (Task 6) needs a framework `ACTION_LOG.md`/`PLAN.md` change staged in *this* repo first.
- **The hook regex false-matches any Bash command where `git` and `commit` co-occur as substrings** — keep both out of `grep`/`echo` arguments and tool descriptions, or the hook blocks a non-commit command. Prefer the Edit/Write tools for file edits (they don't trip it).
- **gitleaks must be wired and confirmed clean BEFORE the first memory file is committed** (Task 1 precedes the store scaffolding). A public commit is irreversible.

## File Structure

- **Create** `.pre-commit-config.yaml` (root) — gitleaks-only local hook (framework's first root pre-commit config).
- **Modify** `.github/workflows/ci.yml` — add a `security` job (full-repo gitleaks scan via pinned binary).
- **Modify** `pyproject.toml` + `uv.lock` — add `pre-commit` to the dev dependency group.
- **Create** `MEMORY.md` (root) — the committed memory index.
- **Create** `_memory/<slug>.md` × 43 — one durable fact per file (`scope: project`).
- **Modify** `CLAUDE.md` — add the `<!-- MEMORY-convention: v1 -->` block + `@MEMORY.md` import.
- **Modify (patterns repo)** `~/Claude Code/Projects/patterns/_docs/committed-memory/implementers.md` (+ its `PLAN.md`/`ACTION_LOG.md`).
- **Modify** `PLAN.md` / `ACTION_LOG.md` — PI tracking (tick `T2`, log entries).

---

### Task 1: Wire gitleaks in the framework's own repo (local pre-commit + CI) and confirm clean

The framework's own repo has NO secret scanning today (verified: no root `.pre-commit-config.yaml`; no gitleaks in `.github/workflows/`). The convention requires it before any memory is committed.

**Files:**
- Create: `.pre-commit-config.yaml`
- Modify: `.github/workflows/ci.yml`, `pyproject.toml`, `uv.lock`

- [ ] **Step 1: Create the root `.pre-commit-config.yaml`** with exactly:

```yaml
# Framework's own secret-scanning backstop (gitleaks). Minimal by design — the
# framework otherwise gates via the PreToolUse hooks in .claude/settings.json and
# CI, not pre-commit. Add more hooks here only if you adopt pre-commit broadly.
default_install_hook_types: [pre-commit, pre-push]
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks
```

- [ ] **Step 2: Add `pre-commit` to the dev dependency group**

Run: `uv add --group dev pre-commit`
Expected: `pyproject.toml` gains `pre-commit` under `[dependency-groups] dev`; `uv.lock` updates.

- [ ] **Step 3: Install the local hook**

Run: `uv run pre-commit install --install-hooks`
Expected: `pre-commit installed at .git/hooks/pre-commit` and `.git/hooks/pre-push`.

- [ ] **Step 4: Run the full-repo gitleaks scan — confirm clean BEFORE any memory exists**

Run: `uv run pre-commit run gitleaks --all-files`
Expected: `Detect hardcoded secrets.....Passed`. **If it FAILS, STOP** — a real secret is present in the repo; surface it, do not proceed to memory migration.

- [ ] **Step 5: Add the `security` job to `.github/workflows/ci.yml`** — append this job under `jobs:` (sibling of `gate`). It installs a pinned gitleaks binary via a `run:` step (no Node action → outside `APPROVED_ACTIONS` scope, and avoids the gitleaks-action PR-permissions 403):

```yaml
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - name: Install gitleaks
        run: |
          curl -sSL https://github.com/gitleaks/gitleaks/releases/download/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz \
            | tar -xz -C /usr/local/bin gitleaks
      - name: Scan repo for secrets
        run: gitleaks detect --source . --redact --no-banner
```

- [ ] **Step 6: Verify the workflow is valid + no node-runtime regression**

Run: `uv run pytest -q tests/test_workflow_node24.py`
Expected: PASS (the only action added is `actions/checkout@v5`, already approved; the gitleaks install is a `run:` step).
Then confirm YAML validity:
Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml valid')"`
Expected: `ci.yml valid`.

- [ ] **Step 7: Confirm no test asserts the framework has no root pre-commit config**

Run: `grep -rIn "pre-commit-config" tests | grep -v template`
Expected: no hits referencing the framework root config (template-payload references are fine). If a test asserts absence, update it.

- [ ] **Step 8: Append PI log entry `#0007`** to `ACTION_LOG.md`:

```markdown

#### #0007 · completed · T2 · 2026-06-13
Wired gitleaks in the framework's own repo (it previously shipped a backstop to
consumers but ran none itself): root `.pre-commit-config.yaml` (gitleaks v8.21.2)
+ `pre-commit install` + a `security` job in `ci.yml` (pinned binary, full-repo
scan). Full-repo scan clean before any memory was committed.
```

- [ ] **Step 9: Commit**

```bash
git add .pre-commit-config.yaml .github/workflows/ci.yml pyproject.toml uv.lock ACTION_LOG.md
git commit -m "feat(plan-26): wire gitleaks in the framework's own repo (pre-commit + CI)"
```

---

### Task 2: Scaffold the committed store skeleton + CLAUDE.md autoload

**Files:**
- Create: `_memory/.gitkeep` (placeholder so the dir exists before files land), `MEMORY.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Create the empty index `MEMORY.md`** with exactly:

```markdown
<!-- MEMORY-convention: v1 -->
# Committed project memory

Project-scoped memories, autoloaded into every session on every machine via the
`@MEMORY.md` import in `CLAUDE.md`. One file per memory under `_memory/`; resolve
`[[slug]]` to `_memory/<slug>.md`. Maintained per
`../../patterns/memory-convention.md` (MEMORY-convention: v1).

Commit a memory only when it is BOTH useful to anyone working this repo AND safe
to publish (this repo is PUBLIC). Otherwise keep it in the native store. When in
doubt, native.

## Index
```

(The index entries are appended in Task 5.)

- [ ] **Step 2: Create `_memory/.gitkeep`** (empty file) so the directory is tracked before Task 3 populates it.

- [ ] **Step 3: Add the MEMORY block + `@MEMORY.md` import to the end of `CLAUDE.md`** — append:

```markdown

<!-- MEMORY-convention: v1 -->
## Committed project memory
Project memory is autoloaded from `MEMORY.md` (imported below). Resolve `[[slug]]`
to `_memory/<slug>.md`. Commit a memory only when it is BOTH useful to anyone
working this repo AND safe to publish; otherwise keep it in the native store.
When in doubt, native. Full rule + never-commit list in
`../../patterns/memory-convention.md`.

@MEMORY.md
```

- [ ] **Step 4: Verify the autoload import resolves**

Run: `grep -n "@MEMORY.md" CLAUDE.md && test -f MEMORY.md && echo "import + target present"`
Expected: the `@MEMORY.md` line is shown and `import + target present` prints.

- [ ] **Step 5: Append PI log entry `#0008`** to `ACTION_LOG.md`:

```markdown

#### #0008 · note · 2026-06-13
Scaffolded the committed memory store: empty `MEMORY.md` index + `_memory/`, and
added the MEMORY-convention block + `@MEMORY.md` autoload import to CLAUDE.md.
```

- [ ] **Step 6: Commit**

```bash
git add MEMORY.md _memory/.gitkeep CLAUDE.md ACTION_LOG.md
git commit -m "feat(plan-26): scaffold committed memory store + CLAUDE.md autoload"
```

---

### Task 3: Migrate the 43 INCLUDE memories (copy + `scope: project`)

The native store is at `/home/chris/.claude/projects/-home-chris-Claude-Code-Projects-framework-swiftwater-framework/memory/`. Copy each INCLUDE file verbatim into `_memory/<slug>.md`, inserting `scope: project` into the frontmatter. **Native files are NOT modified** (copy, not move).

**Verdict table (per-file classification — the authoritative set):**

| # | slug | verdict |
|---|---|---|
| 1 | app-environment-tokens-never-production | INCLUDE |
| 2 | arduino-setup-task-no-node24-release | INCLUDE |
| 3 | audit-prepare-snapshot-stderr-breaks-cli-runner-output | INCLUDE |
| 4 | check-agent-prompt-fit-before-adding-to-target | INCLUDE |
| 5 | commit-gate-hook-false-matches-git-commit-substring | INCLUDE |
| 6 | commit-gate-hook-timing | INCLUDE |
| 7 | compose-profile-dev-needs-observability-overlay | INCLUDE |
| 8 | contracts-agent-pact-v4-false-positive | INCLUDE |
| 9 | controller-skip-marker-recipe | INCLUDE |
| 10 | dependabot-github-actions-conflicts-integrity | EXCLUDE (names Meridian) |
| 11 | design-spec-stale-verify-docs-against-code | INCLUDE |
| 12 | dind-e2e-harness-gotchas | EXCLUDE (machine-specific) |
| 13 | dlq-pii-compliance-followup | INCLUDE |
| 14 | docker-as-root-host-uid-gap | INCLUDE |
| 15 | dogfood-e2e-harness-and-task-ci-coverage-gap | INCLUDE |
| 16 | eval-fixture-patch-truncation | INCLUDE |
| 17 | eval-fixtures-coupled-to-template | INCLUDE |
| 18 | feedback_secrets-in-files | EXCLUDE (personal + keys-file path) |
| 19 | flags-is-dual-use-gate-skips-advisory | INCLUDE |
| 20 | flaky-realize-cached-copytree-git-gc-race | INCLUDE |
| 21 | framework-eval-no-builtin-resume | INCLUDE |
| 22 | full-suite-exhausts-tmp-tmpfs-use-var-tmp | EXCLUDE (machine-specific) |
| 23 | gate-cadence-framework-slices | INCLUDE |
| 24 | hybrid-region-marker-token-in-prose | INCLUDE |
| 25 | key-label-convention | EXCLUDE (secrets-naming + hostnames) |
| 26 | master-branch-protection-ruleset | INCLUDE |
| 27 | meridian-is-the-de-facto-integration-test | EXCLUDE (names Meridian) |
| 28 | never-batch-dependent-pipeline-steps | INCLUDE |
| 29 | new-file-eval-fixtures-empty-diff | INCLUDE |
| 30 | noop-gate-inherits-stale-fail | INCLUDE |
| 31 | obs-completeness-guard-already-exists | INCLUDE |
| 32 | observability-reviewers-assume-manual-instrumentation | INCLUDE |
| 33 | offload-architecture-not-delegate | INCLUDE |
| 34 | paid-path-operative-for-builders | INCLUDE |
| 35 | prefers-conversational-options-over-askuserquestion | EXCLUDE (personal preference) |
| 36 | registering-review-agent-gate-completeness | INCLUDE |
| 37 | release-cut-procedure | INCLUDE |
| 38 | release-readiness-needs-render-not-local-gate | INCLUDE |
| 39 | render-matrix-dockerhub-flake-triage | INCLUDE |
| 40 | reviewer-dev-prod-parity-gap | INCLUDE |
| 41 | reviewer-tuning-is-prompts-not-thresholds | INCLUDE |
| 42 | reviewers-tune-pytest-tmp-accumulation | EXCLUDE (username path / machine) |
| 43 | reviewers-tune-quota-throttling | EXCLUDE (quota / session) |
| 44 | ruff-format-check-after-inline-edits | INCLUDE |
| 45 | scaffold-from-real-tag-not-default-branch | INCLUDE |
| 46 | subagent-backend-large-input-via-stdin-not-argv | INCLUDE |
| 47 | subagent-implementers-stop-before-commit | INCLUDE |
| 48 | subagent-review-model-pattern | INCLUDE |
| 49 | template-audit-uv-run-project-gotcha | INCLUDE |
| 50 | template-payload-tdd-loop | INCLUDE |
| 51 | unattended-runs-across-quota-need-cron-not-schedulewakeup | EXCLUDE (quota / machine) |
| 52 | upskill-strips-identity-answers | EXCLUDE (names Meridian) |
| 53 | user-design-values-separation-and-expose-capability | EXCLUDE (personal preference) |
| 54 | verify-action-node-runtime-from-actionyml | INCLUDE |
| 55 | verify-master-content-after-pr-merge | INCLUDE |
| 56 | verify-parity-not-blocker | EXCLUDE (machine / personal) |

**43 INCLUDE, 13 EXCLUDE, 56 total.**

- [ ] **Step 1: Run the copy script** (copies the 43 INCLUDE files, inserting `scope: project` after the `description:` line; leaves native untouched):

```bash
python3 - <<'PY'
import pathlib
NATIVE = pathlib.Path("/home/chris/.claude/projects/-home-chris-Claude-Code-Projects-framework-swiftwater-framework/memory")
DEST = pathlib.Path("_memory")
INCLUDE = [
 "app-environment-tokens-never-production","arduino-setup-task-no-node24-release",
 "audit-prepare-snapshot-stderr-breaks-cli-runner-output","check-agent-prompt-fit-before-adding-to-target",
 "commit-gate-hook-false-matches-git-commit-substring","commit-gate-hook-timing",
 "compose-profile-dev-needs-observability-overlay","contracts-agent-pact-v4-false-positive",
 "controller-skip-marker-recipe","design-spec-stale-verify-docs-against-code","dlq-pii-compliance-followup",
 "docker-as-root-host-uid-gap","dogfood-e2e-harness-and-task-ci-coverage-gap","eval-fixture-patch-truncation",
 "eval-fixtures-coupled-to-template","flags-is-dual-use-gate-skips-advisory","flaky-realize-cached-copytree-git-gc-race",
 "framework-eval-no-builtin-resume","gate-cadence-framework-slices","hybrid-region-marker-token-in-prose",
 "master-branch-protection-ruleset","never-batch-dependent-pipeline-steps","new-file-eval-fixtures-empty-diff",
 "noop-gate-inherits-stale-fail","obs-completeness-guard-already-exists",
 "observability-reviewers-assume-manual-instrumentation","offload-architecture-not-delegate",
 "paid-path-operative-for-builders","registering-review-agent-gate-completeness","release-cut-procedure",
 "release-readiness-needs-render-not-local-gate","render-matrix-dockerhub-flake-triage","reviewer-dev-prod-parity-gap",
 "reviewer-tuning-is-prompts-not-thresholds","ruff-format-check-after-inline-edits","scaffold-from-real-tag-not-default-branch",
 "subagent-backend-large-input-via-stdin-not-argv","subagent-implementers-stop-before-commit","subagent-review-model-pattern",
 "template-audit-uv-run-project-gotcha","template-payload-tdd-loop","verify-action-node-runtime-from-actionyml",
 "verify-master-content-after-pr-merge",
]
assert len(INCLUDE) == 43, len(INCLUDE)
DEST.mkdir(exist_ok=True)
for slug in INCLUDE:
    src = NATIVE / f"{slug}.md"
    text = src.read_text(encoding="utf-8")
    lines = text.split("\n")
    # frontmatter is between the first two '---' lines
    assert lines[0].strip() == "---", f"{slug}: no frontmatter"
    if "scope:" not in text.split("---")[1]:
        out = []
        inserted = False
        for ln in lines:
            out.append(ln)
            if not inserted and ln.startswith("description:"):
                out.append("scope: project")
                inserted = True
        assert inserted, f"{slug}: no description line to anchor scope"
        text = "\n".join(out)
    (DEST / f"{slug}.md").write_text(text, encoding="utf-8")
print(f"copied {len(INCLUDE)} files to _memory/")
PY
```

- [ ] **Step 2: Verify 43 files landed, each with `scope: project`**

Run: `ls _memory/*.md | grep -v gitkeep | wc -l && grep -L "scope: project" _memory/*.md | grep -v gitkeep; echo "missing-scope-rc=$?"`
Expected: `43`, and no file listed as missing `scope: project` (grep -L prints nothing).

- [ ] **Step 3: Boundary spot-check — confirm no excluded signal leaked into the copies**

Run: `grep -liI "meridian" _memory/*.md; echo "meridian-rc=$?"; grep -liI "/home/chris" _memory/*.md; echo "homepath-rc=$?"`
Expected: both greps print nothing (rc=1). **If any hit, STOP** and re-examine — an INCLUDE verdict was wrong.

- [ ] **Step 4: Append PI log entry `#0009`** to `ACTION_LOG.md`:

```markdown

#### #0009 · completed · T2 · 2026-06-13
Copied the 43 public-safe project memories into `_memory/` (+ `scope: project`);
native store untouched (copy, not move). 13 excluded (3 name Meridian, the rest
machine/personal/preference). Boundary spot-check clean (no Meridian / no
private paths in the copies).
```

- [ ] **Step 5: Commit**

```bash
git add _memory ACTION_LOG.md
git commit -m "feat(plan-26): migrate 43 public-safe memories into the committed store"
```

---

### Task 4: Repair dangling cross-store links in the migrated copies

The convention bars a committed `[[slug]]` pointing at a non-committed memory. 11 migrated files link to EXCLUDE'd or nonexistent slugs. **Reword each to prose** (remove the `[[ ]]` brackets, keep a short plain-text descriptor; do NOT delete the surrounding sentence). Native files are untouched.

**Dangling links to repair (file → token(s) to de-link):**

| committed file | `[[token]]` to reword to prose | why dangling |
|---|---|---|
| `app-environment-tokens-never-production.md` | `[[user-design-values-separation-and-expose-capability]]` | EXCLUDE |
| `compose-profile-dev-needs-observability-overlay.md` | `[[dind-e2e-harness-gotchas]]` | EXCLUDE |
| `docker-as-root-host-uid-gap.md` | `[[verify-parity-not-blocker]]`, `[[dind-e2e-harness-gotchas]]` | EXCLUDE |
| `framework-eval-no-builtin-resume.md` | `[[unattended-runs-across-quota-need-cron-not-schedulewakeup]]`, `[[reviewers-tune-quota-throttling]]` | EXCLUDE |
| `never-batch-dependent-pipeline-steps.md` | `[[reviewers-tune-quota-throttling]]` | EXCLUDE |
| `offload-architecture-not-delegate.md` | `[[plan-5b-deploy-seam]]` | no such memory |
| `paid-path-operative-for-builders.md` | `[[reviewer-subagent-dispatch-model]]` | no such memory |
| `render-matrix-dockerhub-flake-triage.md` | `[[full-suite-exhausts-tmp-tmpfs-use-var-tmp]]` | EXCLUDE |
| `template-audit-uv-run-project-gotcha.md` | `[[verify-parity-not-blocker]]`, `[[reviewers-tune-quota-throttling]]` | EXCLUDE |
| `template-payload-tdd-loop.md` | `[[reviewers-tune-pytest-tmp-accumulation]]` | EXCLUDE |
| `verify-action-node-runtime-from-actionyml.md` | `[[verify-parity-not-blocker]]` | EXCLUDE |

**Reword rule (worked example):** in `template-payload-tdd-loop.md`, a phrase like
`…ruff-format-check the rendered output ([[reviewers-tune-pytest-tmp-accumulation]]).`
becomes `…ruff-format-check the rendered output (and clean stale pytest temp dirs first if a run looks broken).`
i.e. replace the `[[slug]]` token with a brief plain-text gloss of what it pointed at, dropping the brackets. Links to *INCLUDE'd* slugs stay as `[[slug]]` — leave them.

- [ ] **Step 1: For each of the 11 files above, open it and reword every listed `[[token]]` to prose** (use the Edit tool per occurrence). Leave all `[[slug]]` links whose target is an INCLUDE'd memory intact.

- [ ] **Step 2: Verify NO committed `[[link]]` is dangling**

Run:
```bash
python3 - <<'PY'
import pathlib, re
mem = pathlib.Path("_memory")
slugs = {p.stem for p in mem.glob("*.md")}
bad = []
for p in mem.glob("*.md"):
    for m in re.findall(r"\[\[([^\]]+)\]\]", p.read_text(encoding="utf-8")):
        if m not in slugs:
            bad.append((p.name, m))
print("DANGLING:", bad if bad else "none")
PY
```
Expected: `DANGLING: none`.

- [ ] **Step 3: Append PI log entry `#0010`** to `ACTION_LOG.md`:

```markdown

#### #0010 · completed · T2 · 2026-06-13
Repaired 11 migrated memories whose `[[links]]` pointed at non-committed
(excluded/nonexistent) slugs — reworded those references to prose per the
convention's cross-store rule. All committed `[[links]]` now resolve within
`_memory/`. Native links untouched (copy approach).
```

- [ ] **Step 4: Commit**

```bash
git add _memory ACTION_LOG.md
git commit -m "fix(plan-26): reword dangling cross-store memory links to prose"
```

---

### Task 5: Build the `MEMORY.md` index + verify bidirectional completeness

Reuse the curated titles + hooks from the native index, filtered to the 43 INCLUDE slugs, with paths rewritten to `_memory/<slug>.md`.

**Files:**
- Modify: `MEMORY.md`

- [ ] **Step 1: Generate the index entries** from the native `MEMORY.md`, keeping only INCLUDE slugs and rewriting the path:

```bash
python3 - <<'PY'
import pathlib, re
NATIVE_INDEX = pathlib.Path("/home/chris/.claude/projects/-home-chris-Claude-Code-Projects-framework-swiftwater-framework/memory/MEMORY.md")
committed = {p.stem for p in pathlib.Path("_memory").glob("*.md")}
out = []
for ln in NATIVE_INDEX.read_text(encoding="utf-8").splitlines():
    m = re.match(r"- \[.*\]\((?P<f>[^)]+)\.md\)", ln.strip())
    if m and m.group("f") in committed:
        out.append(re.sub(r"\]\(([^)]+)\.md\)", r"](_memory/\1.md)", ln.strip()))
print(f"-- {len(out)} entries (expect 43) --")
print("\n".join(out))
PY
```
Expected: 43 entries printed. Paste them under the `## Index` heading in `MEMORY.md` (using the Edit/Write tool). If the native index is missing a hook for any INCLUDE slug, write a one-line hook from that memory's `description:` frontmatter.

- [ ] **Step 2: Verify index ↔ files bidirectional completeness**

Run:
```bash
python3 - <<'PY'
import pathlib, re
idx = pathlib.Path("MEMORY.md").read_text(encoding="utf-8")
linked = set(re.findall(r"\(_memory/([^)]+)\.md\)", idx))
files = {p.stem for p in pathlib.Path("_memory").glob("*.md")}
print("in index not on disk:", linked - files or "none")
print("on disk not in index:", files - linked or "none")
print("counts:", len(linked), len(files))
PY
```
Expected: both differences `none`; counts `43 43`.

- [ ] **Step 3: Append PI log entry `#0011`** to `ACTION_LOG.md`:

```markdown

#### #0011 · completed · T2 · 2026-06-13
Built `MEMORY.md` (43 entries, reusing the native index's curated titles/hooks,
paths rewritten to `_memory/`). Index ↔ files bidirectionally complete.
```

- [ ] **Step 4: Commit**

```bash
git add MEMORY.md ACTION_LOG.md
git commit -m "feat(plan-26): build the committed MEMORY.md index (43 entries)"
```

---

### Task 6: Self-register in the patterns Committed-Memory registry (cross-repo)

A commit in the **separate patterns repo**. The framework's session commit-gate hook checks *this* repo's staged files (firing before any `cd`), so a framework `ACTION_LOG.md`/`PLAN.md` change must be staged here before the patterns commit (Task 7's tick is the natural carrier — but to keep tasks independent, stage the `#0012` entry below first).

**Files:**
- Modify (patterns repo): `~/Claude Code/Projects/patterns/_docs/committed-memory/implementers.md` (+ its `PLAN.md` `T8`, `ACTION_LOG.md`)
- Modify: `ACTION_LOG.md` (this repo — carrier for the gate)

- [ ] **Step 1: Append the framework row** to the patterns registry table (after the `meridian` row):

```
| swiftwater-framework | ~/Claude Code/Projects/framework/swiftwater-framework | v1 | 2026-06-13 |
```

- [ ] **Step 2: Tick `T8` in the patterns `PLAN.md`** (move it to `Done` with `→ log:#0008`) and append to the patterns `ACTION_LOG.md`:

```markdown

#### #0008 · completed · T8 · 2026-06-13
swiftwater-framework adopted the Committed Memory convention (v1) via the pull
model and registered in the implementer registry.
```

(Use the patterns repo's actual next log id if #0008 is taken — it is monotonic there.)

- [ ] **Step 3: Append PI log entry `#0012`** to this repo's `ACTION_LOG.md` (also the gate carrier for the cross-repo commit):

```markdown

#### #0012 · note · 2026-06-13
Self-registered swiftwater-framework as a Committed Memory adopter in the patterns
registry (`_docs/committed-memory/implementers.md`); ticked its T8.
```

- [ ] **Step 4: Stage this repo's log so the gate passes, then commit the patterns repo**

```bash
git add ACTION_LOG.md
cd ~/"Claude Code/Projects/patterns"
git add _docs/committed-memory/implementers.md PLAN.md ACTION_LOG.md
git commit -m "chore(memory): register swiftwater-framework as a Committed Memory adopter"
cd -
```

- [ ] **Step 5: Commit this repo's registration record**

```bash
git commit -m "docs(plan-26): record Committed Memory self-registration (cross-repo)"
```

---

### Task 7: Final verification + close out T2

**Files:**
- Modify: `PLAN.md` (tick `T2` → Done), `ACTION_LOG.md` (append `#0013`)

- [ ] **Step 1: gitleaks full-repo scan (now WITH the memories present)**

Run: `uv run pre-commit run gitleaks --all-files`
Expected: `Passed`. **If FAIL, STOP** and remove the offending content.

- [ ] **Step 2: Boundary self-audit (human judgment pass gitleaks can't do)** — re-read every file in `_memory/` specifically for: any client/org name, any `/home/<user>` path, any internal hostname/URL, any secret-shaped string. Confirm clean. This is the irreversible-publish gate.

Run (assists the read): `grep -rIniE "meridian|/home/|@swiftwaterhorizon|api[_-]?key|secret|token|password" _memory/ ; echo "audit-rc=$?"`
Expected: review every hit; the only acceptable matches are generic words in technical context (e.g. "token" in "app-environment-tokens", "secret" referenced abstractly). Any real identifier/secret → STOP and remove.

- [ ] **Step 3: Convention invariants**

Run:
```bash
python3 - <<'PY'
import pathlib, re
mem = pathlib.Path("_memory"); slugs = {p.stem for p in mem.glob("*.md")}
idx = pathlib.Path("MEMORY.md").read_text(encoding="utf-8")
linked = set(re.findall(r"\(_memory/([^)]+)\.md\)", idx))
ok = True
for p in mem.glob("*.md"):
    t = p.read_text(encoding="utf-8")
    fm = t.split("---")[1] if t.startswith("---") else ""
    if "scope: project" not in fm: print("MISSING scope:", p.name); ok=False
    if "name:" not in fm: print("MISSING name:", p.name); ok=False
    for m in re.findall(r"\[\[([^\]]+)\]\]", t):
        if m not in slugs: print("DANGLING link:", p.name, m); ok=False
if linked != slugs: print("INDEX mismatch:", linked ^ slugs); ok=False
print("INVARIANTS OK" if ok else "INVARIANTS FAILED")
PY
```
Expected: `INVARIANTS OK`.

- [ ] **Step 4: Full quality gate (no regression)**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: all clean. (No Python source or template payload changed beyond `pyproject`/`ci.yml`/markdown.)

- [ ] **Step 5: Tick `T2` → Done in `PLAN.md`** — remove `- [ ] T2 …` from `Next`, add to `Done`:

```markdown
- [x] T2 — Plan 26: adopt the Committed Memory convention  → log:#0013
```

- [ ] **Step 6: Append the closing log entry `#0013`** to `ACTION_LOG.md`:

```markdown

#### #0013 · completed · T2 · 2026-06-13
Plan 26 complete: Committed Memory convention adopted — gitleaks wired in the
framework's own repo, store scaffolded, 43 public-safe memories migrated (copy),
cross-store links repaired, index built, framework registered as an adopter.
Boundary self-audit + gitleaks clean; convention invariants hold; gate green.
```

- [ ] **Step 7: Commit**

```bash
git add PLAN.md ACTION_LOG.md
git commit -m "docs(plan-26): complete Committed Memory adoption — close out T2"
```

---

## Notes for the executor

- **Review model policy** (working agreement): doc/config-only → spec-compliance review = Sonnet; branch-end whole-branch review = **Opus**. No per-task code-quality review needed beyond the branch-end Opus pass. The gitleaks CI job is the one piece of real config — confirm it actually runs green in CI on the PR.
- **No template payload changes** — do not touch `src/framework_cli/template/`. Generated projects are out of scope (recorded `T9`).
- **The native store is never modified** (copy approach). Do not delete or edit anything under `~/.claude/.../memory/`.
- **Irreversibility:** the repo is PUBLIC. Tasks 3 and 7 each STOP on any boundary failure. When in doubt about a file, exclude it.
- **Branch:** `plan-26-committed-memory` (already created; spec committed there). Finish via `superpowers:finishing-a-development-branch` → PR → merge (clears `gate` + `build` + `render-complete`; the new `security` job also runs).
