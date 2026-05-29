from pathlib import Path

from framework_cli.review.evals import realize_fixture

_PATCH = """\
--- a/src/demo/observability/metrics.py
+++ b/src/demo/observability/metrics.py
@@ -6,6 +6,7 @@
 \"\"\"

 from __future__ import annotations
+UNINSTRUMENTED = True  # seeded defect

 import math
 import threading
"""


def test_realize_fixture_renders_patches_and_diffs(tmp_path: Path):
    root, diff = realize_fixture(tmp_path, batteries=[], patch=_PATCH)
    # The render exists and the patch was applied to the real tree.
    assert (root / "src" / "demo" / "observability" / "metrics.py").is_file()
    assert (
        "UNINSTRUMENTED = True"
        in (root / "src" / "demo" / "observability" / "metrics.py").read_text()
    )
    # The computed diff names the seeded file.
    assert "src/demo/observability/metrics.py" in diff
    assert "UNINSTRUMENTED = True" in diff
