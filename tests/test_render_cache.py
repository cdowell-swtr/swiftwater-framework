"""Tests for the per-worker render cache (FWK94).

`tests._render_cache.render_project` is a drop-in for
`framework_cli.copier_runner.render_project` that renders each distinct answer-set
once per process and hands every caller its own copytree'd tree. These tests pin the
drop-in contract: byte-identical output, mutation isolation between callers, and an
actual cache hit (the underlying copier render runs once for repeated answer-sets).
"""

from pathlib import Path

from framework_cli.copier_runner import render_project as real_render_project
from tests import _render_cache

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_cached_render_is_byte_identical_to_real_render(tmp_path: Path):
    cached = tmp_path / "cached"
    real = tmp_path / "real"
    _render_cache.render_project(cached, DATA)
    real_render_project(real, DATA)
    assert _tree(cached) == _tree(real)


def test_two_callers_get_isolated_trees(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    _render_cache.render_project(a, DATA)
    _render_cache.render_project(b, DATA)
    # Mutating one caller's tree must not affect the other (no shared-base aliasing).
    (a / "pyproject.toml").write_text("CLOBBERED")
    assert (b / "pyproject.toml").read_text() != "CLOBBERED"


def test_repeated_answer_set_renders_copier_once(tmp_path: Path, monkeypatch):
    calls: list[dict] = []
    real = _render_cache._render_project

    def counting_render(dest, data):
        calls.append(dict(data))
        real(dest, data)

    # Fresh cache so the count is deterministic regardless of prior tests in-process.
    monkeypatch.setattr(_render_cache, "_render_project", counting_render)
    monkeypatch.setattr(_render_cache, "_cache", {})
    monkeypatch.setattr(_render_cache, "_cache_root", None)

    _render_cache.render_project(tmp_path / "x", DATA)
    _render_cache.render_project(tmp_path / "y", {**DATA})  # same answer-set, new dict
    _render_cache.render_project(tmp_path / "z", {**DATA, "batteries": ["workers"]})

    # DATA and {**DATA} collapse to one render; the workers combo is a second.
    assert len(calls) == 2


def test_dest_absolute_path_is_not_embedded(tmp_path: Path):
    # The cache renders into its own dir then copytrees into dest; if any rendered file
    # embedded its own absolute path, a cache hit would leak the cache dir into dest.
    dest = tmp_path / "demo"
    _render_cache.render_project(dest, DATA)
    base = _render_cache._base_for(DATA)
    needle = str(base).encode()
    for body in _tree(dest).values():
        assert needle not in body
