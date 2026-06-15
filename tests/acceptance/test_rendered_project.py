import json
import os
import shutil
import subprocess
import time
import urllib.request
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
        # app is published on 8000 in the `lite` profile (no Traefik)
        deadline = time.time() + 90
        body = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    "http://localhost:8000/health", timeout=3
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
        deadline = time.time() + 120
        up_targets = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    "http://localhost:9090/api/v1/targets?state=active", timeout=3
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
        # wait for the app, then generate some log lines (each request is logged)
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://localhost:8000/heartbeat", timeout=3
                ).read()
                break
            except OSError:
                time.sleep(2)
        for _ in range(5):
            try:
                urllib.request.urlopen(
                    "http://localhost:8000/heartbeat", timeout=3
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
                    f"http://localhost:3100/loki/api/v1/query_range?{q}", timeout=5
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
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    "http://localhost:8000/heartbeat", timeout=3
                ).read()
                break
            except OSError:
                time.sleep(2)
        for _ in range(5):
            try:
                urllib.request.urlopen(
                    "http://localhost:8000/heartbeat", timeout=3
                ).read()
            except OSError:
                pass
        deadline = time.time() + 120
        found = False
        while time.time() < deadline and not found:
            try:
                with urllib.request.urlopen(
                    "http://localhost:3200/api/search?q=%7Bresource.service.name%3D%22demo%22%7D&limit=1",
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
        # wait for /health (seeded lite app)
        deadline = time.time() + 120
        ready = False
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    "http://localhost:8000/health", timeout=3
                ) as r:
                    if r.status == 200:
                        ready = True
                        break
            except OSError:
                time.sleep(2)
        assert ready, "lite app did not serve /health within 120s"
        env = {
            **os.environ,
            "SMOKE_TARGET": "http://localhost:8000",
            "SNIFF_TARGET": "http://localhost:8000",
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
            env={**os.environ, "E2E_TARGET": "http://localhost:8000"},
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
        deadline = time.time() + 120
        items = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    "http://localhost:8000/items", timeout=3
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
        # let uvicorn import the app + write __pycache__ into the bind-mounted src
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    "http://localhost:8000/health", timeout=3
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
        # npm ci over the network + vite startup; wait for the dev server (non-vacuous).
        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://localhost:5173", timeout=3) as resp:
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
