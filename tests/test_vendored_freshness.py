"""FWK40: local auth-gated freshness check for the vendored docs-layout validator.

FWK9 vendored cdowell-swtr/patterns' `hooks/docs-layout-check.sh` into the template at
`scripts/docs_layout_check.sh`, pinned by a provenance comment to `docs-layout/v1`. Nothing
detects when upstream ships a newer tag, or when the vendored copy drifts from the pin.

This module adds that detection as a LOCAL, auth-gated check:
- Pure helpers (`parse_pinned_tag`, `latest_version`, `strip_provenance`) hold the logic and are
  unit-tested deterministically (run everywhere, incl. CI).
- Two live integration tests wire those helpers to `gh` against the private patterns repo. A
  reachability probe (evaluated once at import) skips them wherever patterns is unreachable
  (CI, no `gh` auth, offline) — so they never block a PR or merge and need no secret.
"""

import base64
import re
import subprocess
from collections.abc import Iterable

import pytest

from framework_cli.copier_runner import template_path

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


# --- unit tests (deterministic; run everywhere) -------------------------------------------


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


# --- live integration tests (auth-gated; skip where patterns is unreachable) --------------

_PATTERNS = "cdowell-swtr/patterns"
_VENDORED = template_path() / "scripts" / "docs_layout_check.sh"
_UPSTREAM_PATH = "hooks/docs-layout-check.sh"


def _gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _patterns_reachable() -> bool:
    try:
        return _gh("api", f"repos/{_PATTERNS}").returncode == 0
    except OSError:  # gh not installed / not spawnable
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
