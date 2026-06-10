from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from framework_cli.review.agentic import DEFAULT_MAX_TURNS, run_agent_agentic
from framework_cli.review.backend import BackendExhausted
from framework_cli.review.checkpoint import append_record, init_run, pending_items
from framework_cli.review.context import assemble
from framework_cli.review.decisions import relevant_decisions
from framework_cli.review.runner import run_agent


@dataclass(frozen=True)
class EngineItem:
    agent: str
    diff: str
    spec: Any
    review_mode: str = "snapshot"
    base_sha: str | None = None
    base_baseline: str | None = None


@dataclass
class EngineResult:
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    exhausted: bool = False
    reset_hint: str | None = None
    records: list[dict[str, Any]] = field(default_factory=list)


def _failure_record(item: EngineItem, exc: Exception) -> dict[str, Any]:
    """A record for an item whose dispatch failed (non-exhaustion). Carries empty
    findings + an `error` marker; the usage/turns/etc. defaults keep the finalizers'
    int-sums and field reads from crashing on it."""
    return {
        "agent": item.agent,
        "spec_name": item.spec.name,
        "findings": [],
        "review_mode": item.review_mode,
        "base_sha": item.base_sha,
        "base_baseline": item.base_baseline,
        "usage": {},
        "latency_ms": None,
        "stop_reason": "error",
        "raw_text": "",
        "turns": 0,
        "tool_calls": [],
        "error": f"{type(exc).__name__}: {exc}",
    }


def _run_one(item: EngineItem, backend: Any, root: Path) -> dict[str, Any]:
    spec = item.spec
    report: dict[str, Any] = {}
    if spec.context.strategy == "agentic":
        turns = spec.context.max_agentic_turns or DEFAULT_MAX_TURNS
        findings = run_agent_agentic(
            item.diff,
            root,
            spec,
            backend,
            max_turns=turns,
            report=report,
            decisions=tuple(relevant_decisions(item.agent, root)),
        )
    else:
        bundle = assemble(
            item.diff, root, spec.context, model=spec.model, agent=item.agent
        )
        findings = run_agent(bundle, spec, backend, report=report)
    return {
        "agent": item.agent,
        "spec_name": spec.name,
        "findings": [asdict(f) for f in findings],
        "review_mode": item.review_mode,
        "base_sha": item.base_sha,
        "base_baseline": item.base_baseline,
        "usage": report.get("usage", {}),
        "latency_ms": report.get("latency_ms"),
        "stop_reason": report.get("stop_reason"),
        "raw_text": report.get("raw_text", ""),
        "turns": report.get("turns", 1),
        "tool_calls": report.get("tool_calls", []),
    }


def run_engine(
    items: list[EngineItem],
    *,
    backend: Any,
    run_dir: Path,
    root: Path,
    git_sha: str,
    dirty_hash: str,
    backend_name: str,
    resume: bool = False,
) -> EngineResult:
    """Iterate items → dispatch via the unified loop → checkpoint each record as it
    completes. On BackendExhausted, stop scheduling and return what completed."""
    if not resume:
        init_run(
            run_dir,
            planned=[i.agent for i in items],
            git_sha=git_sha,
            dirty_hash=dirty_hash,
            backend=backend_name,
        )
    todo = set(pending_items(run_dir))
    result = EngineResult()
    for item in items:
        if item.agent not in todo:
            continue
        try:
            record = _run_one(item, backend, root)
        except BackendExhausted as exc:
            result.exhausted = True
            result.reset_hint = exc.reset_hint
            break
        except Exception as exc:  # noqa: BLE001 — one-off item failure: record it, keep going
            record = _failure_record(item, exc)
            append_record(run_dir, item.agent, record)
            result.failed.append(item.agent)
            result.records.append(record)
            continue
        append_record(run_dir, item.agent, record)
        result.completed.append(item.agent)
        result.records.append(record)
    return result
