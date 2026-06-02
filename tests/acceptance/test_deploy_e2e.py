"""Multi-container e2e harness for the compose-over-SSH deploy strategy.

This task (T7) builds the HARNESS + a SMOKE test that proves the infra boots:
  - >=2 "app host" containers (Docker-in-Docker + sshd) — the deploy strategy
    ssh-es into these and runs `docker compose`;
  - 1 shared Postgres (managed-DB stand-in);
  - 1 nginx LB (passive health, drains a failing host);
  - 1 controller (reuses the host image) on the same network, with the rendered
    project + ssh private key mounted, so `DEPLOY_HOSTS="host1 host2"` and
    `APP_DATABASE_URL=...@postgres:5432/...` resolve by service name.

Later tasks (T8 rolling-deploy proof, T9 rollback proof) reuse the seams here:
  - HARNESS dir + harness.yml path constants,
  - `_docker_available()` skip helper,
  - `_compose_env()` / `_compose()` / `harness_up` context-manager,
  - the ed25519 keypair generation + authorized_keys plumbing.
"""

import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent / "deploy_e2e"
HARNESS_YML = HARNESS / "harness.yml"
AUTHORIZED_KEYS = HARNESS / "authorized_keys"
APP_HOSTS = ("host1", "host2")


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    return result.returncode == 0


def _compose_env(project_dir: Path, key_path: Path) -> dict[str, str]:
    """Env for the harness compose: service-name-resolvable mounts + host UID/GID
    so container-created bind writes are host-owned (no root-owned /tmp cruft)."""
    return {
        **os.environ,
        "E2E_PROJECT_DIR": str(project_dir),
        "E2E_KEY": str(key_path),
        "UID": str(os.getuid()),
        "GID": str(os.getgid()),
    }


def _compose(env: dict[str, str], *args: str, **kw) -> subprocess.CompletedProcess:
    """Run `docker compose -f harness.yml <args>` from the harness dir."""
    return subprocess.run(
        ["docker", "compose", "-f", str(HARNESS_YML), *args],
        cwd=str(HARNESS),
        env=env,
        **kw,
    )


def _dump_logs(env: dict[str, str]) -> None:
    """Best-effort: print compose logs so a CI/local failure is debuggable."""
    try:
        out = _compose(env, "logs", "--no-color", "--tail", "120", capture_output=True, text=True)
        print("\n===== docker compose logs (tail) =====")
        print(out.stdout)
        print(out.stderr)
    except Exception as exc:  # pragma: no cover - diagnostics only
        print(f"(could not collect compose logs: {exc})")


def _gen_keypair(disk_dir: Path) -> Path:
    """Generate an ed25519 keypair: public key -> the build context's authorized_keys,
    private key kept in the disk-backed dir. Returns the private-key path."""
    key = disk_dir / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key), "-q"],
        check=True,
    )
    pub = (disk_dir / "id_ed25519.pub").read_text()
    AUTHORIZED_KEYS.write_text(pub)
    # ssh refuses keys that are group/other readable; the mount preserves perms.
    key.chmod(0o600)
    return key


def _wait_pg_healthy(env: dict[str, str], timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = _compose(
            env, "ps", "postgres", "--format", "{{.Health}}", capture_output=True, text=True
        )
        if "healthy" in out.stdout:
            return True
        time.sleep(2)
    return False


def _controller_can_reach(env: dict[str, str], host: str, timeout: float = 120.0) -> bool:
    """Poll until the controller can ssh to `host` AND that host's nested docker works.

    dind boot in nested/WSL can take 30-60s; ssh+`docker info` is the combined proof
    that sshd is up, the key is trusted, and dockerd inside the host is functional."""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        out = _compose(
            env,
            "exec",
            "-T",
            "controller",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=5",
            "-i",
            "/home/deploy/.ssh/id_ed25519",
            f"deploy@{host}",
            "docker",
            "info",
            capture_output=True,
            text=True,
        )
        if out.returncode == 0 and "Server Version" in out.stdout:
            return True
        last = (out.stdout or "") + (out.stderr or "")
        time.sleep(3)
    print(f"\n[{host}] last ssh/docker-info attempt output:\n{last}")
    return False


@contextmanager
def harness_up(env: dict[str, str]):
    """Bring the harness up (build) and always tear it down (volumes + authorized_keys)."""
    try:
        up = _compose(env, "up", "-d", "--build", capture_output=True, text=True)
        if up.returncode != 0:
            print(up.stdout)
            print(up.stderr)
            _dump_logs(env)
            raise AssertionError("docker compose up failed")
        yield
    finally:
        _compose(env, "down", "-v", capture_output=True, text=True)
        AUTHORIZED_KEYS.unlink(missing_ok=True)


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: the deploy e2e harness boots a multi-container dind fleet",
)
def test_deploy_e2e_harness_smoke(disk_tmp: Path):
    """Smoke: the whole fleet boots — pg healthy, each host's sshd+nested-docker
    reachable from the controller, nginx LB up. The deploy proof is a later task."""
    key = _gen_keypair(disk_tmp)
    # E2E_PROJECT_DIR can be any readable dir for the smoke test; a later task
    # mounts the real rendered project here.
    env = _compose_env(project_dir=disk_tmp, key_path=key)

    with harness_up(env):
        try:
            assert _wait_pg_healthy(env), "postgres did not become healthy"

            for host in APP_HOSTS:
                assert _controller_can_reach(env, host), (
                    f"controller could not ssh+docker-info {host} "
                    "(sshd down, key untrusted, or nested dockerd not up)"
                )

            # nginx LB container is running.
            lb = _compose(env, "ps", "lb", "--format", "{{.State}}", capture_output=True, text=True)
            assert "running" in lb.stdout, f"nginx lb not running: {lb.stdout!r}"
        except Exception:
            _dump_logs(env)
            raise
