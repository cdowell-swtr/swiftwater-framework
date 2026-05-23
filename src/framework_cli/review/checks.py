from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

from framework_cli.review.findings import Finding, severity_rank
from framework_cli.review.registry import AgentSpec

# GitHub annotation_level per severity.
_LEVEL = {
    "critical": "failure",
    "high": "failure",
    "medium": "warning",
    "low": "notice",
    "info": "notice",
}
_MAX_ANNOTATIONS = 50  # GitHub Checks API limit per request


@dataclass(frozen=True)
class CheckRunPayload:
    name: str
    conclusion: str  # "success" | "neutral" | "failure"
    title: str
    summary: str
    annotations: list[dict] = field(default_factory=list)


def to_check_run(spec: AgentSpec, findings: list[Finding]) -> CheckRunPayload:
    if spec.block_threshold is None:
        # Advisory agent — findings are surfaced but never block.
        blocking: list[Finding] = []
    else:
        threshold = severity_rank(spec.block_threshold)
        blocking = [f for f in findings if severity_rank(f.severity) >= threshold]
    conclusion = "success" if not findings else ("failure" if blocking else "neutral")
    annotations = [
        {
            "path": f.path,
            "start_line": f.line,
            "end_line": f.line,
            "annotation_level": _LEVEL[f.severity],
            "title": f"{spec.name}: {f.severity}",
            "message": f.message + (f"\n\nSuggestion: {f.suggestion}" if f.suggestion else ""),
        }
        for f in findings[:_MAX_ANNOTATIONS]
    ]
    summary = "No findings." if not findings else f"{len(findings)} finding(s); {len(blocking)} blocking."
    return CheckRunPayload(spec.name, conclusion, f"{spec.name}: {conclusion}", summary, annotations)


def neutral_payload(name: str, reason: str) -> CheckRunPayload:
    return CheckRunPayload(name, "neutral", f"{name}: skipped", reason, [])


def post_check_run(payload: CheckRunPayload, *, token: str, repo: str, sha: str) -> None:
    """Post the Check Run via the `gh` CLI (available on GitHub runners)."""
    body = json.dumps(
        {
            "name": payload.name,
            "head_sha": sha,
            "status": "completed",
            "conclusion": payload.conclusion,
            "output": {"title": payload.title, "summary": payload.summary, "annotations": payload.annotations},
        }
    )
    subprocess.run(
        ["gh", "api", f"repos/{repo}/check-runs", "--method", "POST", "--input", "-"],
        input=body,
        text=True,
        check=True,
        capture_output=True,
        env={**os.environ, "GH_TOKEN": token},
    )


def post_or_skip(payload: CheckRunPayload, *, token: str, repo: str, sha: str) -> None:
    """Post if we have GitHub context; never raise (posting failure must not block CI)."""
    if not (token and repo and sha):
        return
    try:
        post_check_run(payload, token=token, repo=repo, sha=sha)
    except Exception:  # noqa: BLE001 - posting failure is non-fatal by design
        pass
