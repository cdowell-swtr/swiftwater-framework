# Framework Integrity (Plan 6a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `framework integrity` / `framework restore` — a CLI self-check that detects when a builder has altered, deleted, or moved the locked framework-infrastructure files a generated project depends on, backed by a checksum manifest generated at `framework new`.

**Architecture:** The integrity engine lives in the installed CLI (`src/framework_cli/integrity/`), never in scaffolded project code, so a builder deleting project files cannot disable the check (spec §17, §719). `framework new` renders the template, then writes `.framework/integrity.lock` — a self-checksummed JSON manifest recording each **locked** file's SHA-256 (tracked tier) plus the **gitignored** framework-managed paths (existence-only tier). `framework integrity` re-hashes and compares; `framework restore <file>` re-renders the canonical file from the bundled template. The local `task integrity` precondition runs it during `task dev`/`test`/`ci`.

**Tech Stack:** Python 3.12, Typer (CLI), Copier (render/restore), `pathspec` (gitignore matching), `pyyaml` (read `.copier-answers.yml`), stdlib `hashlib`/`json`, pytest + `typer.testing.CliRunner`.

---

## Scope

**In scope (this plan):**
- The integrity engine: file-class registry, checksum manifest (generate / load / self-verify), checker, restore.
- CLI: `framework integrity [--ci] [--allow-drift <file>]` and `framework restore <file>`.
- **Locked** class (full-file checksum, tracked tier) + **gitignored** existence tier. The `--allow-drift` escape hatch.
- Local wiring: a `task integrity` target + preconditions on `dev`/`test`/`ci`.
- Framework-side unit tests + an acceptance test proving a rendered project verifies clean, a tampered locked file fails, and `restore` fixes it.

**Deferred (explicitly out of scope here):**
- **Hybrid managed-section files** (`CLAUDE.md`, `.env.example`, `pyproject.toml`, `Taskfile.yml` framework blocks delimited by `FRAMEWORK:BEGIN/END`). The manifest schema already carries a `cls: "hybrid"` value and a `section_sha256` slot so this lands purely additively as **Plan 6a-2**. No `FRAMEWORK:*` markers are added in 6a.
- **CI step-0 activation** (`framework integrity --ci` as a real GitHub Actions job). It requires installing the framework CLI in CI from a portable, versioned source — which is exactly **Plan 6b**'s deliverable (the template-source/versioning model). 6a leaves the `ci.yml` integrity seam job in place and only corrects its comment to point at 6b. The engine is fully exercised locally and by the acceptance test.
- **`framework upskill` / `framework check`** — Plan 6b.
- **Restore-at-an-older-version.** 6a's `restore` re-renders from the *installed* CLI's bundled template; cross-version restore (`copier update` semantics) needs 6b's versioned source. The manifest records `framework_version` now so 6b can use it.

## Repo working agreement for EVERY commit in this plan

This repo has a `PreToolUse` hook that **blocks `git commit` unless `CLAUDE.md` has a staged change**. For each "Commit" step below:
1. Bump the `CLAUDE.md` **Current State → Last updated** line (datetime + `PDT`) and a short note of what the task did.
2. `git add <changed files> CLAUDE.md` — as **one** Bash call.
3. `git commit -m "…"` — as a **separate** Bash call (the hook inspects staged state *before* the commit runs, so a combined `add && commit` fails).

End every commit message body with:
```
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

## File Structure

**New (framework source — gets ruff + mypy):**
- `src/framework_cli/integrity/__init__.py` — package marker + public re-exports.
- `src/framework_cli/integrity/hashing.py` — `sha256_bytes`, `sha256_file`.
- `src/framework_cli/integrity/manifest.py` — `Entry`, `Manifest` (JSON + self-checksum), `installed_framework_version`.
- `src/framework_cli/integrity/classes.py` — the `Rule` registry: which rendered paths are locked/tracked vs. gitignored/existence.
- `src/framework_cli/integrity/generate.py` — `build_manifest`, `write_manifest`, `AuthoringError`.
- `src/framework_cli/integrity/checker.py` — `Finding`, `check`, `record_drift`.
- `src/framework_cli/integrity/restore.py` — `restore_file`.

**Modified (framework source):**
- `src/framework_cli/cli.py` — call `write_manifest` from `new`; add `integrity` + `restore` commands.
- `pyproject.toml` — add `pathspec` + `pyyaml` to `[project] dependencies` (runtime).

**Modified (template payload — re-render + acceptance after):**
- `src/framework_cli/template/Taskfile.yml.jinja` — add `integrity` task + preconditions on `dev`/`test`/`ci`.
- `src/framework_cli/template/.github/workflows/ci.yml.jinja` — correct the step-0 comment to reference Plan 6b.

**New (framework tests):**
- `tests/integrity/__init__.py`
- `tests/integrity/test_hashing.py`, `test_manifest.py`, `test_classes.py`, `test_generate.py`, `test_checker.py`, `test_restore.py`
- `tests/test_cli.py` — extend (manifest written by `new`; `integrity`/`restore` commands).
- `tests/test_copier_runner.py` — extend (Taskfile renders the integrity wiring).
- `tests/acceptance/test_rendered_project.py` — add the end-to-end integrity test.

---

### Task 1: Integrity package + checksum helpers + runtime deps

**Files:**
- Create: `src/framework_cli/integrity/__init__.py`
- Create: `src/framework_cli/integrity/hashing.py`
- Create: `tests/integrity/__init__.py`
- Create: `tests/integrity/test_hashing.py`
- Modify: `pyproject.toml` (add runtime deps)

- [ ] **Step 1: Add runtime dependencies**

In `pyproject.toml`, change the `[project] dependencies` list to:

```toml
dependencies = [
    "typer>=0.15",
    "copier>=9.4",
    "pathspec>=0.12",
    "pyyaml>=6.0",
]
```

Then sync:

Run: `uv sync`
Expected: resolves and installs `pathspec` + `pyyaml`.

- [ ] **Step 2: Write the failing test**

Create `tests/integrity/__init__.py` (empty), then `tests/integrity/test_hashing.py`:

```python
from pathlib import Path

from framework_cli.integrity.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_is_stable():
    # Known SHA-256 of b"abc".
    assert sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_file_matches_bytes(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_bytes(b"hello world")
    assert sha256_file(f) == sha256_bytes(b"hello world")
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_hashing.py -q`
Expected: FAIL — `ModuleNotFoundError: framework_cli.integrity`.

- [ ] **Step 4: Implement**

Create `src/framework_cli/integrity/__init__.py`:

```python
"""Framework integrity engine — verifies generated-project scaffolding is intact.

Lives in the installed CLI (not in scaffolded project code) so a builder cannot
disable the check by editing project files (spec §17).
"""
```

Create `src/framework_cli/integrity/hashing.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file's contents (read as bytes — newline-agnostic)."""
    return sha256_bytes(path.read_bytes())
```

- [ ] **Step 5: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_hashing.py -q && uv run ruff check src tests && uv run mypy src`
Expected: PASS; ruff + mypy clean.

- [ ] **Step 6: Commit** (see the per-commit working agreement above)

```bash
# (bump CLAUDE.md Last updated first)
git add src/framework_cli/integrity/__init__.py src/framework_cli/integrity/hashing.py \
        tests/integrity/__init__.py tests/integrity/test_hashing.py pyproject.toml uv.lock CLAUDE.md
```
```bash
git commit -m "feat(integrity): checksum helpers + integrity package + pathspec/pyyaml deps"
```

---

### Task 2: The manifest model (JSON + self-checksum)

**Files:**
- Create: `src/framework_cli/integrity/manifest.py`
- Test: `tests/integrity/test_manifest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integrity/test_manifest.py`:

```python
import json

from framework_cli.integrity.manifest import Entry, Manifest


def _sample() -> Manifest:
    return Manifest(
        framework_version="0.1.0",
        entries=[
            Entry(path="b.yml", cls="locked", tier="tracked", sha256="bbb"),
            Entry(path="a.yml", cls="locked", tier="tracked", sha256="aaa"),
            Entry(path=".env", cls="locked", tier="gitignored", sha256=None),
        ],
    )


def test_roundtrip_preserves_entries():
    m = _sample()
    back = Manifest.loads(m.dumps())
    assert {e.path for e in back.entries} == {"a.yml", "b.yml", ".env"}
    assert back.framework_version == "0.1.0"
    assert back.version == 1


def test_dump_is_sorted_and_self_checksummed():
    doc = json.loads(_sample().dumps())
    assert [e["path"] for e in doc["entries"]] == [".env", "a.yml", "b.yml"]
    assert doc["self_sha256"] == Manifest.loads(_sample().dumps()).self_sha256()


def test_tampering_with_an_entry_breaks_the_self_checksum():
    text = _sample().dumps()
    doc = json.loads(text)
    stored = doc["self_sha256"]
    doc["entries"][0]["sha256"] = "tampered"
    tampered = json.dumps(doc)
    # The recomputed checksum of the tampered body no longer matches the stored value.
    assert Manifest.loads(tampered).self_sha256() != stored


def test_gitignored_entry_carries_no_checksum():
    doc = json.loads(_sample().dumps())
    env = next(e for e in doc["entries"] if e["path"] == ".env")
    assert "sha256" not in env
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_manifest.py -q`
Expected: FAIL — `ModuleNotFoundError` / `ImportError`.

- [ ] **Step 3: Implement**

Create `src/framework_cli/integrity/manifest.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from framework_cli.integrity.hashing import sha256_bytes

MANIFEST_VERSION = 1
_DIST_NAME = "framework-cli"


def installed_framework_version() -> str:
    """Version of the installed framework CLI (recorded in the manifest)."""
    try:
        return version(_DIST_NAME)
    except PackageNotFoundError:  # pragma: no cover - only in odd install states
        return "0+unknown"


@dataclass(frozen=True)
class Entry:
    path: str
    cls: str  # "locked" | "hybrid"
    tier: str  # "tracked" | "gitignored"
    sha256: str | None = None  # locked/tracked: full-file hash; gitignored: None
    drift: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"path": self.path, "cls": self.cls, "tier": self.tier}
        if self.sha256 is not None:
            d["sha256"] = self.sha256
        if self.drift:
            d["drift"] = True
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Entry":
        return Entry(
            path=d["path"],
            cls=d["cls"],
            tier=d["tier"],
            sha256=d.get("sha256"),
            drift=bool(d.get("drift", False)),
        )


@dataclass
class Manifest:
    framework_version: str
    entries: list[Entry]
    version: int = MANIFEST_VERSION

    def _body(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "framework_version": self.framework_version,
            "entries": [
                e.to_dict() for e in sorted(self.entries, key=lambda x: x.path)
            ],
        }

    def self_sha256(self) -> str:
        canonical = json.dumps(self._body(), sort_keys=True, separators=(",", ":"))
        return sha256_bytes(canonical.encode())

    def dumps(self) -> str:
        doc = self._body()
        doc["self_sha256"] = self.self_sha256()
        return json.dumps(doc, indent=2, sort_keys=True) + "\n"

    @staticmethod
    def loads(text: str) -> "Manifest":
        doc = json.loads(text)
        return Manifest(
            framework_version=doc["framework_version"],
            entries=[Entry.from_dict(e) for e in doc["entries"]],
            version=doc["version"],
        )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_manifest.py -q && uv run mypy src`
Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/manifest.py tests/integrity/test_manifest.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): self-checksummed JSON manifest model"
```

---

### Task 3: File-class registry + authoring invariants

**Files:**
- Create: `src/framework_cli/integrity/classes.py`
- Test: `tests/integrity/test_classes.py`

The registry lists **rendered** paths (Copier has already stripped `.jinja` and interpolated `{{package_name}}` by the time we hash). Two framework-authoring guarantees are unit-tested: (a) every locked/tracked path actually exists in a freshly rendered project (no stale entries), and (b) no locked/tracked path is excluded by the rendered `.gitignore` (spec §712 — you cannot checksum-verify a file that was never committed).

- [ ] **Step 1: Write the failing test**

Create `tests/integrity/test_classes.py`:

```python
from pathlib import Path

import pathspec

from framework_cli.copier_runner import render_project
from framework_cli.integrity.classes import GITIGNORED_EXISTENCE, LOCKED_TRACKED, rules


def _render(tmp_path: Path) -> Path:
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
    return dest


def test_every_locked_path_exists_in_a_rendered_project(tmp_path: Path):
    dest = _render(tmp_path)
    missing = [p for p in LOCKED_TRACKED if not (dest / p).is_file()]
    assert missing == [], f"stale locked-registry entries (not rendered): {missing}"


def test_no_locked_path_is_gitignored(tmp_path: Path):
    dest = _render(tmp_path)
    spec = pathspec.PathSpec.from_lines(
        "gitwildmatch", (dest / ".gitignore").read_text().splitlines()
    )
    leaked = [p for p in LOCKED_TRACKED if spec.match_file(p)]
    assert leaked == [], f"locked files excluded by .gitignore (cannot be tracked): {leaked}"


def test_rules_cover_both_tiers():
    by_tier = {r.tier for r in rules()}
    assert by_tier == {"tracked", "gitignored"}
    assert set(GITIGNORED_EXISTENCE) == {r.glob for r in rules() if r.tier == "gitignored"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_classes.py -q`
Expected: FAIL — `ImportError` on `framework_cli.integrity.classes`.

- [ ] **Step 3: Implement**

Create `src/framework_cli/integrity/classes.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    glob: str  # rendered path, relative to the project root
    cls: str  # "locked" | "hybrid"
    tier: str  # "tracked" | "gitignored"


# Locked + tracked: pure framework infrastructure a builder must never edit (spec §17).
# These are full-file checksummed and must be git-tracked.
LOCKED_TRACKED: tuple[str, ...] = (
    ".github/workflows/ci.yml",
    ".github/workflows/deploy-staging.yml",
    ".github/workflows/deploy-prod.yml",
    ".github/dependabot.yml",
    ".pre-commit-config.yaml",
    ".gitattributes",
    ".dockerignore",
    "alembic.ini",
    "infra/compose/base.yml",
    "infra/compose/dev.yml",
    "infra/compose/prod.yml",
    "infra/compose/staging.yml",
    "infra/compose/test.yml",
    "infra/deploy/strategy.sh",
    "infra/deploy/notify.sh",
    "infra/deploy/README.md",
    "infra/docker/Dockerfile",
    "infra/traefik/traefik.yml",
    "infra/traefik/dynamic/tls.yml",
    "infra/observability/alertmanager/alertmanager.yml",
    "infra/observability/loki/loki-config.yml",
    "infra/observability/otel/otel-collector.yml",
    "infra/observability/prometheus/prometheus.yml",
    "infra/observability/prometheus/alerts/slo_alerts.yml",
    "infra/observability/promtail/promtail-config.yml",
    "infra/observability/tempo/tempo.yml",
    "infra/observability/grafana/dashboards/slo.json",
    "infra/observability/grafana/provisioning/dashboards/provider.yml",
    "infra/observability/grafana/provisioning/datasources/loki.yml",
    "infra/observability/grafana/provisioning/datasources/prometheus.yml",
    "infra/observability/grafana/provisioning/datasources/tempo.yml",
    "scripts/check_migrations.py",
    "scripts/coverage.sh",
    "scripts/entrypoint.sh",
    "scripts/export-openapi.sh",
    "scripts/gen_observability.py",
    "scripts/load.sh",
    "scripts/seed.py",
)

# Gitignored + existence-only: framework-managed files legitimately absent from a fresh
# clone (.env derived from .env.example; mkcert certs). Verified locally only, never in CI.
GITIGNORED_EXISTENCE: tuple[str, ...] = (
    ".env",
    "infra/traefik/certs/localhost.pem",
    "infra/traefik/certs/localhost-key.pem",
)


def rules() -> list[Rule]:
    """The full classification: locked/tracked files plus gitignored/existence paths."""
    locked = [Rule(p, "locked", "tracked") for p in LOCKED_TRACKED]
    gitignored = [Rule(p, "locked", "gitignored") for p in GITIGNORED_EXISTENCE]
    return locked + gitignored
```

> Note: app-source resilience/observability modules (`src/<pkg>/resilience/*`, `middleware/errors.py`) are *candidate*-locked per spec §701 but are intentionally excluded from this first registry to avoid false positives where builders legitimately extend them. Tightening the registry is a follow-on once 6a-2's hybrid sections exist.

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_classes.py -q`
Expected: PASS. If `test_every_locked_path_exists_in_a_rendered_project` fails, a registry path is wrong — fix the registry to match the rendered tree (do **not** weaken the test).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/classes.py tests/integrity/test_classes.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): locked/gitignored file-class registry + authoring invariants"
```

---

### Task 4: Manifest generation over a rendered project

**Files:**
- Create: `src/framework_cli/integrity/generate.py`
- Test: `tests/integrity/test_generate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integrity/test_generate.py`:

```python
from pathlib import Path

import pytest

from framework_cli.integrity.classes import LOCKED_TRACKED
from framework_cli.integrity.generate import AuthoringError, build_manifest, write_manifest
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Manifest


def _fake_project(tmp_path: Path, *, gitignore: str = "") -> Path:
    """A minimal stand-in project containing every locked path + a .gitignore."""
    proj = tmp_path / "proj"
    for rel in LOCKED_TRACKED:
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"content of {rel}\n")
    (proj / ".gitignore").write_text(gitignore)
    return proj


def test_build_manifest_checksums_every_locked_file(tmp_path: Path):
    proj = _fake_project(tmp_path)
    manifest = build_manifest(proj, "0.1.0")
    locked = {e.path: e for e in manifest.entries if e.tier == "tracked"}
    assert set(locked) == set(LOCKED_TRACKED)
    sample = next(iter(LOCKED_TRACKED))
    assert locked[sample].sha256 == sha256_file(proj / sample)


def test_build_manifest_includes_gitignored_existence_tier(tmp_path: Path):
    proj = _fake_project(tmp_path)
    manifest = build_manifest(proj, "0.1.0")
    env = next(e for e in manifest.entries if e.path == ".env")
    assert env.tier == "gitignored" and env.sha256 is None


def test_authoring_error_when_a_locked_file_is_gitignored(tmp_path: Path):
    # Mark a locked path as ignored — a framework authoring bug per spec §712.
    proj = _fake_project(tmp_path, gitignore="*.yml\n")
    with pytest.raises(AuthoringError, match="matches .gitignore"):
        build_manifest(proj, "0.1.0")


def test_authoring_error_when_a_locked_file_is_missing(tmp_path: Path):
    proj = _fake_project(tmp_path)
    (proj / "alembic.ini").unlink()
    with pytest.raises(AuthoringError, match="not rendered"):
        build_manifest(proj, "0.1.0")


def test_write_manifest_creates_loadable_lock(tmp_path: Path):
    proj = _fake_project(tmp_path)
    out = write_manifest(proj, "0.1.0")
    assert out == proj / ".framework" / "integrity.lock"
    Manifest.loads(out.read_text())  # parses without error
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_generate.py -q`
Expected: FAIL — `ImportError` on `framework_cli.integrity.generate`.

- [ ] **Step 3: Implement**

Create `src/framework_cli/integrity/generate.py`:

```python
from __future__ import annotations

from pathlib import Path

import pathspec

from framework_cli.integrity.classes import rules
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Entry, Manifest


class AuthoringError(Exception):
    """A framework authoring bug surfaced at manifest generation (not a builder error)."""


def _gitignore_spec(project: Path) -> pathspec.PathSpec:
    gi = project / ".gitignore"
    lines = gi.read_text().splitlines() if gi.is_file() else []
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def build_manifest(project: Path, framework_version: str) -> Manifest:
    """Build the integrity manifest for a rendered project.

    Enforces spec §712: a checksummed (tracked) file must exist and must not be
    excluded by the project's own .gitignore.
    """
    spec = _gitignore_spec(project)
    entries: list[Entry] = []
    for rule in rules():
        if rule.tier == "tracked":
            if spec.match_file(rule.glob):
                raise AuthoringError(
                    f"{rule.glob} is locked/tracked but matches .gitignore — a "
                    "checksummed file must be git-tracked (spec §17)."
                )
            f = project / rule.glob
            if not f.is_file():
                raise AuthoringError(
                    f"{rule.glob} is declared locked but was not rendered."
                )
            entries.append(
                Entry(rule.glob, rule.cls, rule.tier, sha256=sha256_file(f))
            )
        else:  # gitignored existence tier — recorded, never checksummed
            entries.append(Entry(rule.glob, rule.cls, rule.tier, sha256=None))
    return Manifest(framework_version=framework_version, entries=entries)


def write_manifest(project: Path, framework_version: str) -> Path:
    """Generate and write `.framework/integrity.lock`; return its path."""
    manifest = build_manifest(project, framework_version)
    out = project / ".framework" / "integrity.lock"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manifest.dumps())
    return out
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_generate.py -q && uv run mypy src`
Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/generate.py tests/integrity/test_generate.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): manifest generation with authoring invariants"
```

---

### Task 5: Generate the manifest at `framework new`

**Files:**
- Modify: `src/framework_cli/cli.py:19-41` (the `new` command)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
from framework_cli.integrity.manifest import Manifest


def test_new_writes_a_verifiable_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App"])
    assert result.exit_code == 0, result.output
    lock = tmp_path / "my-app" / ".framework" / "integrity.lock"
    assert lock.is_file()
    manifest = Manifest.loads(lock.read_text())
    # The rendered ci.yml is locked and recorded with a checksum.
    ci = next(e for e in manifest.entries if e.path == ".github/workflows/ci.yml")
    assert ci.cls == "locked" and ci.sha256
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_new_writes_a_verifiable_manifest -q`
Expected: FAIL — no `.framework/integrity.lock`.

- [ ] **Step 3: Implement**

In `src/framework_cli/cli.py`, add the import near the top:

```python
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.manifest import installed_framework_version
```

Then, in `new`, immediately after the `render_project(...)` call and before the success `typer.echo`, add:

```python
    write_manifest(dest, installed_framework_version())
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_cli.py -q && uv run mypy src`
Expected: PASS (all CLI tests); mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): write integrity.lock on framework new"
```

---

### Task 6: The checker (verify + drift recording)

**Files:**
- Create: `src/framework_cli/integrity/checker.py`
- Test: `tests/integrity/test_checker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integrity/test_checker.py`:

```python
from pathlib import Path

from framework_cli.integrity.checker import check, record_drift
from framework_cli.integrity.classes import LOCKED_TRACKED
from framework_cli.integrity.generate import write_manifest


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    for rel in LOCKED_TRACKED:
        f = proj / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"content of {rel}\n")
    (proj / ".gitignore").write_text(".env\ninfra/traefik/certs/*.pem\n")
    (proj / ".env").write_text("APP_ENVIRONMENT=dev\n")
    write_manifest(proj, "0.1.0")
    return proj


def test_clean_project_has_no_findings(tmp_path: Path):
    assert check(_project(tmp_path)) == []


def test_altered_locked_file_is_a_fatal_finding(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "alembic.ini").write_text("hacked\n")
    findings = check(proj)
    assert any(f.path == "alembic.ini" and f.fatal for f in findings)


def test_missing_locked_file_is_fatal(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "alembic.ini").unlink()
    findings = check(proj)
    assert any(f.path == "alembic.ini" and f.fatal for f in findings)


def test_tampered_manifest_is_fatal(tmp_path: Path):
    proj = _project(tmp_path)
    lock = proj / ".framework" / "integrity.lock"
    lock.write_text(lock.read_text().replace('"0.1.0"', '"9.9.9"'))
    findings = check(proj)
    assert len(findings) == 1 and findings[0].fatal
    assert "self-checksum" in findings[0].problem


def test_missing_gitignored_file_is_a_warning_local_only(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / ".env").unlink()
    # Local: a non-fatal warning.
    local = check(proj, ci=False)
    assert any(f.path == ".env" and not f.fatal for f in local)
    # CI: gitignored existence checks are skipped entirely.
    assert all(f.path != ".env" for f in check(proj, ci=True))


def test_drift_recorded_file_is_skipped(tmp_path: Path):
    proj = _project(tmp_path)
    (proj / "alembic.ini").write_text("builder's intentional change\n")
    record_drift(proj, ["alembic.ini"])
    assert all(f.path != "alembic.ini" for f in check(proj))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_checker.py -q`
Expected: FAIL — `ImportError` on `framework_cli.integrity.checker`.

- [ ] **Step 3: Implement**

Create `src/framework_cli/integrity/checker.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Manifest

_LOCK_REL = ".framework/integrity.lock"


@dataclass(frozen=True)
class Finding:
    path: str
    problem: str
    fix: str
    fatal: bool


def _load(project: Path) -> tuple[Manifest, str] | None:
    lock = project / _LOCK_REL
    if not lock.is_file():
        return None
    return Manifest.loads(lock.read_text()), lock.read_text()


def check(project: Path, ci: bool = False) -> list[Finding]:
    """Verify a project against its manifest. Returns findings (empty == intact)."""
    loaded = _load(project)
    if loaded is None:
        return [
            Finding(
                _LOCK_REL,
                "integrity manifest is missing",
                "restore it from version control, or re-scaffold",
                True,
            )
        ]
    manifest, text = loaded
    stored = json.loads(text).get("self_sha256")
    if stored != manifest.self_sha256():
        # The manifest itself was edited; its entries can no longer be trusted.
        return [
            Finding(
                _LOCK_REL,
                "manifest self-checksum mismatch (tampered)",
                "restore the manifest from version control",
                True,
            )
        ]

    findings: list[Finding] = []
    for e in manifest.entries:
        if e.drift:
            continue
        f = project / e.path
        if e.tier == "gitignored":
            if not ci and not f.exists():
                findings.append(
                    Finding(
                        e.path,
                        "framework-managed file is absent",
                        "create it (e.g. copy .env.example to .env) — local check only",
                        False,
                    )
                )
            continue
        # tracked tier
        if not f.is_file():
            findings.append(
                Finding(e.path, "locked file is missing", f"framework restore {e.path}", True)
            )
            continue
        if e.cls == "locked" and sha256_file(f) != e.sha256:
            findings.append(
                Finding(
                    e.path,
                    "locked file has been altered",
                    f"framework restore {e.path}  (or `framework integrity "
                    f"--allow-drift {e.path}` to keep your change)",
                    True,
                )
            )
        # hybrid section verification arrives in Plan 6a-2.
    return findings


def record_drift(project: Path, paths: list[str]) -> None:
    """Mark the given managed files as intentionally diverged and rewrite the manifest."""
    lock = project / _LOCK_REL
    manifest = Manifest.loads(lock.read_text())
    known = {e.path for e in manifest.entries}
    unknown = [p for p in paths if p not in known]
    if unknown:
        raise ValueError(f"not framework-managed file(s): {', '.join(unknown)}")
    wanted = set(paths)
    manifest.entries = [
        replace(e, drift=True) if e.path in wanted else e for e in manifest.entries
    ]
    lock.write_text(manifest.dumps())
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_checker.py -q && uv run mypy src`
Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/checker.py tests/integrity/test_checker.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): checker (verify, --ci tier, drift) "
```

---

### Task 7: `framework integrity` CLI command

**Files:**
- Modify: `src/framework_cli/cli.py` (add `integrity` command)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_integrity_passes_on_a_fresh_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["new", "My App"]).exit_code == 0
    monkeypatch.chdir(tmp_path / "my-app")
    result = runner.invoke(app, ["integrity", "--ci"])
    assert result.exit_code == 0, result.output
    assert "OK" in result.output


def test_integrity_fails_when_a_locked_file_is_altered(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["new", "My App"])
    project = tmp_path / "my-app"
    (project / "alembic.ini").write_text("tampered\n")
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["integrity", "--ci"])
    assert result.exit_code == 1
    assert "alembic.ini" in result.output


def test_integrity_allow_drift_then_passes(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["new", "My App"])
    project = tmp_path / "my-app"
    (project / "alembic.ini").write_text("tampered\n")
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["integrity", "--allow-drift", "alembic.ini"]).exit_code == 0
    assert runner.invoke(app, ["integrity", "--ci"]).exit_code == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py -k integrity -q`
Expected: FAIL — no `integrity` command (Typer exits non-zero with "No such command").

- [ ] **Step 3: Implement**

In `src/framework_cli/cli.py`, add imports:

```python
from framework_cli.integrity.checker import check, record_drift
```

Add the command (after `new`):

```python
@app.command()
def integrity(
    ci: bool = typer.Option(
        False, "--ci", help="CI mode: skip gitignored existence checks (fresh checkouts)."
    ),
    allow_drift: list[str] = typer.Option(
        [], "--allow-drift", help="Record a managed file as intentionally diverged."
    ),
) -> None:
    """Verify the framework scaffolding in the current project is intact."""
    project = Path.cwd()
    if allow_drift:
        try:
            record_drift(project, allow_drift)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"Recorded intentional drift: {', '.join(allow_drift)}")
        raise typer.Exit(0)

    findings = check(project, ci=ci)
    for f in findings:
        label = "ERROR" if f.fatal else "warning"
        typer.echo(f"{label}: {f.path}: {f.problem} — {f.fix}", err=f.fatal)
    if any(f.fatal for f in findings):
        fatal = sum(1 for f in findings if f.fatal)
        typer.echo(f"\nframework integrity: {fatal} problem(s) found.", err=True)
        raise typer.Exit(1)
    typer.echo("framework integrity: OK")
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_cli.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/cli.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): framework integrity command (--ci, --allow-drift)"
```

---

### Task 8: `framework restore <file>`

**Files:**
- Create: `src/framework_cli/integrity/restore.py`
- Modify: `src/framework_cli/cli.py` (add `restore` command)
- Test: `tests/integrity/test_restore.py`, `tests/test_cli.py`

`restore` re-renders the canonical file from the **bundled** template using the project's recorded Copier answers, overwrites the locked file (full-file for 6a), then refreshes that entry's checksum and clears any drift. (Hybrid block-only rewrite is 6a-2; cross-version restore is 6b.)

- [ ] **Step 1: Write the failing test**

Create `tests/integrity/test_restore.py`:

```python
from pathlib import Path

from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.generate import write_manifest
from framework_cli.integrity.restore import restore_file


def _new_project(tmp_path: Path) -> Path:
    dest = tmp_path / "demo"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    write_manifest(dest, installed_framework_version())
    return dest


def test_restore_recovers_an_altered_locked_file(tmp_path: Path):
    proj = _new_project(tmp_path)
    target = proj / "alembic.ini"
    canonical = target.read_text()
    target.write_text("tampered\n")
    assert any(f.path == "alembic.ini" and f.fatal for f in check(proj))

    restore_file(proj, "alembic.ini")

    assert target.read_text() == canonical
    assert check(proj) == []


def test_restore_rejects_unmanaged_file(tmp_path: Path):
    proj = _new_project(tmp_path)
    try:
        restore_file(proj, "src/demo/main.py")
    except ValueError as exc:
        assert "not a restorable" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for an unmanaged path")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/integrity/test_restore.py -q`
Expected: FAIL — `ImportError` on `framework_cli.integrity.restore`.

- [ ] **Step 3: Implement**

Create `src/framework_cli/integrity/restore.py`:

```python
from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

import yaml

from framework_cli.copier_runner import render_project
from framework_cli.integrity.hashing import sha256_file
from framework_cli.integrity.manifest import Manifest

_LOCK_REL = ".framework/integrity.lock"
_ANSWERS_REL = ".copier-answers.yml"


def _answers(project: Path) -> dict[str, str]:
    data = yaml.safe_load((project / _ANSWERS_REL).read_text())
    return {k: str(v) for k, v in data.items() if not k.startswith("_")}


def restore_file(project: Path, rel: str) -> None:
    """Re-render `rel` from the bundled template and overwrite the project's copy.

    6a restores locked (full-file) entries to the installed framework version.
    """
    lock = project / _LOCK_REL
    manifest = Manifest.loads(lock.read_text())
    entry = next((e for e in manifest.entries if e.path == rel), None)
    if entry is None or entry.tier != "tracked":
        raise ValueError(f"{rel} is not a restorable framework file")

    with tempfile.TemporaryDirectory() as tmp:
        canonical_root = Path(tmp) / "render"
        render_project(canonical_root, _answers(project))
        canonical = canonical_root / rel
        if not canonical.is_file():
            raise ValueError(f"{rel} was not produced by the canonical template")
        (project / rel).write_bytes(canonical.read_bytes())

    manifest.entries = [
        replace(e, sha256=sha256_file(project / rel), drift=False)
        if e.path == rel
        else e
        for e in manifest.entries
    ]
    lock.write_text(manifest.dumps())
```

In `src/framework_cli/cli.py`, add the import and command:

```python
from framework_cli.integrity.restore import restore_file
```

```python
@app.command()
def restore(
    file: str = typer.Argument(
        ..., help="Path (relative to the project root) of the framework file to restore."
    ),
) -> None:
    """Re-fetch a canonical framework file, discarding local edits to it."""
    try:
        restore_file(Path.cwd(), file)
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Restored {file} to the canonical framework version.")
```

Add to `tests/test_cli.py`:

```python
def test_restore_command_fixes_a_tampered_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["new", "My App"])
    project = tmp_path / "my-app"
    (project / "alembic.ini").write_text("tampered\n")
    monkeypatch.chdir(project)
    assert runner.invoke(app, ["restore", "alembic.ini"]).exit_code == 0
    assert runner.invoke(app, ["integrity", "--ci"]).exit_code == 0
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/integrity/test_restore.py tests/test_cli.py -q && uv run mypy src && uv run ruff check src tests`
Expected: PASS; mypy + ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/integrity/restore.py src/framework_cli/cli.py \
        tests/integrity/test_restore.py tests/test_cli.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): framework restore <file>"
```

---

### Task 9: Wire `task integrity` into the template Taskfile

**Files:**
- Modify: `src/framework_cli/template/Taskfile.yml.jinja`
- Modify: `src/framework_cli/template/.github/workflows/ci.yml.jinja` (comment only)
- Test: `tests/test_copier_runner.py`

The precondition is **guarded** so it never breaks a contributor who has not installed the CLI (`command -v framework`); when the CLI is present, a failed check blocks the task. CI step-0 activation (which installs the CLI) is Plan 6b.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_copier_runner.py` (it already renders a project — reuse its rendering helper/fixture; if it renders inline, mirror that):

```python
def test_taskfile_wires_integrity(tmp_path: Path):
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
    taskfile = (dest / "Taskfile.yml").read_text()
    assert "\n  integrity:\n" in taskfile
    assert "command -v framework" in taskfile
```

> If `tests/test_copier_runner.py` lacks a `render_project` import or a shared render fixture, add `from framework_cli.copier_runner import render_project` at the top.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py::test_taskfile_wires_integrity -q`
Expected: FAIL — no `integrity:` task in the rendered Taskfile.

- [ ] **Step 3: Implement**

In `src/framework_cli/template/Taskfile.yml.jinja`, add a new task (place it just before the `dev:` task, after the `tasks:` line):

```yaml
  integrity:
    desc: Verify framework scaffolding is intact (locked files unaltered). Needs the `framework` CLI.
    cmds:
      - framework integrity
```

Then add this preconditions block to the `dev`, `test`, and `ci` tasks. For `dev`, merge it into the existing `preconditions:` list (append the item). For `test` and `ci` (which currently have no `preconditions:`), add the block. The item to add everywhere:

```yaml
      - sh: 'if command -v framework >/dev/null 2>&1; then framework integrity; fi'
        msg: "Framework integrity check failed. Run `framework integrity`, then `framework restore <file>`."
```

For example, `test:` becomes:

```yaml
  test:
    desc: Run the test suite
    preconditions:
      - sh: 'if command -v framework >/dev/null 2>&1; then framework integrity; fi'
        msg: "Framework integrity check failed. Run `framework integrity`, then `framework restore <file>`."
    cmds:
      - uv run pytest -q
```

And `ci:` becomes:

```yaml
  ci:
    desc: Full local CI pre-flight before `task push` (lint, 85% gate, audit, OpenAPI export).
    preconditions:
      - sh: 'if command -v framework >/dev/null 2>&1; then framework integrity; fi'
        msg: "Framework integrity check failed. Run `framework integrity`, then `framework restore <file>`."
    cmds:
      - task: lint
      - task: test:cov:ci
      - task: audit
      - task: openapi:export
```

In `src/framework_cli/template/.github/workflows/ci.yml.jinja`, correct the step-0 comments (lines 1-3 and 15-19) so they reference Plan 6b for CI activation:

```yaml
  # Step 0: framework integrity. The check engine ships in framework v6 (Plan 6a); activating
  # it here requires installing the CLI from a versioned source, delivered in Plan 6b.
  integrity:
    runs-on: ubuntu-latest
    steps:
      - run: echo "framework integrity --ci is activated once the CLI install source ships (Plan 6b)."
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_copier_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/Taskfile.yml.jinja \
        src/framework_cli/template/.github/workflows/ci.yml.jinja \
        tests/test_copier_runner.py CLAUDE.md
```
```bash
git commit -m "feat(integrity): wire task integrity precondition into the template"
```

---

### Task 10: Acceptance — a rendered project verifies, tamper fails, restore fixes

**Files:**
- Modify: `tests/acceptance/test_rendered_project.py`

This is the end-to-end proof against a real rendered project (the manifest written by `new`, the real registry, the real checker). It does not require Docker.

- [ ] **Step 1: Write the failing test**

Add to `tests/acceptance/test_rendered_project.py` (reuse the module's existing rendered-project fixture if one exists; otherwise render into `tmp_path` as below):

```python
from framework_cli.integrity.checker import check
from framework_cli.integrity.restore import restore_file


def test_rendered_project_integrity_verifies_tamper_and_restore(tmp_path):
    from framework_cli.copier_runner import render_project
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "acc"
    render_project(
        dest,
        {
            "project_name": "Acc",
            "project_slug": "acc",
            "package_name": "acc",
            "python_version": "3.12",
        },
    )
    write_manifest(dest, installed_framework_version())

    # Fresh project verifies clean.
    assert check(dest, ci=True) == []

    # Tampering with a locked file is caught as fatal.
    locked = dest / ".pre-commit-config.yaml"
    locked.write_text(locked.read_text() + "\n# sneaky edit\n")
    findings = check(dest, ci=True)
    assert any(f.path == ".pre-commit-config.yaml" and f.fatal for f in findings)

    # Restore returns it to canonical and the project verifies clean again.
    restore_file(dest, ".pre-commit-config.yaml")
    assert check(dest, ci=True) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_project_integrity_verifies_tamper_and_restore -q`
Expected: PASS *if* Tasks 1-8 are done (this test only depends on the engine, not Task 9). Run it now to confirm the engine works end-to-end against a real render. If `new` did not write the manifest, it fails on the first `check`.

> Because `write_manifest` is also called inside `framework new`, an alternative is to invoke the CLI; the direct call above keeps the acceptance test independent of CWD handling.

- [ ] **Step 3: Run the full framework gate**

Run:
```bash
uv run pytest -q
uv run ruff check .
uv run mypy src
```
Expected: all green. Note `mypy src` excludes the template payload (see `pyproject.toml`), so the Jinja edits are not type-checked — correct.

- [ ] **Step 4: Commit**

```bash
git add tests/acceptance/test_rendered_project.py CLAUDE.md
```
```bash
git commit -m "test(integrity): end-to-end verify/tamper/restore on a rendered project"
```

---

## Self-Review

**1. Spec coverage (§17 / §20 "The Integrity Logic"):**
- File classification (locked / gitignored tiers) → Task 3. Hybrid class declared in the schema (Task 2) but its files/markers are 6a-2 (scoped out, stated).
- Manifest `.framework/integrity.lock`, generated at `framework new`, self-checksummed → Tasks 2, 4, 5.
- Two tiers (tracked+checksummed vs gitignored+existence) → Tasks 3, 4, 6; `--ci` skips the gitignored tier → Task 6/7.
- Invariant "checksummed files must be git-tracked" → Task 4 (`AuthoringError`), Task 3 test.
- Execution: Taskfile precondition → Task 9. CI step 0 → explicitly deferred to 6b (install source), comment corrected in Task 9.
- Logic lives in the installed CLI → all engine code under `src/framework_cli/integrity/`, none scaffolded into projects.
- Failure/remediation: missing→fatal, altered→fatal, drift escape hatch, `restore` → Tasks 6, 7, 8.
- §20 integrity-logic test matrix (tamper locked→fail; gitignored absent in `--ci`→pass; tampered manifest→fail) → Task 6. ("Edit outside a managed section→pass" is a hybrid case → 6a-2.)

**2. Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". Every code step shows complete code; every run step shows the command + expected result. The only deferrals are explicitly scoped (hybrid → 6a-2, CI activation + cross-version restore → 6b) and are not gaps in *this* plan's tasks.

**3. Type consistency:** `Entry(path, cls, tier, sha256, drift)` and `Manifest(framework_version, entries, version)` are used identically across Tasks 2, 4, 6, 8. `Finding(path, problem, fix, fatal)` consistent in Tasks 6 (def) and 7 (consumer). `build_manifest`/`write_manifest(project, framework_version)`, `check(project, ci)`, `record_drift(project, paths)`, `restore_file(project, rel)`, `installed_framework_version()` signatures match their call sites. CLI command function `restore` is distinct from the library `restore_file` (no shadowing).

**4. Scope:** One subsystem (integrity verify/restore), 10 tasks, each producing a tested increment. Larger-but-related concerns (hybrid sections, CI activation, upskill) are split out with reasons.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-framework-integrity.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec compliance, then code quality) between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
