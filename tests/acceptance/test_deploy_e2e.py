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
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

from framework_cli.copier_runner import render_project

HARNESS = Path(__file__).parent / "deploy_e2e"
HARNESS_YML = HARNESS / "harness.yml"
AUTHORIZED_KEYS = HARNESS / "authorized_keys"
APP_HOSTS = ("host1", "host2")

# Canonical render inputs — match tests/test_copier_runner.py's DATA (baseline, no batteries;
# default alert channel = webhook).
DATA = {
    "project_name": "Acme",
    "project_slug": "acme",
    "package_name": "acme",
    "python_version": "3.12",
}
LB = "http://localhost:8080"


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
        out = _compose(
            env, "logs", "--no-color", "--tail", "120", capture_output=True, text=True
        )
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
            env,
            "ps",
            "postgres",
            "--format",
            "{{.Health}}",
            capture_output=True,
            text=True,
        )
        if "healthy" in out.stdout:
            return True
        time.sleep(2)
    return False


def _controller_can_reach(
    env: dict[str, str], host: str, timeout: float = 120.0
) -> bool:
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


# =========================================================================================
# T8 reusable seams (also used by T9 rollback proof): image build + load, pg-IP resolution,
# the controller-run strategy invocation, LB readiness, and a continuous LB poller.
# =========================================================================================


def _run(cmd: list[str], cwd: Path | None = None, **kw) -> subprocess.CompletedProcess:
    """Run a command, asserting rc==0 and surfacing stdout/stderr on failure."""
    p = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, **kw
    )
    assert p.returncode == 0, (
        f"command failed ({p.returncode}): {' '.join(cmd)}\n"
        f"--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}"
    )
    return p


def _build_app_image(project: Path, tag: str) -> None:
    """Build the rendered project's app image on the OUTER (WSL host) docker."""
    _run(
        ["docker", "build", "-f", "infra/docker/Dockerfile", "-t", tag, "."],
        cwd=project,
        timeout=900,
    )


def _add_expand_migration(project: Path) -> None:
    """Append an EXPAND migration (new NULLABLE column 'note' on 'items') chained onto the
    current head, so the v2 image carries a forward+down path the strategy can apply once."""
    versions = project / "migrations" / "versions"
    # Baseline render head is 0001; assert it so a template change that adds a baseline
    # migration is caught loudly rather than producing a broken revision chain.
    heads = sorted(p.stem.split("_")[0] for p in versions.glob("*.py"))
    assert heads == ["0001"], f"unexpected baseline migration heads: {heads}"
    down = "0001"
    (versions / "0099_e2e_expand.py").write_text(
        '"""e2e expand: nullable items.note (T8 no-downtime proof)\n\n'
        "Revision ID: 0099\n"
        f"Revises: {down}\n"
        "Create Date: 2026-06-02\n"
        '"""\n\n'
        "import sqlalchemy as sa\n\n"
        "from alembic import op\n\n"
        'revision = "0099"\n'
        f'down_revision = "{down}"\n'
        "branch_labels = None\n"
        "depends_on = None\n\n\n"
        "def upgrade() -> None:\n"
        '    op.add_column("items", sa.Column("note", sa.String(length=255), nullable=True))\n\n\n'
        "def downgrade() -> None:\n"
        '    op.drop_column("items", "note")\n'
    )


def _compose_base(env: dict[str, str]) -> list[str]:
    """The `docker compose -f harness.yml` prefix (used to exec into harness services)."""
    return ["docker", "compose", "-f", str(HARNESS_YML)]


def _column_exists(env: dict[str, str], table: str, col: str) -> bool:
    """True iff `col` exists on `table` in the shared harness Postgres (creds app/app/app)."""
    q = (
        f"SELECT 1 FROM information_schema.columns "
        f"WHERE table_name='{table}' AND column_name='{col}'"
    )
    out = subprocess.run(
        [
            *_compose_base(env),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "app",
            "-d",
            "app",
            "-tAc",
            q,
        ],
        cwd=str(HARNESS),
        env=env,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip() == "1"


def _current_release(env: dict[str, str], strat_env: dict[str, str]) -> str:
    """`strategy.sh current-release` -> the most-recent release's image tag (stripped)."""
    r = _strategy(env, strat_env, "current-release")
    assert r.returncode == 0, (
        f"current-release failed:\n--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}"
    )
    return r.stdout.strip()


def _resolve_pg_ip(env: dict[str, str]) -> str:
    """Wrinkle A: a nested app (inside host1/host2's dind) can't resolve the sibling harness
    service name `postgres` (different network), but it CAN reach postgres's harness-network IP
    via the dind container's outbound NAT. Resolve that IP from the controller (same harness net)."""
    out = _compose(
        env,
        "exec",
        "-T",
        "controller",
        "getent",
        "hosts",
        "postgres",
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0 and out.stdout.strip(), (
        f"could not resolve postgres harness IP: rc={out.returncode} "
        f"out={out.stdout!r} err={out.stderr!r}"
    )
    ip = out.stdout.split()[0]
    return ip


def _load_image_into_hosts(env: dict[str, str], tag: str) -> None:
    """`docker save` the outer image and `docker load` it into each host's nested dockerd."""
    save = subprocess.run(["docker", "save", tag], capture_output=True)
    assert save.returncode == 0, f"docker save {tag} failed: {save.stderr!r}"
    for host in APP_HOSTS:
        p = _compose(
            env,
            "exec",
            "-T",
            host,
            "docker",
            "load",
            input=save.stdout,
            capture_output=True,
        )
        assert p.returncode == 0, f"docker load {tag} into {host} failed: {p.stderr!r}"


def _strategy(
    env: dict[str, str], strat_env: dict[str, str], op: str
) -> subprocess.CompletedProcess:
    """Wrinkle B: run the REAL deploy strategy AS the `deploy` user from /work on the controller.
    strategy.sh / compose-ssh.sh ssh with the deploy user's default identity (no -i), so the
    mounted key at /home/deploy/.ssh/id_ed25519 (mode 600, host-uid-owned == deploy uid) is used.
    HOME is forced so ssh finds that default key."""
    env_args: list[str] = []
    for k, v in strat_env.items():
        env_args += ["-e", f"{k}={v}"]
    return _compose(
        env,
        "exec",
        "-T",
        "-u",
        "deploy",
        "-w",
        "/work",
        "-e",
        "HOME=/home/deploy",
        *env_args,
        "controller",
        "bash",
        "infra/deploy/strategy.sh",
        op,
        capture_output=True,
        text=True,
    )


def _await_lb_healthy(timeout: float = 150.0) -> bool:
    """Poll the LB's /health until it returns 200 (a host is up + routed)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(LB + "/health", timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


class _Poller(threading.Thread):
    """Hammer the LB continuously; count totals + failures (non-200 or exception)."""

    def __init__(self, paths=("/heartbeat", "/health"), interval: float = 0.05):
        super().__init__(daemon=True)
        self._paths = paths
        self._interval = interval
        # NOT `_stop` — that shadows threading.Thread._stop() and breaks join().
        self._stop_evt = threading.Event()
        self.total = 0
        self.failures = 0
        self.errors: list[str] = []

    def run(self) -> None:
        i = 0
        while not self._stop_evt.is_set():
            path = self._paths[i % len(self._paths)]
            i += 1
            self.total += 1
            try:
                with urllib.request.urlopen(LB + path, timeout=5) as resp:
                    if resp.status != 200:
                        self.failures += 1
                        self.errors.append(f"{path} -> {resp.status}")
            except Exception as exc:
                self.failures += 1
                self.errors.append(f"{path} -> {type(exc).__name__}: {exc}")
            time.sleep(self._interval)

    def stop(self) -> None:
        self._stop_evt.set()


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
            lb = _compose(
                env,
                "ps",
                "lb",
                "--format",
                "{{.State}}",
                capture_output=True,
                text=True,
            )
            assert "running" in lb.stdout, f"nginx lb not running: {lb.stdout!r}"
        except Exception:
            _dump_logs(env)
            raise


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: the deploy e2e harness boots a multi-container dind fleet",
)
def test_deploy_e2e_rolling_update_has_no_downtime(disk_tmp: Path):
    """Headline proof: the REAL compose-over-SSH strategy does a NO-DOWNTIME rolling update
    across 2 hosts. Deploy v1, start hammering the LB, deploy v2 (= v1 + an expand migration);
    the migrate-once + per-host roll (drain one host at a time) must serve every request."""
    project = disk_tmp / "app"
    render_project(project, DATA)
    # A fresh render has no uv.lock; the app Dockerfile COPYs + `uv sync --frozen`s it. Generate
    # it once on the host (the controller re-syncs its own venv from the same lock at warm-up).
    _run(["uv", "lock"], cwd=project, timeout=600)

    # Build v1 (baseline), then add the expand migration and build v2 (baseline + migration).
    _build_app_image(project, "acme:v1")
    _add_expand_migration(project)
    _build_app_image(project, "acme:v2")

    key = _gen_keypair(disk_tmp)
    env = _compose_env(project_dir=project, key_path=key)

    try:
        with harness_up(env):
            try:
                assert _wait_pg_healthy(env), "postgres did not become healthy"
                for host in APP_HOSTS:
                    assert _controller_can_reach(env, host), (
                        f"controller could not reach {host}"
                    )

                # Wrinkle A: nested app reaches the shared pg by its harness-network IP, not name.
                pg_ip = _resolve_pg_ip(env)
                db_url = f"postgresql+psycopg://app:app@{pg_ip}:5432/app"

                # Warm the controller's project venv once (repo_head_revision runs `uv run alembic
                # heads`; lazy-syncing inside the first deploy would bury any sync error). Mirrors
                # a CI runner having already `uv sync`-ed the checkout.
                warm = _compose(
                    env,
                    "exec",
                    "-T",
                    "-u",
                    "deploy",
                    "-w",
                    "/work",
                    "-e",
                    "HOME=/home/deploy",
                    "controller",
                    "uv",
                    "run",
                    "alembic",
                    "heads",
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                # /work carries the expand migration (added before the v2 build), so the single
                # head the controller resolves is 0099 — confirming the chain + the synced venv.
                assert warm.returncode == 0 and "0099" in warm.stdout, (
                    f"controller venv warm-up failed:\n{warm.stdout}\n{warm.stderr}"
                )

                _load_image_into_hosts(env, "acme:v1")
                _load_image_into_hosts(env, "acme:v2")

                base_strat_env = {
                    "DEPLOY_TARGET": "compose-ssh",
                    "DEPLOY_ENV": "prod",
                    "DEPLOY_HOSTS": " ".join(APP_HOSTS),
                    "DEPLOY_BASE_URL": "http://lb",  # controller reaches the LB by service name
                    "APP_DATABASE_URL": db_url,
                    "APP_ALERT_WEBHOOK_URL": "http://x",  # satisfies check_alert_secrets (webhook)
                    "DEPLOY_AWAIT_TIMEOUT": "150",
                    # The deploy user owns its deploy dir (the default /opt/app is root-only on the
                    # host image); the compose file + release state live here.
                    "DEPLOY_PATH": "/home/deploy/app",
                }

                # Deploy v1: real strategy from the controller, as the deploy user (Wrinkle B).
                r1 = _strategy(
                    env, {**base_strat_env, "APP_IMAGE": "acme:v1"}, "deploy"
                )
                assert r1.returncode == 0, (
                    f"v1 deploy failed:\n--- stdout ---\n{r1.stdout}\n--- stderr ---\n{r1.stderr}"
                )
                assert _await_lb_healthy(), (
                    "LB did not serve /health after the v1 deploy"
                )

                # Start hammering the LB, then roll to v2 (migrate-once + per-host rolling restart).
                poller = _Poller()
                poller.start()
                time.sleep(1)
                r2 = _strategy(
                    env, {**base_strat_env, "APP_IMAGE": "acme:v2"}, "deploy"
                )
                time.sleep(1)
                poller.stop()
                poller.join(timeout=10)

                assert r2.returncode == 0, (
                    f"v2 rolling deploy failed:\n--- stdout ---\n{r2.stdout}\n--- stderr ---\n{r2.stderr}"
                )
                assert poller.total > 10, (
                    f"poller barely ran (total={poller.total}); the proof window is too short"
                )
                assert poller.failures == 0, (
                    f"DOWNTIME during the rolling update: {poller.failures}/{poller.total} "
                    f"requests failed; first errors: {poller.errors[:10]}"
                )
                print(
                    f"\n[no-downtime] poller total={poller.total} failures={poller.failures}"
                )
            except Exception:
                _dump_logs(env)
                raise
    finally:
        # The v1/v2 images were built on the OUTER docker (for `docker save` into the hosts);
        # remove them so reruns + CI don't accumulate dangling app images.
        subprocess.run(
            ["docker", "rmi", "-f", "acme:v1", "acme:v2"], capture_output=True
        )


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: the deploy e2e harness boots a multi-container dind fleet",
)
def test_deploy_e2e_rollback_reverts_code_and_schema(disk_tmp: Path):
    """Headline proof: the REAL compose-over-SSH strategy ROLLS BACK code AND schema.

    Deploy v1 (baseline, recorded revision 0001), then v2 (= v1 + an expand migration,
    recorded revision 0099; the expand `items.note` is applied once). `strategy.sh
    rollback` must then (a) roll the code back to v1 on all hosts AND (b) downgrade the
    schema ONCE to v1's recorded revision (0001) — so the prior release serves and the
    expand column is gone.

    The recorded revisions are the crux: `deploy` records `repo_head_revision()` =
    `alembic heads` in the controller's `/work` checkout AT DEPLOY TIME. So the v1 deploy
    must run with `/work` carrying ONLY the baseline (head 0001), and the v2 deploy with
    `/work` carrying the expand migration (head 0099). We stage `/work` (== the rendered
    project dir, mounted rw into the controller) accordingly between deploys. The rollback
    downgrade itself runs inside the recorded head image (acme:v2, which HAS the 0099
    down-path), independent of the `/work` checkout state at rollback time.
    """
    project = disk_tmp / "app"
    render_project(project, DATA)
    _run(["uv", "lock"], cwd=project, timeout=600)

    # Build v1 (baseline-only), then add the expand migration and build v2 (baseline + expand).
    _build_app_image(project, "acme:v1")
    _add_expand_migration(project)
    _build_app_image(project, "acme:v2")

    # CRITICAL /work staging: remove the expand migration from the render dir so the v1 deploy's
    # controller checkout (== /work) heads at 0001 → v1's release row records revision 0001.
    expand_mig = project / "migrations" / "versions" / "0099_e2e_expand.py"
    expand_mig.unlink()

    key = _gen_keypair(disk_tmp)
    env = _compose_env(project_dir=project, key_path=key)

    try:
        with harness_up(env):
            try:
                assert _wait_pg_healthy(env), "postgres did not become healthy"
                for host in APP_HOSTS:
                    assert _controller_can_reach(env, host), (
                        f"controller could not reach {host}"
                    )

                pg_ip = _resolve_pg_ip(env)
                db_url = f"postgresql+psycopg://app:app@{pg_ip}:5432/app"

                # Warm the controller's project venv (baseline /work: head must resolve to 0001).
                warm = _compose(
                    env,
                    "exec",
                    "-T",
                    "-u",
                    "deploy",
                    "-w",
                    "/work",
                    "-e",
                    "HOME=/home/deploy",
                    "controller",
                    "uv",
                    "run",
                    "alembic",
                    "heads",
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                assert warm.returncode == 0 and "0001" in warm.stdout, (
                    f"controller venv warm-up (baseline head 0001) failed:\n"
                    f"{warm.stdout}\n{warm.stderr}"
                )

                _load_image_into_hosts(env, "acme:v1")
                _load_image_into_hosts(env, "acme:v2")

                base_strat_env = {
                    "DEPLOY_TARGET": "compose-ssh",
                    "DEPLOY_ENV": "prod",
                    "DEPLOY_HOSTS": " ".join(APP_HOSTS),
                    "DEPLOY_BASE_URL": "http://lb",
                    "APP_DATABASE_URL": db_url,
                    "APP_ALERT_WEBHOOK_URL": "http://x",
                    "DEPLOY_AWAIT_TIMEOUT": "150",
                    "DEPLOY_PATH": "/home/deploy/app",
                }

                # Deploy v1: /work heads at 0001 → release row records (acme:v1, 0001).
                r1 = _strategy(
                    env, {**base_strat_env, "APP_IMAGE": "acme:v1"}, "deploy"
                )
                assert r1.returncode == 0, (
                    f"v1 deploy failed:\n--- stdout ---\n{r1.stdout}\n--- stderr ---\n{r1.stderr}"
                )
                assert _await_lb_healthy(), (
                    "LB did not serve /health after the v1 deploy"
                )
                assert not _column_exists(env, "items", "note"), (
                    "items.note already exists after the v1 (baseline) deploy — "
                    "the v1 image should carry only the 0001 schema"
                )

                # CRITICAL /work staging: re-add the expand migration so the v2 deploy's controller
                # checkout heads at 0099 → v2's release row records revision 0099.
                _add_expand_migration(project)

                # Deploy v2: /work heads at 0099 → release row records (acme:v2, 0099); the expand
                # migration runs ONCE against the shared DB → items.note appears.
                r2 = _strategy(
                    env, {**base_strat_env, "APP_IMAGE": "acme:v2"}, "deploy"
                )
                assert r2.returncode == 0, (
                    f"v2 deploy failed:\n--- stdout ---\n{r2.stdout}\n--- stderr ---\n{r2.stderr}"
                )
                assert _await_lb_healthy(), (
                    "LB did not serve /health after the v2 deploy"
                )

                # PROOF (pre-rollback): the expand column is present after the v2 deploy.
                assert _column_exists(env, "items", "note"), (
                    "items.note missing after the v2 deploy — the expand migration "
                    "did not apply, so the rollback proof would be meaningless"
                )
                assert _current_release(env, base_strat_env) == "acme:v2", (
                    "current-release should be acme:v2 after the v2 deploy"
                )

                # ROLLBACK: reverse the schema to v1's recorded revision (0001), via the recorded
                # head image (acme:v2, which has the 0099 down-path), THEN redeploy v1's image.
                rb = _strategy(env, base_strat_env, "rollback")
                assert rb.returncode == 0, (
                    f"rollback failed:\n--- stdout ---\n{rb.stdout}\n--- stderr ---\n{rb.stderr}"
                )
                assert _await_lb_healthy(), (
                    "LB did not serve /health after the rollback"
                )

                # PROOF (post-rollback): the prior release (acme:v1) serves AND the expand column
                # is gone (a REAL downgrade ran 0099.downgrade() against the shared DB).
                current = _current_release(env, base_strat_env)
                assert current == "acme:v1", (
                    f"rollback did not restore the prior release: current-release={current!r} "
                    f"(expected 'acme:v1')"
                )
                note_after = _column_exists(env, "items", "note")
                assert note_after is False, (
                    "items.note STILL EXISTS after rollback — the schema was NOT reverted. "
                    "Likely v1's release row recorded the wrong revision (0099 not 0001); "
                    "inspect /home/deploy/app/releases-prod.tsv. Do NOT relax this assertion."
                )
                print(
                    "\n[rollback] current-release=acme:v1; items.note before=True after=False"
                )
            except Exception:
                _dump_logs(env)
                # Surface the recorded release rows — the usual rollback-revision suspect.
                rows = _compose(
                    env,
                    "exec",
                    "-T",
                    "-u",
                    "deploy",
                    "controller",
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-i",
                    "/home/deploy/.ssh/id_ed25519",
                    "deploy@host1",
                    "cat",
                    "/home/deploy/app/releases-prod.tsv",
                    capture_output=True,
                    text=True,
                )
                print("\n===== releases-prod.tsv (host1) =====")
                print(rows.stdout)
                print(rows.stderr)
                raise
    finally:
        subprocess.run(
            ["docker", "rmi", "-f", "acme:v1", "acme:v2"], capture_output=True
        )
