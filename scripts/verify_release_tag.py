"""Release-time invariant guard: assert the pushed tag == pyproject version."""

import sys
from pathlib import Path

from framework_cli.release import assert_tag_matches

if __name__ == "__main__":
    tag = sys.argv[1]
    assert_tag_matches(tag, Path("pyproject.toml"))
    print(f"release tag {tag} matches the project version — OK")
