"""FWK35 — the framework's own `task doctor` host-tool preflight (dogfoods the template's)."""

import subprocess
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]


def test_framework_taskfile_has_doctor_target():
    tf = yaml.safe_load((_ROOT / "Taskfile.yml").read_text())
    assert "doctor" in tf["tasks"], "framework Taskfile is missing the `doctor` target"
    assert "scripts/doctor.sh" in " ".join(tf["tasks"]["doctor"]["cmds"])


def test_framework_doctor_script_valid_and_checks_core_tools():
    script = _ROOT / "scripts" / "doctor.sh"
    assert script.exists(), "scripts/doctor.sh is missing"
    assert subprocess.run(["bash", "-n", str(script)]).returncode == 0, (
        "scripts/doctor.sh is not valid bash"
    )
    body = script.read_text()
    # The framework suite shells out to every one of these — doctor must preflight each.
    for tool in (
        "docker",
        "docker buildx",
        "uv",
        "git",
        "task",
        "mkcert",
        "node",
        "npm",
        "shellcheck",
    ):
        assert tool in body, f"doctor.sh should check for {tool!r}"
