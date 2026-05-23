from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Fixture:
    agent: str
    kind: Literal["bad", "good"]
    name: str
    diff: str
    seeded_file: str | None  # the path the detection rule matches; set for bad fixtures


def load_fixtures(root: Path) -> list[Fixture]:
    """Discover `<root>/<agent>/{bad,good}/*.diff`. A bad fixture without a valid
    `<slug>.expect.json` (naming the seeded `file`) is skipped — it can't be scored."""
    fixtures: list[Fixture] = []
    for agent_dir in sorted(p for p in root.glob("*") if p.is_dir()):
        agent = agent_dir.name
        for kind in ("bad", "good"):
            for diff_path in sorted((agent_dir / kind).glob("*.diff")):
                try:
                    diff = diff_path.read_text()
                except OSError:
                    continue
                seeded_file: str | None = None
                if kind == "bad":
                    sidecar = diff_path.with_suffix(".expect.json")
                    try:
                        seeded_file = str(json.loads(sidecar.read_text())["file"])
                    except (OSError, json.JSONDecodeError, KeyError, TypeError):
                        continue  # unscoreable bad fixture
                fixtures.append(Fixture(agent, kind, diff_path.stem, diff, seeded_file))
    return fixtures
