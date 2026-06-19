# FWK40 — docs-layout validator re-vendor freshness check — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local, auth-gated pytest check that fails when `cdowell-swtr/patterns` ships a `docs-layout/v*` tag newer than the one the template's vendored `scripts/docs_layout_check.sh` is pinned to, and that the vendored copy still matches upstream at the pin — skipping cleanly wherever patterns is unreachable (CI, no `gh` auth, offline).

**Architecture:** One self-contained test module `tests/test_vendored_freshness.py`. Pure helpers (`parse_pinned_tag`, `latest_version`, `strip_provenance`) hold all logic and are unit-tested deterministically (run in CI). Two live integration tests wire those helpers to `gh` against the private patterns repo; a module-level reachability probe (`gh api repos/cdowell-swtr/patterns`, evaluated once at import) drives a `skipif` so the live tests are inert without patterns auth. No secrets, no new workflow, no template/operational-surface changes (so no integrity/FWK29 edits).

**Tech Stack:** pytest, `subprocess` + `gh` CLI (auth-gated), `re`, `base64`. The vendored file is located via `framework_cli.copier_runner.template_path()`.

**Spec:** `docs/superpowers/specs/2026-06-18-fwk40-vendored-freshness-design.md`

**Fixed facts (verified):**
- Vendored file: `src/framework_cli/template/scripts/docs_layout_check.sh`; line 2 is exactly
  `# vendored from cdowell-swtr/patterns hooks/docs-layout-check.sh @ docs-layout/v1 (2026-06-18); re-vendor on a later docs-layout/v tag.`
  (Note: that line contains `docs-layout/v1` AND a no-digit `docs-layout/v tag` — the parse regex must require a digit so it matches `v1`, not the trailing `v tag`.)
- Upstream tag list: `gh api repos/cdowell-swtr/patterns/tags --jq '.[].name'` includes `docs-layout/v1`.
- Upstream script at the pin: `gh api repos/cdowell-swtr/patterns/contents/hooks/docs-layout-check.sh?ref=docs-layout/v1 --jq .content` → base64.
- The vendored copy = upstream content with the single provenance line inserted as line 2; so `strip_provenance(vendored)` must reproduce upstream byte-for-byte.
- mypy gate is `mypy src` (framework source only) — it does NOT cover `tests/`, so no typing burden here; but `ruff check .` and `ruff format --check .` DO cover the test file.

---

## File map

| Path | Action | Responsibility |
|---|---|---|
| `tests/test_vendored_freshness.py` | **create** | Pure helpers + their unit tests (Task 1); the auth-gated live integration tests + reachability probe (Task 2). |

No other files change. No integrity-class or FWK29-registry edits (test-only; no rendered/operational surface added).

---

## Task 1: Pure helpers + deterministic unit tests

**Files:**
- Create: `tests/test_vendored_freshness.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_vendored_freshness.py` with the tests FIRST (helpers not yet defined → fails at import/collection):

```python
"""FWK40: local auth-gated freshness check for the vendored docs-layout validator.

Pure helpers (unit-tested below, run everywhere) + live integration tests (auth-gated,
skip where cdowell-swtr/patterns is unreachable).
"""

import pytest

from tests.test_vendored_freshness import (  # self-import resolved once helpers exist
    latest_version,
    parse_pinned_tag,
    strip_provenance,
)


def test_parse_pinned_tag_reads_the_version_int():
    line = (
        "# vendored from cdowell-swtr/patterns hooks/docs-layout-check.sh @ "
        "docs-layout/v1 (2026-06-18); re-vendor on a later docs-layout/v tag."
    )
    assert parse_pinned_tag(line) == 1


def test_parse_pinned_tag_multi_digit():
    assert parse_pinned_tag("pinned @ docs-layout/v12 here") == 12


def test_parse_pinned_tag_ignores_no_digit_occurrence():
    # The real provenance line ends with "docs-layout/v tag" (no digit) — must not match that.
    assert parse_pinned_tag("docs-layout/v tag ... docs-layout/v3 ...") == 3


def test_parse_pinned_tag_raises_when_absent():
    with pytest.raises(ValueError):
        parse_pinned_tag("no pin here")


def test_latest_version_picks_max_docs_layout_tag():
    tags = ["git/v1", "docs-layout/v1", "memory/v1", "docs-layout/v2"]
    assert latest_version(tags) == 2


def test_latest_version_is_numeric_not_lexical():
    assert latest_version(["docs-layout/v2", "docs-layout/v10", "docs-layout/v1"]) == 10


def test_latest_version_none_when_no_docs_layout_tags():
    assert latest_version(["git/v1", "memory/v1"]) is None


def test_strip_provenance_removes_only_the_vendor_line():
    vendored = (
        "#!/usr/bin/env bash\n"
        "# vendored from cdowell-swtr/patterns hooks/docs-layout-check.sh @ docs-layout/v1 (x).\n"
        "# docs-layout validator (DOCS-convention).\n"
        "set -uo pipefail\n"
    )
    upstream = (
        "#!/usr/bin/env bash\n"
        "# docs-layout validator (DOCS-convention).\n"
        "set -uo pipefail\n"
    )
    assert strip_provenance(vendored) == upstream
```

> Note on the self-import: the cleanest pattern is to define the helpers at the top of this SAME module and have the tests reference them directly (no import). If you prefer, drop the `from tests.test_vendored_freshness import ...` block and just call the module-level functions. Use whichever keeps the file clean — the functions and tests live in one file.

- [ ] **Step 2: Run to verify they FAIL**

Run: `uv run pytest tests/test_vendored_freshness.py -k "parse_pinned or latest_version or strip_provenance" -v`
Expected: FAIL (helpers undefined / ImportError).

- [ ] **Step 3: Implement the pure helpers** (at the top of the module, above the tests; remove the self-import block):

```python
import re
from collections.abc import Iterable

_PIN_RE = re.compile(r"docs-layout/v(\d+)")
_TAG_RE = re.compile(r"^docs-layout/v(\d+)$")
_PROVENANCE_MARKER = "vendored from cdowell-swtr/patterns"


def parse_pinned_tag(provenance_text: str) -> int:
    """Return N from the first `docs-layout/vN` reference in the provenance text."""
    m = _PIN_RE.search(provenance_text)
    if m is None:
        raise ValueError(f"no docs-layout/vN pin found in: {provenance_text!r}")
    return int(m.group(1))


def latest_version(tag_names: Iterable[str]) -> int | None:
    """Max N among `docs-layout/vN` tag names, or None if there are none."""
    versions = [int(m.group(1)) for t in tag_names if (m := _TAG_RE.match(t))]
    return max(versions) if versions else None


def strip_provenance(vendored_text: str) -> str:
    """Return the vendored script with the single inserted provenance line removed."""
    lines = vendored_text.splitlines(keepends=True)
    kept = [ln for ln in lines if _PROVENANCE_MARKER not in ln]
    return "".join(kept)
```

- [ ] **Step 4: Run to verify they PASS**

Run: `uv run pytest tests/test_vendored_freshness.py -k "parse_pinned or latest_version or strip_provenance" -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Format/lint, then stage (do NOT commit — controller finalizes)**

Run: `uv run ruff format --check . && uv run ruff check .`
Then: `git add tests/test_vendored_freshness.py`

---

## Task 2: Live auth-gated integration tests

**Files:**
- Modify: `tests/test_vendored_freshness.py` (append the probe + two live tests)

- [ ] **Step 1: Write the failing live tests** (append to the module):

```python
import base64
import subprocess

from framework_cli.copier_runner import template_path

_PATTERNS = "cdowell-swtr/patterns"
_VENDORED = template_path() / "scripts" / "docs_layout_check.sh"
_UPSTREAM_PATH = "hooks/docs-layout-check.sh"


def _gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _patterns_reachable() -> bool:
    try:
        return _gh("api", f"repos/{_PATTERNS}").returncode == 0
    except FileNotFoundError:  # gh not installed
        return False


# Probe once at import so the live tests skip cleanly without an extra gh call each.
_REACHABLE = _patterns_reachable()
requires_patterns = pytest.mark.skipif(
    not _REACHABLE,
    reason=f"{_PATTERNS} not reachable (no gh auth / offline / CI) — freshness check is local-only",
)


@requires_patterns
def test_docs_layout_validator_pin_is_latest():
    pinned = parse_pinned_tag(_VENDORED.read_text())
    res = _gh("api", "--paginate", f"repos/{_PATTERNS}/tags", "--jq", ".[].name")
    assert res.returncode == 0, res.stderr
    latest = latest_version(res.stdout.splitlines())
    if latest is None:
        pytest.skip("no docs-layout/v* tags upstream — cannot determine staleness")
    assert latest <= pinned, (
        f"docs-layout/v{latest} shipped upstream but the template is vendored at "
        f"docs-layout/v{pinned}. Re-vendor src/framework_cli/template/scripts/docs_layout_check.sh "
        f"from cdowell-swtr/patterns hooks/docs-layout-check.sh @ docs-layout/v{latest} "
        f"(keep the provenance line; bump it to v{latest})."
    )


@requires_patterns
def test_docs_layout_validator_matches_upstream_at_pin():
    pinned = parse_pinned_tag(_VENDORED.read_text())
    res = _gh(
        "api",
        f"repos/{_PATTERNS}/contents/{_UPSTREAM_PATH}?ref=docs-layout/v{pinned}",
        "--jq",
        ".content",
    )
    assert res.returncode == 0, res.stderr
    upstream = base64.b64decode(res.stdout).decode()
    assert strip_provenance(_VENDORED.read_text()) == upstream, (
        "the vendored docs_layout_check.sh has diverged from cdowell-swtr/patterns "
        f"hooks/docs-layout-check.sh @ docs-layout/v{pinned} (modulo the provenance line). "
        "Re-vendor it verbatim or fix the drift."
    )
```

- [ ] **Step 2: Run the live tests**

Run: `uv run pytest tests/test_vendored_freshness.py -k "pin_is_latest or matches_upstream" -v`
Expected on a patterns-authed machine: **2 passed** (pin is `v1`, latest is `v1`; vendored matches upstream). On a machine without patterns auth: **2 skipped**. Report which you saw.

- [ ] **Step 3: Prove non-vacuity (only where patterns is reachable)**

This is the whole point — demonstrate both live tests actually bite:
1. Temporarily edit the provenance line's pin `v1` → `v0` in `src/framework_cli/template/scripts/docs_layout_check.sh`; run `-k pin_is_latest` → it must **FAIL** (latest v1 > pinned v0). Restore the file exactly.
2. Temporarily append a stray line (e.g. `# drift`) to the vendored script body; run `-k matches_upstream` → it must **FAIL**. Restore the file exactly.
Confirm `git status` shows `docs_layout_check.sh` UNMODIFIED after both probes. Report both FAIL observations. (If patterns is NOT reachable in your environment, you cannot run this — report that the tests skipped and that the non-vacuity probe must be done on a patterns-authed machine.)

- [ ] **Step 4: Full local gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pytest tests/test_vendored_freshness.py -v`
Expected: ruff clean; the 8 unit tests pass; the 2 live tests pass-or-skip (per environment).

- [ ] **Step 5: Stage**

Confirm `git status` shows ONLY `tests/test_vendored_freshness.py` changed (the validator restored). Then: `git add tests/test_vendored_freshness.py`

---

## Task 3: Full gate + branch-end review + finalize

- [ ] **Step 1: Run the framework gate**

Run:
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest tests/test_vendored_freshness.py -v
```
Expected: all green (the broader suite is unaffected — this adds one test file).

- [ ] **Step 2: Branch-end review (Opus)**

Controller dispatches a whole-branch review focused on: helper correctness (regex edge cases, numeric-vs-lexical version compare, provenance-strip fidelity), the skip/auth-gating (truly inert in CI — no network failure leaks as a test error), failure-message actionability, and confirming non-vacuity was demonstrated. Address findings.

- [ ] **Step 3: Finalize**

Controller: move FWK40 → PLAN `Done`, append the completion `ACTION_LOG` entry, finalize commits, then open a PR (master protected) per finishing-a-development-branch.

---

## Execution

**Review-model policy (repo standing rule — restate; don't let the generic "least-powerful model" guidance collapse it):** implementer → **Sonnet**; spec/mechanistic review → **Sonnet**; code-quality review → **Opus**; branch-end review → **Opus**. Pass `model` explicitly per role.

**Commit cadence (framework slice):** implementers stage + pass the commit-gate but do **not** run `git commit` (subagent commits are blocked); the controller verifies and finalizes each task's commit with its `ACTION_LOG` entry. The reviewers-gate degrades skip-neutral (no AI backend), so it won't block. Keep the word "commit" out of Bash command *descriptions* and out of any inline `gh`/heredoc text (the PreToolUse gate matches the `git`+`commit` substring in the command AND the description); stage in one call, commit in a separate call.

**No release / no template payload change:** FWK40 adds a maintainer-side test only (no rendered output changes), so no integrity/FWK29 edits and nothing ships to consumers. After merge, move FWK40 → `Done` and log it.

**Self-review (controller, against the spec):** Goals — staleness FAIL (Task 2 `pin_is_latest`) ✓, fidelity (Task 2 `matches_upstream`) ✓, zero-secret/skip-in-CI (the `requires_patterns` gate) ✓. Helpers + unit tests (Task 1) ✓. Error handling — `gh` absent/unreachable → skip (probe returns False) ✓; missing provenance → `parse_pinned_tag` raises ✓; no upstream tags → `pytest.skip` ✓. No placeholders; helper names consistent across Task 1 (definitions) and Task 2 (uses).
