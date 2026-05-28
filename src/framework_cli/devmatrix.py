from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from framework_cli.batteries import battery_names

_ALL_CHANNELS = ("webhook", "slack", "email", "pagerduty")


@dataclass(frozen=True)
class Combo:
    """One render-matrix entry: a battery set + optional alert channels."""

    name: str
    batteries: tuple[str, ...]
    alerts: tuple[str, ...] = ()

    @property
    def with_flags(self) -> str:
        return " ".join(f"--with {b}" for b in self.batteries)

    @property
    def alerts_flag(self) -> str:
        return f"--alerts {','.join(self.alerts)}" if self.alerts else ""

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "batteries": list(self.batteries),
            "with_flags": self.with_flags,
            "alerts_flag": self.alerts_flag,
            "has_react": "react" in self.batteries,
        }


def _name_for(batteries: tuple[str, ...]) -> str:
    return "+".join(batteries) if batteries else "baseline"


def representative_combos() -> list[Combo]:
    """The fixed, fast PR set — one per known interaction class (spec section 5.3)."""
    return [
        Combo("baseline", ()),
        Combo("webhooks+workers", ("webhooks", "workers")),
        Combo("graphql+react", ("graphql", "react")),
        Combo("mongodb+pgvector", ("mongodb", "pgvector")),
        Combo("workers+redis", ("redis", "workers")),
        Combo("full", tuple(battery_names()), _ALL_CHANNELS),
    ]


def pairwise_combos(max_size: int = 4) -> list[Combo]:
    """Greedy all-pairs: every battery pair co-occurs in at least one combo."""
    names = battery_names()
    uncovered = {frozenset(p) for p in itertools.combinations(names, 2)}
    combos: list[Combo] = []
    while uncovered:
        seed = min(uncovered, key=lambda p: sorted(p))
        chosen = list(sorted(seed))
        while len(chosen) < max_size:
            best: str | None = None
            best_gain = 0
            for c in names:
                if c in chosen:
                    continue
                gain = sum(frozenset((c, x)) in uncovered for x in chosen)
                if gain > best_gain:
                    best, best_gain = c, gain
            if best is None:
                break
            chosen.append(best)
        chosen = sorted(chosen)
        for a, b in itertools.combinations(chosen, 2):
            uncovered.discard(frozenset((a, b)))
        combos.append(Combo(_name_for(tuple(chosen)), tuple(chosen)))
    return combos


def sample_combos(seed: int, n: int) -> list[Combo]:
    """N distinct pseudo-random battery subsets, deterministic for `seed`."""
    rng = random.Random(seed)
    names = battery_names()
    seen: set[tuple[str, ...]] = set()
    combos: list[Combo] = []
    attempts = 0
    while len(combos) < n and attempts < n * 50:
        attempts += 1
        k = rng.randint(1, len(names))
        subset = tuple(sorted(rng.sample(names, k)))
        if subset in seen:
            continue
        seen.add(subset)
        combos.append(Combo(_name_for(subset), subset))
    return combos


def broad_combos(seed: int, sample_size: int = 6) -> list[Combo]:
    """The pairwise floor plus a seeded random rotation (spec section 5.3)."""
    floor = pairwise_combos()
    floor_sets = {c.batteries for c in floor}
    extra = [
        c for c in sample_combos(seed, sample_size) if c.batteries not in floor_sets
    ]
    return floor + extra


def combos_for_strategy(
    strategy: str, *, seed: int = 0, sample_size: int = 6
) -> list[Combo]:
    """Dispatch to the named combo strategy; seed/sample_size apply to sample & broad."""
    if strategy == "representative":
        return representative_combos()
    if strategy == "pairwise":
        return pairwise_combos()
    if strategy == "sample":
        return sample_combos(seed, sample_size)
    if strategy == "broad":
        return broad_combos(seed, sample_size)
    raise ValueError(f"unknown strategy: {strategy!r}")
