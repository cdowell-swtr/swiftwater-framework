import itertools

import pytest

from framework_cli.batteries import battery_names
from framework_cli.devmatrix import (
    Combo,
    broad_combos,
    combos_for_strategy,
    pairwise_combos,
    representative_combos,
    sample_combos,
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
        "multitenantauth",
        "multitenantauth+workers",
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


def test_sample_is_deterministic_for_a_seed():
    assert [c.batteries for c in sample_combos(seed=7, n=5)] == [
        c.batteries for c in sample_combos(seed=7, n=5)
    ]


def test_sample_differs_across_seeds():
    a = [c.batteries for c in sample_combos(seed=1, n=8)]
    b = [c.batteries for c in sample_combos(seed=2, n=8)]
    assert a != b


def test_sample_yields_n_distinct_valid_combos():
    combos = sample_combos(seed=3, n=6)
    assert len(combos) == 6
    seen = {c.batteries for c in combos}
    assert len(seen) == 6  # distinct
    for c in combos:
        assert all(b in battery_names() for b in c.batteries)


def test_broad_is_pairwise_floor_plus_sample():
    broad = broad_combos(seed=5, sample_size=4)
    floor = {c.batteries for c in pairwise_combos()}
    broad_sets = {c.batteries for c in broad}
    assert floor <= broad_sets  # pairwise floor always present
    assert len(broad_sets) > len(floor)  # the random rotation actually added combos


def test_combos_for_strategy_dispatch():
    assert [c.name for c in combos_for_strategy("representative")] == [
        c.name for c in representative_combos()
    ]
    assert [c.batteries for c in combos_for_strategy("pairwise")] == [
        c.batteries for c in pairwise_combos()
    ]
    assert [
        c.batteries for c in combos_for_strategy("sample", seed=9, sample_size=3)
    ] == [c.batteries for c in sample_combos(seed=9, n=3)]
    assert [
        c.batteries for c in combos_for_strategy("broad", seed=9, sample_size=3)
    ] == [c.batteries for c in broad_combos(seed=9, sample_size=3)]
    with pytest.raises(ValueError, match="unknown strategy"):
        combos_for_strategy("nonsense")
