import hashlib
import hmac
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from framework_cli.batteries import resolve
from framework_cli.copier_runner import render_project
from framework_cli.downskill import remove_battery
from framework_cli.integrity.checker import check
from framework_cli.integrity.restore import restore_file

DATA = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def _docker_available() -> bool:
    if shutil.which("uv") is None or shutil.which("docker") is None:
        return False
    result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
    return result.returncode == 0


def _compose_env() -> dict[str, str]:
    """Env for `docker compose up` so the dev app runs as the host user (host-owned bind writes)."""
    return {**os.environ, "UID": str(os.getuid()), "GID": str(os.getgid())}


def _free_tcp_port() -> int:
    """An OS-assigned free TCP port (bind :0, read it back, release). Used to give each
    co-running stack distinct, non-colliding host ports without guessing fixed numbers."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return int(s.getsockname()[1])


def _compose_host_port(
    dest: Path, compose_files: list[str], service: str, container_port: int
) -> int:
    """The ephemeral host port docker assigned to <service>:<container_port> for this stack."""
    fargs: list[str] = []
    for f in compose_files:
        fargs += ["-f", f]
    out = subprocess.run(
        ["docker", "compose", *fargs, "port", service, str(container_port)],
        cwd=dest,
        env=_compose_env(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # docker prints "0.0.0.0:NNNNN" (or "[::]:NNNNN"); take the trailing port.
    return int(out.rsplit(":", 1)[1])


@contextmanager
def _run_image_serving(
    image: str,
    *,
    extra_env: dict[str, str] | None = None,
    ready_path: str = "/heartbeat",
) -> Iterator[str]:
    """`docker run -d` the built image on a free host port with migrations disabled, poll
    <ready_path> until 200, and yield the base URL. DB-less: APP_RUN_MIGRATIONS=false makes the
    entrypoint skip alembic/seed and exec uvicorn; every Settings field has a default and the
    app's lifespan does not require the DB. Removes the container on exit; on not-ready it raises
    with `docker logs` attached so a boot crash is diagnosable."""
    port = _free_tcp_port()
    env_args = ["-e", "APP_RUN_MIGRATIONS=false"]
    for k, v in (extra_env or {}).items():
        env_args += ["-e", f"{k}={v}"]
    run = subprocess.run(
        ["docker", "run", "-d", "-p", f"{port}:8000", *env_args, image],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, f"docker run failed for {image}:\n{run.stderr}"
    cid = run.stdout.strip()
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 60
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base}{ready_path}", timeout=3) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                pass
            time.sleep(2)
        if not ready:
            logs = subprocess.run(
                ["docker", "logs", cid], capture_output=True, text=True
            )
            raise AssertionError(
                f"{image} did not serve {ready_path} within 60s\n"
                f"--- docker logs ---\n{logs.stdout}\n{logs.stderr}"
            )
        yield base
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True)


def _poll_json(url: str, *, timeout: float, predicate) -> dict | None:
    """Poll an HTTP endpoint returning JSON until `predicate(parsed)` is truthy or `timeout`
    elapses. Returns the parsed JSON that satisfied the predicate, else None. Tolerates the
    not-yet-up window (connection refused / 5xx / partial JSON) by swallowing OSError + JSON
    errors between polls — the obs stack's scrape/ingest/provisioning all have a boot lag."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                parsed = json.loads(resp.read())
            if predicate(parsed):
                return parsed
        except (OSError, ValueError):
            pass
        time.sleep(3)
    return None


def _mkcert_ssl_context() -> ssl.SSLContext:
    """An SSL context that trusts ONLY the mkcert CA (chain-verify), with hostname check off
    (the cert's *.localhost wildcard SAN is browser-valid but OpenSSL won't match it)."""
    caroot = subprocess.run(
        ["mkcert", "-CAROOT"], capture_output=True, text=True
    ).stdout.strip()
    ctx = ssl.create_default_context(cafile=str(Path(caroot) / "rootCA.pem"))
    ctx.check_hostname = False
    return ctx


def _traefik_request(
    https_port: int,
    host: str,
    ctx: ssl.SSLContext,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, str]:
    """One HTTP/1.1 request THROUGH Traefik over TLS (connect 127.0.0.1:<port>, SNI+Host=<host>,
    Connection: close so we read to EOF). Returns (status, body_text). Mirrors the recipe in
    test_rendered_project_dev_stack_routes_through_traefik."""
    lines = [f"{method} {path} HTTP/1.1", f"Host: {host}", "Connection: close"]
    for k, v in (headers or {}).items():
        lines.append(f"{k}: {v}")
    if body is not None:
        lines.append(f"Content-Length: {len(body)}")
    req = ("\r\n".join(lines) + "\r\n\r\n").encode() + (body or b"")
    raw = socket.create_connection(("127.0.0.1", https_port), timeout=5)
    with ctx.wrap_socket(raw, server_hostname=host) as ssock:
        ssock.sendall(req)
        data = b""
        while True:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            data += chunk
    head, _, payload = data.partition(b"\r\n\r\n")
    status = int(head.split(b"\r\n", 1)[0].split()[1])
    return status, payload.decode(errors="replace")


def _traefik_ws_upgrade(https_port: int, host: str, ctx: ssl.SSLContext) -> int:
    """Open a WebSocket upgrade to /ws THROUGH Traefik; return the HTTP status (expect 101
    Switching Protocols — proves the proxy negotiates the WS upgrade, the M8 risk). We assert the
    handshake only (frame echo is covered in-process by the websockets battery's own test)."""
    import base64

    key = base64.b64encode(b"fwk24-ws-testkey").decode()  # 16-byte nonce (RFC 6455)
    req = (
        f"GET /ws HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode()
    raw = socket.create_connection(("127.0.0.1", https_port), timeout=5)
    with ctx.wrap_socket(raw, server_hostname=host) as ssock:
        ssock.sendall(req)
        head = ssock.recv(4096)
    return int(head.split(b"\r\n", 1)[0].split()[1])


@pytest.fixture(autouse=True)
def _isolate_compose_project(request, monkeypatch):
    """Give each acceptance test its OWN docker compose project namespace.

    The generated project sets no top-level compose `name:`, so
    `docker compose -f infra/compose/base.yml …` derives the project name from the
    compose-file directory → `compose`. A developer's `task dev` stack (or another
    acceptance test) uses the SAME name and so shares container/network/volume names:
    without isolation an `up` reuses the other stack's containers and the `down -v`
    teardown DESTROYS its postgres volume. A unique COMPOSE_PROJECT_NAME — honoured by
    `up` (via `_compose_env()`, which spreads `os.environ`) and by the bare `down` calls
    (inherited env) alike — keeps each test's stack in its own namespace and scopes
    `down -v` to that test only. FWK31 (now IMPLEMENTED template-side: a per-slug project
    name + parameterized host ports) lets two generated projects co-run on one host; this
    fixture additionally binds every published host port to an ephemeral port (below) so a
    test stack never collides with a live UAT stack or another test on a fixed host port.
    """
    safe = (
        re.sub(r"[^a-z0-9]+", "-", request.node.name.lower()).strip("-")[:40] or "test"
    )
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", f"swfwacc-{safe}")
    # FWK31: bind every published host port to an ephemeral port (0 -> docker picks a free
    # one) so a test stack never collides with a live UAT stack or another test. Tests that
    # connect to a service discover the assigned port via `_compose_host_port` below.
    for var in (
        "HTTP_HOST_PORT",
        "POSTGRES_HOST_PORT",
        "TRAEFIK_HTTPS_PORT",
        "TRAEFIK_HTTP_PORT",
        "MONGO_HOST_PORT",
        "REDIS_HOST_PORT",
        "FRONTEND_HOST_PORT",
        "PROMETHEUS_HOST_PORT",
        "GRAFANA_HOST_PORT",
        "ALERTMANAGER_HOST_PORT",
        "LOKI_HOST_PORT",
        "TEMPO_HOST_PORT",
        "POSTGRES_EXPORTER_HOST_PORT",
        "MONGODB_EXPORTER_HOST_PORT",
        "CELERY_EXPORTER_HOST_PORT",
        "REDIS_EXPORTER_HOST_PORT",
    ):
        monkeypatch.setenv(var, "0")


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_passes_its_own_tests(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(["uv", "run", "pytest", "-q"], cwd=dest)
    assert result.returncode == 0, "the generated project's test suite did not pass"


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_coverage_gate_passes(tmp_path: Path):
    # The fast pre-commit-equivalent gate: unit + functional, >=70%, via scripts/coverage.sh.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"], cwd=dest
    )
    assert result.returncode == 0, "the 70% unit+functional coverage gate did not pass"


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_websockets_battery_passes(tmp_path: Path):
    # Renders a project with the websockets battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm the WS echo test
    # (tests/functional/test_websockets.py) is collected and passes.
    data_with_ws = {**DATA, "batteries": ["websockets"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_ws)

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "routes" / "websockets.py").exists(), (
        "routes/websockets.py was not rendered by the websockets battery"
    )
    assert (dest / "tests" / "functional" / "test_websockets.py").exists(), (
        "tests/functional/test_websockets.py was not rendered by the websockets battery"
    )
    assert (dest / "src" / "demo" / "websockets" / "connection_manager.py").exists(), (
        "websockets/connection_manager.py was not rendered by the websockets battery"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — this collects test_websockets.py.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the websockets battery project:\n"
        + result.stdout
        + result.stderr
    )
    # Prove the WS functional test actually ran: the route handler reaches full coverage
    # only when test_websocket_echo_broadcast exercises it (router autodiscovery alone
    # imports routes/websockets.py on every create_app() call, yielding ~46% — so the
    # filename appearing in the coverage table is NOT sufficient proof). 100% only occurs
    # when the connect→send→broadcast→receive→disconnect path runs.
    combined_output = result.stdout + result.stderr
    ws_cov_line = next(
        (ln for ln in combined_output.splitlines() if "routes/websockets.py" in ln), ""
    )
    assert "100%" in ws_cov_line, (
        f"WS route not fully exercised; coverage line: {ws_cov_line!r}\n"
        "Expected 100% coverage of routes/websockets.py — was "
        "tests/functional/test_websockets.py collected and did it pass?\n"
        + combined_output
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_webhooks_battery_passes(tmp_path: Path):
    # Renders a project with the webhooks battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm the webhook tests
    # (tests/functional/test_webhooks.py) are collected and pass — exercising the
    # 0002_webhook_events migration, HMAC signature verification, and dedup logic.
    data_with_webhooks = {**DATA, "batteries": ["webhooks"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_webhooks)

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "routes" / "webhooks.py").exists(), (
        "routes/webhooks.py was not rendered by the webhooks battery"
    )
    assert (dest / "tests" / "functional" / "test_webhooks.py").exists(), (
        "tests/functional/test_webhooks.py was not rendered by the webhooks battery"
    )
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").exists(), (
        "migrations/versions/0002_webhook_events.py was not rendered by the webhooks battery"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — this collects test_webhooks.py and runs
    # it against a real testcontainers Postgres (the 0002 migration provisions webhook_events).
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the webhooks battery project:\n"
        + result.stdout
        + result.stderr
    )
    # Prove the webhook functional tests actually ran: the route handler reaches full coverage
    # only when test_webhooks.py exercises the valid-sig 200 / bad-sig 401 / duplicate-dedup
    # paths (router autodiscovery imports routes/webhooks.py on every create_app() call,
    # yielding ~40% import-only — so the filename appearing is NOT sufficient proof).
    # 100% only occurs when all three test cases run against the real DB.
    combined_output = result.stdout + result.stderr
    wh_cov_line = next(
        (ln for ln in combined_output.splitlines() if "routes/webhooks.py" in ln), ""
    )
    assert "100%" in wh_cov_line, (
        f"Webhook route not fully exercised; coverage line: {wh_cov_line!r}\n"
        "Expected 100% coverage of routes/webhooks.py — was "
        "tests/functional/test_webhooks.py collected and did it pass?\n"
        + combined_output
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_llm_battery_passes(tmp_path: Path):
    # Renders a project with the llm battery active, asserts the battery files were
    # emitted, then runs unit+functional (70% gate) to confirm both llm test files
    # (tests/unit/test_llm_unit.py + tests/functional/test_llm.py) are collected
    # and pass — exercising the LiteLLM-backed LLMService (mocked), the in-process
    # metrics, and the /llm/complete route's 200 / 503 / 502 paths.
    data_with_llm = {**DATA, "batteries": ["llm"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_llm)

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "llm" / "service.py").exists(), (
        "llm/service.py was not rendered by the llm battery"
    )
    assert (dest / "src" / "demo" / "routes" / "llm.py").exists(), (
        "routes/llm.py was not rendered by the llm battery"
    )
    assert (dest / "tests" / "unit" / "test_llm_unit.py").exists(), (
        "tests/unit/test_llm_unit.py was not rendered by the llm battery"
    )
    assert (dest / "tests" / "functional" / "test_llm.py").exists(), (
        "tests/functional/test_llm.py was not rendered by the llm battery"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — collects the llm tests (LiteLLM is
    # monkeypatched, so no network / API key is needed) and runs them.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the llm battery project:\n"
        + result.stdout
        + result.stderr
    )
    # Prove the llm functional tests actually ran: the route handler reaches full
    # coverage only when test_llm.py exercises the 200 / 503-exhaustion / 502-error
    # paths (router autodiscovery imports routes/llm.py on every create_app() call,
    # yielding import-only coverage — so the filename appearing is NOT sufficient proof).
    combined_output = result.stdout + result.stderr
    llm_cov_line = next(
        (ln for ln in combined_output.splitlines() if "routes/llm.py" in ln), ""
    )
    assert "100%" in llm_cov_line, (
        f"LLM route not fully exercised; coverage line: {llm_cov_line!r}\n"
        "Expected 100% coverage of routes/llm.py — was "
        "tests/functional/test_llm.py collected and did it pass?\n" + combined_output
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_claudesubscriptioncli_battery_passes(tmp_path: Path):
    # claudesubscriptioncli requires llm, so render the dependency-closed set (as the CLI does).
    # Confirms the litellm-claude-cli git dep installs, register() wires at startup, and the
    # battery's unit tests (registration + keyless routing + ClaudeExhausted mapping) run.
    data = {**DATA, "batteries": resolve(["claudesubscriptioncli"])}
    dest = tmp_path / "demo"
    render_project(dest, data)

    assert (dest / "tests" / "unit" / "test_claudesubscriptioncli.py").exists(), (
        "the claudesubscriptioncli unit test was not rendered"
    )
    assert "litellm-claude-cli @ git+" in (dest / "pyproject.toml").read_text(), (
        "the litellm-claude-cli PEP 508 dep was not rendered"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed (could not fetch litellm-claude-cli?)"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the claudesubscriptioncli project:\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_agents_battery_passes(tmp_path: Path):
    # agents requires llm, so render the dependency-closed set (as the CLI does). Confirms the
    # agents module + route render and the battery's unit + functional tests (tool registry,
    # read-only Item tools, the run loop, POST /agents/run) run.
    data = {**DATA, "batteries": resolve(["agents"])}
    dest = tmp_path / "demo"
    render_project(dest, data)

    assert (dest / "src" / "demo" / "agents" / "runner.py").exists(), (
        "agents/runner.py was not rendered"
    )
    assert (dest / "src" / "demo" / "routes" / "agents.py").exists(), (
        "routes/agents.py was not rendered"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the agents battery project:\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: builds the rendered project's Docker builder stage",
)
def test_rendered_claudesubscriptioncli_docker_builder_stage_builds(tmp_path: Path):
    # Regression (Meridian 2026-06-15): the claudesubscriptioncli battery adds a git-sourced
    # dep (litellm-claude-cli @ git+...). The uv builder image has no `git`, so `uv sync` in
    # the Docker builder stage failed to clone it ("Git executable not found"). Invisible to
    # the host-uv-sync acceptance tests above — only a real `docker build` catches it. Build
    # the builder stage (the failing step) for a claudesubscriptioncli render.
    data = {**DATA, "batteries": resolve(["claudesubscriptioncli"])}
    dest = tmp_path / "demo"
    render_project(dest, data)

    # Generate uv.lock on the host (which has git) so the Dockerfile's `COPY ... uv.lock`
    # has a lockfile; the builder stage's `uv sync --frozen` then exercises the git clone.
    lock = subprocess.run(["uv", "lock"], cwd=dest, capture_output=True, text=True)
    assert lock.returncode == 0, "uv lock failed:\n" + lock.stdout + lock.stderr

    result = subprocess.run(
        [
            "docker",
            "build",
            "--target",
            "builder",
            "-f",
            "infra/docker/Dockerfile",
            "-t",
            "fwk-claudesub-builder-test",
            ".",
        ],
        cwd=dest,
        capture_output=True,
        text=True,
        env={**os.environ, "DOCKER_BUILDKIT": "1"},
    )
    subprocess.run(
        ["docker", "rmi", "-f", "fwk-claudesub-builder-test"], capture_output=True
    )
    assert result.returncode == 0, (
        "the Docker builder stage failed for a claudesubscriptioncli render — git missing "
        "for the litellm-claude-cli git dep?\n" + result.stdout + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: builds + runs the claudesubscriptioncli FULL runtime image",
)
def test_rendered_claudesubscriptioncli_docker_runtime_serves_heartbeat(tmp_path: Path):
    # H5/FWK21: the builder-stage test above builds only `--target builder`; nothing builds the
    # FULL runtime image or runs it, so a runtime-only break in the litellm-claude-cli git dep
    # (a COPY --from=builder interaction, or a runtime import) ships green. Build the default
    # (runtime) target and run it: create_app calls register_claude_cli(), so a 200 on /heartbeat
    # proves the dep is importable in the runtime image (the app booted past create_app).
    data = {**DATA, "batteries": resolve(["claudesubscriptioncli"])}
    dest = tmp_path / "demo"
    render_project(dest, data)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    image = "fwk-claudesub-runtime-test"
    build = subprocess.run(
        ["docker", "build", "-f", "infra/docker/Dockerfile", "-t", image, "."],
        cwd=dest,
        capture_output=True,
        text=True,
        env={**os.environ, "DOCKER_BUILDKIT": "1"},
    )
    try:
        assert build.returncode == 0, (
            "claudesubscriptioncli runtime image build failed:\n"
            + build.stdout
            + build.stderr
        )
        with _run_image_serving(image) as base:
            with urllib.request.urlopen(f"{base}/heartbeat", timeout=5) as resp:
                assert resp.status == 200, (
                    f"runtime image did not serve /heartbeat 200 (got {resp.status})"
                )
    finally:
        subprocess.run(["docker", "rmi", "-f", image], capture_output=True)


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_workers_battery_passes(tmp_path: Path):
    # Renders a project with the workers battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm both workers test
    # files (tests/unit/test_workers_unit.py + tests/functional/test_workers_functional.py)
    # are collected and pass — exercising the 0003_dead_letter migration and DLQ logic.
    data_with_workers = {**DATA, "batteries": ["workers"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_workers)

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "tasks" / "app.py").exists(), (
        "tasks/app.py was not rendered by the workers battery"
    )
    assert (dest / "tests" / "unit" / "test_workers_unit.py").exists(), (
        "tests/unit/test_workers_unit.py was not rendered by the workers battery"
    )
    assert (dest / "tests" / "functional" / "test_workers_functional.py").exists(), (
        "tests/functional/test_workers_functional.py was not rendered by the workers battery"
    )
    assert (dest / "migrations" / "versions" / "0003_dead_letter.py").exists(), (
        "migrations/versions/0003_dead_letter.py was not rendered by the workers battery"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — this collects both workers test files and
    # runs the functional tests against a real testcontainers Postgres (0003 migration
    # provisions the dead_letter_tasks table). Celery runs in eager mode (autouse session
    # fixture in conftest.py), so no live broker is required.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the workers battery project:\n"
        + result.stdout
        + result.stderr
    )
    # Prove the workers functional tests actually ran (not just collected): dead_letter.py
    # reaches 100% only when test_workers_functional.py exercises record_failure / count /
    # list_recent / render_dlq_metrics + the on_failure DLQ-drain path against the real DB.
    combined_output = result.stdout + result.stderr
    dlq_cov_line = next(
        (ln for ln in combined_output.splitlines() if "tasks/dead_letter.py" in ln), ""
    )
    assert "100%" in dlq_cov_line, (
        f"DLQ repository not fully exercised; coverage line: {dlq_cov_line!r}\n"
        "Expected 100% coverage of tasks/dead_letter.py — was "
        "tests/functional/test_workers_functional.py collected and did it pass?\n"
        + combined_output
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_webhooks_and_workers_passes(tmp_path: Path):
    # Renders a project with BOTH webhooks + workers batteries, verifies the full
    # migration chain (0001 → 0002 webhook_events → 0003 dead_letter), the webhooks
    # functional tests pass with the enqueue handler (Celery eager mode), and the
    # workers functional tests pass — proving end-to-end composition.
    data_with_both = {**DATA, "batteries": ["webhooks", "workers"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_both)

    # Both battery file sets must exist.
    assert (dest / "src" / "demo" / "routes" / "webhooks.py").exists(), (
        "routes/webhooks.py was not rendered"
    )
    assert (dest / "src" / "demo" / "tasks" / "app.py").exists(), (
        "tasks/app.py was not rendered"
    )
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").exists(), (
        "0002_webhook_events.py was not rendered"
    )
    assert (dest / "migrations" / "versions" / "0003_dead_letter.py").exists(), (
        "0003_dead_letter.py was not rendered"
    )

    # Verify the handler uses process_async.delay (enqueue composition is wired).
    handler = (dest / "src" / "demo" / "webhooks" / "handler.py").read_text()
    assert "process_async.delay" in handler, (
        "handler.py does not call process_async.delay — webhooks+workers composition not wired"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — alembic upgrade head walks 0001→0002→0003,
    # the webhooks functional tests pass (the route calls handle_event → process_async.delay,
    # which runs eagerly via the autouse session fixture), and the workers functional tests
    # pass. Coverage must reach 70% across the combined project.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate did not pass for the webhooks+workers project:\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_downskill_webhooks_is_green(tmp_path: Path):
    # Renders a project WITH the webhooks battery, removes it via remove_battery, and
    # verifies that the remaining project is still green (no dangling imports break
    # alembic upgrade / pytest collection, and the 70% coverage gate still passes).
    data_with_webhooks = {**DATA, "batteries": ["webhooks"]}
    dest = tmp_path / "demo"
    render_project(dest, data_with_webhooks)

    # Sanity: battery files must exist before removal.
    assert (dest / "src" / "demo" / "routes" / "webhooks.py").exists(), (
        "routes/webhooks.py was not rendered — webhooks battery did not activate"
    )

    # Remove the battery (no force needed — no builder code references it).
    remove_battery(dest, "webhooks")

    # Battery-owned route file must be gone.
    assert not (dest / "src" / "demo" / "routes" / "webhooks.py").exists(), (
        "routes/webhooks.py was not deleted by remove_battery"
    )

    # Migration must be PRESERVED (remove_battery keeps migrations/).
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").exists(), (
        "0002_webhook_events.py was unexpectedly deleted — migrations should be preserved"
    )

    # migrations/env.py must no longer reference webhooks (hybrid section stripped).
    env_py = (dest / "migrations" / "env.py").read_text()
    assert "webhooks" not in env_py, (
        "migrations/env.py still contains 'webhooks' after remove_battery"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the post-downskill project"

    # Run unit + functional tiers (70% gate) — alembic upgrade head applies both
    # migrations (0001 + 0002); the webhook_events table goes unused but causes no errors.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional coverage gate failed after downskilling webhooks:\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the e2e tier runs against real Postgres",
)
def test_rendered_project_combined_coverage_gate_passes(tmp_path: Path):
    # The authoritative CI gate: unit + functional + e2e, >=85%, via scripts/coverage.sh.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "85", "unit", "functional", "e2e"], cwd=dest
    )
    assert result.returncode == 0, "the 85% combined coverage gate did not pass"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_precommit_config_is_valid(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["uv", "run", "pre-commit", "validate-config", ".pre-commit-config.yaml"],
        cwd=dest,
    )
    assert result.returncode == 0, "pre-commit config is invalid"


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("git") is None,
    reason="uv and git are required for this test",
)
def test_rendered_project_precommit_runs_clean(tmp_path: Path):
    # A freshly generated project must make a clean first pass on the NO-DOCKER hooks:
    # ruff-check / ruff-format / mypy / gitleaks / file-hygiene must pass on the
    # scaffolded files (no hook rewrites them). The `coverage-threshold` hook runs the
    # DB test suite against a real Postgres (testcontainers), so it's skipped here and
    # exercised instead by the Docker-gated coverage test.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["uv", "run", "pre-commit", "run", "--all-files"],
        cwd=dest,
        env={**os.environ, "SKIP": "coverage-threshold"},
    )
    assert result.returncode == 0, (
        "pre-commit hooks did not pass cleanly on a fresh project"
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("git") is None,
    reason="uv and git are required for this test",
)
def test_rendered_project_precommit_clean_with_docs_battery(tmp_path: Path):
    # The docs battery adds mkdocs.yml, documentation/*.md, docs.yml, and
    # documentation/.gitignore. A freshly generated docs-battery project must
    # make a clean first pass on the NO-DOCKER hooks.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["uv", "run", "pre-commit", "run", "--all-files"],
        cwd=dest,
        env={**os.environ, "SKIP": "coverage-threshold"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"pre-commit hooks did not pass cleanly on a docs-battery project:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("git") is None,
    reason="uv and git are required for this test",
)
def test_rendered_project_precommit_clean_with_llm_battery(tmp_path: Path):
    # The llm battery adds the llm/ module (service/metrics/errors), the
    # /llm/complete route, the litellm dep + a litellm mypy override, and the llm
    # settings (incl. a SecretStr). A freshly generated llm-battery project must make
    # a clean first pass on the NO-DOCKER hooks — in particular the generated project's
    # mypy must accept `import litellm` (no PEP 561 stubs) via the override.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["llm"]})

    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    result = subprocess.run(
        ["uv", "run", "pre-commit", "run", "--all-files"],
        cwd=dest,
        env={**os.environ, "SKIP": "coverage-threshold"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"pre-commit hooks did not pass cleanly on an llm-battery project:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_exports_openapi(tmp_path: Path):
    # The export needs the app importable (uv sync) but NOT a database — create_app()
    # introspects routes without connecting, so this runs without Docker.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    result = subprocess.run(["bash", "scripts/export-openapi.sh"], cwd=dest)
    assert result.returncode == 0, "export-openapi.sh failed"

    spec = json.loads((dest / "openapi.json").read_text())
    # The OpenAPI title is the service identifier (settings.service_name, which defaults to the
    # package name) — the same identifier used for structlog/OTEL, so it is lowercase.
    assert spec["info"]["title"] == DATA["package_name"]
    for path in ("/items", "/health", "/heartbeat", "/metrics"):
        assert path in spec["paths"], f"{path} missing from the exported OpenAPI spec"


def _run_hook(dest: Path, file_path: Path) -> subprocess.CompletedProcess[str]:
    payload = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": str(file_path)}}
    )
    return subprocess.run(
        ["uv", "run", "python", ".claude/hooks/lint_changed.py"],
        cwd=dest,
        input=payload,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_blocks_on_bad_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    bad = dest / "src" / "demo" / "scratch_bad.py"
    bad.write_text("import os\n")  # unused import -> ruff F401

    result = _run_hook(dest, bad)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "F401" in (result.stdout + result.stderr)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_passes_clean_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    clean = dest / "src" / "demo" / "scratch_clean.py"
    clean.write_text("VALUE: int = 1\n")

    result = _run_hook(dest, clean)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_lint_hook_ignores_non_python(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    note = dest / "notes.txt"
    note.write_text("not python\n")

    result = _run_hook(dest, note)
    assert result.returncode == 0, result.stdout + result.stderr


def _run_gate_hook(
    dest: Path,
    payload: dict,
    *,
    stub_exit_code: int,
    marker_verdict: str | None = None,
) -> "subprocess.CompletedProcess[str]":
    """Invoke .claude/hooks/reviewers-gate-check.sh with a synthetic PreToolUse payload.

    Places a fake `framework` binary at the front of PATH that exits `stub_exit_code` so the
    hook never touches a real backend. If `marker_verdict` is given, pre-writes
    .framework/audit/marker.json with that verdict so the hook's summary-readback succeeds.
    The hook does `git rev-parse --show-toplevel`; `render_project` does NOT git-init, so we
    make `dest` its own repo here (else rev-parse resolves to the framework repo, or the hook's
    `|| exit 0` short-circuits and the FAIL case never reaches exit 2).
    """
    import stat

    # `dest` must be a git repo for the hook's `git rev-parse --show-toplevel` to resolve to it.
    # A fresh `git init` installs no git hooks, so `git commit` here runs nothing extra.
    subprocess.run(["git", "init", "-q"], cwd=dest, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dest, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=dest,
        check=True,
    )

    # Build a fake `framework` binary that exits stub_exit_code.
    fake_bin = dest / ".fwk27-bin"
    fake_bin.mkdir(exist_ok=True)
    fake_framework = fake_bin / "framework"
    fake_framework.write_text(f"#!/usr/bin/env bash\nexit {stub_exit_code}\n")
    fake_framework.chmod(
        fake_framework.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH
    )

    # Pre-write the marker.json if the FAIL branch will try to read it.
    if marker_verdict is not None:
        marker_dir = dest / ".framework" / "audit"
        marker_dir.mkdir(parents=True, exist_ok=True)
        (marker_dir / "marker.json").write_text(
            json.dumps({"verdict": marker_verdict, "summary": "FWK27 test finding"})
        )

    # Prepend the fake bin dir to PATH so `uv run framework gate` calls our stub, not the
    # real CLI.  uv itself is still found at its normal location.
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}

    return subprocess.run(
        ["bash", ".claude/hooks/reviewers-gate-check.sh"],
        cwd=dest,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("bash") is None,
    reason="uv + bash required: renders the project and invokes the gate hook shell script",
)
def test_rendered_gate_hook_blocks_on_fail_marker(tmp_path: Path):
    # M15/FWK27: the hook's FAIL path (exit 2) is never exercised — only render-text-checked.
    # Pipe a `git commit` PreToolUse payload; the fake `framework` binary exits 1 (gate FAIL);
    # the hook reads .framework/audit/marker.json and exits 2.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    # uv sync not required: we don't call the rendered project's venv — only bash + the fake stub.

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'test commit'"},
    }
    result = _run_gate_hook(dest, payload, stub_exit_code=1, marker_verdict="FAIL")
    assert result.returncode == 2, (
        "gate hook did not exit 2 on a FAIL verdict — FAIL->exit-2 translation broken\n"
        + result.stdout
        + result.stderr
    )
    assert "FAILED" in result.stderr, (
        "expected 'FAILED' in hook stderr on a FAIL verdict\n" + result.stderr
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("bash") is None,
    reason="uv + bash required: renders the project and invokes the gate hook shell script",
)
def test_rendered_gate_hook_passes_on_pass_marker(tmp_path: Path):
    # M15/FWK27: the hook's PASS path (exit 0 after framework gate succeeds) must also be
    # asserted — the fake `framework` binary exits 0 (gate PASS); the hook exits 0.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'test commit'"},
    }
    result = _run_gate_hook(dest, payload, stub_exit_code=0, marker_verdict="PASS")
    assert result.returncode == 0, (
        "gate hook did not exit 0 on a PASS verdict\n" + result.stdout + result.stderr
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("bash") is None,
    reason="uv + bash required: renders the project and invokes the gate hook shell script",
)
def test_rendered_gate_hook_skips_non_commit(tmp_path: Path):
    # M15/FWK27: the grep guard (line 8 of the hook) must exit 0 for non-commit Bash payloads
    # without reaching the `framework gate` call at all. Use stub_exit_code=1 so if the grep
    # guard breaks and the hook proceeds, it would exit 2 — making the skip a detectable failure.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
    result = _run_gate_hook(dest, payload, stub_exit_code=1)
    assert result.returncode == 0, (
        "gate hook did not skip (exit 0) on a non-commit Bash payload — grep guard broken\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv and docker are required for the live-stack test",
)
def test_rendered_project_dev_lite_stack_serves_health(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base = "infra/compose/base.yml"
    dev = "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "up",
        "-d",
        "--build",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "down",
        "-v",
    ]
    assert subprocess.run(up, cwd=dest, env=_compose_env()).returncode == 0
    try:
        # app is published on 8000 in the `lite` profile (no Traefik); discover the
        # ephemeral host port docker assigned (FWK31 binds host ports to 0).
        port = _compose_host_port(dest, [base, dev], "app", 8000)
        deadline = time.time() + 90
        body = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}/health", timeout=3
                ) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read())
                        break
            except OSError:
                time.sleep(2)
        assert body is not None, "app did not serve /health within 90s"
        assert body["status"] in {"ok", "degraded"}
        assert "request_latency_p99_ms" in body["slos"]
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: test-profile stack + tmpfs ephemeral-DB reset",
)
def test_rendered_test_profile_stack_serves_and_resets_db(tmp_path: Path) -> None:
    # FWK19 (M3): test.yml is shipped and documented (`task test:stack`), but the acceptance
    # tier never uses --profile test — the tmpfs ephemeral-DB reset is undriven. Bring the
    # stack up twice and assert: (a) the app serves /health on the first up, and (b) the
    # postgres-test container has a DIFFERENT container ID on the second up, proving the tmpfs
    # was torn down and recreated (ephemeral reset, not a persistent volume re-mount).
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    # test.yml + base.yml: base.yml defines the app build+healthcheck; test.yml adds the test
    # profile + postgres-test. Neither publishes a host port for `app`; add one via an inline
    # ephemeral override so _compose_host_port can discover the assigned ephemeral port.
    # The _isolate_compose_project autouse fixture sets HTTP_HOST_PORT=0, so docker assigns
    # a free ephemeral port automatically.
    (dest / "infra" / "compose" / "fwk19.override.yml").write_text(
        'services:\n  app:\n    ports:\n      - "${HTTP_HOST_PORT:-8000}:8000"\n'
    )

    base = "infra/compose/base.yml"
    test_overlay = "infra/compose/test.yml"
    override = "infra/compose/fwk19.override.yml"
    files = [base, test_overlay, override]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]

    compose = ["docker", "compose", *fargs, "--profile", "test"]
    up = [*compose, "up", "-d", "--build"]
    up_no_rebuild = [*compose, "up", "-d", "--no-build"]
    down = [*compose, "down", "-v"]
    env = _compose_env()

    try:
        # --- First boot ---
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0, (
            "test-profile stack first `up --build` failed"
        )
        port = _compose_host_port(dest, files, "app", 8000)

        # Poll /health until 200 (app runs alembic upgrade head before uvicorn serves).
        deadline = time.time() + 120
        body = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}/health", timeout=3
                ) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read())
                        break
            except OSError:
                time.sleep(2)
        assert body is not None, (
            "test-profile app did not serve /health 200 within 120s on first boot"
        )
        assert body["status"] in {"ok", "degraded"}, (
            f"unexpected /health status on first boot: {body}"
        )

        # Capture the postgres-test container ID on the first boot.
        cid1 = subprocess.run(
            [*compose, "ps", "-q", "postgres-test"],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert cid1, "postgres-test container not found after first up"

        # --- Teardown (with -v: drop named volumes — there are none for postgres-test since
        # it uses tmpfs, but -v is consistent with the other acceptance tests) ---
        assert subprocess.run(down, cwd=dest, env=env).returncode == 0, (
            "test-profile stack `down -v` failed"
        )

        # --- Second boot (no rebuild — image is already built) ---
        assert subprocess.run(up_no_rebuild, cwd=dest, env=env).returncode == 0, (
            "test-profile stack second `up --no-build` failed"
        )
        # Re-discover the port (ephemeral; may differ after a new up).
        port2 = _compose_host_port(dest, files, "app", 8000)

        # Poll /health on the second boot.
        deadline2 = time.time() + 120
        body2 = None
        while time.time() < deadline2:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port2}/health", timeout=3
                ) as resp:
                    if resp.status == 200:
                        body2 = json.loads(resp.read())
                        break
            except OSError:
                time.sleep(2)
        assert body2 is not None, (
            "test-profile app did not serve /health 200 within 120s on second boot — "
            "the tmpfs reset may have left postgres-test in an inconsistent state, or the "
            "app failed to re-run alembic upgrade head against the fresh DB"
        )

        # The tmpfs reset proof: postgres-test was torn down and recreated — its container ID
        # must differ between the first and second boot (a persistent volume would allow the
        # same container to be restarted, but `down` removes containers, so this mainly proves
        # the second `up` created a brand-new postgres-test rather than re-attaching to a
        # lingering one from a stale project namespace).
        cid2 = subprocess.run(
            [*compose, "ps", "-q", "postgres-test"],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert cid2, "postgres-test container not found after second up"
        assert cid2 != cid1, (
            "postgres-test container ID did not change between first and second boot — "
            "the tmpfs ephemeral-DB reset did not produce a fresh container "
            f"(first={cid1!r}, second={cid2!r})"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)


@pytest.mark.skipif(
    not _docker_available() or shutil.which("task") is None,
    reason="uv + docker + go-task required: task dev:lite precondition fast-fail",
)
def test_rendered_taskfile_dev_lite_precondition_rejects_missing_lock(
    tmp_path: Path,
) -> None:
    # M5/FWK25 (negative): the dev:lite precondition `test -f uv.lock` should fail fast
    # (non-zero, without starting any containers) when uv.lock is absent. This covers the
    # precondition machinery that the raw-compose dev:lite test never exercises.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    # Do NOT run uv lock — leave uv.lock absent so the precondition fires.
    result = subprocess.run(
        ["task", "dev:lite"],
        cwd=dest,
        env=_compose_env(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, (
        "task dev:lite should have failed fast with a missing uv.lock precondition, "
        f"but exited 0.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The precondition message (Taskfile.yml.jinja:35) says "Run `uv sync` first".
    combined = result.stdout + result.stderr
    assert "uv sync" in combined or "uv.lock" in combined, (
        "task dev:lite failed (non-zero) but did not emit the expected precondition "
        f"message about uv.lock/uv sync:\n{combined}"
    )


@pytest.mark.skipif(
    not _docker_available() or shutil.which("task") is None,
    reason="uv + docker + go-task required: task dev:lite live-stack exercise",
)
def test_rendered_taskfile_dev_lite_target_drives_stack(tmp_path: Path) -> None:
    # FWK37: `task dev:lite` now runs DETACHED (`up -d --wait`) and prints the stack-is-up
    # summary, then returns. Run it synchronously; assert /health over the ephemeral port AND
    # that the summary names the app at that port. Teardown uses a bare `down -v` (NOT
    # `task dev:down`): the isolate-fixture renames the project via COMPOSE_PROJECT_NAME, which
    # the env carries into a bare `down`, but `dev:down`'s explicit `-p {{slug}}` would override
    # that and tear down the wrong (empty) project, leaking this test's isolated stack.
    import json as _json

    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    env = _compose_env()
    try:
        up = subprocess.run(
            ["task", "dev:lite"],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert up.returncode == 0, f"task dev:lite failed:\n{up.stdout}\n{up.stderr}"
        port = _compose_host_port(dest, [base, dev], "app", 8000)
        with urllib.request.urlopen(
            f"http://localhost:{port}/health", timeout=5
        ) as resp:
            assert resp.status == 200
            body = _json.loads(resp.read())
        assert body["status"] in {"ok", "degraded"}
        # the summary (printed by dev_summary.sh as the 2nd cmd) named the app at this port;
        # stdout carries the Python print() output from dev_summary.sh
        out = up.stdout + up.stderr
        assert "stack is up" in out, f"no summary in task dev:lite output:\n{out}"
        assert f"http://localhost:{port}" in out, (
            f"summary did not show the app at the ephemeral port {port}:\n{out}"
        )
    finally:
        # bare `down -v` with env (carries COMPOSE_PROJECT_NAME from the isolate fixture) → tears
        # down THIS test's isolated stack; -v is correct for a throwaway test stack.
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                base,
                "-f",
                dev,
                "--profile",
                "lite",
                "down",
                "-v",
            ],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
        )


@pytest.mark.skipif(
    not _docker_available() or shutil.which("task") is None,
    reason="uv + docker + go-task required: task db:migrate + db:seed live exercise",
)
def test_rendered_taskfile_db_targets_seed_rows(tmp_path: Path) -> None:
    # M6/FWK25 (live half): no pytest tier calls `task db:migrate` or `task db:seed` — the
    # acceptance tier calls `bash scripts/coverage.sh` (which runs alembic via conftest) and
    # scripts/seed.py is invoked only via entrypoint.sh in the full dev stack. Run the db:
    # targets via `task` against a live compose Postgres, asserting seed rows land. This catches
    # a broken db:seed cwd-from-root (scripts/seed.py path not resolved from dest) or a
    # mis-wired alembic invocation.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    base = "infra/compose/base.yml"
    dev = "infra/compose/dev.yml"
    env = _compose_env()
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "up",
        "-d",
        "postgres",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "down",
        "-v",
    ]
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        pg_port = _compose_host_port(dest, [base, dev], "postgres", 5432)
        db_url = f"postgresql+psycopg://app:app@localhost:{pg_port}/app"
        task_env = {**env, "APP_DATABASE_URL": db_url}

        # Wait for postgres to be ready (healthcheck is pg_isready; poll via psql).
        ready = False
        deadline = time.time() + 90
        while time.time() < deadline:
            r = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    base,
                    "-f",
                    dev,
                    "--profile",
                    "lite",
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-U",
                    "app",
                    "-d",
                    "app",
                    "-c",
                    "SELECT 1",
                ],
                cwd=dest,
                env=env,
                capture_output=True,
            )
            if r.returncode == 0:
                ready = True
                break
            time.sleep(3)
        assert ready, "compose postgres never accepted a psql connection within 90s"

        # task db:migrate — runs `uv run alembic upgrade head` in dest.
        migrate = subprocess.run(
            ["task", "db:migrate"],
            cwd=dest,
            env=task_env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert migrate.returncode == 0, (
            "task db:migrate failed:\n" + migrate.stdout + migrate.stderr
        )

        # task db:seed — runs `uv run python scripts/seed.py` in dest.
        # The M6 risk: if go-task resolves scripts/seed.py from a wrong cwd, it fails here.
        seed = subprocess.run(
            ["task", "db:seed"],
            cwd=dest,
            env=task_env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert seed.returncode == 0, (
            "task db:seed failed (cwd-from-root regression: scripts/seed.py not found, "
            "or alembic migrations not applied first):\n" + seed.stdout + seed.stderr
        )

        # Assert seed rows actually landed in the DB (not just exit 0 from a no-op).
        count_result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                base,
                "-f",
                dev,
                "--profile",
                "lite",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "app",
                "-d",
                "app",
                "-t",
                "-c",
                "SELECT COUNT(*) FROM items;",
            ],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
        )
        assert count_result.returncode == 0, (
            "psql row count query failed:\n" + count_result.stdout + count_result.stderr
        )
        row_count = int(count_result.stdout.strip())
        assert row_count > 0, (
            f"task db:seed exited 0 but left {row_count} rows in the items table — "
            "seed.py ran in the wrong cwd (scripts/seed.py not found relative to dest) "
            "or is silently idempotent-but-empty on a fresh DB"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)


@pytest.mark.skipif(
    not _docker_available()
    or shutil.which("mkcert") is None
    or shutil.which("task") is None,
    reason="docker + mkcert + go-task required (local-only dev-stack tier)",
)
def test_rendered_project_dev_stack_routes_through_traefik(tmp_path: Path):
    # Regression guard for the v3.1->Docker-27 break AND the mkcert cert path (the incident's
    # origin). The --profile dev tests START Traefik but never route THROUGH it; this one does.
    # A *verified* 200 proves the whole chain: `task certs`/mkcert issued a valid cert -> it
    # mounted -> tls.yml loaded it -> Traefik served it for *.localhost and the client TRUSTED
    # it -> AND the docker provider discovered the labeled app and proxied to :8000.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    certs = subprocess.run(["task", "certs"], cwd=dest, capture_output=True, text=True)
    assert certs.returncode == 0, "task certs failed:\n" + certs.stdout + certs.stderr

    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    up = ["docker", "compose", *fargs, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]

    assert subprocess.run(up, cwd=dest, env=_compose_env()).returncode == 0
    try:
        # FWK31 binds Traefik's 443 to an ephemeral host port; discover it.
        https_port = _compose_host_port(dest, files, "traefik", 443)
        host = f"{DATA['project_slug']}.localhost"
        caroot = subprocess.run(
            ["mkcert", "-CAROOT"], capture_output=True, text=True
        ).stdout.strip()
        # Trust ONLY the mkcert CA, so a verified handshake proves Traefik served the real
        # mkcert cert (task certs -> mount -> tls.yml), not a default. We connect to 127.0.0.1
        # directly ({slug}.localhost is not in this host's DNS) and route via the Host header;
        # check_hostname is off because the cert's wildcard SAN *.localhost is browser-valid
        # but OpenSSL won't match it to {slug}.localhost — the CHAIN check is the cert proof.
        ctx = ssl.create_default_context(cafile=str(Path(caroot) / "rootCA.pem"))
        ctx.check_hostname = False
        deadline = time.time() + 120
        body = None
        last_err = "no attempt"
        while time.time() < deadline:
            try:
                raw = socket.create_connection(("127.0.0.1", https_port), timeout=5)
                with ctx.wrap_socket(raw, server_hostname=host) as ssock:
                    ssock.sendall(
                        f"GET /health HTTP/1.1\r\nHost: {host}\r\n"
                        f"Connection: close\r\n\r\n".encode()
                    )
                    data = b""
                    while True:
                        chunk = ssock.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                head, _, payload = data.partition(b"\r\n\r\n")
                status = int(head.split(b"\r\n", 1)[0].split()[1])
                if status == 200:
                    body = json.loads(payload)
                    break
                last_err = f"HTTP {status} via Traefik"
            except (
                OSError
            ) as exc:  # ssl.SSLError (chain) + conn errors while it settles
                last_err = f"{type(exc).__name__}: {exc}"
                time.sleep(3)
        assert body is not None, (
            f"no chain-verified 200 through Traefik within 120s (last: {last_err}) — "
            "docker-provider routing or the mkcert cert chain (task certs/mount/tls.yml) is broken"
        )
        assert body["status"] in {"ok", "degraded"}
        assert "request_latency_p99_ms" in body["slos"]
    finally:
        subprocess.run(down, cwd=dest, env=_compose_env())


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: live dev stack for the Traefik :80 redirect + mongo health",
)
def test_rendered_dev_stack_http_redirect_and_mongo_health(tmp_path: Path) -> None:
    # FWK26 (M1 + M2): the only through-Traefik test connects to :443; nothing connects to :80, so a
    # removed/broken HTTP->HTTPS redirect ships silently. And the mongo COMPOSE service (mongosh-ping
    # healthcheck quoting, mongodata volume, 27017) is never `compose up`-ed — only the testcontainers
    # data-store round-trip is. Bring up ONE dev stack (with the mongodb battery so `mongo:` renders)
    # and assert both: (M1) :80 -> 30x + Location: https://, (M2) mongo container reports healthy +
    # a mongosh client pings. NOTE: no `task certs` / mkcert — the :80 probe is plaintext and we never
    # hit :443.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": resolve(["mongodb"])})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    compose = ["docker", "compose", *fargs, "--profile", "dev"]
    up = [*compose, "up", "-d", "--build", "app", "postgres", "traefik", "mongo"]
    down = [*compose, "down", "-v"]
    env = _compose_env()
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        # ---------- M1: HTTP (:80) redirects to HTTPS ----------
        http_port = _compose_host_port(dest, files, "traefik", 80)
        host = f"{DATA['project_slug']}.localhost"

        # Raw plaintext HTTP/1.1 GET; Traefik's `web` entrypoint redirects (RedirectScheme) BEFORE any
        # backend routing, so the Host header need not match a router — but send the real host anyway.
        def _probe_redirect() -> tuple[int, str]:
            raw = socket.create_connection(("127.0.0.1", http_port), timeout=5)
            try:
                raw.sendall(
                    f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
                )
                data = b""
                while True:
                    chunk = raw.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            finally:
                raw.close()
            head = data.split(b"\r\n\r\n", 1)[0].decode(errors="replace")
            status = int(head.split("\r\n", 1)[0].split()[1])
            location = ""
            for line in head.split("\r\n")[1:]:
                if line.lower().startswith("location:"):
                    location = line.split(":", 1)[1].strip()
            return status, location

        status, location = 0, ""
        deadline = time.time() + 90
        last = "no attempt"
        while time.time() < deadline:
            try:
                status, location = _probe_redirect()
                if status in (301, 302, 307, 308):
                    break
                last = f"HTTP {status} (no redirect)"
            except OSError as exc:  # Traefik still settling
                last = f"{type(exc).__name__}: {exc}"
            time.sleep(3)
        assert status in (301, 302, 307, 308), (
            f"Traefik :80 did not redirect within 90s (last: {last}) — the web->websecure "
            "RedirectScheme entrypoint (infra/traefik/traefik.yml) is broken/removed"
        )
        assert location.startswith("https://"), (
            f"redirect Location is not https:// (got {location!r}) — wrong scheme on the "
            "web entrypoint redirect"
        )

        # ---------- M2: mongo compose service reports healthy + a client connects ----------
        cid = subprocess.run(
            [*compose, "ps", "-q", "mongo"],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert cid, "mongo container id not found (the mongo service did not start)"

        healthy = False
        deadline = time.time() + 90
        while time.time() < deadline:
            state = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", cid],
                capture_output=True,
                text=True,
            ).stdout.strip()
            if state == "healthy":
                healthy = True
                break
            time.sleep(3)
        assert healthy, (
            "mongo compose service never reported healthy within 90s — the mongosh-ping "
            "healthcheck (quoting) or the mongodata volume mount is broken (dev.yml.jinja:83-95)"
        )

        # A client can actually connect+ping through the running service (compose exec, like the
        # FWK20 DLQ/redis queries — no host-side pymongo driver needed).
        ping = subprocess.run(
            [
                *compose,
                "exec",
                "-T",
                "mongo",
                "mongosh",
                "--quiet",
                "--eval",
                "db.adminCommand('ping').ok",
            ],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
        )
        assert ping.returncode == 0 and ping.stdout.strip().endswith("1"), (
            "mongosh ping against the live mongo service did not return ok==1:\n"
            + ping.stdout
            + ping.stderr
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: dev:lite stack to exercise --reload on the bind mount",
)
def test_rendered_dev_lite_hot_reload_picks_up_edit(tmp_path: Path) -> None:
    # FWK26 (M4): every dev/lite test runs uvicorn with --reload + WATCHFILES_FORCE_POLLING=true, but
    # none edits a source file post-startup and asserts the worker reloaded. If polling-reload broke
    # (env removed, inotify dead on the WSL bind mount), every test passes because none re-edits. Bring
    # up dev:lite, GET /heartbeat (=="OK"), edit the rendered heartbeat() to return a sentinel, and
    # poll /heartbeat until the NEW response appears — proving --reload + polling on the bind mount.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "up",
        "-d",
        "--build",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "down",
        "-v",
    ]
    env = _compose_env()
    sentinel = "FWK26-RELOADED-OK"
    health_py = dest / "src" / "demo" / "routes" / "health.py"
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        port = _compose_host_port(dest, [base, dev], "app", 8000)
        url = f"http://localhost:{port}/heartbeat"

        def _get_body() -> str | None:
            try:
                with urllib.request.urlopen(url, timeout=3) as resp:
                    if resp.status == 200:
                        return resp.read().decode()
            except OSError:
                return None
            return None

        # 1) Wait for the ORIGINAL response so the edit is a true post-startup change.
        deadline = time.time() + 90
        original = None
        while time.time() < deadline:
            original = _get_body()
            if original is not None:
                break
            time.sleep(2)
        assert original == "OK", (
            f"app did not serve the original /heartbeat 'OK' within 90s (got {original!r})"
        )

        # 2) Edit the rendered source on the host (bind-mounted into the container).
        src = health_py.read_text()
        assert '"OK"' in src, (
            'the rendered heartbeat route no longer returns the literal "OK" — re-confirm the '
            "mutation target in routes/health.py before relying on this reload test"
        )
        health_py.write_text(src.replace('"OK"', f'"{sentinel}"'))

        # 3) Poll until --reload + WATCHFILES polling restart the worker and serve the sentinel.
        deadline = time.time() + 90
        reloaded = False
        while time.time() < deadline:
            if _get_body() == sentinel:
                reloaded = True
                break
            time.sleep(2)
        assert reloaded, (
            "uvicorn --reload did not pick up the source edit within 90s — "
            "WATCHFILES_FORCE_POLLING / --reload on the bind mount is broken (dev.yml.jinja:9,15)"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
        # Defensive root-residue reclaim: the app runs as the host UID, so nothing root-owned is
        # expected, but reclaim in case a future template change drops the `user:` line (otherwise
        # pytest can't clean tmp_path). Mirrors the no-root tests' alpine chown.
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{dest}:/work",
                "alpine",
                "chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/work",
            ]
        )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: drives the rendered module-level DB engine against a real Postgres",
)
def test_rendered_db_engine_pool_pre_ping_and_dispose(tmp_path: Path) -> None:
    # FWK26 (M14): pool_pre_ping recovery of the REAL module-level engine and real pool disposal are
    # asserted nowhere — conftest builds a SEPARATE test engine and the graceful-shutdown test
    # monkeypatches dispose_engine. Drive the shipped demo.db.engine against a live compose Postgres:
    # terminate the pooled connection's backend, prove the next checkout recovers via pre-ping, then
    # prove dispose_engine() really disposes the pool. Runs inside the rendered project's venv so it
    # imports the project's own module-level engine (not conftest's).
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert (
        subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    )  # need the project venv

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "up",
        "-d",
        "postgres",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "down",
        "-v",
    ]
    env = _compose_env()
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        pg_port = _compose_host_port(dest, [base, dev], "postgres", 5432)
        db_url = f"postgresql+psycopg://app:app@localhost:{pg_port}/app"

        # Wait for postgres to accept connections (its healthcheck is pg_isready; poll a trivial
        # query via the project's psycopg through a tiny driver).
        ready_driver = (
            "import sqlalchemy as sa;"
            "e=sa.create_engine(__import__('os').environ['APP_DATABASE_URL']);"
            "c=e.connect();c.execute(sa.text('SELECT 1'));c.close();print('READY')"
        )
        ready = False
        deadline = time.time() + 90
        while time.time() < deadline:
            r = subprocess.run(
                ["uv", "run", "python", "-c", ready_driver],
                cwd=dest,
                env={**env, "APP_DATABASE_URL": db_url},
                capture_output=True,
                text=True,
            )
            if r.returncode == 0 and "READY" in r.stdout:
                ready = True
                break
            time.sleep(2)
        assert ready, "compose postgres never accepted a connection within 90s"

        # The driver exercises the SHIPPED module-level engine:
        #  1) check out connection c, capture its backend PID; keep c open so the pool can't
        #     reuse it for the killer — if c were returned first, k would get the same PID and
        #     pg_terminate_backend would kill itself (AdminShutdown on k.execute);
        #  2) while c is still open, open a SECOND connection k; pg_terminate_backend(c's PID)
        #     kills the server process behind c; call c.invalidate() to tell SQLAlchemy the
        #     DBAPI connection is dead so the pool discards it on return (instead of trying to
        #     auto-ROLLBACK on context exit and raising AdminShutdown itself);
        #  3) next checkout: pool_pre_ping probes the dead slot, discards it, dials fresh;
        #     SELECT 1 succeeds; new PID != killed PID;
        #  4) dispose_engine(): pool identity changes (SQLAlchemy default close=True replaces pool).
        driver = "\n".join(
            [
                "from sqlalchemy import text",
                "from demo.db.engine import engine, dispose_engine",
                "# 1) checkout c, capture backend PID",
                "c = engine.connect()",
                "pid = c.execute(text('SELECT pg_backend_pid()')).scalar()",
                "# 2) while c is open, kill its backend from a separate connection",
                "with engine.connect() as k:",
                "    k.execute(text('SELECT pg_terminate_backend(:p)'), {'p': pid})",
                "    k.commit()",
                "# invalidate c so the pool discards it cleanly (no auto-ROLLBACK on dead conn)",
                "c.invalidate()",
                "c.close()",
                "# 3) next checkout must transparently reconnect via pool_pre_ping",
                "with engine.connect() as c2:",
                "    assert c2.execute(text('SELECT 1')).scalar() == 1, 'pre-ping did not recover'",
                "    new_pid = c2.execute(text('SELECT pg_backend_pid()')).scalar()",
                "    assert new_pid != pid, 'reused the dead backend — pre-ping did not reconnect'",
                "# 4) real disposal: capture the pool identity, dispose, assert a fresh pool",
                "pool_before = engine.pool",
                "dispose_engine()",
                "assert engine.pool is not pool_before, 'dispose_engine did not recreate the pool'",
                "assert engine.pool.checkedout() == 0, 'connections still checked out after dispose'",
                "print('OK')",
            ]
        )
        result = subprocess.run(
            ["uv", "run", "python", "-c", driver],
            cwd=dest,
            env={**env, "APP_DATABASE_URL": db_url},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0 and result.stdout.strip().endswith("OK"), (
            "the module-level engine pre-ping/dispose driver failed:\n"
            + result.stdout
            + result.stderr
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)


@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live-stack test"
)
def test_rendered_project_dev_stack_prometheus_scrapes_app(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        "infra/compose/observability.yml",
        "-f",
        dev,
        "--profile",
        "dev",
        "up",
        "-d",
        "--build",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        "infra/compose/observability.yml",
        "-f",
        dev,
        "--profile",
        "dev",
        "down",
        "-v",
    ]
    assert subprocess.run(up, cwd=dest, env=_compose_env()).returncode == 0
    try:
        # FWK31 binds prometheus's 9090 to an ephemeral host port; discover it.
        prom_port = _compose_host_port(
            dest, [base, "infra/compose/observability.yml", dev], "prometheus", 9090
        )
        deadline = time.time() + 120
        up_targets = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{prom_port}/api/v1/targets?state=active",
                    timeout=3,
                ) as resp:
                    data = json.loads(resp.read())
                    actives = data.get("data", {}).get("activeTargets", [])
                    app_targets = [
                        t for t in actives if t.get("labels", {}).get("job") == "app"
                    ]
                    if app_targets and app_targets[0].get("health") == "up":
                        up_targets = app_targets
                        break
            except OSError:
                pass
            time.sleep(3)
        assert up_targets, (
            "prometheus did not report the app target healthy within 120s"
        )
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live-stack test"
)
def test_rendered_project_app_logs_reach_loki(tmp_path: Path):
    import urllib.parse

    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        "infra/compose/observability.yml",
        "-f",
        dev,
        "--profile",
        "dev",
        "up",
        "-d",
        "--build",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        "infra/compose/observability.yml",
        "-f",
        dev,
        "--profile",
        "dev",
        "down",
        "-v",
    ]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # FWK31 binds host ports to ephemeral ones; discover the app's and Loki's.
        files = [base, "infra/compose/observability.yml", dev]
        app_port = _compose_host_port(dest, files, "app", 8000)
        loki_port = _compose_host_port(dest, files, "loki", 3100)
        # wait for the app, then generate some log lines (each request is logged)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    f"http://localhost:{app_port}/heartbeat", timeout=3
                ).read()
                break
            except OSError:
                time.sleep(2)
        for _ in range(5):
            try:
                urllib.request.urlopen(
                    f"http://localhost:{app_port}/heartbeat", timeout=3
                ).read()
            except OSError:
                pass
        # poll Loki for the app's logs (ship + ingest has a lag)
        deadline = time.time() + 90
        found = False
        while time.time() < deadline and not found:
            q = urllib.parse.urlencode(
                {
                    "query": '{service="app"}',
                    "limit": "5",
                    "start": str(int((time.time() - 600) * 1e9)),
                }
            )
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{loki_port}/loki/api/v1/query_range?{q}",
                    timeout=5,
                ) as resp:
                    data = json.loads(resp.read())
                    result = data.get("data", {}).get("result", [])
                    if result and any(stream.get("values") for stream in result):
                        found = True
                        break
            except OSError:
                pass
            time.sleep(3)
        assert found, "no app logs reached Loki within the timeout"
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live-stack test"
)
def test_rendered_project_traces_reach_tempo(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        "infra/compose/observability.yml",
        "-f",
        dev,
        "--profile",
        "dev",
        "up",
        "-d",
        "--build",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        "infra/compose/observability.yml",
        "-f",
        dev,
        "--profile",
        "dev",
        "down",
        "-v",
    ]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # FWK31 binds host ports to ephemeral ones; discover the app's and Tempo's.
        files = [base, "infra/compose/observability.yml", dev]
        app_port = _compose_host_port(dest, files, "app", 8000)
        tempo_port = _compose_host_port(dest, files, "tempo", 3200)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    f"http://localhost:{app_port}/heartbeat", timeout=3
                ).read()
                break
            except OSError:
                time.sleep(2)
        for _ in range(5):
            try:
                urllib.request.urlopen(
                    f"http://localhost:{app_port}/heartbeat", timeout=3
                ).read()
            except OSError:
                pass
        deadline = time.time() + 120
        found = False
        while time.time() < deadline and not found:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{tempo_port}/api/search?q=%7Bresource.service.name%3D%22demo%22%7D&limit=1",
                    timeout=5,
                ) as resp:
                    data = json.loads(resp.read())
                    if data.get("traces"):
                        found = True
                        break
            except OSError:
                pass
            time.sleep(4)
        assert found, "no app traces reached Tempo within the timeout"
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv and docker are required for the live obs-stack test",
)
def test_rendered_obs_stack_self_scrape_rules_and_grafana(tmp_path: Path):
    # FWK23 (M10-baseline + M11 + M13): the only live obs test today asserts the `app` scrape
    # target healthy and nothing else — the prometheus/otel-collector self-scrape targets, the
    # alert-rule groups, and the entire Grafana provisioning (datasources/dashboards/anon-auth)
    # are present-but-unasserted. Bring the FULL obs stack up ONCE and assert all three.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    # No service allowlist: bring the whole --profile dev obs stack up (grafana included). dev.yml
    # re-applies grafana's anonymous-admin override (GF_AUTH_ANONYMOUS_*), so M13 anon-auth is live.
    up = ["docker", "compose", *fargs, "--profile", "dev", "up", "-d", "--build"]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        prom_port = _compose_host_port(dest, files, "prometheus", 9090)
        graf_port = _compose_host_port(dest, files, "grafana", 3000)

        # --- M10-baseline: prometheus + otel-collector self-scrape targets up==1 ---
        # (The app target is already covered by the existing test; here assert the self-scrape ones.)
        def _baseline_targets_up(parsed: dict) -> bool:
            actives = parsed.get("data", {}).get("activeTargets", [])
            by_job = {t.get("labels", {}).get("job"): t.get("health") for t in actives}
            return (
                by_job.get("prometheus") == "up"
                and by_job.get("otel-collector") == "up"
            )

        targets = _poll_json(
            f"http://localhost:{prom_port}/api/v1/targets?state=active",
            timeout=120,
            predicate=_baseline_targets_up,
        )
        assert targets is not None, (
            "prometheus/otel-collector self-scrape targets never both reported up==1 within 120s"
        )

        # --- M11: alert rule groups loaded/parsed (no rule-group load error) ---
        # Baseline (no batteries) renders: slo, postgres, otel-collector, prometheus, alertmanager.
        expected_groups = {
            "slo",
            "postgres",
            "otel-collector",
            "prometheus",
            "alertmanager",
        }

        def _rules_loaded(parsed: dict) -> bool:
            groups = parsed.get("data", {}).get("groups", [])
            names = {g.get("name") for g in groups}
            return expected_groups.issubset(names)

        rules = _poll_json(
            f"http://localhost:{prom_port}/api/v1/rules",
            timeout=90,
            predicate=_rules_loaded,
        )
        assert rules is not None, (
            "prometheus did not load all baseline rule groups "
            f"{sorted(expected_groups)} within 90s (a malformed PromQL expr fails the group load)"
        )

        # --- M13: Grafana health (anon), datasources resolve, dashboards provisioned ---
        # anon-admin is on (dev.yml override), so no auth header is needed.
        health = _poll_json(
            f"http://localhost:{graf_port}/api/health",
            timeout=90,
            predicate=lambda p: p.get("database") == "ok",
        )
        assert health is not None, (
            "grafana /api/health never reported database==ok within 90s"
        )

        ds = _poll_json(
            f"http://localhost:{graf_port}/api/datasources",
            timeout=30,
            predicate=lambda p: (
                {d.get("uid") for d in p} >= {"prometheus", "loki", "tempo"}
            ),
        )
        assert ds is not None, (
            "grafana did not provision the prometheus/loki/tempo datasources "
            "(wrong uid or a malformed provisioning yaml)"
        )
        # Datasource upstream health probes — Prometheus and Loki implement /health (returns
        # {"status": "OK"}). The Grafana 11.3.0 Tempo plugin does NOT implement the health
        # endpoint (returns 404 "Method not implemented" regardless of Tempo's status), so we
        # probe Tempo's own /-/ready instead (the otel-collector forwards to it).
        for uid in ("prometheus", "loki"):
            h = _poll_json(
                f"http://localhost:{graf_port}/api/datasources/uid/{uid}/health",
                timeout=60,
                predicate=lambda p: p.get("status") == "OK",
            )
            assert h is not None, (
                f"grafana datasource {uid!r} health probe never returned OK "
                "(the datasource url in provisioning/datasources/*.yml is unreachable/wrong)"
            )
        # Tempo: probe its own /ready endpoint (Grafana 11.3.0 Tempo plugin does not implement
        # the datasource /health API — verified empirically: 404 "Method not implemented").
        tempo_port = _compose_host_port(dest, files, "tempo", 3200)
        # /ready returns plain text "ready", not JSON; use a direct urllib probe.
        tempo_deadline = time.time() + 60
        tempo_ok = False
        while time.time() < tempo_deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{tempo_port}/ready", timeout=5
                ) as r:
                    if b"ready" in r.read():
                        tempo_ok = True
                        break
            except OSError:
                pass
            time.sleep(3)
        assert tempo_ok, (
            "Tempo /ready never returned 'ready' within 60s "
            "(Grafana's Tempo datasource url is http://tempo:3200 — Tempo unreachable)"
        )

        # dashboards: the SLO provider loads the provisioned dashboards from /var/lib/grafana/dashboards.
        search = _poll_json(
            f"http://localhost:{graf_port}/api/search?type=dash-db",
            timeout=60,
            predicate=lambda p: len(p) >= 1,
        )
        assert search is not None, (
            "grafana provisioned no dashboards (the dashboards provider.yml path or the dashboard "
            "JSON failed to load)"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv and docker are required for the live obs-stack test",
)
def test_rendered_obs_exporter_targets_up(tmp_path: Path):
    # FWK23 (M10-batteries): the postgres/redis/celery/mongodb exporter scrape targets are
    # battery-gated AND present-but-unasserted (the baseline live-targets test hard-filters to
    # job=='app'). Render workers+redis+mongodb so ALL FOUR exporters render in one stack, up the
    # obs overlay + the exporters' data deps, and assert each exporter target reports up==1.
    dest = tmp_path / "demo"
    render_project(
        dest, {**DATA, "batteries": resolve(["workers", "redis", "mongodb"])}
    )
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    # Up the scrape source (prometheus) + every exporter + each exporter's data dep. The exporters
    # depend_on their data store HEALTHY (postgres/redis/mongo), so naming the exporters pulls the
    # deps; name them explicitly too for clarity. The app is needed so prometheus's depends_on
    # (service_healthy) is satisfied and the scrape loop runs.
    services = [
        "app",
        "postgres",
        "redis",
        "mongo",
        "prometheus",
        "postgres-exporter",
        "redis-exporter",
        "celery-exporter",
        "mongodb-exporter",
    ]
    up = [
        "docker",
        "compose",
        *fargs,
        "--profile",
        "dev",
        "up",
        "-d",
        "--build",
        *services,
    ]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        prom_port = _compose_host_port(dest, files, "prometheus", 9090)
        # The exporter scrape JOB names in prometheus.yml are: postgres, redis, celery, mongodb.
        expected_jobs = {"postgres", "redis", "celery", "mongodb"}

        def _exporters_up(parsed: dict) -> bool:
            actives = parsed.get("data", {}).get("activeTargets", [])
            up_jobs = {
                t.get("labels", {}).get("job")
                for t in actives
                if t.get("health") == "up"
            }
            return expected_jobs.issubset(up_jobs)

        targets = _poll_json(
            f"http://localhost:{prom_port}/api/v1/targets?state=active",
            timeout=180,
            predicate=_exporters_up,
        )
        assert targets is not None, (
            "not all exporter scrape targets reported up==1 within 180s "
            f"(expected jobs {sorted(expected_jobs)} — a wrong DATA_SOURCE_NAME, a down exporter, "
            "or a wrong telemetry address would leave one down)"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
        # mongo/postgres/redis run as their image users; nothing root-owned is written to the bind
        # mount here (only named volumes), so no chown-reclaim is needed (cf. the worker test, which
        # does need it because worker/beat write the bind-mounted /app). Down -v drops the volumes.


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv and docker are required for the live alertmanager test",
)
def test_rendered_alertmanager_routes_webhook(tmp_path: Path):
    # FWK23 (M12): amtool check-config validates SYNTAX only — no test fires an alert through the
    # real alertmanager.yml and asserts the route/group/receiver actually delivers. Bring up
    # alertmanager with its webhook receiver pointed at a local capture server, POST a firing alert,
    # and assert the capture server received the routed/grouped notification.
    import http.server
    import json as _json
    import threading
    from datetime import datetime, timezone

    dest = tmp_path / "demo"
    render_project(
        dest, DATA
    )  # alert_channels defaults to ["webhook"] -> webhook_configs receiver
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    captured: list[dict] = []

    class _Receiver(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                captured.append(_json.loads(body))
            except ValueError:
                captured.append({"_raw": body.decode(errors="replace")})
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):  # silence the default stderr logging
            pass

    recv_port = _free_tcp_port()
    server = http.server.HTTPServer(("0.0.0.0", recv_port), _Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Mount the webhook_url file (the rendered alertmanager.yml reads `url_file`) and give the
    # container a route back to the host's capture server via host.docker.internal.
    url_file = dest / "infra" / "observability" / "alertmanager" / "webhook_url"
    url_file.write_text(f"http://host.docker.internal:{recv_port}/")
    (dest / "infra" / "compose" / "fwk23.override.yml").write_text(
        "services:\n"
        "  alertmanager:\n"
        "    extra_hosts:\n"
        '      - "host.docker.internal:host-gateway"\n'
        "    volumes:\n"
        '      - "../observability/alertmanager/webhook_url:/etc/alertmanager/webhook_url:ro"\n'
    )
    # Include dev.yml so the services it defines (postgres, redis, traefik …) satisfy the
    # depends_on references inside observability.yml (postgres-exporter depends on postgres,
    # which lives in dev.yml, not base.yml). Only `alertmanager` is actually started.
    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
        "infra/compose/fwk23.override.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    # --profile dev activates the profile-gated services (postgres, redis …) so that
    # observability.yml's depends_on graph resolves cleanly. Only `alertmanager` is actually
    # started (no deps of its own in observability.yml).
    up = ["docker", "compose", *fargs, "--profile", "dev", "up", "-d", "alertmanager"]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        am_port = _compose_host_port(dest, files, "alertmanager", 9093)

        # Wait for alertmanager to be ready (its own /-/ready endpoint).
        ready = _poll_json(
            f"http://localhost:{am_port}/api/v2/status",
            timeout=60,
            predicate=lambda p: bool(p.get("cluster") or p.get("versionInfo")),
        )
        assert ready is not None, "alertmanager never became ready within 60s"

        # POST a firing alert. /api/v2/alerts accepts a JSON array of alerts.
        now = datetime.now(timezone.utc).isoformat()
        alert = [
            {
                "labels": {"alertname": "FWK23ProbeAlert", "severity": "warning"},
                "annotations": {"summary": "fwk23 routing probe"},
                "startsAt": now,
            }
        ]
        req = urllib.request.Request(
            f"http://localhost:{am_port}/api/v2/alerts",
            data=_json.dumps(alert).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status in (200, 202), (
                f"alertmanager rejected the alert POST: {resp.status}"
            )

        # The route's group_wait is 10s; poll the capture server for the routed notification.
        deadline = time.time() + 60
        routed = None
        while time.time() < deadline:
            for note in captured:
                alerts = note.get("alerts", []) if isinstance(note, dict) else []
                if any(
                    a.get("labels", {}).get("alertname") == "FWK23ProbeAlert"
                    for a in alerts
                ):
                    routed = note
                    break
            if routed is not None:
                break
            time.sleep(2)
        assert routed is not None, (
            "alertmanager never routed the firing alert to the webhook receiver within 60s "
            "(a route/group/receiver-wiring regression that stays amtool-valid would do this)"
        )
        # The grouped notification carries the receiver name from the route.
        assert routed.get("receiver") == "default", (
            f"webhook notification routed to an unexpected receiver: {routed.get('receiver')!r}"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
        server.shutdown()


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv and docker are required for the live worker-tracing test",
)
def test_rendered_worker_span_reaches_tempo(tmp_path: Path):
    # FWK23 (M7): the Tempo test is app-only and queries service.name='demo' (shared by app+worker),
    # so a worker-span regression passes silently. Bring up worker + otel-collector + tempo with OTEL
    # enabled, run a Celery task through the LIVE broker, and assert a WORKER/TASK span (the
    # CeleryInstrumentor 'run/<task>' span) reaches Tempo — not just service.name.
    import urllib.parse

    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": resolve(["workers"])})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, obs, dev = (
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    )
    # The dev worker service already sets APP_OTEL_ENABLED=true + the OTLP endpoint (verified in
    # dev.yml.jinja), so OTEL is on with no override.
    files = [base, obs, dev]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    compose = ["docker", "compose", *fargs, "--profile", "dev"]
    # otel-collector forwards to tempo; bring up the worker's data deps + the trace pipeline.
    up = [
        *compose,
        "up",
        "-d",
        "--build",
        "postgres",
        "redis",
        "worker",
        "otel-collector",
        "tempo",
    ]
    down = [*compose, "down", "-v"]
    env = _compose_env()

    def _exec(*argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*compose, "exec", "-T", *argv],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
            check=check,
        )

    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        # worker depends_on postgres+redis healthy; create the schema by hand (the app service,
        # which would migrate, is not started). Mirrors the FWK20 worker bootstrap.
        migrated = False
        deadline = time.time() + 120
        while time.time() < deadline:
            if (
                _exec("worker", "alembic", "upgrade", "head", check=False).returncode
                == 0
            ):
                migrated = True
                break
            time.sleep(3)
        assert migrated, "alembic upgrade head never succeeded in the worker container"

        # Enqueue the shipped heartbeat task through the live redis broker; the worker runs it under
        # CeleryInstrumentor, emitting a 'run/demo.tasks.tasks.heartbeat' span exported to tempo.
        _exec(
            "worker",
            "python",
            "-c",
            "from demo.tasks.tasks import heartbeat; heartbeat.delay()",
        )

        tempo_port = _compose_host_port(dest, files, "tempo", 3200)
        # TraceQL: match a span by name (the celery task span), NOT service.name. URL-encode the
        # query `{ name =~ "run/.*heartbeat.*" }`. (If the worker's celery span name differs,
        # broaden to `{ span.celery.task_name != "" }` — confirm the attribute via a one-off tempo
        # search during the GREEN run.)
        traceql = '{ name =~ "run/.*heartbeat.*" }'
        q = urllib.parse.urlencode({"q": traceql, "limit": "1"})

        found = _poll_json(
            f"http://localhost:{tempo_port}/api/search?{q}",
            timeout=120,
            predicate=lambda p: bool(p.get("traces")),
        )
        assert found is not None, (
            "no WORKER/TASK span reached Tempo within 120s — the celery task span "
            "'run/<task>' is missing (worker OTEL tracing is the M7 surface; an app span alone "
            "would NOT satisfy this name filter)"
        )
    finally:
        subprocess.run(down, cwd=dest, env=env)
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{dest}:/work",
                "alpine",
                "chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/work",
            ]
        )


@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live-stack test"
)
def test_rendered_project_smoke_and_sniff_against_lite(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "up",
        "-d",
        "--build",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "down",
        "-v",
    ]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # FWK31 binds the app's 8000 to an ephemeral host port; discover it.
        port = _compose_host_port(dest, [base, dev], "app", 8000)
        target = f"http://localhost:{port}"
        # wait for /health (seeded lite app)
        deadline = time.time() + 120
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{target}/health", timeout=3) as r:
                    if r.status == 200:
                        ready = True
                        break
            except OSError:
                time.sleep(2)
        assert ready, "lite app did not serve /health within 120s"
        env = {
            **os.environ,
            "SMOKE_TARGET": target,
            "SNIFF_TARGET": target,
        }
        smoke = subprocess.run(
            ["uv", "run", "pytest", "tests/smoke", "-q"], cwd=dest, env=env
        )
        assert smoke.returncode == 0, "smoke suite failed against the live lite stack"
        sniff = subprocess.run(
            ["uv", "run", "pytest", "tests/sniff", "-q"], cwd=dest, env=env
        )
        assert sniff.returncode == 0, "sniff suite failed against the live lite stack"
        e2e = subprocess.run(
            ["uv", "run", "pytest", "tests/e2e", "-q"],
            cwd=dest,
            env={**os.environ, "E2E_TARGET": target},
        )
        assert e2e.returncode == 0, "remote-mode e2e failed against the live lite stack"
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required for this test")
def test_rendered_project_blocks_contract_migration(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    # The scaffold's own migration is safe (reversible + expand-only) -> exit 0.
    clean = subprocess.run(
        ["uv", "run", "python", "scripts/check_migrations.py"], cwd=dest
    )
    assert clean.returncode == 0, (
        "the scaffold's 0001 migration should pass both guards"
    )

    versions = dest / "migrations" / "versions"

    # A destructive (contract) upgrade with NO marker -> blocked (exit 1).
    bad = versions / "9999_drop.py"
    bad.write_text(
        "def upgrade():\n    op.drop_column('items', 'name')\n\n"
        "def downgrade():\n    op.add_column('items', sa.Column('name', sa.String()))\n"
    )
    blocked = subprocess.run(
        ["uv", "run", "python", "scripts/check_migrations.py"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert blocked.returncode == 1, (
        "a contract migration without the marker must be blocked"
    )
    assert "contract" in (blocked.stdout + blocked.stderr).lower()

    # Same migration WITH the acknowledgement marker -> allowed (exit 0).
    bad.write_text(
        "# deploy: contract\n"
        "def upgrade():\n    op.drop_column('items', 'name')\n\n"
        "def downgrade():\n    op.add_column('items', sa.Column('name', sa.String()))\n"
    )
    allowed = subprocess.run(
        ["uv", "run", "python", "scripts/check_migrations.py"], cwd=dest
    )
    assert allowed.returncode == 0, (
        "the '# deploy: contract' marker must exempt the migration"
    )

    bad.unlink()


def test_rendered_project_hybrid_section_integrity(tmp_path):
    from framework_cli.copier_runner import render_project
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version
    from framework_cli.integrity.sections import section_span

    dest = tmp_path / "hyb"
    render_project(
        dest,
        {
            "project_name": "Hyb",
            "project_slug": "hyb",
            "package_name": "hyb",
            "python_version": "3.12",
        },
    )
    write_manifest(dest, installed_framework_version())
    assert check(dest, ci=True) == []

    claude = dest / "CLAUDE.md"
    # Editing OUTSIDE the markers (the builder's area) stays clean — defines "hybrid".
    claude.write_text(
        claude.read_text() + "\n## My project notes\nsome builder content\n"
    )
    assert check(dest, ci=True) == []

    # Editing INSIDE the markers is fatal.
    text = claude.read_text()
    begin, _ = section_span(text)
    lines = text.splitlines()
    lines[begin + 1] = lines[begin + 1] + "  SNEAKY"
    claude.write_text("\n".join(lines) + "\n")
    findings = check(dest, ci=True)
    assert any(f.path == "CLAUDE.md" and f.fatal for f in findings)


def test_rendered_project_integrity_verifies_tamper_and_restore(tmp_path: Path):
    from framework_cli.integrity.generate import write_manifest
    from framework_cli.integrity.manifest import installed_framework_version

    dest = tmp_path / "acc"
    render_project(
        dest,
        {
            "project_name": "Acc",
            "project_slug": "acc",
            "package_name": "acc",
            "python_version": "3.12",
        },
    )
    write_manifest(dest, installed_framework_version())

    # Fresh project verifies clean.
    assert check(dest, ci=True) == []

    # Tampering with a locked file is caught as fatal. (`.pre-commit-config.yaml` is no
    # longer locked — it is hybrid, so appending below the marker is the builder's space;
    # the hybrid tamper/restore path is covered by test_restore_precommit_preserves_builder_hooks.)
    locked = dest / "alembic.ini"
    locked.write_text(locked.read_text() + "\n# sneaky edit\n")
    findings = check(dest, ci=True)
    assert any(f.path == "alembic.ini" and f.fatal for f in findings)

    # Restore returns it to canonical and the project verifies clean again.
    restore_file(dest, "alembic.ini")
    assert check(dest, ci=True) == []


@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live-stack test"
)
def test_rendered_project_dev_stack_serves_seeded_items(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    # `lite` profile = app + postgres only (no Traefik/observability) — app on 8000.
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "up",
        "-d",
        "--build",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "down",
        "-v",
    ]
    assert subprocess.run(up, cwd=dest).returncode == 0
    try:
        # FWK31 binds the app's 8000 to an ephemeral host port; discover it.
        port = _compose_host_port(dest, [base, dev], "app", 8000)
        deadline = time.time() + 120
        items = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}/items", timeout=3
                ) as resp:
                    if resp.status == 200:
                        payload = json.loads(resp.read())
                        if payload:
                            items = payload
                            break
            except OSError:
                pass
            time.sleep(3)
        assert items, "no seeded items served by /items within 120s"
        assert {row["name"] for row in items} >= {"alpha", "beta"}
    finally:
        subprocess.run(down, cwd=dest)


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: the rendered suite runs DB tests against real Postgres",
)
def test_rendered_project_with_graphql_battery_passes(tmp_path: Path):
    # Renders a project with the graphql battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm the GraphQL tests
    # (tests/functional/test_graphql.py) are collected and pass — exercising a query,
    # a createItem mutation, and the introspection-off check against real Postgres.
    data = {**DATA, "batteries": ["graphql"]}
    dest = tmp_path / "demo"
    render_project(dest, data)

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "graphql" / "schema.py").exists(), (
        "graphql/schema.py was not rendered by the graphql battery"
    )
    assert (dest / "src" / "demo" / "routes" / "graphql.py").exists(), (
        "routes/graphql.py was not rendered by the graphql battery"
    )
    assert (dest / "tests" / "functional" / "test_graphql.py").exists(), (
        "tests/functional/test_graphql.py was not rendered by the graphql battery"
    )

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    # Run unit + functional tiers (70% gate) — this collects test_graphql.py and runs
    # it against a real testcontainers Postgres (alembic upgrade head applies the 0001
    # migration). Strawberry runs in the app process; no broker required.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the graphql battery project:\n"
        + result.stdout
        + result.stderr
    )
    # Prove the GraphQL functional tests actually RAN (not just that the files exist).
    # routes/graphql.py is pure module-level wiring, so it hits 100% from autodiscovery
    # import alone — NOT a discriminating signal. graphql/schema.py is: its _to_item,
    # Query.items, and Mutation.create_item resolver bodies plus the disable_introspection
    # branch only reach 100% when the query (success path, introspection off) AND the
    # createItem mutation AND the introspection-off check all execute. So assert on
    # schema.py — it is the real proof the functional suite ran. (returncode==0 on the
    # 70% gate above is the backstop; this pins query+mutation execution specifically.)
    combined_output = result.stdout + result.stderr
    schema_cov_line = next(
        (ln for ln in combined_output.splitlines() if "graphql/schema.py" in ln), ""
    )
    assert "100%" in schema_cov_line, (
        f"GraphQL resolvers not fully exercised; coverage line: {schema_cov_line!r}\n"
        "Expected 100% coverage of graphql/schema.py — were the query + createItem "
        "mutation + introspection-off tests in test_graphql.py collected and did they pass?\n"
        + combined_output
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: real Postgres with pgvector extension",
)
def test_rendered_project_with_pgvector_battery_passes(tmp_path: Path):
    # Renders a project with the pgvector battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm the vectors functional
    # test (tests/functional/test_vectors.py) is collected and passes — exercising the
    # 0004_embeddings migration, add_embedding, and nearest (similarity search) against
    # the custom Postgres image built from infra/docker/postgres.Dockerfile (via DockerImage
    # in the conftest fixture).
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "vectors" / "repository.py").exists(), (
        "vectors/repository.py was not rendered by the pgvector battery"
    )
    assert (dest / "src" / "demo" / "vectors" / "models.py").exists(), (
        "vectors/models.py was not rendered by the pgvector battery"
    )
    assert (dest / "tests" / "functional" / "test_vectors.py").exists(), (
        "tests/functional/test_vectors.py was not rendered by the pgvector battery"
    )
    assert (dest / "migrations" / "versions" / "0004_embeddings.py").exists(), (
        "migrations/versions/0004_embeddings.py was not rendered by the pgvector battery"
    )

    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    # Run unit + functional tiers (70% gate) — alembic upgrade head applies the 0004
    # migration (CREATE EXTENSION vector + embeddings table) on the custom Postgres image
    # built from infra/docker/postgres.Dockerfile, then test_vectors.py inserts two embeddings
    # and asserts that nearest() returns the closer one by cosine distance.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the pgvector battery project:\n"
        + result.stdout
        + result.stderr
    )
    # Prove the vectors functional test actually RAN: vectors/repository.py reaches 100%
    # only when test_vectors.py exercises both add_embedding and nearest against the real DB
    # (import-time alone would yield 0% — these are plain functions, not imported by routes).
    cov = result.stdout + result.stderr
    line = next((ln for ln in cov.splitlines() if "vectors/repository.py" in ln), "")
    assert "100%" in line, (
        f"vectors repo not fully exercised; coverage line: {line!r}\n"
        "Expected 100% coverage of vectors/repository.py — was "
        "tests/functional/test_vectors.py collected and did it pass?\n" + cov
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: builds the AGE Postgres image and runs the live graph test",
)
def test_rendered_age_battery_passes(tmp_path: Path):
    # Renders the age (Apache AGE) battery, runs unit+functional (70% gate) so test_graph.py
    # runs relate()/neighbors() Cypher against the custom Postgres image (AGE + create_graph
    # via the 0006 migration) — proving graph queries work on the built image, not just a spike.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["age"]})
    assert (dest / "src" / "demo" / "graph" / "repository.py").exists()
    assert (dest / "migrations" / "versions" / "0006_graph.py").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the age battery project:\n"
        + result.stdout
        + result.stderr
    )
    cov = result.stdout + result.stderr
    line = next((ln for ln in cov.splitlines() if "graph/repository.py" in ln), "")
    assert "100%" in line, (
        f"graph repo not fully exercised; coverage line: {line!r}\n"
        "Expected 100% of graph/repository.py — did test_graph.py run on the AGE image?\n"
        + cov
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: real Mongo + Postgres",
)
def test_rendered_project_with_mongodb_battery_passes(tmp_path: Path):
    # Renders a project with the mongodb battery active, asserts the battery files
    # were emitted, then runs unit+functional (70% gate) to confirm the mongo functional
    # test (tests/functional/test_mongo.py) is collected and passes — exercising
    # insert_document and find_documents against a real MongoDbContainer("mongo:7").
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["mongodb"]})

    # Battery files must exist in the rendered project.
    assert (dest / "src" / "demo" / "mongo" / "repository.py").exists(), (
        "mongo/repository.py was not rendered by the mongodb battery"
    )
    assert (dest / "src" / "demo" / "mongo" / "client.py").exists(), (
        "mongo/client.py was not rendered by the mongodb battery"
    )
    assert (dest / "tests" / "functional" / "test_mongo.py").exists(), (
        "tests/functional/test_mongo.py was not rendered by the mongodb battery"
    )

    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    # Run unit + functional tiers (70% gate) — test_mongo.py spins up a MongoDbContainer
    # and exercises insert_document + find_documents against a real mongo:7 instance.
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the mongodb battery project:\n"
        + result.stdout
        + result.stderr
    )
    # Prove the mongo functional test actually RAN: mongo/repository.py reaches 100%
    # only when test_mongo.py exercises both insert_document and find_documents against
    # the real DB (import-time alone would yield 0% — these are plain functions, not
    # imported by routes).
    cov = result.stdout + result.stderr
    line = next((ln for ln in cov.splitlines() if "mongo/repository.py" in ln), "")
    assert "100%" in line, (
        f"mongo repo not fully exercised: {line!r}\n"
        "Expected 100% coverage of mongo/repository.py — was "
        "tests/functional/test_mongo.py collected and did it pass?\n" + cov
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: real Postgres with pgvector extension",
)
def test_rendered_project_migration_chain_webhooks_workers_pgvector(tmp_path: Path):
    # Renders a project with webhooks + workers + pgvector batteries, verifies the full
    # migration chain (0001 → 0002 webhook_events → 0003 dead_letter → 0004 embeddings)
    # applies cleanly via alembic upgrade head (driven by the engine fixture in conftest),
    # and the 70% unit+functional gate passes across all three batteries together.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["webhooks", "workers", "pgvector"]})

    # All three battery migration files must be present with the correct chain.
    assert (dest / "migrations" / "versions" / "0002_webhook_events.py").exists(), (
        "0002_webhook_events.py was not rendered"
    )
    assert (dest / "migrations" / "versions" / "0003_dead_letter.py").exists(), (
        "0003_dead_letter.py was not rendered"
    )
    assert (dest / "migrations" / "versions" / "0004_embeddings.py").exists(), (
        "0004_embeddings.py was not rendered"
    )

    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0

    # Run unit + functional tiers (70% gate) — alembic upgrade head walks 0001→0002→0003→0004,
    # so a failure here proves the chain did not apply (the pgvector extension must be available
    # via the custom Postgres image built from infra/docker/postgres.Dockerfile in the conftest fixture).
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "0001->0002->0003->0004 chain did not apply:\n" + result.stdout + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: builds the custom Postgres image and runs the live test stack",
)
def test_rendered_pgvector_builds_extension_image_and_migrates(tmp_path: Path):
    """The pgvector project's Postgres image actually installs `vector`, so the 0004
    CREATE EXTENSION migration succeeds against the BUILT image (not just a prebuilt pull)."""
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector"]})
    assert (dest / "infra" / "docker" / "postgres.Dockerfile").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "pgvector live-build gate failed (CREATE EXTENSION vector on the built image?):\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: builds the TimescaleDB image and runs the live test stack",
)
def test_rendered_timescaledb_battery_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["timescaledb"]})
    assert (dest / "migrations" / "versions" / "0005_readings.py").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "timescaledb gate failed (create_hypertable / time_bucket on the built image?):\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: builds the all-extension Postgres image (pgvector+timescaledb+age)",
)
def test_rendered_all_extensions_chain_passes(tmp_path: Path):
    # The custom image installs pgvector (apt) + timescaledb (multi-stage COPY) + AGE (multi-stage COPY) together,
    # alembic walks 0001->0004(pgvector)->0005(timescaledb)->0006(age create_graph), and all three
    # functional tests (vectors, timeseries, graph) run against the one live image.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["pgvector", "timescaledb", "age"]})
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "all-extensions chain gate failed (pgvector+timescaledb+age on one built image?):\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: real Redis + Postgres",
)
def test_rendered_redis_battery_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["redis"]})
    assert (dest / "src" / "demo" / "cache" / "repository.py").exists()
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for the redis battery project:\n"
        + result.stdout
        + result.stderr
    )
    cov = result.stdout + result.stderr
    line = next((ln for ln in cov.splitlines() if "cache/repository.py" in ln), "")
    assert "100%" in line, (
        f"cache repo not fully exercised; coverage line: {line!r}\n"
        "Expected 100% of cache/repository.py — did test_cache.py run?\n" + cov
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: workers+redis project (mypy on the merged /health + functional)",
)
def test_rendered_workers_redis_battery_passes(tmp_path: Path):
    # The shared redis service + both /health blocks (workers liveness + redis cache ping) must
    # type-check together (regression guard for the _redis alias collision) AND the suite must pass.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers", "redis"]})
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    mypy = subprocess.run(
        ["uv", "run", "mypy", "src"], cwd=dest, capture_output=True, text=True
    )
    assert mypy.returncode == 0, (
        "generated project's mypy failed for workers+redis:\n"
        + mypy.stdout
        + mypy.stderr
    )
    result = subprocess.run(
        ["bash", "scripts/coverage.sh", "70", "unit", "functional"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the 70% unit+functional gate did not pass for workers+redis:\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: builds the react frontend + the prod image",
)
def test_rendered_react_battery_passes(tmp_path: Path):
    import shutil

    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    # `framework new` ships a uv.lock (write_lockfile); mirror that here so the multi-stage
    # Dockerfile's `COPY uv.lock` + `uv sync --frozen` work in the prod image build below.
    from framework_cli.lockfile import write_lockfile

    assert write_lockfile(dest), "uv lock failed in the rendered react project"
    assert (dest / "frontend" / "package.json").exists()
    if shutil.which("npm"):
        assert subprocess.run(["npm", "ci"], cwd=dest / "frontend").returncode == 0
        assert (
            subprocess.run(
                ["npm", "run", "typecheck"], cwd=dest / "frontend"
            ).returncode
            == 0
        )
        assert (
            subprocess.run(["npm", "run", "test"], cwd=dest / "frontend").returncode
            == 0
        )
    # the prod image builds (incl. the frontend-build stage) — proves the SPA build wiring
    build = subprocess.run(
        [
            "docker",
            "build",
            "-f",
            "infra/docker/Dockerfile",
            "-t",
            "demo-react:ci",
            ".",
        ],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, (
        "react app image build failed:\n" + build.stdout + build.stderr
    )
    # H6/FWK21: COPY succeeds whenever the source exists, so a wrong dist path or empty build
    # still builds green. Run the built image and request the served SPA to prove
    # /app/frontend/dist landed and is served by the StaticFiles mount (main.py), not merely
    # that the build exited 0.
    with _run_image_serving("demo-react:ci") as base:
        with urllib.request.urlopen(f"{base}/", timeout=5) as resp:
            body = resp.read().decode()
            assert resp.status == 200, f"served SPA returned {resp.status}, not 200"
            assert 'id="root"' in body, (
                f"served / is not the SPA shell (no root div):\n{body[:500]}"
            )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: pact consumer + provider verification (app over testcontainers Postgres)",
)
def test_rendered_consumers_battery_passes(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["consumers"]})
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    consumer = subprocess.run(
        ["uv", "run", "pytest", "tests/functional/test_consumer_inventory.py", "-q"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert consumer.returncode == 0, (
        "consumer pact test failed:\n" + consumer.stdout + consumer.stderr
    )
    assert (dest / "pacts" / "demo-inventory.json").exists(), (
        "consumer test did not write its pact"
    )
    provider = subprocess.run(
        ["uv", "run", "pytest", "tests/contract/test_provider_pact.py", "-q"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert provider.returncode == 0, (
        "provider verification failed:\n" + provider.stdout + provider.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: validates rendered alertmanager.yml with amtool inside the alertmanager image",
)
def test_alertmanager_config_valid_multichannel(tmp_path: Path):
    # Validates the rendered alertmanager.yml with amtool (webhook+slack+pagerduty).
    # Email is excluded: its ${...} non-secret fields are envsubst'd by the deploy host
    # before mounting — raw ${...} is not valid amtool input.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["webhook", "slack", "pagerduty"]})
    cfg = dest / "infra/observability/alertmanager/alertmanager.yml"
    assert cfg.is_file(), f"alertmanager.yml was not rendered at {cfg}"
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{cfg}:/cfg.yml:ro",
            "--entrypoint",
            "amtool",
            "prom/alertmanager:v0.27.0",
            "check-config",
            "/cfg.yml",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "amtool check-config failed for webhook+slack+pagerduty alertmanager.yml:\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(), reason="uv and docker are required for the live-stack test"
)
def test_rendered_project_dev_lite_stack_leaves_no_root_owned_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "up",
        "-d",
        "--build",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        dev,
        "--profile",
        "lite",
        "down",
        "-v",
    ]
    assert subprocess.run(up, cwd=dest, env=_compose_env()).returncode == 0
    served = False
    try:
        # FWK31 binds the app's 8000 to an ephemeral host port; discover it so the readiness
        # wait (which makes the ownership scan below non-vacuous) actually connects.
        port = _compose_host_port(dest, [base, dev], "app", 8000)
        # let uvicorn import the app + write __pycache__ into the bind-mounted src
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}/health", timeout=3
                ) as resp:
                    if resp.status == 200:
                        served = True
                        break
            except OSError:
                time.sleep(2)
    finally:
        subprocess.run(down, cwd=dest, env=_compose_env())
    # Liveness gate: if the app never served, the ownership scan below would pass vacuously
    # (no container ever wrote into src). Assert the stack actually came up first.
    assert served, (
        "app did not serve /health within 90s — ownership check would be vacuous"
    )
    me = os.getuid()
    bad = [p for p in (dest / "src").rglob("*") if p.stat().st_uid != me]
    assert not bad, f"root/non-host-owned files left behind: {bad[:5]}"


@pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv required to build the rendered project's docs site",
)
def test_rendered_project_docs_battery_builds_strict(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["docs"]})

    assert (dest / "mkdocs.yml").is_file()
    assert (dest / "documentation" / "index.md").is_file()

    sync = subprocess.run(["uv", "sync"], cwd=dest)
    assert sync.returncode == 0, "uv sync failed in the generated project"

    export = subprocess.run(["bash", "scripts/export-openapi.sh"], cwd=dest)
    assert export.returncode == 0, "OpenAPI export failed"
    shutil.copyfile(dest / "openapi.json", dest / "documentation" / "openapi.json")

    build = subprocess.run(
        ["uv", "run", "--group", "docs", "mkdocs", "build", "--strict"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, (
        f"mkdocs --strict build failed:\n{build.stdout}\n{build.stderr}"
    )
    assert (dest / "site" / "index.html").is_file()


def test_frontend_dev_command_uses_npm_ci_not_install(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    dev = (dest / "infra" / "compose" / "dev.yml").read_text()
    assert "npm ci" in dev, (
        "frontend dev command must use `npm ci` (frozen lockfile, no host-bind write)"
    )
    assert "npm install" not in dev, (
        "frontend must not use `npm install` — it rewrites package-lock.json into the host "
        "bind as root"
    )
    # node_modules must stay a named volume so npm's writes never land on the host.
    assert "frontend_node_modules:/app/frontend/node_modules" in dev


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: brings up the workers dev stack to check file ownership",
)
def test_rendered_workers_dev_stack_leaves_no_root_owned_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    # Mirror `task dev`'s real merge order (base + observability + dev). observability.yml
    # supplies grafana's image (dev.yml's grafana is an image-less anonymous-auth override);
    # without it, `--profile dev` config-validation rejects the incomplete grafana service.
    # We only `up` worker/beat (+ their deps), so the obs containers never start.
    obs = "infra/compose/observability.yml"
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        obs,
        "-f",
        dev,
        "--profile",
        "dev",
        "up",
        "-d",
        "--build",
        "worker",
        "beat",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        obs,
        "-f",
        dev,
        "--profile",
        "dev",
        "down",
        "-v",
    ]
    env = _compose_env()
    # Liveness signal: the worker imports the package on startup, writing __pycache__ into
    # the bind-mounted /app/src. Wait for that to appear (proves the scan is non-vacuous).
    pycache = dest / "src" / "demo" / "tasks" / "__pycache__"
    ran = False
    bad: list[Path] = []
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        deadline = time.time() + 120
        while time.time() < deadline:
            if pycache.exists():
                ran = True
                break
            time.sleep(2)
    finally:
        subprocess.run(down, cwd=dest, env=env)
        # Capture ownership state BEFORE reclaiming (so the assertion below is meaningful).
        me = os.getuid()
        bad = [p for p in (dest / "src").rglob("*") if p.stat().st_uid != me]
        # Reclaim any root-owned residue (the red state) so pytest can clean tmp_path.
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{dest}:/work",
                "alpine",
                "chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/work",
            ]
        )
    assert ran, (
        "worker never wrote __pycache__ within 120s — ownership check would be vacuous"
    )
    assert not bad, f"root/non-host-owned files left behind by worker/beat: {bad[:5]}"


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker required: brings the workers dev stack up live to exercise the "
    "broker->worker->DLQ + beat round-trips",
)
def test_rendered_workers_live_broker_dlq_and_beat(tmp_path: Path):
    # FWK20 (H3+H4): every other workers test runs Celery EAGER (task_always_eager=True), so the
    # live broker->worker->DLQ path and beat's live scheduling are exercised by NOTHING. Bring up
    # redis+worker+beat (+postgres) and prove BOTH round-trips end-to-end:
    #   * DLQ: enqueue a deterministically-failing task through the REAL redis broker; the worker
    #     consumes it, exhausts retries, and BaseTask.on_failure writes a dead_letter_tasks row.
    #   * beat: beat schedules the heartbeat task (every 30s) -> the worker runs it -> it writes the
    #     liveness marker in redis, proving beat->broker->worker (stronger than "beat started").
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["workers"]})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0

    # No shipped task fails deterministically (process_async returns None), so inject one. With
    # max_retries=0 the first failure exhausts retries immediately (no backoff wait) -> on_failure
    # -> DLQ. Injected before the build so it is baked into the image (build context = project
    # root) and registered via app.py's `include=[...tasks.tasks...]`.
    tasks_py = dest / "src" / "demo" / "tasks" / "tasks.py"
    tasks_py.write_text(
        tasks_py.read_text()
        + (
            "\n\n"
            "@app.task(base=BaseTask, bind=True, max_retries=0)\n"
            "def _acceptance_boom(self) -> None:\n"
            '    """FWK20 live-broker DLQ probe (test-injected): always fails terminally."""\n'
            '    raise ValueError("boom")\n'
        )
    )

    # Mirror `task dev`'s real merge order (base + observability + dev); observability.yml supplies
    # grafana's image so --profile dev config-validation accepts it. We only `up` the data services
    # + worker + beat, so the obs containers never start (cf. the no-root worker test above).
    base, obs, dev = (
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    )
    compose = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        obs,
        "-f",
        dev,
        "--profile",
        "dev",
    ]
    up = [*compose, "up", "-d", "--build", "postgres", "redis", "worker", "beat"]
    down = [*compose, "down", "-v"]
    env = _compose_env()

    def _exec(*argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        # `docker compose exec -T <argv>`; argv carries any exec flags, the service, and the cmd.
        return subprocess.run(
            [*compose, "exec", "-T", *argv],
            cwd=dest,
            env=env,
            capture_output=True,
            text=True,
            check=check,
        )

    dlq_count = -1
    heartbeat = ""
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        # the worker depends_on postgres+redis HEALTHY, so once the worker container is execable
        # postgres is ready. APP_RUN_MIGRATIONS=false on worker/beat -> create the dead_letter_tasks
        # table by hand (the `app` service, which we don't start, is what normally migrates).
        migrated = False
        deadline = time.time() + 120
        while time.time() < deadline:
            if (
                _exec("worker", "alembic", "upgrade", "head", check=False).returncode
                == 0
            ):
                migrated = True
                break
            time.sleep(3)
        assert migrated, "alembic upgrade head never succeeded in the worker container"

        # DLQ round-trip: enqueue the failing task THROUGH the live redis broker (from inside the
        # worker container, which carries APP_CELERY_BROKER_URL); the worker pool then consumes it.
        _exec(
            "worker",
            "python",
            "-c",
            "from demo.tasks.tasks import _acceptance_boom; _acceptance_boom.delay()",
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            r = _exec(
                "-e",
                "PGPASSWORD=app",
                "postgres",
                "psql",
                "-U",
                "app",
                "-d",
                "app",
                "-tAc",
                "SELECT count(*) FROM dead_letter_tasks",
                check=False,
            )
            if r.returncode == 0 and r.stdout.strip().isdigit():
                dlq_count = int(r.stdout.strip())
                if dlq_count >= 1:
                    break
            time.sleep(2)

        # beat round-trip: beat schedules `heartbeat` (30s) -> worker runs it -> writes the redis
        # liveness key, proving the beat->broker->worker chain (not merely that beat booted).
        deadline = time.time() + 90
        while time.time() < deadline:
            r = _exec("redis", "redis-cli", "GET", "demo:worker:heartbeat", check=False)
            if r.returncode == 0 and r.stdout.strip():
                heartbeat = r.stdout.strip()
                break
            time.sleep(3)
    finally:
        subprocess.run(down, cwd=dest, env=env)
        # worker/beat run as the host UID, but reclaim any residue so pytest can clean tmp_path.
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{dest}:/work",
                "alpine",
                "chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/work",
            ]
        )
    assert dlq_count >= 1, (
        "the failing task never landed in dead_letter_tasks via the live broker->worker->DLQ "
        f"path (last count={dlq_count})"
    )
    assert heartbeat, (
        "beat never drove the heartbeat task through the broker to the worker "
        "(redis liveness marker demo:worker:heartbeat unset)"
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker (+ network for npm ci) required: brings up the frontend dev service",
)
def test_rendered_frontend_dev_stack_leaves_no_root_owned_files(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    # Mirror `task dev`'s merge (base + observability + dev); only `up` the frontend (+deps).
    obs = "infra/compose/observability.yml"
    base, dev = "infra/compose/base.yml", "infra/compose/dev.yml"
    up = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        obs,
        "-f",
        dev,
        "--profile",
        "dev",
        "up",
        "-d",
        "--build",
        "frontend",
    ]
    down = [
        "docker",
        "compose",
        "-f",
        base,
        "-f",
        obs,
        "-f",
        dev,
        "--profile",
        "dev",
        "down",
        "-v",
    ]
    env = _compose_env()
    served = False
    bad: list[Path] = []
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        # FWK31 binds frontend's 5173 to an ephemeral host port; discover it so the
        # readiness wait (which makes the ownership scan non-vacuous) actually connects.
        port = _compose_host_port(dest, [base, obs, dev], "frontend", 5173)
        # npm ci over the network + vite startup; wait for the dev server (non-vacuous).
        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}", timeout=3
                ) as resp:
                    if resp.status == 200:
                        served = True
                        break
            except OSError:
                time.sleep(3)
    finally:
        subprocess.run(down, cwd=dest, env=env)
        # Capture ownership BEFORE reclaiming, so the assertion is meaningful.
        me = os.getuid()
        bad = [p for p in (dest / "frontend").rglob("*") if p.stat().st_uid != me]
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{dest}:/work",
                "alpine",
                "chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/work",
            ]
        )
    assert served, (
        "frontend dev server did not serve on :5173 within 240s — scan would be vacuous"
    )
    assert not bad, f"root/non-host-owned files left in frontend/: {bad[:5]}"


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: brings up two concurrent dev:lite stacks",
)
def test_two_dev_lite_stacks_corun_without_collision(tmp_path: Path):
    """FWK31: two stacks of the same project run at once — distinct compose projects +
    distinct host ports — and tearing one down leaves the other healthy (isolated volumes)."""
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    files = ["infra/compose/base.yml", "infra/compose/dev.yml"]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]

    def up(project: str) -> int:
        # OS-picked free ports per stack — never fixed 8000/5432, which a live consumer
        # stack on this box may already hold (the very scenario FWK31 addresses).
        http_port = _free_tcp_port()
        pg_port = _free_tcp_port()
        env = {
            **_compose_env(),
            "COMPOSE_PROJECT_NAME": project,
            "HTTP_HOST_PORT": str(http_port),
            "POSTGRES_HOST_PORT": str(pg_port),
        }
        assert (
            subprocess.run(
                [
                    "docker",
                    "compose",
                    *fargs,
                    "--profile",
                    "lite",
                    "up",
                    "-d",
                    "--build",
                ],
                cwd=dest,
                env=env,
            ).returncode
            == 0
        ), f"{project} up failed"
        return http_port

    def down(project: str) -> None:
        subprocess.run(
            ["docker", "compose", *fargs, "--profile", "lite", "down", "-v"],
            cwd=dest,
            env={**_compose_env(), "COMPOSE_PROJECT_NAME": project},
        )

    def healthy(port: int) -> bool:
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://localhost:{port}/health", timeout=3
                ) as r:
                    if r.status == 200:
                        return True
            except OSError:
                time.sleep(2)
        return False

    # Both stacks are ALWAYS torn down (once each) on every exit path. `down -v` on an
    # already-removed project is an idempotent no-op, so tearing A down inside the body
    # and again here is harmless.
    try:
        p_a = up("swfwacc-corun-a")
        p_b = up("swfwacc-corun-b")
        assert healthy(p_a) and healthy(p_b), (
            "both stacks must serve /health concurrently"
        )
        down("swfwacc-corun-a")  # tear A down...
        assert healthy(p_b), "B stays healthy after A's down -v (isolated volumes)"
    finally:
        down("swfwacc-corun-a")
        down("swfwacc-corun-b")


@pytest.mark.skipif(
    not _docker_available()
    or shutil.which("mkcert") is None
    or shutil.which("task") is None,
    reason="uv + docker + mkcert + task: live per-battery routes through Traefik",
)
def test_rendered_per_battery_routes_through_traefik(tmp_path: Path) -> None:
    # M8/FWK24: every _passes test asserts routes at ~100% IN-PROCESS (TestClient, LLM mocked) —
    # never on a live compose stack served through Traefik. Render the route-batteries together
    # (fork 1A), bring up app+postgres+traefik, and exercise each route through 127.0.0.1:<traefik
    # 443 ephemeral port> with Host: demo.localhost.
    dest = tmp_path / "demo"
    render_project(
        dest,
        {
            **DATA,
            "batteries": resolve(
                ["websockets", "webhooks", "llm", "graphql", "agents", "react"]
            ),
        },
    )
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    certs = subprocess.run(["task", "certs"], cwd=dest, capture_output=True, text=True)
    assert certs.returncode == 0, "task certs failed:\n" + certs.stdout + certs.stderr

    # Inject a known webhook signing secret via a merge overlay (base.yml hardcodes the app
    # environment; compose merges `environment` maps additively, so this adds without replacing).
    secret = "fwk24-test-secret"
    (dest / "infra" / "compose" / "fwk24.override.yml").write_text(
        "services:\n  app:\n    environment:\n"
        f'      APP_WEBHOOK_SIGNING_SECRET: "{secret}"\n'
    )
    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
        "infra/compose/fwk24.override.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    up = [
        "docker",
        "compose",
        *fargs,
        "--profile",
        "dev",
        "up",
        "-d",
        "--build",
        "app",
        "postgres",
        "traefik",
    ]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    assert subprocess.run(up, cwd=dest, env=env).returncode == 0
    try:
        https_port = _compose_host_port(dest, files, "traefik", 443)
        host = f"{DATA['project_slug']}.localhost"
        ctx = _mkcert_ssl_context()
        # Readiness: poll /health through Traefik until 200 (proves the chain + app up).
        deadline = time.time() + 120
        ready = False
        while time.time() < deadline:
            try:
                st, _ = _traefik_request(https_port, host, ctx, "GET", "/health")
                if st == 200:
                    ready = True
                    break
            except OSError:
                pass
            time.sleep(3)
        assert ready, "app never served /health 200 through Traefik within 120s"

        # websockets: the upgrade negotiates through the proxy (101).
        assert _traefik_ws_upgrade(https_port, host, ctx) == 101, (
            "WS /ws upgrade did not return 101 through Traefik"
        )

        # webhooks: valid HMAC-SHA256(secret, raw body) -> 200; tampered sig -> 401.
        payload = b'{"id": "fwk24-1", "type": "ping"}'
        good = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        st, _ = _traefik_request(
            https_port,
            host,
            ctx,
            "POST",
            "/webhooks",
            headers={"X-Webhook-Signature": good, "Content-Type": "application/json"},
            body=payload,
        )
        assert st == 200, f"signed /webhooks did not return 200 (got {st})"
        st, _ = _traefik_request(
            https_port,
            host,
            ctx,
            "POST",
            "/webhooks",
            headers={
                "X-Webhook-Signature": "deadbeef",
                "Content-Type": "application/json",
            },
            body=payload,
        )
        assert st == 401, f"bad-signature /webhooks did not return 401 (got {st})"

        # graphql: a basic query succeeds (introspection is ON in dev — assert dev behavior; the
        # prod fail-closed off-path is env-derived + unit-covered, not re-tested on this dev stack).
        st, gql = _traefik_request(
            https_port,
            host,
            ctx,
            "POST",
            "/graphql",
            headers={"Content-Type": "application/json"},
            body=b'{"query": "{ __typename }"}',
        )
        assert st == 200 and '"data"' in gql, f"/graphql query failed: {st} {gql[:200]}"

        # llm (fork 2A): no API key -> service raises LLMError -> route 502; the attempt records
        # app_llm_calls_total{outcome="error"} -> assert the series appears on /metrics.
        st, _ = _traefik_request(
            https_port,
            host,
            ctx,
            "POST",
            "/llm/complete",
            headers={"Content-Type": "application/json"},
            body=b'{"prompt": "hi"}',
        )
        assert st == 502, f"/llm/complete (no key) did not return 502 (got {st})"
        st, metrics = _traefik_request(https_port, host, ctx, "GET", "/metrics")
        assert st == 200 and "app_llm_calls_total" in metrics, (
            "app_llm_* series missing from /metrics after a live /llm/complete attempt"
        )

        # agents (fork 2A): LLM-backed (AgentRunner -> LLMService.respond) -> 502/503 with no key,
        # proving the route is mounted + reached on the live ASGI/Traefik path.
        st, _ = _traefik_request(
            https_port,
            host,
            ctx,
            "POST",
            "/agents/run",
            headers={"Content-Type": "application/json"},
            body=b'{"prompt": "hi"}',
        )
        assert st in {502, 503}, f"/agents/run (no key) returned {st}, expected 502/503"
    finally:
        subprocess.run(down, cwd=dest, env=env)


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker: runs the rendered react project's RUM functional test",
)
def test_rendered_react_rum_round_trip(tmp_path: Path) -> None:
    # M9/FWK24: the rendered react project SHIPS tests/functional/test_frontend_rum.py
    # (test_frontend_metrics_round_trip_through_metrics_endpoint: POST /internal/rum -> app_frontend_*
    # on /metrics), but no framework tier runs the react project's python pytest. Run that one test.
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    assert subprocess.run(["uv", "sync"], cwd=dest).returncode == 0
    result = subprocess.run(
        ["uv", "run", "pytest", "tests/functional/test_frontend_rum.py", "-q"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the rendered react RUM round-trip test failed:\n"
        + result.stdout
        + result.stderr
    )


@pytest.mark.skipif(
    not _docker_available(),
    reason="uv + docker (+ npm network): the dev Vite server serves the SPA live",
)
def test_rendered_frontend_dev_server_serves_spa(tmp_path: Path) -> None:
    # FWK24 (re-pointed from H6/FWK21): the dev `frontend` service runs the Vite dev server
    # (`npm ci && npm run dev -- --host`) — brought up by the no-root test but never asserted to
    # SERVE. Up it and GET the Vite port, asserting the SPA shell (id="root").
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "batteries": ["react"]})
    assert subprocess.run(["uv", "lock"], cwd=dest).returncode == 0
    files = [
        "infra/compose/base.yml",
        "infra/compose/observability.yml",
        "infra/compose/dev.yml",
    ]
    fargs: list[str] = []
    for f in files:
        fargs += ["-f", f]
    up = [
        "docker",
        "compose",
        *fargs,
        "--profile",
        "dev",
        "up",
        "-d",
        "--build",
        "frontend",
    ]
    down = ["docker", "compose", *fargs, "--profile", "dev", "down", "-v"]
    env = _compose_env()
    served = ""
    try:
        assert subprocess.run(up, cwd=dest, env=env).returncode == 0
        port = _compose_host_port(dest, files, "frontend", 5173)
        # Vite + `npm ci` take time on first boot; poll for the served shell.
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=3
                ) as resp:
                    if resp.status == 200:
                        served = resp.read().decode()
                        if 'id="root"' in served:
                            break
            except Exception:
                pass
            time.sleep(3)
    finally:
        subprocess.run(down, cwd=dest, env=env)
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{dest}:/work",
                "alpine",
                "chown",
                "-R",
                f"{os.getuid()}:{os.getgid()}",
                "/work",
            ]
        )
    assert 'id="root"' in served, (
        f"the Vite dev server never served the SPA shell within 180s:\n{served[:300]}"
    )


# ---------------------------------------------------------------------------
# L2/FWK28 — load.sh graceful-degradation smoke
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _docker_available(),
    reason="docker required: load.sh wraps grafana/k6 in a Docker container",
)
def test_load_sh_fails_gracefully_without_docker_target(tmp_path: Path) -> None:
    """L2/FWK28 (graceful degradation): load.sh exits non-zero when K6_TARGET is unreachable.

    Scope: this test confirms the script runs (syntax, invocation path) and propagates a
    non-zero exit when k6 cannot reach the target. It does NOT assert the SLO-threshold
    pass/fail with a live app stack — that requires grafana/k6:latest + a running service and
    is logged as an ongoing KNOWN_GAP in the registry (script:scripts/load.sh).

    K6_TARGET is set to a port that is guaranteed not to be listening (free TCP port chosen at
    test time). K6_DURATION is set to "1s" and K6_VUS to "1" to fail fast. The Docker pull of
    grafana/k6:latest is required; the test asserts a k6-emitted marker in the output so that a
    non-zero exit caused by k6 *actually running and failing to reach the target* (the graceful-
    degradation path under test) is distinguishable from one caused by k6 never starting (image
    pull failure / registry outage) — the latter fails the test with a clear message rather than
    passing for the wrong reason.
    """
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    # Pick a port that is not listening.
    unreachable_port = _free_tcp_port()
    target = f"http://127.0.0.1:{unreachable_port}"

    result = subprocess.run(
        ["bash", "scripts/load.sh"],
        cwd=dest,
        capture_output=True,
        text=True,
        env={
            **_compose_env(),
            "K6_TARGET": target,
            "K6_DURATION": "1s",
            "K6_VUS": "1",
        },
        timeout=120,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "load.sh exited 0 on an unreachable target — threshold-propagation broken or "
        "k6 did not actually run\n" + combined
    )
    # Prove k6 genuinely launched and dialed the target (so this is real graceful degradation,
    # not an image-pull failure that never reached the propagation path). k6 logs the dial error
    # on a refused connection and always prints its http_req metric summary.
    assert "connection refused" in combined.lower() or "http_req" in combined, (
        "k6 produced no run output — the image likely failed to pull, so the graceful-degradation "
        "path was never exercised (this test cannot pass on an image-pull failure)\n"
        + combined
    )


# ---------------------------------------------------------------------------
# FWK6 — managed topology live acceptance
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _docker_available(), reason="docker required")
def test_rendered_project_managed_db_boots_without_colocated_postgres(
    tmp_path: Path,
) -> None:
    """FWK6 (live): the managed topology — app with NO co-located postgres and NO depends_on —
    boots and runs migrations against an EXTERNAL postgres reached purely via the injected
    APP_DATABASE_URL. Complements the docker-compose-config topology test with a real boot.

    Proves: entrypoint runs ``alembic upgrade head`` + seed against the external DB (if either
    step fails the container exits before uvicorn starts, so /heartbeat never returns 200).
    """
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    # Mirror what `framework new` does: generate uv.lock on the host so the Dockerfile's
    # `COPY pyproject.toml uv.lock` + `uv sync --frozen` have a lockfile to work with.
    lock = subprocess.run(["uv", "lock"], cwd=dest, capture_output=True, text=True)
    assert lock.returncode == 0, f"uv lock failed:\n{lock.stdout}\n{lock.stderr}"
    port = _free_tcp_port()
    suffix = str(port)
    net = f"fwk6net-{suffix}"
    pg = f"fwk6pg-{suffix}"
    app = f"fwk6app-{suffix}"
    image = f"fwk6-managed-{suffix}:ci"
    try:
        assert (
            subprocess.run(
                ["docker", "network", "create", net], capture_output=True, text=True
            ).returncode
            == 0
        )
        # External postgres — not in any compose stack, reached only by URL over the shared net.
        pg_run = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                pg,
                "--network",
                net,
                "-e",
                "POSTGRES_USER=app",
                "-e",
                "POSTGRES_PASSWORD=app",
                "-e",
                "POSTGRES_DB=app",
                "postgres:17",
            ],
            capture_output=True,
            text=True,
        )
        assert pg_run.returncode == 0, pg_run.stderr
        # Build the project image from the rendered project.
        build = subprocess.run(
            ["docker", "build", "-f", "infra/docker/Dockerfile", "-t", image, "."],
            cwd=dest,
            capture_output=True,
            text=True,
        )
        assert build.returncode == 0, f"docker build failed:\n{build.stderr[-3000:]}"
        # Run the app in the MANAGED shape: external DB via injected URL, migrations ON
        # (the default APP_RUN_MIGRATIONS=true runs alembic + seed before uvicorn).
        ext_url = f"postgresql+psycopg://app:app@{pg}:5432/app"
        app_run = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                app,
                "--network",
                net,
                "-p",
                f"{port}:8000",
                "-e",
                f"APP_DATABASE_URL={ext_url}",
                image,
            ],
            capture_output=True,
            text=True,
        )
        assert app_run.returncode == 0, app_run.stderr
        base = f"http://127.0.0.1:{port}"
        # Allow 90s: postgres init (~5s) + migrate + seed + uvicorn boot.
        deadline = time.time() + 90
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{base}/heartbeat", timeout=3) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                pass
            time.sleep(2)
        if not ready:
            logs = subprocess.run(
                ["docker", "logs", app], capture_output=True, text=True
            )
            raise AssertionError(
                "managed-topology app did not serve /heartbeat in 90s\n"
                f"--- docker logs ---\n{logs.stdout[-3000:]}\n{logs.stderr[-3000:]}"
            )
    finally:
        for name in (app, pg):
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "network", "rm", net], capture_output=True)
