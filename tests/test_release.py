from pathlib import Path

import pytest

from framework_cli.release import assert_tag_matches, read_project_version

_PYPROJECT = """\
[project]
name = "framework-cli"
version = "1.4.0"
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(_PYPROJECT)
    return p


def test_read_project_version(tmp_path):
    assert read_project_version(_write(tmp_path)) == "1.4.0"


def test_tag_matches_version(tmp_path):
    assert_tag_matches("v1.4.0", _write(tmp_path))  # no raise


def test_tag_mismatch_raises(tmp_path):
    with pytest.raises(ValueError, match="does not match"):
        assert_tag_matches("v1.4.1", _write(tmp_path))


def test_real_pyproject_version_is_readable():
    root = Path(__file__).parent.parent / "pyproject.toml"
    assert read_project_version(root)
