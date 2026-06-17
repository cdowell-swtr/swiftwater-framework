import pytest

import framework_cli.version_sync as vs
from framework_cli.integrity import restore as restore_mod
from framework_cli.version_sync import VersionSkewError


def test_restore_refuses_on_skew(monkeypatch, tmp_path):
    # A project pinned ahead of the installed CLI: restore must refuse, not render.
    (tmp_path / ".copier-answers.yml").write_text("_commit: v0.2.11\n")
    (tmp_path / ".framework").mkdir()
    (tmp_path / ".framework" / "integrity.lock").write_text("{}")  # never reached
    monkeypatch.setattr(vs, "installed_framework_version", lambda: "0.2.8")

    rendered = []
    monkeypatch.setattr(
        restore_mod, "render_project", lambda *a, **k: rendered.append(1)
    )
    with pytest.raises(VersionSkewError, match="uv tool install.*@v0.2.11"):
        restore_mod.restore_file(tmp_path, "infra/docker/Dockerfile")
    assert rendered == []  # guard fired before any render
