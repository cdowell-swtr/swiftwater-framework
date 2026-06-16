"""FWK29 — the closed-world coverage-completeness ratchet."""

import re
from pathlib import Path

import pytest

from framework_cli.batteries import battery_names, resolve
from framework_cli.copier_runner import render_project

from .enumerate import enumerate_surfaces
from .registry import REGISTRY, Status, registry_keys

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}
_TESTS_ROOT = Path(__file__).resolve().parents[1]
_TEST_FN = re.compile(r"^def (test_\w+)", re.MULTILINE)
_FWK_REF = re.compile(r"^FWK\d+\b")


@pytest.fixture(scope="module")
def maximal(tmp_path_factory):
    dest = tmp_path_factory.mktemp("cov-complete") / "demo"
    render_project(dest, {**_BASE, "batteries": resolve(battery_names())})
    return dest


def _all_test_function_names() -> set[str]:
    names: set[str] = set()
    for p in _TESTS_ROOT.rglob("test_*.py"):
        names |= set(_TEST_FN.findall(p.read_text()))
    return names


def test_every_surface_is_classified(maximal):
    enumerated = enumerate_surfaces(maximal)
    unclassified = enumerated - registry_keys()
    assert not unclassified, (
        "Unclassified operational surface(s) — classify each in registry.py as "
        "EXERCISED / EXEMPT / KNOWN_GAP:\n"
        + "\n".join(f"  - {k}" for k in sorted(unclassified))
    )


def test_no_stale_registry_entries(maximal):
    stale = registry_keys() - enumerate_surfaces(maximal)
    assert not stale, (
        "Stale registry entries (surface no longer rendered):\n"
        + "\n".join(f"  - {k}" for k in sorted(stale))
    )


def test_registry_keys_are_unique():
    keys = [e.key for e in REGISTRY]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, f"duplicate registry keys: {dupes}"


def test_exercised_entries_name_an_existing_test():
    names = _all_test_function_names()
    bad = [
        e.key
        for e in REGISTRY
        if e.status is Status.EXERCISED and e.evidence not in names
    ]
    assert not bad, (
        f"EXERCISED entries naming a non-existent test (registry rot): {bad}"
    )


def test_known_gap_entries_link_a_task():
    bad = [
        e.key
        for e in REGISTRY
        if e.status is Status.KNOWN_GAP and not _FWK_REF.match(e.evidence)
    ]
    assert not bad, f"KNOWN_GAP entries whose evidence does not start 'FWK<N>': {bad}"


def test_exempt_entries_have_a_reason():
    bad = [
        e.key for e in REGISTRY if e.status is Status.EXEMPT and not e.evidence.strip()
    ]
    assert not bad, f"EXEMPT entries with an empty reason: {bad}"
