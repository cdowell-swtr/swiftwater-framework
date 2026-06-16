"""Unit tests for the six enumeration rules (FWK29)."""

import pytest

from framework_cli.batteries import battery_names, resolve
from framework_cli.copier_runner import render_project

from .enumerate import enumerate_surfaces

_BASE = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


@pytest.fixture(scope="module")
def maximal(tmp_path_factory):
    """An all-batteries (dependency-resolved) render — the maximal operational surface."""
    dest = tmp_path_factory.mktemp("cov-enum") / "demo"
    render_project(dest, {**_BASE, "batteries": resolve(battery_names())})
    return dest


def test_enumerate_finds_each_rule_class(maximal):
    keys = enumerate_surfaces(maximal)
    # One concrete representative per rule must be present in an all-batteries render.
    expected = {
        "overlay:prod.yml",  # compose overlay rule
        "service:dev.yml:redis",  # compose service rule (redis battery)
        "docker-stage:Dockerfile:runtime",  # Dockerfile stage rule
        "script:scripts/entrypoint.sh",  # operational script rule
        "job:ci.yml:lint",  # workflow job rule
        "hook:gitleaks",  # pre-commit hook rule
    }
    missing = expected - keys
    assert not missing, f"enumeration missed expected keys: {sorted(missing)}"


def test_enumerate_pins_docker_stage_multiplicity(maximal):
    # Exact-set on one fully-known rule output — guards against a rule regressing to
    # under- or over-enumerate (presence-of-one-representative wouldn't catch that).
    stages = {
        k
        for k in enumerate_surfaces(maximal)
        if k.startswith("docker-stage:Dockerfile:")
    }
    assert stages == {
        "docker-stage:Dockerfile:builder",
        "docker-stage:Dockerfile:frontend-build",
        "docker-stage:Dockerfile:runtime",
    }, sorted(stages)


def test_enumerate_keys_are_unique_strings(maximal):
    keys = enumerate_surfaces(maximal)
    assert keys, "enumeration returned no surfaces"
    assert all(isinstance(k, str) and ":" in k for k in keys)
