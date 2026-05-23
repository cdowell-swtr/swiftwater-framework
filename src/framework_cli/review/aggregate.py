from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from framework_cli.review.findings import Finding


def write_findings(path: Path, agent: str, conclusion: str, findings: list[Finding]) -> None:
    """Write this agent's result as the lossless JSON the aggregator consumes.

    Called at every terminal path of `framework review` so a skipped/neutral agent still
    produces a file (conclusion set, empty findings) and the aggregator sees the full set.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "agent": agent,
        "conclusion": conclusion,
        "findings": [asdict(f) for f in findings],
    }
    path.write_text(json.dumps(payload, indent=2))
