from pathlib import Path

from framework_cli.review.context import generated_project_target


def test_generated_project_target_uses_root_and_active(tmp_path: Path):
    t = generated_project_target(tmp_path, ("security", "performance"))
    assert t.root == tmp_path
    assert t.active == ("security", "performance")
