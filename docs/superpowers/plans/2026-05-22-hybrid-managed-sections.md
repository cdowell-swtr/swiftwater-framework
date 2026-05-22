# Hybrid Managed-Section Integrity (Plan 6a-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the **hybrid** file class to framework integrity — checksum the `FRAMEWORK:BEGIN/END` framework region of `CLAUDE.md`, `.env.example`, and `Taskfile.yml` (tamper-evident), while leaving content outside the markers free for the builder.

**Architecture:** Additive on the Plan 6a engine (`src/framework_cli/integrity/`). A new `sections.py` extracts/hashes the region between `FRAMEWORK:BEGIN`/`FRAMEWORK:END` marker lines (comment-syntax-agnostic). `build_manifest` records the *section* hash in the existing `sha256` field for `cls: hybrid` entries (no schema change); `check` verifies it; `restore` re-renders the canonical file and splices only the marker span, preserving builder content. `pyproject.toml` is deliberately excluded (its dependency arrays must stay builder-editable; breakage there is loud, not silent).

**Tech Stack:** Python 3.12, the existing integrity engine, Copier (re-render for restore), pytest. Design spec: `docs/superpowers/specs/2026-05-22-hybrid-managed-sections-design.md`.

---

## Scope

**In scope:** the `hybrid` class for three files (`CLAUDE.md`, `.env.example`, `Taskfile.yml`); the `sections.py` extractor; hybrid branches in `generate`/`checker`/`restore`; `HYBRID_TRACKED` in the registry; `FRAMEWORK:BEGIN/END` markers added to `.env.example` + `Taskfile.yml` (`CLAUDE.md` already has them).

**Out of scope (deliberate, per the design):** `pyproject.toml` (stays builder-owned); multiple regions per file (exactly one region per file); any new drift mechanism (6a's per-file `--allow-drift` covers in-region edits); CI step-0 activation (Plan 6b).

## Repo working agreement for EVERY commit in this plan

A `PreToolUse` hook **blocks `git commit` unless `CLAUDE.md` has a staged change.** For each "Commit" step:
1. Bump the `CLAUDE.md` **Current State → Last updated** line (datetime + `PDT`) with a one-line note of the task.
2. `git add <changed files> CLAUDE.md` — as **one** Bash call.
3. `git commit -m "…"` — as a **separate** Bash call (the hook checks staged state *before* the commit runs, so a combined `add && commit` fails).

End every commit message body with:
```
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

> NOTE on `CLAUDE.md`: from Task 4 onward, `CLAUDE.md` is a **registered hybrid file**. The per-commit "Last updated" bump edits the Current State pointer, which is the repo-root `CLAUDE.md` — that's the *framework repo's* file and is **not** a generated-project file, so it is unaffected by this plan's integrity logic (the logic only applies to rendered projects). Edit it normally.

## File Structure

**New (framework source):**
- `src/framework_cli/integrity/sections.py` — `section_span`, `section_content`, `section_sha256`.

**Modified (framework source):**
- `src/framework_cli/integrity/classes.py` — add `HYBRID_TRACKED` + include it in `rules()`.
- `src/framework_cli/integrity/generate.py` — hybrid branch in `build_manifest`.
- `src/framework_cli/integrity/checker.py` — hybrid branch in `check`.
- `src/framework_cli/integrity/restore.py` — hybrid splice path in `restore_file`.

**Modified (template payload — re-render + acceptance after):**
- `src/framework_cli/template/.env.example` — add `# FRAMEWORK:BEGIN/END` markers.
- `src/framework_cli/template/Taskfile.yml.jinja` — add `# FRAMEWORK:BEGIN/END` markers around the framework tasks.

**New / extended tests:**
- `tests/integrity/test_sections.py` (new)
- `tests/integrity/test_checker.py`, `test_generate.py`, `test_classes.py`, `test_restore.py` (extended)
- `tests/test_copier_runner.py` (markers render)
- `tests/acceptance/test_rendered_project.py` (end-to-end hybrid behavior)

---

### Task 1: The section extractor (`sections.py`)

**Files:**
- Create: `src/framework_cli/integrity/sections.py`
- Test: `tests/integrity/test_sections.py`

- [ ] **Step 1: Write the failing test** — Create `tests/integrity/test_sections.py`:

```python
from framework_cli.integrity.sections import section_content, section_sha256, section_span

_DOC = "\n".join(
    [
        "# Title",
        "<!-- FRAMEWORK:BEGIN -->",
        "managed line one",
        "managed line two",
        "<!-- FRAMEWORK:END -->",
        "## Builder notes",
        "builder text",
    ]
)


def test_section_content_is_text_between_markers():
    assert section_content(_DOC) == "managed line one\nmanaged line two"


def test_section_span_is_inclusive_of_marker_lines():
    assert section_span(_DOC) == (1, 4)


def test_section_sha256_is_stable_and_ignores_outside_edits():
    edited = _DOC.replace("builder text", "DIFFERENT builder text")
    assert section_sha256(edited) == section_sha256(_DOC)


def test_section_sha256_changes_when_inside_edited():
    edited = _DOC.replace("managed line one", "managed line ONE")
    assert section_sha256(edited) != section_sha256(_DOC)


def test_missing_markers_return_none():
    assert section_content("no markers here") is None
    assert section_span("no markers here") is None
    assert section_sha256("no markers here") is None


def test_unbalanced_or_out_of_order_markers_return_none():
    only_begin = "<!-- FRAMEWORK:BEGIN -->\nx\n"
    assert section_content(only_begin) is None
    reversed_markers = "# FRAMEWORK:END\nx\n# FRAMEWORK:BEGIN\n"
    assert section_span(reversed_markers) is None
    two_begins = "# FRAMEWORK:BEGIN\na\n# FRAMEWORK:BEGIN\nb\n# FRAMEWORK:END\n"
    assert section_content(two_begins) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_sections.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.integrity.sections`.

- [ ] **Step 3: Implement** — Create `src/framework_cli/integrity/sections.py`:

```python
"""Extract and hash the FRAMEWORK:BEGIN/END region of a hybrid file.

Markers are matched by the literal tokens appearing on a line, so this is agnostic to
the file's comment syntax (`<!-- -->`, `#`, ...). Exactly one balanced, in-order pair is
required; anything else is treated as "no section" (the checker reports it as damaged).
"""

from __future__ import annotations

from framework_cli.integrity.hashing import sha256_bytes

_BEGIN = "FRAMEWORK:BEGIN"
_END = "FRAMEWORK:END"


def section_span(text: str) -> tuple[int, int] | None:
    """The (begin, end) line indices inclusive of the marker lines, or None if the
    markers are absent, duplicated, or out of order."""
    lines = text.splitlines()
    begins = [i for i, line in enumerate(lines) if _BEGIN in line]
    ends = [i for i, line in enumerate(lines) if _END in line]
    if len(begins) != 1 or len(ends) != 1 or begins[0] >= ends[0]:
        return None
    return begins[0], ends[0]


def section_content(text: str) -> str | None:
    """The text strictly between the marker lines, or None if the markers are malformed."""
    span = section_span(text)
    if span is None:
        return None
    begin, end = span
    return "\n".join(text.splitlines()[begin + 1 : end])


def section_sha256(text: str) -> str | None:
    """SHA-256 of the managed section, or None if the markers are malformed."""
    content = section_content(text)
    return None if content is None else sha256_bytes(content.encode())
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_sections.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/sections.py tests/integrity/test_sections.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): FRAMEWORK:BEGIN/END section extractor"
```

---

### Task 2: Add markers to `.env.example` and `Taskfile.yml.jinja`

**Files:**
- Modify: `src/framework_cli/template/.env.example`
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Test: `tests/test_copier_runner.py`

`CLAUDE.md.jinja` already has its markers — no change there. This task only adds markers to the two unmarked files and asserts all three render with a well-formed section. No engine/registry change yet (the markers are inert until Task 4), so the existing suite stays green.

- [ ] **Step 1: Write the failing test** — Add to `tests/test_copier_runner.py` (the file already imports `render_project` and `Path`; reuse them):

```python
def test_hybrid_files_render_with_markers(tmp_path: Path):
    from framework_cli.integrity.sections import section_content

    dest = tmp_path / "proj"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    for rel in ("CLAUDE.md", ".env.example", "Taskfile.yml"):
        text = (dest / rel).read_text()
        assert section_content(text) is not None, f"{rel} has no FRAMEWORK section"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_hybrid_files_render_with_markers -q`
Expected: FAIL — `.env.example` and `Taskfile.yml` have no markers yet (assertion error on the first of them).

- [ ] **Step 3: Implement the markers**

In `src/framework_cli/template/.env.example`, wrap the entire current body in a region and add a builder area. Replace the whole file with:

```
# FRAMEWORK:BEGIN
# Managed by the framework. Add your own config below FRAMEWORK:END; the framework will not overwrite it.
# Copy to .env (gitignored) and adjust. All vars are read via config/settings.py.
# Application environment: dev | test | staging | prod (drives log level + config).
APP_ENVIRONMENT=dev
# Optional explicit log level (DEBUG/INFO/WARNING/ERROR). Unset = derived from APP_ENVIRONMENT.
# APP_LOG_LEVEL=
# SLO thresholds (drive /health evaluation and, in Plan 3b, dashboards + alerts).
APP_SLO_REQUEST_LATENCY_P99_MS=200
APP_SLO_ERROR_RATE_PCT=1.0
# Database. Host-side tooling (alembic, tests) uses localhost; the Compose stack
# injects the in-network URL (postgres / postgres-test).
APP_DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/app
# FRAMEWORK:END

# Your app's config below.
```

In `src/framework_cli/template/Taskfile.yml.jinja`, insert a `BEGIN` marker immediately after the `tasks:` line and an `END` marker after the final task. Specifically:

(a) Change the top from:
```yaml
tasks:
  integrity:
```
to:
```yaml
tasks:
  # FRAMEWORK:BEGIN
  # Managed by the framework. Add your own tasks below FRAMEWORK:END; the framework will not overwrite them.
  integrity:
```

(b) Change the end from:
```yaml
  push:
    desc: Push the current branch — triggers the authoritative GitHub Actions CI pipeline.
    cmds:
      - git push
```
to:
```yaml
  push:
    desc: Push the current branch — triggers the authoritative GitHub Actions CI pipeline.
    cmds:
      - git push
  # FRAMEWORK:END

  # Add your project's tasks below.
```

- [ ] **Step 4: Run it to verify it passes + nothing else broke**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS, including the existing `test_taskfile_wires_integrity` (the substring `"\n  integrity:\n"` is still present — the `# FRAMEWORK:BEGIN` comment line sits before `  integrity:`, which is still on its own `\n  integrity:\n` line).

- [ ] **Step 5: Verify the rendered Taskfile is still valid YAML and parses for `task`**

Run:
```bash
uv run python -c "
import tempfile, pathlib, yaml
from framework_cli.copier_runner import render_project
d = pathlib.Path(tempfile.mkdtemp())/'p'
render_project(d, {'project_name':'Demo','project_slug':'demo','package_name':'demo','python_version':'3.12'})
doc = yaml.safe_load((d/'Taskfile.yml').read_text())
print('tasks parse OK:', sorted(doc['tasks'])[:5], '...')
"
```
Expected: prints a task list (the `#` markers are valid YAML comments — `tasks` still parses with all task keys present).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/.env.example \
        src/framework_cli/template/Taskfile.yml.jinja \
        tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): add FRAMEWORK markers to .env.example and Taskfile"
```

---

### Task 3: Hybrid verification in the checker

**Files:**
- Modify: `src/framework_cli/integrity/checker.py`
- Test: `tests/integrity/test_checker.py`

Add a hybrid branch to the tracked-tier logic. Tested with a synthetic project (a manually-built manifest + a marked file), independent of the registry — which is updated in Task 4.

- [ ] **Step 1: Write the failing test** — Add to `tests/integrity/test_checker.py`:

```python
def _hybrid_project(tmp_path: Path) -> Path:
    from framework_cli.integrity.manifest import Entry, Manifest
    from framework_cli.integrity.sections import section_sha256

    proj = tmp_path / "hyb"
    (proj / ".framework").mkdir(parents=True)
    claude = proj / "CLAUDE.md"
    claude.write_text(
        "# Title\n<!-- FRAMEWORK:BEGIN -->\nmanaged line\n<!-- FRAMEWORK:END -->\n"
        "## Notes\nbuilder text\n"
    )
    manifest = Manifest(
        framework_version="0.1.0",
        entries=[
            Entry("CLAUDE.md", "hybrid", "tracked", sha256=section_sha256(claude.read_text()))
        ],
    )
    (proj / ".framework" / "integrity.lock").write_text(manifest.dumps())
    return proj


def test_hybrid_clean_has_no_findings(tmp_path: Path):
    assert check(_hybrid_project(tmp_path)) == []


def test_hybrid_edit_outside_the_block_is_clean(tmp_path: Path):
    proj = _hybrid_project(tmp_path)
    claude = proj / "CLAUDE.md"
    claude.write_text(claude.read_text() + "\nmore builder notes\n")
    assert check(proj) == []


def test_hybrid_edit_inside_the_block_is_fatal(tmp_path: Path):
    proj = _hybrid_project(tmp_path)
    claude = proj / "CLAUDE.md"
    claude.write_text(claude.read_text().replace("managed line", "managed LINE"))
    findings = check(proj)
    assert any(f.path == "CLAUDE.md" and f.fatal for f in findings)


def test_hybrid_damaged_markers_are_fatal(tmp_path: Path):
    proj = _hybrid_project(tmp_path)
    (proj / "CLAUDE.md").write_text("markers deleted\n")
    findings = check(proj)
    assert any(f.path == "CLAUDE.md" and f.fatal and "markers" in f.problem for f in findings)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_checker.py -k hybrid -q`
Expected: FAIL — the checker has no hybrid branch yet, so `test_hybrid_edit_inside_the_block_is_fatal` and `test_hybrid_damaged_markers_are_fatal` fail (no finding produced).

- [ ] **Step 3: Implement** — In `src/framework_cli/integrity/checker.py`:

Change the import line
```python
from framework_cli.integrity.hashing import sha256_file
```
to
```python
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.sections import section_sha256
```

Then replace the tracked-tier block (currently from `# tracked tier` through the `# hybrid section verification arrives in Plan 6a-2.` comment) with:

```python
        # tracked tier (locked = full file; hybrid = the FRAMEWORK:BEGIN/END section)
        if not f.is_file():
            findings.append(
                Finding(e.path, "framework file is missing", f"framework restore {e.path}", True)
            )
            continue
        if e.cls == "hybrid":
            section_hash = section_sha256(f.read_text())
            if section_hash is None:
                findings.append(
                    Finding(
                        e.path,
                        "managed-section markers are missing or damaged",
                        f"framework restore {e.path}",
                        True,
                    )
                )
            elif section_hash != e.sha256:
                findings.append(
                    Finding(
                        e.path,
                        "framework-managed section has been altered",
                        f"framework restore {e.path}  (or `framework integrity "
                        f"--allow-drift {e.path}` to keep your change)",
                        True,
                    )
                )
        elif sha256_file(f) != e.sha256:  # cls == "locked"
            findings.append(
                Finding(
                    e.path,
                    "locked file has been altered",
                    f"framework restore {e.path}  (or `framework integrity "
                    f"--allow-drift {e.path}` to keep your change)",
                    True,
                )
            )
```

> Note: the missing-file message is generalized from "locked file is missing" to "framework file is missing" (it now covers hybrid too). The existing 6a tests assert only `path`/`fatal`, not the message, so they remain green.

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_checker.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS (all checker tests — the 6a ones plus the four new hybrid ones); mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/checker.py tests/integrity/test_checker.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): verify hybrid managed sections in the checker"
```

---

### Task 4: Generate hybrid entries + register the hybrid files (turn-on)

**Files:**
- Modify: `src/framework_cli/integrity/generate.py`
- Modify: `src/framework_cli/integrity/classes.py`
- Test: `tests/integrity/test_generate.py`, `tests/integrity/test_classes.py`

This is the moment hybrid integrity goes live: register the three files and make `build_manifest` record their section hashes (markers exist from Task 2; the checker verifies them from Task 3).

- [ ] **Step 1: Write the failing tests**

Add to `tests/integrity/test_classes.py`:

```python
from framework_cli.integrity.classes import HYBRID_TRACKED  # add to existing imports


def test_every_hybrid_path_renders_with_markers(tmp_path: Path):
    from framework_cli.integrity.sections import section_content

    dest = _render(tmp_path)
    for rel in HYBRID_TRACKED:
        assert (dest / rel).is_file(), f"hybrid path not rendered: {rel}"
        assert section_content((dest / rel).read_text()) is not None, f"{rel} lacks markers"


def test_no_hybrid_path_is_gitignored(tmp_path: Path):
    dest = _render(tmp_path)
    spec = pathspec.PathSpec.from_lines(
        "gitignore", (dest / ".gitignore").read_text().splitlines()
    )
    leaked = [p for p in HYBRID_TRACKED if spec.match_file(p)]
    assert leaked == [], f"hybrid files excluded by .gitignore: {leaked}"
```

Add to `tests/integrity/test_generate.py`:

```python
def test_build_manifest_records_hybrid_section_hash(tmp_path: Path):
    from framework_cli.copier_runner import render_project
    from framework_cli.integrity.sections import section_sha256

    dest = tmp_path / "proj"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    manifest = build_manifest(dest, "0.1.0")
    claude = next(e for e in manifest.entries if e.path == "CLAUDE.md")
    assert claude.cls == "hybrid" and claude.tier == "tracked"
    assert claude.sha256 == section_sha256((dest / "CLAUDE.md").read_text())


def test_build_manifest_raises_when_hybrid_file_lacks_markers(tmp_path: Path):
    # A fake project: every locked path present, but a hybrid file with NO markers.
    proj = tmp_path / "p"
    for rel in LOCKED_TRACKED:
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"content of {rel}\n")
    (proj / ".gitignore").write_text("")
    for rel in ("CLAUDE.md", "Taskfile.yml"):
        (proj / rel).write_text("no markers\n")
    (proj / ".env.example").write_text("no markers\n")
    with pytest.raises(AuthoringError, match="markers"):
        build_manifest(proj, "0.1.0")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/integrity/test_classes.py tests/integrity/test_generate.py -q`
Expected: FAIL — `HYBRID_TRACKED` doesn't exist; `build_manifest` neither records hybrid entries nor raises on missing markers.

- [ ] **Step 3: Implement**

In `src/framework_cli/integrity/classes.py`, add the `HYBRID_TRACKED` tuple after `GITIGNORED_EXISTENCE`:

```python
# Hybrid + tracked: files the builder extends, carrying a framework-owned region delimited
# by FRAMEWORK:BEGIN/END. The section between the markers is checksummed; content outside is
# the builder's. (pyproject.toml is intentionally excluded — its dependency arrays must stay
# builder-editable, and its breakage is loud, not silent.)
HYBRID_TRACKED: tuple[str, ...] = ("CLAUDE.md", ".env.example", "Taskfile.yml")
```

And update `rules()` to include them:

```python
def rules() -> list[Rule]:
    """The full classification: locked + hybrid tracked files, plus gitignored/existence paths."""
    locked = [Rule(p, "locked", "tracked") for p in LOCKED_TRACKED]
    hybrid = [Rule(p, "hybrid", "tracked") for p in HYBRID_TRACKED]
    gitignored = [Rule(p, "locked", "gitignored") for p in GITIGNORED_EXISTENCE]
    return locked + hybrid + gitignored
```

In `src/framework_cli/integrity/generate.py`, add the import:

```python
from framework_cli.integrity.sections import section_sha256
```

Then, inside `build_manifest`'s `if rule.tier == "tracked":` block, replace the single `entries.append(...)` (the locked-only one) so it branches on `cls`:

```python
            f = project / rule.path
            if not f.is_file():
                raise AuthoringError(
                    f"{rule.path} is declared locked but was not rendered."
                )
            if rule.cls == "hybrid":
                section_hash = section_sha256(f.read_text())
                if section_hash is None:
                    raise AuthoringError(
                        f"{rule.path} is a hybrid file but has no FRAMEWORK:BEGIN/END markers."
                    )
                entries.append(Entry(rule.path, rule.cls, rule.tier, sha256=section_hash))
            else:
                entries.append(
                    Entry(rule.path, rule.cls, rule.tier, sha256=sha256_file(f))
                )
```

(The gitignore-match check and the `not f.is_file()` check above it are unchanged; only the entry construction now branches on `rule.cls`.)

- [ ] **Step 4: Run the integrity suite to verify it passes**

Run: `uv run pytest tests/integrity -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS — `build_manifest` now records section hashes for the three hybrid files; the checker (Task 3) verifies them; existing locked/gitignored behavior unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/generate.py src/framework_cli/integrity/classes.py \
        tests/integrity/test_generate.py tests/integrity/test_classes.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): register hybrid files + record section hashes (turn-on)"
```

---

### Task 5: Hybrid restore (splice the block, preserve builder content)

**Files:**
- Modify: `src/framework_cli/integrity/restore.py`
- Test: `tests/integrity/test_restore.py`

- [ ] **Step 1: Write the failing test** — Add to `tests/integrity/test_restore.py`:

```python
from framework_cli.integrity.sections import section_content, section_span


def test_restore_hybrid_fixes_block_and_preserves_builder_content(tmp_path: Path):
    proj = _new_project(tmp_path)  # render + write_manifest (now includes hybrid entries)
    claude = proj / "CLAUDE.md"
    original = claude.read_text()
    begin, _ = section_span(original)  # type: ignore[misc]
    lines = original.splitlines()
    lines[begin + 1] = lines[begin + 1] + "  TAMPER"  # edit first in-block line
    claude.write_text("\n".join(lines) + "\nMY BUILDER NOTE\n")  # + content outside the block

    assert any(f.path == "CLAUDE.md" and f.fatal for f in check(proj, ci=True))

    restore_file(proj, "CLAUDE.md")

    restored = claude.read_text()
    assert "TAMPER" not in (section_content(restored) or "")  # block restored
    assert "MY BUILDER NOTE" in restored  # builder content outside the block preserved
    assert check(proj, ci=True) == []


def test_restore_hybrid_errors_when_markers_destroyed(tmp_path: Path):
    proj = _new_project(tmp_path)
    (proj / "CLAUDE.md").write_text("the builder deleted the markers\n")
    try:
        restore_file(proj, "CLAUDE.md")
    except ValueError as exc:
        assert "markers" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError when markers are destroyed")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_restore.py -k hybrid -q`
Expected: FAIL — restore overwrites the whole file (losing `MY BUILDER NOTE`) and records a full-file hash, so the assertions fail.

- [ ] **Step 3: Implement** — In `src/framework_cli/integrity/restore.py`:

Add the import:

```python
from framework_cli.integrity.sections import section_span, section_sha256
```

Add this helper above `restore_file`:

```python
def _restore_section(target: Path, canonical: Path) -> None:
    """Replace target's FRAMEWORK:BEGIN/END span with canonical's, preserving outside content."""
    target_text = target.read_text()
    t_span = section_span(target_text)
    if t_span is None:
        raise ValueError(
            f"{target.name}: managed-section markers are missing or damaged — "
            "fix the FRAMEWORK:BEGIN/END markers or re-scaffold"
        )
    canonical_text = canonical.read_text()
    c_span = section_span(canonical_text)
    if c_span is None:  # the bundled template should always be marked
        raise ValueError(f"{target.name}: canonical template is missing its markers")
    t_lines = target_text.splitlines()
    c_lines = canonical_text.splitlines()
    new_lines = (
        t_lines[: t_span[0]] + c_lines[c_span[0] : c_span[1] + 1] + t_lines[t_span[1] + 1 :]
    )
    trailing = "\n" if target_text.endswith("\n") else ""
    target.write_text("\n".join(new_lines) + trailing)
```

Then, in `restore_file`, branch the write and the hash refresh on `entry.cls`. Replace the body from the `with tempfile.TemporaryDirectory()` block through the manifest rewrite with:

```python
    with tempfile.TemporaryDirectory() as tmp:
        canonical_root = Path(tmp) / "render"
        render_project(canonical_root, _answers(project))
        canonical = canonical_root / rel
        if not canonical.is_file():
            raise ValueError(f"{rel} was not produced by the canonical template")
        if entry.cls == "hybrid":
            _restore_section(project / rel, canonical)
        else:
            (project / rel).write_bytes(canonical.read_bytes())

    if entry.cls == "hybrid":
        new_sha = section_sha256((project / rel).read_text())
    else:
        new_sha = sha256_file(project / rel)
    manifest.entries = [
        replace(e, sha256=new_sha, drift=False) if e.path == rel else e
        for e in manifest.entries
    ]
    lock.write_text(manifest.dumps())
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_restore.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS (the 6a locked-restore tests plus the two new hybrid ones); mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/restore.py tests/integrity/test_restore.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): hybrid restore splices the block, preserves builder content"
```

---

### Task 6: End-to-end acceptance + full gate

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

Proves the defining hybrid behavior against a real rendered project: an edit *outside* the markers stays clean; an edit *inside* is fatal. No Docker required.

- [ ] **Step 1: Write the test** — Add to `tests/acceptance/test_rendered_project.py` (the module already imports `check`, `render_project`, and the manifest helpers from the Task-10 work in Plan 6a; reuse them — add `from framework_cli.integrity.sections import section_span` at the top):

```python
def test_rendered_project_hybrid_section_integrity(tmp_path):
    from framework_cli.copier_runner import render_project
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version
    from framework_cli.integrity.sections import section_span

    dest = tmp_path / "hyb"
    render_project(
        dest,
        {
            "project_name": "Hyb",
            "project_slug": "hyb",
            "package_name": "hyb",
            "python_version": "3.12",
        },
    )
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []

    claude = dest / "CLAUDE.md"
    # Editing OUTSIDE the markers (the builder's area) stays clean — defines "hybrid".
    claude.write_text(claude.read_text() + "\n## My project notes\nsome builder content\n")
    assert check(dest, ci=True) == []

    # Editing INSIDE the markers is fatal.
    text = claude.read_text()
    begin, _ = section_span(text)
    lines = text.splitlines()
    lines[begin + 1] = lines[begin + 1] + "  SNEAKY"
    claude.write_text("\n".join(lines) + "\n")
    findings = check(dest, ci=True)
    assert any(f.path == "CLAUDE.md" and f.fatal for f in findings)
```

- [ ] **Step 2: Run the new acceptance test**

Run: `uv run pytest "tests/acceptance/test_rendered_project.py::test_rendered_project_hybrid_section_integrity" -q`
Expected: PASS (depends only on the engine + the markers; no Docker).

- [ ] **Step 3: Run the full framework gate**

Run:
```bash
uv run ruff check .
uv run mypy src
rm -rf /tmp/pytest-of-chris/garbage-* 2>/dev/null
uv run pytest -q
```
Expected: ruff + mypy clean; full suite green (incl. the Docker-gated acceptance tests if Docker is present — among them `test_rendered_project_precommit_runs_clean`, which confirms the `.env.example` + `Taskfile` marker additions don't break the freshly generated project's first pre-commit pass). Report pass/fail/skip counts; `/tmp` cleanup warnings are harmless.

- [ ] **Step 4: Commit**

```bash
git add tests/acceptance/test_rendered_project.py CLAUDE.md
```
```bash
git commit -m "test(integrity): end-to-end hybrid section integrity on a rendered project"
```

---

## Self-Review

**1. Spec coverage (`docs/superpowers/specs/2026-05-22-hybrid-managed-sections-design.md`):**
- §2 scope = 3 files, pyproject excluded, one region per file, per-file drift → Task 4 registry (`HYBRID_TRACKED`, no pyproject); single-region enforced by `section_span` requiring exactly one balanced pair (Task 1); drift reuses 6a's `record_drift` (skip in `check`, cleared by restore) — no new code, verified by the existing 6a drift test still passing.
- §3 marker model + per-file placement → Task 2 (`.env.example`, `Taskfile`), CLAUDE.md already marked; comment-syntax-agnostic token match (Task 1).
- §4 engine: `sections.py` (Task 1); manifest reuses `sha256`, no schema change (Tasks 3–5 use the field as the section hash); generation hybrid branch + `AuthoringError` on missing markers (Task 4); checker hybrid branch with the three failure modes (Task 3); restore splices the inclusive span and errors on damaged markers (Task 5).
- §5 registry + failure modes → Task 4 (`HYBRID_TRACKED`, authoring tests extend); failure modes (altered / damaged markers / missing) in Tasks 3.
- §6 testing: `test_sections.py` (Task 1); generate hybrid + AuthoringError (Task 4); checker inside-fatal / outside-clean / damaged-fatal (Task 3); restore preserves-outside + damaged-errors (Task 5); template render + pre-commit-clean + `task` parse (Tasks 2, 6); acceptance edit-outside-clean / edit-inside-fatal (Task 6).

**2. Placeholder scan:** none — every code step shows complete code; every run step has a command + expected result. No "TBD"/"handle edge cases"/"similar to".

**3. Type consistency:** `section_span(text) -> tuple[int,int] | None`, `section_content(text) -> str | None`, `section_sha256(text) -> str | None` are used identically across Tasks 1, 3, 4, 5, 6. `Entry(path, cls, tier, sha256, drift)` and `Finding(path, problem, fix, fatal)` match their 6a definitions (no schema change). `build_manifest`/`check`/`restore_file` signatures are unchanged from 6a; only their bodies branch on `cls`. The checker import adds `section_sha256` alongside `sha256_file`; generate adds `section_sha256`; restore adds `section_span` + `section_sha256`.

**Sequencing note:** the checker's hybrid branch (Task 3) is exercised only by synthetic tests until Task 4 registers the hybrid files — intentional TDD staging so each task commits green.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-hybrid-managed-sections.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec → quality) between tasks, fast iteration.

**2. Inline Execution** — execute the tasks here with checkpoints.

Which approach?
