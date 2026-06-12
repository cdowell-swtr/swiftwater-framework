# Lock-taxonomy correction + `task doctor` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unlock the two composition-seam files the framework wrongly locks (`scripts/seed.py`, `infra/deploy/notify.sh`) and add a `task doctor` host-tool preflight, shipping in v0.2.4.

**Architecture:** Two independent changes to the template + integrity layer. (1) In `src/framework_cli/integrity/classes.py`, move the two files out of `LOCKED_TRACKED` into a new `INTENTIONALLY_UNLOCKED` record, guarded by a narrow re-lock test (the full reverse-coverage scan is a separate, deferred slice). (2) A new locked `scripts/doctor.sh` template script + a `doctor:` Taskfile task that checks host tools by presence, advisory-only, with the existing lazy guards cross-referencing it.

**Tech Stack:** Python (framework CLI + pytest), Copier/Jinja template payload, go-task `Taskfile.yml`, bash.

**Spec:** `docs/superpowers/specs/2026-06-12-lock-taxonomy-and-doctor-design.md`

---

## File map

- `src/framework_cli/integrity/classes.py` — remove 2 from `LOCKED_TRACKED`; add `INTENTIONALLY_UNLOCKED`; add `scripts/doctor.sh` to `LOCKED_TRACKED`; update header comment.
- `src/framework_cli/template/scripts/doctor.sh.jinja` — **new**, locked. Host-tool preflight (battery-conditional node).
- `src/framework_cli/template/Taskfile.yml.jinja` — add `doctor:` task; append a `task doctor` pointer to the `mkcert` and `docker` precondition messages.
- `src/framework_cli/template/scripts/seed.py.jinja` — one-line "this is yours" example comment.
- `src/framework_cli/template/README.md.jinja` — one-line Prerequisites pointer.
- Tests: `tests/integrity/test_classes.py`, `tests/integrity/test_checker.py`, `tests/test_copier_runner.py`, **new** `tests/test_doctor.py`.
- Docs/state (final task): lock docs under `documentation/` if any enumerate the managed set; `docs/superpowers/plans/2026-05-20-meta-plan.md` status table; `CLAUDE.md`.

**Note on TDD loop:** these tests run in the framework venv — they render the template and assert file *content*, or run bash against a stub PATH. None imports the generated package, so the heavier "generated-project venv" loop is not needed here. Run the gate after each task: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy src`.

---

## Task 1: Unlock `seed.py` + `notify.sh` in the integrity registry

**Files:**
- Modify: `src/framework_cli/integrity/classes.py`
- Test: `tests/integrity/test_classes.py`, `tests/integrity/test_checker.py`

- [ ] **Step 1: Write the failing classes-level guard test**

Add to `tests/integrity/test_classes.py`:

```python
def test_seam_files_are_intentionally_unlocked():
    from framework_cli.integrity.classes import INTENTIONALLY_UNLOCKED

    for rel in ("scripts/seed.py", "infra/deploy/notify.sh"):
        assert rel not in LOCKED_TRACKED, f"{rel} should be unlocked (composition seam)"
        assert rel in INTENTIONALLY_UNLOCKED, f"{rel} should be recorded as intentionally unlocked"
```

- [ ] **Step 2: Write the failing checker behavioral test**

Add to `tests/integrity/test_checker.py`:

```python
def test_unlocked_seam_files_are_not_flagged_when_modified(tmp_path: Path):
    proj = _project(tmp_path)
    # Composition seams the scaffold ships but no longer tracks — a builder edits them freely.
    (proj / "scripts").mkdir(parents=True, exist_ok=True)
    (proj / "scripts" / "seed.py").write_text("# builder's own domain seeding\n")
    (proj / "infra" / "deploy").mkdir(parents=True, exist_ok=True)
    (proj / "infra" / "deploy" / "notify.sh").write_text("#!/usr/bin/env bash\nslack_notify\n")
    write_manifest(proj, "0.1.0")
    flagged = {f.path for f in check(proj)}
    assert "scripts/seed.py" not in flagged
    assert "infra/deploy/notify.sh" not in flagged
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `uv run pytest tests/integrity/test_classes.py::test_seam_files_are_intentionally_unlocked tests/integrity/test_checker.py::test_unlocked_seam_files_are_not_flagged_when_modified -v`
Expected: FAIL — `test_classes` errors on `ImportError: cannot import name 'INTENTIONALLY_UNLOCKED'`; `test_checker` fails because the still-locked, now-modified files are flagged.

- [ ] **Step 4: Edit `classes.py`**

Remove `"infra/deploy/notify.sh",` and `"scripts/seed.py",` from the `LOCKED_TRACKED` tuple. Then add the new tuple immediately after `LOCKED_TRACKED` closes (before `GITIGNORED_EXISTENCE`):

```python
# Framework-shipped files deliberately left unmanaged: composition seams the scaffold invites the
# project to replace. Not checksummed. Recorded here so the unlock is intentional and visible, and
# so a future reverse-coverage check can distinguish "deliberately unlocked" from "a framework file
# that escaped classification". (That full reverse scan is a separate slice — an all-batteries
# render has ~23 unclassified infra files needing a per-file audit; see the design doc.)
INTENTIONALLY_UNLOCKED: tuple[str, ...] = (
    "scripts/seed.py",  # thin entrypoint; the idempotent seed() helper in db/seed.py is the mechanism
    "infra/deploy/notify.sh",  # deploy-notification seam — "wire your channel here"
)
```

Also update the header comment (lines ~13-18) so it no longer says the reverse check is wholly deferred — note that `INTENTIONALLY_UNLOCKED` now records deliberate exclusions, and the full scan remains a separate slice.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/integrity/ -q`
Expected: PASS (the two new tests green; all existing `test_classes`/`test_checker`/`test_generate` still green — they derive from `LOCKED_TRACKED` so they stay consistent).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/integrity/classes.py tests/integrity/test_classes.py tests/integrity/test_checker.py
git commit -m "feat(integrity): unlock seed.py + notify.sh as intentional composition seams"
```

---

## Task 2: Mark `seed.py` as a "this is yours" example

**Files:**
- Modify: `src/framework_cli/template/scripts/seed.py.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py` (near the existing seed assertions around line 446-450):

```python
def test_seed_script_reads_as_an_owned_example(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    cli = (dest / "scripts" / "seed.py").read_text()
    assert "compose your domain seeding here" in cli
    assert "db.seed" in cli  # still points at the reusable helper
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_seed_script_reads_as_an_owned_example -v`
Expected: FAIL on the `"compose your domain seeding here"` assertion.

- [ ] **Step 3: Add the comment in `scripts/seed.py.jinja`**

Insert a comment block above `def main()`:

```jinja
# This entrypoint is yours — compose your domain seeding here. The reusable, idempotent seed()
# helper (insert-if-empty, safe to run on every start) lives in {{ package_name }}/db/seed.py.
def main() -> None:
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py::test_seed_script_reads_as_an_owned_example -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/scripts/seed.py.jinja tests/test_copier_runner.py
git commit -m "docs(template): mark scripts/seed.py as an owned composition example"
```

---

## Task 3: Add the `scripts/doctor.sh` template script (locked)

**Files:**
- Create: `src/framework_cli/template/scripts/doctor.sh.jinja`
- Modify: `src/framework_cli/integrity/classes.py` (add `"scripts/doctor.sh"` to `LOCKED_TRACKED`)
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing content test**

Add to `tests/test_copier_runner.py`:

```python
def test_doctor_script_checks_expected_host_tools(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)  # baseline: no react battery
    doctor = (dest / "scripts" / "doctor.sh").read_text()
    for probe in (
        "command -v docker",
        "docker compose version",
        "docker buildx version",
        "command -v mkcert",
        "command -v uv",
        "command -v git",
    ):
        assert probe in doctor, f"doctor.sh missing probe: {probe}"
    assert "command -v node" not in doctor  # node only with the react battery


def test_doctor_script_checks_node_only_with_react(tmp_path: Path):
    dest = tmp_path / "demo_react"
    render_project(dest, {**DATA, "batteries": ["react"]})
    doctor = (dest / "scripts" / "doctor.sh").read_text()
    assert "command -v node" in doctor
    assert "command -v npm" in doctor


def test_doctor_script_is_locked():
    from framework_cli.integrity.classes import LOCKED_TRACKED

    assert "scripts/doctor.sh" in LOCKED_TRACKED
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_copier_runner.py -k doctor -v`
Expected: FAIL — `doctor.sh` does not render; `scripts/doctor.sh` not in `LOCKED_TRACKED`.

- [ ] **Step 3: Create `src/framework_cli/template/scripts/doctor.sh.jinja`**

```jinja
#!/usr/bin/env bash
# task doctor — preflight the host tools the dev workflow assumes. Advisory: run it yourself.
# NOT part of `task ci` (CI images don't ship mkcert) and not a per-task precondition.
# Presence-only — answers "is it installed", not "is it new enough" (no version floors).
set -uo pipefail  # deliberately NOT -e: check every tool and report, don't abort on the first miss

missing=0
_ok() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
_miss() {
  printf '  \033[31m✗\033[0m %s — %s\n' "$1" "$2"
  missing=$((missing + 1))
}
_check() { # _check <label> <probe-command> <install-hint>
  if eval "$2" >/dev/null 2>&1; then _ok "$1"; else _miss "$1" "$3"; fi
}

echo "Host-tool preflight (task doctor):"
_check "docker" "command -v docker" "install Docker — https://docs.docker.com/get-docker/"
_check "docker compose" "docker compose version" "install the Docker Compose v2 plugin"
_check "docker buildx" "docker buildx version" "install the Docker buildx plugin"
_check "mkcert" "command -v mkcert" "install mkcert — https://github.com/FiloSottile/mkcert#installation"
_check "uv" "command -v uv" "install uv — https://docs.astral.sh/uv/getting-started/installation/"
_check "git" "command -v git" "install git"
{%- if "react" in batteries %}
_check "node" "command -v node" "install Node 22+ — https://nodejs.org/"
_check "npm" "command -v npm" "install npm (ships with Node)"
{%- endif %}

if [ "$missing" -gt 0 ]; then
  echo "doctor: $missing required host tool(s) missing — see the hints above." >&2
  exit 1
fi
echo "doctor: all required host tools present."
```

- [ ] **Step 4: Add `scripts/doctor.sh` to `LOCKED_TRACKED`**

In `src/framework_cli/integrity/classes.py`, add `"scripts/doctor.sh",` to the `LOCKED_TRACKED` tuple (group it with the other `scripts/` entries).

- [ ] **Step 5: Run the content tests + verify shellcheck-clean**

Run: `uv run pytest tests/test_copier_runner.py -k doctor tests/integrity/test_classes.py -q`
Expected: PASS (incl. the existing `test_every_locked_path_exists_in_a_rendered_project`, now covering doctor.sh).

Then confirm the rendered script passes shellcheck (the generated project's pre-commit runs it):
Run: `shellcheck` against a rendered copy — e.g. `uv run python -c "from framework_cli.copier_runner import render_project; from pathlib import Path; render_project(Path('/tmp/doc'), {'project_name':'D','project_slug':'d','package_name':'d','python_version':'3.12'})"` then `shellcheck /tmp/doc/scripts/doctor.sh`.
Expected: no shellcheck findings. (If `eval "$2"` trips SC2294 or similar, replace `_check`'s `eval` with a `case`-based dispatch — keep behavior identical.)

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/scripts/doctor.sh.jinja src/framework_cli/integrity/classes.py tests/test_copier_runner.py
git commit -m "feat(template): add scripts/doctor.sh host-tool preflight (locked)"
```

---

## Task 4: Behavioral test — `doctor.sh` exits per tool presence

**Files:**
- Create: `tests/test_doctor.py`

- [ ] **Step 1: Write the failing behavioral test**

Create `tests/test_doctor.py`:

```python
import os
import stat
import subprocess
from pathlib import Path

from framework_cli.copier_runner import render_project

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def _stub_bin(dirpath: Path, names: list[str]) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    for name in names:
        f = dirpath / name
        # exit 0 for any invocation — satisfies both `command -v X` and `X <subcmd> version`.
        f.write_text("#!/usr/bin/env bash\nexit 0\n")
        f.chmod(f.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run_doctor(project: Path, path_dir: Path) -> int:
    return subprocess.run(
        ["bash", "scripts/doctor.sh"],
        cwd=project,
        env={**os.environ, "PATH": str(path_dir)},
    ).returncode


def test_doctor_passes_when_all_tools_present(tmp_path: Path):
    proj = tmp_path / "proj"
    render_project(proj, DATA)
    bindir = tmp_path / "bin"
    _stub_bin(bindir, ["docker", "mkcert", "uv", "git", "bash"])
    assert _run_doctor(proj, bindir) == 0


def test_doctor_fails_when_a_required_tool_is_missing(tmp_path: Path):
    proj = tmp_path / "proj"
    render_project(proj, DATA)
    bindir = tmp_path / "bin"
    _stub_bin(bindir, ["docker", "uv", "git", "bash"])  # mkcert deliberately absent
    assert _run_doctor(proj, bindir) != 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_doctor.py -v`
Expected: FAIL only if `doctor.sh` is wrong; if Task 3 is correct these should pass. If they fail, the most likely cause is `PATH` excluding the real `bash` — the stub set includes `bash`, but if your `#!/usr/bin/env bash` needs `env`, add `"env"` to the stub set OR keep the real PATH dirs: set `"PATH": f"{path_dir}:/usr/bin:/bin"` and instead make the "missing" test shadow mkcert by NOT stubbing it while ensuring no real mkcert is on `/usr/bin` (it isn't on CI). Prefer the explicit-stub approach; only widen PATH if `env`/`bash` resolution fails.

- [ ] **Step 3: Adjust if needed, then verify pass**

Run: `uv run pytest tests/test_doctor.py -v`
Expected: PASS — exit 0 with all stubs, non-zero with mkcert removed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_doctor.py
git commit -m "test(doctor): assert doctor.sh exit code tracks host-tool presence"
```

---

## Task 5: Wire the `doctor:` task + cross-reference the lazy guards

**Files:**
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_doctor_task_present_and_not_in_ci(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "\n  doctor:" in taskfile
    assert "bash scripts/doctor.sh" in taskfile
    # doctor is advisory — it must NOT be wired into `task ci` (CI has no mkcert).
    ci_block = taskfile.split("\n  ci:")[1].split("\n  push:")[0]
    assert "doctor" not in ci_block


def test_host_tool_guards_point_at_doctor(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    taskfile = (dest / "Taskfile.yml").read_text()
    # The lazy precondition messages cross-reference the canonical preflight.
    assert taskfile.count("run `task doctor`") >= 2  # mkcert (certs) + docker (dev) at least
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k "doctor_task or guards_point" -v`
Expected: FAIL — no `doctor:` task; messages don't mention `task doctor`.

- [ ] **Step 3: Add the `doctor:` task**

In `src/framework_cli/template/Taskfile.yml.jinja`, insert directly after the `certs:` task's last `cmds:` line and before `  hooks:`:

```yaml
  doctor:
    desc: Preflight host tools the dev workflow needs (docker, mkcert, uv, git[, node]). Advisory — not part of `task ci`.
    cmds:
      - bash scripts/doctor.sh

```

- [ ] **Step 4: Append the `task doctor` pointer to the guard messages**

Edit these four precondition `msg:` strings (append `" Run \`task doctor\` to check all host tools."`):
- `certs:` — the `mkcert is required.` message.
- `dev:` — the `Docker is required for \`task dev\`.` message.
- `dev:lite:` — the `Docker is required for \`task dev:lite\`.` message.
- `dev:reset:` — the `Docker is required for \`task dev:reset\`.` message.

Example (certs):
```yaml
        msg: "mkcert is required. Install it (https://github.com/FiloSottile/mkcert#installation), then retry. Run `task doctor` to check all host tools."
```

- [ ] **Step 5: Run to verify pass + Taskfile stays valid YAML**

Run: `uv run pytest tests/test_copier_runner.py -k "doctor_task or guards_point" -q`
Then verify the rendered Taskfile parses: `uv run python -c "import yaml,subprocess,tempfile,pathlib; from framework_cli.copier_runner import render_project; d=pathlib.Path(tempfile.mkdtemp())/'p'; render_project(d, {'project_name':'D','project_slug':'d','package_name':'d','python_version':'3.12'}); yaml.safe_load((d/'Taskfile.yml').read_text()); print('ok')"`
Expected: PASS, prints `ok`.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/Taskfile.yml.jinja tests/test_copier_runner.py
git commit -m "feat(template): add `task doctor`; lazy host-tool guards point at it"
```

---

## Task 6: README Prerequisites pointer

**Files:**
- Modify: `src/framework_cli/template/README.md.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py`:

```python
def test_readme_points_at_doctor_for_prerequisites(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    readme = (dest / "README.md").read_text()
    assert "task doctor" in readme
    assert "Prerequisites" in readme
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_readme_points_at_doctor_for_prerequisites -v`
Expected: FAIL.

- [ ] **Step 3: Add the line under `## Local stack (HTTPS)`**

In `src/framework_cli/template/README.md.jinja`, insert immediately after the `## Local stack (HTTPS)` heading and before the code fence:

```jinja
> **Prerequisites:** run `task doctor` to check the host tools this needs — Docker, mkcert, uv, git{% if "react" in batteries %}, Node{% endif %}.

```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_copier_runner.py::test_readme_points_at_doctor_for_prerequisites -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/README.md.jinja tests/test_copier_runner.py
git commit -m "docs(template): README Prerequisites points at task doctor"
```

---

## Task 7: Full gate + render/acceptance + docs/state

**Files:**
- Modify: `docs/superpowers/plans/2026-05-20-meta-plan.md`, `CLAUDE.md`, and any `documentation/` page enumerating the managed/locked set.

- [ ] **Step 1: Run the full local gate**

Run:
```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: all green. (If the full suite exhausts `/tmp`, set `TMPDIR=/var/tmp`.)

- [ ] **Step 2: Run the render + acceptance tiers (template-payload change)**

Run: `TMPDIR=/var/tmp uv run pytest tests/test_copier_runner.py tests/acceptance/test_rendered_project.py -q`
Expected: PASS — the freshly generated project's integrity (now manifesting `doctor.sh`, no longer `seed.py`/`notify.sh`) is clean, and its first pre-commit (shellcheck over `doctor.sh`) passes.

- [ ] **Step 3: Update docs that enumerate the managed set**

Grep for lock/integrity enumerations and reconcile the two unlocks + the `doctor.sh` lock:
Run: `grep -rniE "locked|managed file|integrity" documentation/ | grep -iE "seed|notify|locked set|managed" || true`
Update any page that lists `scripts/seed.py` / `infra/deploy/notify.sh` as locked. If none enumerate them specifically, no change.

- [ ] **Step 4: Update the meta-plan status table**

Add a row for this plan (mark DONE on merge, with the FF/merge SHA and `v0.2.4`), and add two **deferred** rows so they are on the record:
- *Data-store runtime parity* — parameterize data-store endpoints, conditional `depends_on`, managed/container/native runtimes first-class + docs; resolves the `services.yml`/`dev.yml` lock decision. No urgency (consumers use colocated docker).
- *Full reverse integrity-coverage check + battery-infra classification* — classify the 23 unclassified infra files (18 battery observability, 2 battery scripts, `docs.yml`, `postgres.Dockerfile`, `traefik/certs/.gitkeep`) + a full infra-surface scan consuming `INTENTIONALLY_UNLOCKED`.

- [ ] **Step 5: Update `CLAUDE.md` Current State + commit**

Update the Current State pointer (and `Last updated` with tz). Stage and commit (the commit gate requires `CLAUDE.md` staged):
```bash
git add docs/superpowers/plans/2026-05-20-meta-plan.md CLAUDE.md documentation/ 2>/dev/null; git add -A
git commit -m "docs: record lock-taxonomy/doctor slice + defer data-store & reverse-coverage work"
```

---

## Branch-end review, merge, release

- **Branch-end whole-branch review (Opus)** via requesting-code-review before merge.
- Open the PR via finishing-a-development-branch → merge to `master` (clears `gate` + `build` + `render-complete`).
- **Cut `v0.2.4`** per the release-cut procedure (bump `pyproject` → `0.2.4`, `uv lock`, `DOGFOOD_COMMIT="v0.2.4"`, meta-plan/CLAUDE.md; release branch → PR → merge → lightweight tag `v0.2.4` → `release.yml`). Then Meridian pulls it with `framework upgrade . --to v0.2.4`, and its `scripts/seed.py` `--allow-drift` bridge becomes a no-op.

## Execution (review-model policy — restated per CLAUDE.md)

Subagent-driven, TDD per task. **Implementers → Sonnet** (Haiku for trivial doc-only steps). **Spec-compliance review → Sonnet. Code-quality review → Opus. Branch-end whole-branch review → Opus.** Pass `model` explicitly per role; do not let the generic "least powerful model" guidance collapse the reviewers. Gate cadence: per-task lightweight review + controller skip-marker commits; one branch-end full review (see `[[gate-cadence-framework-slices]]`).

## Self-review (done)

- **Spec coverage:** unlock seam files (T1) ✓; INTENTIONALLY_UNLOCKED + narrow guard (T1) ✓; seed.py example (T2) ✓; task doctor script (T3) + behavioral (T4) ✓; doctor task + lazy-guard pointers, not-in-ci (T5) ✓; README prereq (T6) ✓; docs + deferred rows (T7) ✓. Full reverse-coverage check + services.yml are spec Non-goals — correctly absent.
- **Placeholders:** none — every step has concrete code/commands.
- **Type/name consistency:** `INTENTIONALLY_UNLOCKED`, `scripts/doctor.sh`, `bash scripts/doctor.sh`, `task doctor`, `check`/`write_manifest`/`render_project` used consistently across tasks and match the existing codebase APIs.
