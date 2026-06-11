from pathlib import Path

import pytest

from framework_cli.review.evals import validate_patch_hunks

_WELLFORMED = """\
--- a/src/demo/x.py
+++ b/src/demo/x.py
@@ -1,3 +1,4 @@
 import os
+import sys
 import json
 import math
"""

_MALFORMED = """\
--- a/src/demo/x.py
+++ b/src/demo/x.py
@@ -1,3 +1,3 @@
 import os
+import sys
 import json
 import math
"""  # header claims +1,3 (3 new lines) but body has 4 new-side lines (3 context + 1 add)


def test_validate_passes_a_wellformed_patch():
    assert validate_patch_hunks(_WELLFORMED) == []


def test_validate_flags_a_miscounted_hunk():
    errors = validate_patch_hunks(_MALFORMED)
    assert errors, "expected a hunk-count error"
    assert "@@ -1,3 +1,3 @@" in errors[0]


# A multi-file `git diff` (always correctly counted) must validate clean. The
# `diff --git`/`index` separators between files must NOT be miscounted as context
# lines of the preceding hunk (the +2-per-extra-file regression).
_MULTIFILE_WELLFORMED = """\
diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1,2 +1,3 @@
 import os
+import sys
 import json
diff --git a/b.py b/b.py
index 3333333..4444444 100644
--- a/b.py
+++ b/b.py
@@ -1,2 +1,3 @@
 import math
+import re
 import io
"""


def test_validate_passes_a_multifile_diff():
    assert validate_patch_hunks(_MULTIFILE_WELLFORMED) == []


_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "tests" / "eval" / "fixtures"
_PATCHES = sorted(_FIXTURES_ROOT.glob("*/*/*/change.patch"))


def test_fixture_corpus_is_present():
    # Guard against a glob that silently matches nothing (e.g. a moved fixtures root).
    assert _PATCHES, f"no change.patch files found under {_FIXTURES_ROOT}"


@pytest.mark.parametrize("patch_path", _PATCHES, ids=lambda p: str(p.relative_to(_FIXTURES_ROOT)))
def test_fixtures_are_wellformed(patch_path: Path):
    errors = validate_patch_hunks(patch_path.read_text())
    assert errors == [], f"{patch_path} has malformed hunks: {errors}"
