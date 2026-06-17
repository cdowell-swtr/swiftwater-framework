import pytest

from framework_cli import version_sync as vs
from framework_cli.version_sync import VersionSkew, VersionSkewError, parse_version


def _project(tmp_path, commit: str | None):
    answers = tmp_path / ".copier-answers.yml"
    body = "project_slug: demo\n"
    if commit is not None:
        body += f"_commit: {commit}\n"
    answers.write_text(body)
    return tmp_path


@pytest.mark.parametrize(
    "installed,commit,expected",
    [
        ("0.2.11", "v0.2.11", VersionSkew.IN_SYNC),
        ("0.2.8", "v0.2.11", VersionSkew.CLI_BEHIND),
        ("0.2.11", "v0.2.8", VersionSkew.CLI_AHEAD),
    ],
)
def test_project_version_skew(monkeypatch, tmp_path, installed, commit, expected):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: installed)
    skew, installed_tag, commit_tag = vs.project_version_skew(
        _project(tmp_path, commit)
    )
    assert skew is expected
    assert installed_tag == f"v{installed}"
    assert commit_tag == commit


def test_missing_commit_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    with pytest.raises(VersionSkewError, match="_commit"):
        vs.project_version_skew(_project(tmp_path, None))


def test_require_version_sync_passes_in_sync(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    vs.require_version_sync(_project(tmp_path, "v0.2.11"))  # no raise


def test_require_version_sync_behind_names_remedy(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")
    with pytest.raises(VersionSkewError, match="uv tool install.*@v0.2.11"):
        vs.require_version_sync(_project(tmp_path, "v0.2.11"))


def test_require_version_sync_ahead_suggests_upgrade(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    with pytest.raises(VersionSkewError, match="framework upgrade"):
        vs.require_version_sync(_project(tmp_path, "v0.2.8"))


def test_parse_version():
    assert parse_version("v0.2.11") == (0, 2, 11)
    assert parse_version("0.2.11") == (0, 2, 11)
    with pytest.raises(ValueError):
        parse_version("v0+unknown")


def test_non_tag_commit_raises_skew_error_not_valueerror(monkeypatch, tmp_path):
    # A copier-native project can record a non-tag _commit (a SHA); it must surface as a
    # VersionSkewError, never a raw ValueError, so `integrity` handles it without a traceback.
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.11")
    with pytest.raises(VersionSkewError, match="not a vX.Y.Z release tag"):
        vs.project_version_skew(_project(tmp_path, "abc1234"))
