from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Literal

from framework_cli.copier_runner import render_project
from framework_cli.review.findings import Finding, severity_rank
from framework_cli.review.registry import AgentSpec


@dataclass(frozen=True)
class Fixture:
    agent: str
    kind: Literal["bad", "good"]
    name: str
    diff: str
    seeded_file: str | None  # the path the detection rule matches; set for bad fixtures


def flags(findings: list[Finding], spec: AgentSpec, *, file: str | None = None) -> bool:
    """True if the agent raised a blocking concern, optionally restricted to `file`.

    Blocking agent (`block_threshold` set): a finding at/above the threshold. Advisory agent
    (`block_threshold is None` — never blocks in production): any finding counts as 'surfaced',
    so its evals score detection on surfacing rather than blocking.
    """
    for f in findings:
        if file is not None and f.path != file:
            continue
        if spec.block_threshold is None or severity_rank(f.severity) >= severity_rank(
            spec.block_threshold
        ):
            return True
    return False


@dataclass(frozen=True)
class Thresholds:
    recall_min: float
    fp_max: float


DEFAULT_THRESHOLDS = Thresholds(recall_min=0.67, fp_max=0.34)


def load_thresholds(path: Path) -> dict[str, Thresholds]:
    """Parse the optional per-agent threshold override file; missing file → {}."""
    if not path.is_file():
        return {}
    import yaml

    data = yaml.safe_load(path.read_text()) or {}
    result: dict[str, Thresholds] = {}
    for agent, v in data.items():
        try:
            result[agent] = Thresholds(float(v["recall_min"]), float(v["fp_max"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"thresholds.yaml: agent {agent!r} needs numeric recall_min and fp_max"
            ) from exc
    return result


@dataclass(frozen=True)
class AgentScore:
    agent: str
    recall: float
    fp_rate: float
    bad_total: int
    good_total: int
    passed: bool
    reason: str  # empty when passed


def score_agent(
    agent: str,
    bad_detect_rates: list[float],
    good_block_rates: list[float],
    thr: Thresholds,
) -> AgentScore:
    """Set-level recall/precision. Each rate is a per-fixture hit fraction (hits/repeat)."""
    recall = mean(bad_detect_rates) if bad_detect_rates else 1.0
    fp_rate = mean(good_block_rates) if good_block_rates else 0.0
    reasons: list[str] = []
    # Compare at the 2dp the scorecard prints, so e.g. 2/3=0.667 clears a 0.67 gate.
    if round(recall, 2) < thr.recall_min:
        reasons.append(f"recall {recall:.2f} < {thr.recall_min:.2f}")
    if round(fp_rate, 2) > thr.fp_max:
        reasons.append(f"fp {fp_rate:.2f} > {thr.fp_max:.2f}")
    return AgentScore(
        agent,
        recall,
        fp_rate,
        len(bad_detect_rates),
        len(good_block_rates),
        not reasons,
        "; ".join(reasons),
    )


_FIXTURE_ANSWERS = {
    "project_name": "Demo",
    "project_slug": "demo",
    "package_name": "demo",
    "python_version": "3.12",
}


def realize_fixture(
    dest: Path, *, batteries: list[str], patch: str
) -> tuple[Path, str]:
    """Render the template into `dest`, apply `patch`, and return (project root, diff).

    The render is a real generated project, so the same assembler used in production runs
    against it. The patch is the seeded bad/good change; the returned diff is what the
    review sees. `dest` must be an empty directory the caller owns (e.g. a tmp_path).
    """
    root = dest / "demo"
    render_project(root, {**_FIXTURE_ANSWERS, "batteries": batteries})
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "apply", "-"], cwd=root, input=patch, text=True, check=True)
    diff = subprocess.run(
        ["git", "diff"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    return root, diff


def load_fixtures(root: Path) -> list[Fixture]:
    """Discover `<root>/<agent>/{bad,good}/*.diff`. A bad fixture without a valid
    `<slug>.expect.json` (naming the seeded `file`) is skipped here; the well-formedness
    gate test fails loudly on a malformed fixture rather than relying on a runtime warning."""
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
