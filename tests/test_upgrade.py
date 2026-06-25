import subprocess
from pathlib import Path

import pytest

from framework_cli.upgrade import (
    UpgradeError,
    _duplicate_top_level_keys,
    upgrade_project,
)


def _git(repo: Path, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def _source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "isrc"
    sub = repo / "tmpl"
    pkg = sub / "src" / "{{ package_name }}"
    pkg.mkdir(parents=True)
    (repo / "copier.yml").write_text('_subdirectory: tmpl\n_exclude: ["copier.yml"]\n')
    (sub / "copier.yml").write_text(
        "_templates_suffix: .jinja\n"
        "project_name:\n  type: str\n"
        'project_slug:\n  type: str\n  default: "{{ project_name|lower }}"\n'
        'package_name:\n  type: str\n  default: "{{ project_slug }}"\n'
        'python_version:\n  type: str\n  default: "3.12"\n'
        "batteries:\n  type: yaml\n  default: []\n"
        'alert_channels:\n  type: yaml\n  default: ["webhook"]\n'
    )
    (pkg / "__init__.py.jinja").write_text("# {{ package_name }}\n")
    (sub / "framework_line.txt").write_text("framework v1\n")
    (sub / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml }}"
    )
    (sub / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'true'\n"
    )
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "s@x")
    _git(repo, "config", "user.name", "s")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "v1")
    _git(repo, "tag", "v1")
    return repo


def _project(tmp_path: Path, source: Path) -> Path:
    from copier import run_copy

    from framework_cli.source import record_identity

    proj = tmp_path / "iproj"
    run_copy(
        str(source),
        str(proj),
        data={
            "project_name": "demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref="v1",
    )
    ans = proj / ".copier-answers.yml"
    kept = [
        ln
        for ln in ans.read_text().splitlines()
        if not ln.startswith(("_src_path:", "_commit:"))
    ]
    kept += [f"_src_path: {source}", "_commit: v1"]
    ans.write_text("\n".join(kept) + "\n")
    record_identity(
        proj,
        {
            "project_name": "demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
        },
    )
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "b@x")
    _git(proj, "config", "user.name", "b")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-qm", "scaffold")
    return proj


def _bump(source: Path, tag: str, *, green: bool = True) -> None:
    (source / "tmpl" / "framework_line.txt").write_text(f"framework {tag}\n")
    if not green:
        (source / "tmpl" / "Taskfile.yml").write_text(
            "version: '3'\ntasks:\n  test:\n    cmds:\n      - 'false'\n"
        )
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", tag)
    _git(source, "tag", tag)


def test_upgrade_refuses_dirty_tree(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2")
    (proj / "dirty.txt").write_text("uncommitted\n")  # dirty working tree
    with pytest.raises(UpgradeError, match="clean"):
        upgrade_project(proj, to="v2")
    assert (proj / "framework_line.txt").read_text() == "framework v1\n"  # untouched


def test_upgrade_no_op_when_already_at_target(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    outcome = upgrade_project(proj, to="v1")
    assert outcome.status == "already-current"
    assert outcome.target == "v1"


def test_upgrade_applies_target_and_reports_green(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2")
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "green"
    assert outcome.target == "v2"
    assert (proj / "framework_line.txt").read_text() == "framework v2\n"
    assert "_commit: v2" in (proj / ".copier-answers.yml").read_text()
    assert (proj / "src" / "demo" / "__init__.py").is_file()  # identity preserved


def test_upgrade_reports_red_when_tests_fail(tmp_path: Path):
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2", green=False)
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "red"
    assert outcome.target == "v2"


def test_upgrade_applies_derived_default_for_newly_added_question(tmp_path: Path):
    """DV-1: a question added after the project was created (no persisted answer) must
    render with its derived default on upgrade, not empty.

    Reproduces Meridian's pre-FWK9 `pi_prefix` case: the project's answers predate the
    question, so on upgrade the managed block that uses it would render blank unless the
    update core supplies the derived default copier computes for a fresh render.
    """
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)  # answers have NO pi_prefix (pre-question shape)
    sub = source / "tmpl"
    cy = sub / "copier.yml"
    cy.write_text(
        cy.read_text() + "pi_prefix:\n  type: str\n"
        "  default: \"{{ (project_slug | upper | replace('-', '')"
        " | replace('_', ''))[:4] }}\"\n"
    )
    (sub / "prefix_line.txt.jinja").write_text("prefix={{ pi_prefix }}\n")
    _bump(source, "v2")
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "green"
    # project_slug "demo" → derived prefix "DEMO"; must NOT be empty ("prefix=").
    assert (proj / "prefix_line.txt").read_text() == "prefix=DEMO\n"


def test_duplicate_top_level_keys_detects_only_repeated_top_level_keys():
    """DV-4 detector: flag repeated top-level keys; ignore nested/once-only/comment lines."""
    text = (
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: x\n"
        "default_install_hook_types: [pre-commit]\n"
        "# default_install_hook_types: commented\n"
        "default_install_hook_types: [pre-commit, commit-msg]\n"
    )
    assert _duplicate_top_level_keys(text) == ["default_install_hook_types"]
    # No duplicates → empty.
    assert _duplicate_top_level_keys("repos: []\nci:\n  skip: []\n") == []


def test_upgrade_warns_on_duplicate_precommit_key(tmp_path: Path):
    """DV-4: an upgrade that yields a duplicate top-level key in .pre-commit-config.yaml
    surfaces a non-fatal warning (the project still upgrades green)."""
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    # v2 ships a .pre-commit-config.yaml with a duplicate top-level key (the post-merge shape
    # a hand-added key + the managed region produce).
    (source / "tmpl" / ".pre-commit-config.yaml.jinja").write_text(
        "default_install_hook_types: [pre-commit]\n"
        "repos: []\n"
        "default_install_hook_types: [pre-commit, commit-msg]\n"
    )
    _bump(source, "v2")
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "green"
    assert any("duplicate top-level key" in w for w in outcome.warnings)
    assert any("default_install_hook_types" in w for w in outcome.warnings)


def test_upgrade_no_precommit_warning_when_clean(tmp_path: Path):
    """DV-4: a clean .pre-commit-config.yaml yields no warning."""
    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    (source / "tmpl" / ".pre-commit-config.yaml.jinja").write_text(
        "default_install_hook_types: [pre-commit]\nrepos: []\n"
    )
    _bump(source, "v2")
    outcome = upgrade_project(proj, to="v2")
    assert outcome.status == "green"
    assert outcome.warnings == []


def test_upgrade_requires_git_tracked(tmp_path: Path):
    from copier import run_copy

    source = _source_repo(tmp_path)
    proj = tmp_path / "bare"
    run_copy(
        str(source),
        str(proj),
        data={"project_name": "demo"},
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref="v1",
    )
    with pytest.raises(UpgradeError, match="git"):
        upgrade_project(proj, to="v1")


def test_upgrade_defaults_to_latest_release(tmp_path: Path, monkeypatch):
    import framework_cli.upgrade as up

    source = _source_repo(tmp_path)
    proj = _project(tmp_path, source)
    _bump(source, "v2")
    monkeypatch.setattr(up, "latest_release", lambda: "v2")
    outcome = upgrade_project(proj)  # no `to=` → default latest
    assert outcome.status == "green"
    assert outcome.target == "v2"
    assert "_commit: v2" in (proj / ".copier-answers.yml").read_text()


def test_upgrade_bumps_cli_then_reexecs_when_target_newer(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    import framework_cli.self_bump as sb
    import framework_cli.version_sync as vs
    from framework_cli.cli import app

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")
    monkeypatch.setattr(cli, "latest_release", lambda: "v0.2.11")
    monkeypatch.setattr(sb, "is_uv_tool_install", lambda: True)
    monkeypatch.setattr(sb, "_interactive", lambda: True)
    monkeypatch.setattr(sb, "_confirm", lambda msg: True)

    installed, reexeced = [], []
    monkeypatch.setattr(sb, "run_uv_tool_install", lambda tag: installed.append(tag))
    monkeypatch.setattr(sb, "reexec", lambda argv: reexeced.append(argv))
    # upgrade_project must NOT run in this process (the re-exec'd one does it)
    monkeypatch.setattr(
        cli, "upgrade_project", lambda *a, **k: (_ for _ in ()).throw(AssertionError())
    )

    CliRunner().invoke(app, ["upgrade", str(project)])
    assert installed == ["v0.2.11"]
    assert reexeced and reexeced[0][1:3] == ["upgrade", str(project)]


def test_upgrade_refuses_when_non_uv_tool(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    import framework_cli.self_bump as sb
    import framework_cli.version_sync as vs
    from framework_cli.cli import app

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")
    monkeypatch.setattr(cli, "latest_release", lambda: "v0.2.11")
    monkeypatch.setattr(sb, "is_uv_tool_install", lambda: False)

    result = CliRunner().invoke(app, ["upgrade", str(project)])
    assert result.exit_code == 1
    assert "uv tool install" in result.output and "@v0.2.11" in result.output


def test_upgrade_proceeds_when_target_not_newer(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    import framework_cli.version_sync as vs
    from framework_cli.cli import app
    from framework_cli.upgrade import UpgradeOutcome

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    monkeypatch.setattr(cli, "latest_release", lambda: "v0.2.11")
    called = []
    monkeypatch.setattr(
        cli,
        "upgrade_project",
        lambda p, to: (
            called.append(to) or UpgradeOutcome(status="already-current", target=to)
        ),
    )

    result = CliRunner().invoke(app, ["upgrade", str(project)])
    assert result.exit_code == 0
    assert called == ["v0.2.11"]  # resolved target passed through; no bump attempted


def test_upgrade_errors_when_no_release_found(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    import framework_cli.cli as cli
    from framework_cli.cli import app

    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(cli, "latest_release", lambda: None)
    result = CliRunner().invoke(app, ["upgrade", str(project)])
    assert result.exit_code == 1
    assert "no framework release" in result.output
