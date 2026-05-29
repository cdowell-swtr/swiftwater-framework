from pathlib import Path

from framework_cli.review.agentic import _run_tool


def _tree(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("import os\nSECRET = 'x'\n")
    (root / "pkg" / "b.py").write_text("from pkg.a import SECRET\n")
    (root / "README.md").write_text("# Demo\n")


def test_read_file_returns_contents(tmp_path):
    _tree(tmp_path)
    out = _run_tool("read_file", {"path": "pkg/a.py"}, tmp_path)
    assert "SECRET = 'x'" in out


def test_read_file_rejects_escape(tmp_path):
    _tree(tmp_path)
    assert "error" in _run_tool("read_file", {"path": "../secrets"}, tmp_path).lower()
    assert "error" in _run_tool("read_file", {"path": "/etc/passwd"}, tmp_path).lower()


def test_read_file_truncates_large_file(tmp_path):
    _tree(tmp_path)
    (tmp_path / "big.py").write_text("x = 1\n" * 20000)  # > 50k chars
    out = _run_tool("read_file", {"path": "big.py"}, tmp_path)
    assert "[truncated]" in out
    assert len(out) < 60_000


def test_grep_finds_matches_with_location(tmp_path):
    _tree(tmp_path)
    out = _run_tool("grep", {"pattern": "SECRET"}, tmp_path)
    assert "pkg/a.py:2:" in out
    assert "pkg/b.py:1:" in out


def test_grep_bad_regex_returns_error(tmp_path):
    _tree(tmp_path)
    assert "error" in _run_tool("grep", {"pattern": "["}, tmp_path).lower()


def test_glob_lists_paths(tmp_path):
    _tree(tmp_path)
    out = _run_tool("glob", {"pattern": "pkg/*.py"}, tmp_path)
    assert "pkg/a.py" in out
    assert "pkg/b.py" in out
    assert "README.md" not in out


def test_unknown_tool_and_missing_arg_return_error(tmp_path):
    assert "error" in _run_tool("nope", {}, tmp_path).lower()
    assert "error" in _run_tool("read_file", {}, tmp_path).lower()  # missing 'path'


def test_tools_work_on_a_real_rendered_project(tmp_path):
    from framework_cli.copier_runner import render_project

    root = tmp_path / "demo"
    render_project(
        root,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
            "batteries": [],
        },
    )
    # Plant a .git dir like realize_fixture / a checked-out repo would have, so the
    # skip behavior is exercised against a real tree.
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n")

    listing = _run_tool("glob", {"pattern": "src/demo/routes/*.py"}, root)
    assert "src/demo/routes/items.py" in listing
    contents = _run_tool("read_file", {"path": "src/demo/routes/items.py"}, root)
    assert "router" in contents.lower()
    matches = _run_tool(
        "grep", {"pattern": "APIRouter", "path_glob": "src/demo/**/*.py"}, root
    )
    assert "items.py" in matches
    # The .git directory and its contents are skipped — assert on path COMPONENTS, not a
    # substring (a sibling like .gitignore contains ".git" but must NOT be skipped).
    all_paths = _run_tool("glob", {"pattern": "**/*"}, root).splitlines()
    assert not any(p == ".git" or p.startswith(".git/") for p in all_paths)
    # And grep does not surface the planted .git/config contents.
    assert ".git/config" not in _run_tool("grep", {"pattern": "core"}, root)
