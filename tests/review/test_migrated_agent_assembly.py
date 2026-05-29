from pathlib import Path

import pytest
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


# ---------------------------------------------------------------------------
# Parametrized: every migrated bundle agent assembles domain context
# ---------------------------------------------------------------------------

_BUNDLE_AGENTS = {
    "observability": [],
    "application-logic": [],
    "performance": [],
    "data-integrity": [],
    "security": [],
    "compliance": [],
    "test-quality": [],
    "documentation": [],
    "dependency": [],
    "accessibility": ["react"],
    "usability": ["react"],
}


def _first_bad_case(agent: str) -> Path:
    bad = _FIXTURES / agent / "bad"
    cases = sorted(
        p for p in bad.glob("*") if p.is_dir() and (p / "change.patch").is_file()
    )
    assert cases, f"{agent}: no rendered-project bad fixture"
    return cases[0]


@pytest.mark.parametrize("agent", sorted(_BUNDLE_AGENTS))
def test_bundle_agent_assembles_domain_context(agent, tmp_path):
    spec = get_agent(agent)
    assert spec.context.strategy == "bundle"
    case = _first_bad_case(agent)
    batteries = (yaml.safe_load((case / "fixture.yaml").read_text()) or {}).get(
        "batteries", []
    )
    root, diff = realize_fixture(
        tmp_path, batteries=batteries, patch=(case / "change.patch").read_text()
    )
    bundle = assemble(diff, root, spec.context, model=spec.model)
    assert bundle.context_files, f"{agent}: empty bundle"
    rels = {p for p, _ in bundle.context_files}
    # The bundle must reach the agent's declared glob domain. Resolve the globs the same
    # way the assembler does (root.glob — correct for `**`, unlike fnmatch) and require a
    # non-empty intersection with the assembled files.
    domain = {
        str(p.relative_to(root))
        for g in spec.context.context_globs
        for p in root.glob(g)
        if p.is_file()
    }
    assert rels & domain, (
        f"{agent}: no context file in glob domain {spec.context.context_globs}; got {sorted(rels)}"
    )
