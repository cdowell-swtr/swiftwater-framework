import itertools

from framework_cli.batteries import battery_names
from framework_cli.devmatrix import (
    Combo,
    pairwise_combos,
    representative_combos,
)


def test_combo_with_flags_and_dict():
    c = Combo(name="graphql+react", batteries=("graphql", "react"))
    assert c.with_flags == "--with graphql --with react"
    assert c.alerts_flag == ""
    d = c.as_dict()
    assert d["name"] == "graphql+react"
    assert d["batteries"] == ["graphql", "react"]
    assert d["with_flags"] == "--with graphql --with react"
    assert d["has_react"] is True


def test_baseline_combo_has_empty_flags():
    c = Combo(name="baseline", batteries=())
    assert c.with_flags == ""
    assert c.as_dict()["batteries"] == []
    assert c.as_dict()["has_react"] is False


def test_representative_is_the_documented_set():
    names = [c.name for c in representative_combos()]
    assert names == [
        "baseline",
        "webhooks+workers",
        "graphql+react",
        "mongodb+pgvector",
        "workers+redis",
        "full",
    ]
    full = next(c for c in representative_combos() if c.name == "full")
    assert set(full.batteries) == set(battery_names())
    assert full.alerts_flag == "--alerts webhook,slack,email,pagerduty"


def test_pairwise_covers_every_battery_pair():
    combos = pairwise_combos()
    covered = set()
    for c in combos:
        for a, b in itertools.combinations(c.batteries, 2):
            covered.add(frozenset((a, b)))
    all_pairs = {frozenset(p) for p in itertools.combinations(battery_names(), 2)}
    assert all_pairs <= covered


def test_pairwise_is_deterministic_and_valid():
    assert [c.batteries for c in pairwise_combos()] == [
        c.batteries for c in pairwise_combos()
    ]
    valid = set(battery_names())
    for c in pairwise_combos():
        # every emitted combo is a valid battery set within the declared max size
        assert set(c.batteries) <= valid
        assert len(c.batteries) <= 4
