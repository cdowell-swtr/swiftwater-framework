"""FWK90 — per-mutation test-selection logic (the pure `select_targets`).

These exercise the inner-loop accelerator's *selection*, not its runner: given the set of
changed repo-relative paths, which fast-tier pytest targets to run (or the `FULL` sentinel).
Pure path logic + a read of the on-disk eval fixtures — runs in the framework venv / fast tier.
"""

from __future__ import annotations

from scripts.affected_tests import (
    FULL,
    TEMPLATE_GUARDS,
    fixture_anchored_paths,
    select_targets,
)

EVALS = "tests/review/test_evals.py"


def test_framework_module_selects_its_test_file():
    assert select_targets(["src/framework_cli/source.py"]) == ["tests/test_source.py"]


def test_framework_subpackage_selects_its_test_area():
    assert select_targets(["src/framework_cli/integrity/restore.py"]) == [
        "tests/integrity/"
    ]


def test_review_subpackage_selects_review_area():
    assert select_targets(["src/framework_cli/review/agents/security.md"]) == [
        "tests/review/"
    ]


def test_changed_test_file_selects_itself():
    assert select_targets(["tests/test_naming.py"]) == ["tests/test_naming.py"]


def test_template_edit_anchored_by_a_fixture_pulls_evals():
    # `.env.example.jinja` renders to `.env.example`, which a fixture's change.patch anchors on
    # (the FWK100 motivating bug). The widen must pull test_evals.py into scope.
    targets = select_targets(["src/framework_cli/template/.env.example.jinja"])
    assert targets != FULL
    assert EVALS in targets
    assert set(TEMPLATE_GUARDS).issubset(set(targets))


def test_template_edit_not_anchored_runs_guards_without_evals():
    # `Taskfile.yml.jinja` renders to `Taskfile.yml`, which no fixture anchors on.
    targets = select_targets(["src/framework_cli/template/Taskfile.yml.jinja"])
    assert targets != FULL
    assert set(TEMPLATE_GUARDS).issubset(set(targets))
    assert EVALS not in targets


def test_doc_only_change_selects_nothing():
    assert select_targets(["PLAN.md", "ACTION_LOG.md", "docs/x/y.md"]) == []


def test_unknown_path_widens_to_full():
    assert select_targets(["some/unmapped/thing.xyz"]) == FULL


def test_module_without_a_test_file_widens_to_full():
    # __init__.py has no `tests/test___init__.py` — fail safe to FULL, never silently drop it.
    assert select_targets(["src/framework_cli/__init__.py"]) == FULL


def test_multi_path_change_takes_the_union():
    targets = select_targets(["src/framework_cli/source.py", "tests/test_naming.py"])
    assert targets == ["tests/test_naming.py", "tests/test_source.py"]


def test_full_is_absorbing():
    # Any unknown path forces FULL even alongside a perfectly-mapped one.
    assert select_targets(["src/framework_cli/source.py", "weird.xyz"]) == FULL


def test_fixture_anchor_parser_resolves_real_fixtures():
    # Meta-guard: the change.patch parser must keep finding real anchors — if it silently
    # rotted to an empty set, the whole template->fixture widen would quietly stop firing.
    anchored = fixture_anchored_paths()
    assert ".env.example" in anchored
    assert "src/demo/routes/items.py" in anchored
    assert len(anchored) > 10
