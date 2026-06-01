"""Env-parity guard: every app-image compose service must carry the OTEL env.

The app gets APP_OTEL_* via the observability.yml overlay; worker/beat are defined
in dev.yml + services.yml and must carry the same vars so they export traces in
every environment. Per-file YAML parse — no Docker.
"""

from pathlib import Path

import yaml

from framework_cli.copier_runner import render_project

_OTEL_VARS = {"APP_OTEL_ENABLED", "APP_OTEL_EXPORTER_OTLP_ENDPOINT"}


def _services(path: Path) -> dict:
    return (yaml.safe_load(path.read_text()) or {}).get("services", {})


def test_app_image_services_carry_otel_env(tmp_path):
    root = tmp_path / "proj"
    render_project(
        root,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
            "batteries": ["workers", "redis"],
        },
    )
    # app: OTEL via the observability overlay
    obs = _services(root / "infra/compose/observability.yml")
    assert _OTEL_VARS <= set(obs["app"]["environment"]), "app missing OTEL env"

    # worker + beat: OTEL in BOTH dev.yml and the prod/staging services.yml overlay
    dev = _services(root / "infra/compose/dev.yml")
    svc = _services(root / "infra/compose/services.yml")
    for name in ("worker", "beat"):
        assert _OTEL_VARS <= set(dev[name]["environment"]), f"dev.yml {name} missing OTEL env"
        assert _OTEL_VARS <= set(svc[name]["environment"]), f"services.yml {name} missing OTEL env"
