"""FWK119 — project-local custom reviewers (the consumer half of FWK48)."""

from __future__ import annotations

from pathlib import Path

import pytest

from framework_cli.review import registry
from framework_cli.review.project_reviewers import (
    discover_project_reviewers,
    register_project_reviewers,
)


@pytest.fixture
def restore_specs():
    """Snapshot/restore the registry global so a register_* test can't leak a
    project reviewer into another test's roster."""
    orig = dict(registry._SPECS)
    yield
    registry._SPECS.clear()
    registry._SPECS.update(orig)


def _write_reviewer(
    root: Path, name: str, *, toml: str | None, prompt: str = "Flag X."
) -> None:
    rdir = root / ".framework" / "reviewers"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / f"{name}.md").write_text(prompt)
    if toml is not None:
        (rdir / f"{name}.toml").write_text(toml)


def test_discover_parses_md_and_toml(tmp_path: Path):
    _write_reviewer(
        tmp_path,
        "house-style",
        prompt="Flag house-style violations.",
        toml='block_threshold = "high"\nactive_when = "always"\n',
    )
    specs = discover_project_reviewers(tmp_path)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "house-style"
    assert spec.prompt == "Flag house-style violations."
    assert spec.block_threshold == "high"
    assert spec.active_when == "always"
    assert spec.framework_only is False


def test_discover_absent_dir_is_noop(tmp_path: Path):
    # rookie-free: a project that adds no reviewers behaves exactly as today
    assert discover_project_reviewers(tmp_path) == []


def test_discover_defaults_to_advisory_without_toml(tmp_path: Path):
    _write_reviewer(tmp_path, "naming", toml=None)
    (spec,) = discover_project_reviewers(tmp_path)
    assert spec.block_threshold is None  # advisory
    assert spec.active_when == "always"
    assert spec.context.strategy == "diff"


def test_discover_rejects_invalid_block_threshold(tmp_path: Path):
    _write_reviewer(tmp_path, "bad", toml='block_threshold = "extreme"\n')
    with pytest.raises(ValueError, match="block_threshold"):
        discover_project_reviewers(tmp_path)


def test_register_merges_into_active_agents_and_get_agent(
    tmp_path: Path, restore_specs
):
    _write_reviewer(tmp_path, "house-style", toml='active_when = "always"\n')
    names = register_project_reviewers(tmp_path)
    assert names == ["house-style"]
    # framework audit --target project resolves it via active_agents() + get_agent()
    assert "house-style" in registry.active_agents("pull_request", [])
    assert registry.get_agent("house-style").prompt == "Flag X."


def test_register_collision_with_builtin_is_loud(tmp_path: Path, restore_specs):
    _write_reviewer(tmp_path, "security", toml='block_threshold = "high"\n')
    with pytest.raises(ValueError, match="security"):
        register_project_reviewers(tmp_path)


def test_register_is_idempotent_for_identical_specs(tmp_path: Path, restore_specs):
    _write_reviewer(tmp_path, "house-style", toml='active_when = "always"\n')
    register_project_reviewers(tmp_path)
    # a second call (same process / re-run) must not raise on the self-overlap
    assert register_project_reviewers(tmp_path) == ["house-style"]


def test_build_audit_items_registers_project_reviewers(
    tmp_path: Path, monkeypatch, restore_specs
):
    """`framework audit --target project` resolves a project-local reviewer end-to-end
    (the framework-audit half): _build_audit_items registers it, so it appears in the
    built EngineItem set."""
    import framework_cli.cli as cli
    import framework_cli.review.diff as diffmod

    _write_reviewer(tmp_path, "house-style", toml='active_when = "always"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli, "_resolve_audit_base", lambda *a, **k: ("snapshot", None, None)
    )
    monkeypatch.setattr(diffmod, "snapshot_seed", lambda *a, **k: "fake diff")

    items = cli._build_audit_items("project", ["house-style"], True, None)
    assert any(getattr(it, "agent", None) == "house-style" for it in items)
