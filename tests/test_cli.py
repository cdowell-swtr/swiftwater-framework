from pathlib import Path

from typer.testing import CliRunner

from framework_cli.cli import app
from framework_cli.integrity.manifest import Manifest

runner = CliRunner()


def test_new_creates_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["new", "My App"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "my-app" / "pyproject.toml").is_file()
    assert (tmp_path / "my-app" / "src" / "my_app" / "main.py").is_file()
    assert (tmp_path / "my-app" / ".copier-answers.yml").is_file()


def test_new_rejects_existing_directory(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "my-app").mkdir()
    result = runner.invoke(app, ["new", "My App"])
    assert result.exit_code == 1
    assert "already exists" in result.output


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
