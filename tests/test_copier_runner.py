from pathlib import Path

from framework_cli.copier_runner import render_project

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def test_render_creates_expected_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    assert (dest / "pyproject.toml").is_file()
    assert (dest / "Taskfile.yml").is_file()
    assert (dest / ".copier-answers.yml").is_file()
    assert (dest / "src" / "demo" / "main.py").is_file()
    assert (dest / "src" / "demo" / "routes" / "health.py").is_file()
    assert (dest / "tests" / "unit" / "test_health.py").is_file()


def test_render_substitutes_package_name(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    main_py = (dest / "src" / "demo" / "main.py").read_text()
    assert "from demo.routes import health" in main_py


def test_render_includes_coverage_config(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pytest-cov" in pyproject
    assert "[tool.coverage.run]" in pyproject

    taskfile = (dest / "Taskfile.yml").read_text()
    assert "test:cov" in taskfile


def test_render_includes_precommit_config(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    cfg = dest / ".pre-commit-config.yaml"
    assert cfg.is_file()
    text = cfg.read_text()
    assert "ruff" in text
    assert "mypy" in text
    assert "gitleaks" in text

    pyproject = (dest / "pyproject.toml").read_text()
    assert "pre-commit" in pyproject


def test_render_includes_claude_md(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    claude = dest / "CLAUDE.md"
    assert claude.is_file()
    text = claude.read_text()
    assert "<!-- FRAMEWORK:BEGIN -->" in text
    assert "<!-- FRAMEWORK:END -->" in text
    assert "Demo" in text
    assert "write the failing test first" in text.lower()
