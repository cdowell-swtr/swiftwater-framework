from pathlib import Path

import yaml

from framework_cli.review.context import assemble
from framework_cli.review.evals import realize_fixture
from framework_cli.review.registry import get_agent

_FIXTURES = Path("tests/eval/fixtures")


def _realize(case: Path, tmp_path: Path):
    batteries = (yaml.safe_load((case / "fixture.yaml").read_text()) or {}).get(
        "batteries", []
    )
    return realize_fixture(
        tmp_path, batteries=batteries, patch=(case / "change.patch").read_text()
    )


def test_observability_is_bundle_strategy():
    assert get_agent("observability").context.strategy == "bundle"


def test_observability_bundle_pulls_obs_subtree(tmp_path: Path):
    spec = get_agent("observability")
    root, diff = _realize(
        _FIXTURES / "observability" / "bad" / "uninstrumented-route", tmp_path
    )
    bundle = assemble(diff, root, spec.context, model=spec.model)
    paths = [p for p, _ in bundle.context_files]
    # The assembler reaches the observability subtree, not just the changed route file.
    assert any(p.endswith("observability/metrics.py") for p in paths)
    assert any(p.endswith("observability/tracing.py") for p in paths)
    # The changed route file (the diff's file) is also present (it matches src/*/routes/*.py).
    assert any(p.endswith("routes/items.py") for p in paths)


def test_observability_good_fixture_applies(tmp_path: Path):
    # The good fixture must render + patch cleanly (proves it's well-formed for Slice D).
    root, diff = _realize(
        _FIXTURES / "observability" / "good" / "instrumented-route", tmp_path
    )
    assert diff.strip()
