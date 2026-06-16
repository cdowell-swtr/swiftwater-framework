from __future__ import annotations

import json
import re
import shutil
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
    batteries: tuple[str, ...]
    patch: str
    seeded_file: str | None  # new-side path the detection matches; set for bad


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


# Agents whose review target is the framework SOURCE (template payload + the FWK29 registry),
# not a rendered project. Their fixtures realize a framework-shaped base, not a render.
_FRAMEWORK_SHAPED_AGENTS = frozenset({"coverage-gap"})

# Repo subtrees a framework-shaped fixture needs (relative to the framework repo root).
_FRAMEWORK_SUBTREES = ("src/framework_cli/template", "tests/runtime_coverage")


def _framework_repo_root() -> Path:
    # evals.py lives at <root>/src/framework_cli/review/evals.py
    return Path(__file__).resolve().parents[3]


def _framework_base(base: Path) -> None:
    """Populate `base` with a minimal framework-shaped tree and an initial git commit."""
    root = _framework_repo_root()
    for sub in _FRAMEWORK_SUBTREES:
        src = root / sub
        dst = base / sub
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
    subprocess.run(["git", "init", "-q"], cwd=base, check=True)
    subprocess.run(
        ["git", "config", "gc.auto", "0"], cwd=base, check=True
    )  # GC race guard
    subprocess.run(["git", "add", "-A"], cwd=base, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=base,
        check=True,
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


def realize_cached(
    fx: Fixture, cache: dict[tuple[str, ...], Path], base_dir: Path
) -> tuple[Path, str]:
    """Realize `fx` reusing a per-combo rendered+committed base. `base_dir` is a
    caller-owned tempdir; `cache` maps battery-combo → committed base path.

    For framework-shaped agents (e.g. coverage-gap), the base is a copy of the
    framework's own source subtrees (template payload + FWK29 registry) rather than
    a rendered project.
    """
    if fx.agent in _FRAMEWORK_SHAPED_AGENTS:
        cache_key: tuple[str, ...] = ("__framework__",)
        if cache_key not in cache:
            base = base_dir / "framework-base"
            base.mkdir(parents=True, exist_ok=True)
            _framework_base(base)
            cache[cache_key] = base
        work = base_dir / f"fx-{fx.agent}-{fx.kind}-{fx.name}"
        shutil.copytree(cache[cache_key], work)
        subprocess.run(
            ["git", "apply", "-"], cwd=work, input=fx.patch, text=True, check=True
        )
        # Stage so newly-added files (a new operational surface — exactly what coverage-gap
        # hunts) appear in the seed diff, matching production pr_diff() which shows committed
        # new files. A bare `git diff` would omit untracked additions.
        subprocess.run(["git", "add", "-A"], cwd=work, check=True)
        diff = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=work,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return work, diff

    if fx.batteries not in cache:
        base = base_dir / ("base-" + ("-".join(fx.batteries) or "none")) / "demo"
        render_project(base, {**_FIXTURE_ANSWERS, "batteries": list(fx.batteries)})
        subprocess.run(["git", "init", "-q"], cwd=base, check=True)
        subprocess.run(["git", "add", "-A"], cwd=base, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-qm",
                "base",
            ],
            cwd=base,
            check=True,
        )
        cache[fx.batteries] = base
    work = base_dir / f"fx-{fx.agent}-{fx.kind}-{fx.name}"
    shutil.copytree(cache[fx.batteries], work)
    subprocess.run(
        ["git", "apply", "-"], cwd=work, input=fx.patch, text=True, check=True
    )
    diff = subprocess.run(
        ["git", "diff"], cwd=work, capture_output=True, text=True, check=True
    ).stdout
    return work, diff


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def validate_patch_hunks(patch: str) -> list[str]:
    """Return a list of error strings for any unified-diff hunk whose declared
    line counts disagree with its body. An empty list means well-formed.

    Catches the truncation class: a `@@ -a,b +c,d @@` header where `b` != (context
    + removed) or `d` != (context + added) makes `git apply` silently truncate.
    """
    errors: list[str] = []
    lines = patch.splitlines()
    i = 0
    while i < len(lines):
        m = _HUNK_RE.match(lines[i])
        if not m:
            i += 1
            continue
        header = lines[i]
        old_decl = int(m.group(2)) if m.group(2) is not None else 1
        new_decl = int(m.group(4)) if m.group(4) is not None else 1
        i += 1
        ctx = rem = add = 0
        while i < len(lines):
            ln = lines[i]
            if ln == "":  # blank context line (whitespace-stripped " ")
                ctx += 1
                i += 1
                continue
            if ln.startswith("\\"):  # "\ No newline at end of file"
                i += 1
                continue
            if ln.startswith("--- ") or ln.startswith("+++ "):
                break  # file header — end of this hunk's body
            if ln.startswith("+"):
                add += 1
            elif ln.startswith("-"):
                rem += 1
            elif ln.startswith(" "):
                ctx += 1
            else:
                # Any other leading char (@@, "diff --git", "index", "new file
                # mode", "Binary files", …) ends the hunk body. Without this,
                # the inter-file separators of a multi-file diff are miscounted
                # as context lines of the preceding hunk (a +2-per-extra-file bug).
                break
            i += 1
        if ctx + rem != old_decl or ctx + add != new_decl:
            errors.append(
                f"{header}: declared (-{old_decl},+{new_decl}) but body has "
                f"old={ctx + rem}, new={ctx + add}"
            )
    return errors


def load_fixtures(root: Path) -> list[Fixture]:
    """Discover rendered-project fixtures (lazy — no render here):
    `<root>/<agent>/{bad,good}/<case>/{fixture.yaml,change.patch[,expect.json]}`.
    A bad case missing a valid `expect.json` (naming the seeded `file`) is skipped."""
    import yaml

    fixtures: list[Fixture] = []
    for agent_dir in sorted(p for p in root.glob("*") if p.is_dir()):
        agent = agent_dir.name
        for kind in ("bad", "good"):
            for case in sorted(p for p in (agent_dir / kind).glob("*") if p.is_dir()):
                patch_f, spec_f = case / "change.patch", case / "fixture.yaml"
                if not (patch_f.is_file() and spec_f.is_file()):
                    continue
                batteries = tuple(
                    (yaml.safe_load(spec_f.read_text()) or {}).get("batteries", [])
                )
                seeded_file: str | None = None
                if kind == "bad":
                    try:
                        seeded_file = str(
                            json.loads((case / "expect.json").read_text())["file"]
                        )
                    except (OSError, json.JSONDecodeError, KeyError, TypeError):
                        continue
                fixtures.append(
                    Fixture(
                        agent,
                        kind,
                        case.name,
                        batteries,
                        patch_f.read_text(),
                        seeded_file,
                    )
                )
    return fixtures
