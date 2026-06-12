"""Behavioral test for the rendered scripts/doctor.sh host-tool preflight.

doctor.sh is presence-only: it exits 0 when every required host tool is on PATH and
non-zero when any is missing. We render the script and run it against a stub PATH so the
test is hermetic — independent of whatever is actually installed on the box.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

from framework_cli.copier_runner import render_project

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}

# Resolve a real bash up front (via the real PATH); the doctor run itself uses a stub-only PATH.
_BASH = shutil.which("bash")


def _stub_bin(dirpath: Path, names: list[str]) -> None:
    """Create exit-0 stub executables. `#!/bin/sh` (absolute) so executing a stub needs no
    PATH lookup — the doctor run sets PATH to this dir alone."""
    dirpath.mkdir(parents=True, exist_ok=True)
    for name in names:
        f = dirpath / name
        f.write_text("#!/bin/sh\nexit 0\n")
        f.chmod(f.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run_doctor(project: Path, path_dir: Path) -> int:
    # Invoke the real bash by absolute path; doctor.sh's internal `command -v` probes see only
    # the stub dir on PATH.
    return subprocess.run(
        [_BASH, "scripts/doctor.sh"],
        cwd=project,
        env={**os.environ, "PATH": str(path_dir)},
    ).returncode


def test_doctor_passes_when_all_tools_present(tmp_path: Path):
    proj = tmp_path / "proj"
    render_project(proj, DATA)
    bindir = tmp_path / "bin"
    _stub_bin(bindir, ["docker", "mkcert", "uv", "git"])
    assert _run_doctor(proj, bindir) == 0


def test_doctor_fails_when_a_required_tool_is_missing(tmp_path: Path):
    proj = tmp_path / "proj"
    render_project(proj, DATA)
    bindir = tmp_path / "bin"
    _stub_bin(bindir, ["docker", "uv", "git"])  # mkcert deliberately absent
    assert _run_doctor(proj, bindir) != 0
