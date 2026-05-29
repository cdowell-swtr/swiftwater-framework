from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal

from framework_cli.batteries import get_battery
from framework_cli.review.findings import Severity

ActiveWhen = Literal["always", "battery", "file-trigger"]

# Latest Sonnet (good cost/quality default; per-agent overridable).
DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class ContextPolicy:
    """How much repository context an agent's review call receives.

    - "diff": the unified diff only (legacy behavior; the default).
    - "bundle": diff + full content of changed files + files matching `context_globs`.
    - "agentic": a tool-using loop over the project tree (designed in Slice B).
    `max_context_tokens` overrides the model-window-derived budget when set.
    """

    strategy: Literal["diff", "bundle", "agentic"]
    context_globs: tuple[str, ...] = ()
    max_context_tokens: int | None = None


@dataclass(frozen=True)
class AgentSpec:
    name: str
    prompt: str
    block_threshold: Severity | None  # None = advisory (never blocks)
    active_when: ActiveWhen
    model: str
    on_push: bool = False
    trigger_globs: tuple[str, ...] | None = None
    context: ContextPolicy = ContextPolicy("diff")


def _prompt(name: str) -> str:
    return (files("framework_cli.review") / "agents" / f"{name}.md").read_text()


_SPECS: dict[str, AgentSpec] = {
    "security": AgentSpec(
        name="review-security",
        prompt=_prompt("security"),
        block_threshold="high",
        active_when="always",
        model=DEFAULT_MODEL,
        on_push=True,
        context=ContextPolicy(
            "bundle",
            # The whole package: a security reviewer needs the full attack surface.
            context_globs=("src/*/**/*.py",),
        ),
    ),
    "data-integrity": AgentSpec(
        "review-data-integrity",
        _prompt("data-integrity"),
        "info",
        "always",
        DEFAULT_MODEL,
        on_push=True,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "src/*/db/*.py",
                "migrations/versions/*.py",
            ),
        ),
    ),
    "data-lineage": AgentSpec(
        "review-data-lineage",
        _prompt("data-lineage"),
        "high",
        "always",
        DEFAULT_MODEL,
        on_push=True,
    ),
    "application-logic": AgentSpec(
        "review-application-logic",
        _prompt("application-logic"),
        "info",
        "always",
        DEFAULT_MODEL,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "src/*/routes/*.py",
                "src/*/db/*.py",
            ),
        ),
    ),
    "observability": AgentSpec(
        "review-observability",
        _prompt("observability"),
        "high",
        "always",
        DEFAULT_MODEL,
        on_push=True,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "src/*/observability/*.py",
                "src/*/main.py",
                "src/*/routes/*.py",
            ),
        ),
    ),
    "observability-infra": AgentSpec(
        "review-observability-infra",
        _prompt("observability-infra"),
        "high",
        "file-trigger",
        DEFAULT_MODEL,
        trigger_globs=("infra/*",),
    ),
    "observability-db": AgentSpec(
        "review-observability-db",
        _prompt("observability-db"),
        "high",
        "file-trigger",
        DEFAULT_MODEL,
        trigger_globs=(
            "*/db/*",
            "*/vectors/*",
            "*/mongo/*",
            "*/cache/*",
            "*/timeseries/*",
            "*/graph/*",
            "migrations/*",
        ),
    ),
    "test-quality": AgentSpec(
        "review-test-quality",
        _prompt("test-quality"),
        "high",
        "always",
        DEFAULT_MODEL,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "tests/**/*.py",
                "src/*/**/*.py",
            ),
        ),
    ),
    "architecture": AgentSpec(
        "review-architecture", _prompt("architecture"), "high", "always", DEFAULT_MODEL
    ),
    "performance": AgentSpec(
        "review-performance",
        _prompt("performance"),
        "high",
        "always",
        DEFAULT_MODEL,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "src/*/routes/*.py",
                "src/*/db/*.py",
            ),
        ),
    ),
    "compliance": AgentSpec(
        "review-compliance",
        _prompt("compliance"),
        "high",
        "always",
        DEFAULT_MODEL,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "src/*/routes/*.py",
                "src/*/middleware/*.py",
                "src/*/config/*.py",
            ),
        ),
    ),
    "privacy": AgentSpec(
        "review-privacy", _prompt("privacy"), "high", "always", DEFAULT_MODEL
    ),
    "documentation": AgentSpec(
        "review-documentation",
        _prompt("documentation"),
        None,
        "always",
        DEFAULT_MODEL,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "README.md",
                "docs/**/*.md",
                "src/*/**/*.py",
            ),
        ),
    ),
    "dependency": AgentSpec(
        "review-dependency",
        _prompt("dependency"),
        None,
        "file-trigger",
        DEFAULT_MODEL,
        trigger_globs=(
            "pyproject.toml",
            "uv.lock",
            "package.json",
            "package-lock.json",
        ),
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "pyproject.toml",
                "uv.lock",
            ),
        ),
    ),
    "api-design": AgentSpec(
        "review-api-design", _prompt("api-design"), "high", "battery", DEFAULT_MODEL
    ),
    "contracts": AgentSpec(
        "review-contracts", _prompt("contracts"), "high", "battery", DEFAULT_MODEL
    ),
    "accessibility": AgentSpec(
        "review-accessibility",
        _prompt("accessibility"),
        "high",
        "battery",
        DEFAULT_MODEL,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "frontend/src/**/*.tsx",
                "frontend/src/**/*.ts",
                "frontend/index.html",
            ),
        ),
    ),
    "usability": AgentSpec(
        "review-usability",
        _prompt("usability"),
        None,
        "battery",
        DEFAULT_MODEL,
        context=ContextPolicy(
            "bundle",
            context_globs=(
                "frontend/src/**/*.tsx",
                "frontend/src/**/*.css",
            ),
        ),
    ),
}


def get_agent(name: str) -> AgentSpec:
    if name not in _SPECS:
        raise KeyError(f"unknown review agent: {name}")
    return _SPECS[name]


def agent_names() -> list[str]:
    return sorted(_SPECS)


def active_agents(event: str, batteries: Sequence[str] = ()) -> list[str]:
    """Agent names active for a CI event. On push, the always-on-main subset; on a PR, all
    non-battery agents. A battery in `batteries` additionally activates its `gates_agents` —
    on push only if that agent is itself `on_push` (so the push set stays the curated subset)."""
    gated = {a for b in batteries for a in get_battery(b).gates_agents}
    if event == "push":
        base = {
            k for k, s in _SPECS.items() if s.on_push and s.active_when != "battery"
        }
        battery_extra = {
            k
            for k, s in _SPECS.items()
            if s.active_when == "battery" and s.on_push and k in gated
        }
    else:
        base = {
            k for k, s in _SPECS.items() if s.active_when in ("always", "file-trigger")
        }
        battery_extra = {
            k for k, s in _SPECS.items() if s.active_when == "battery" and k in gated
        }
    return sorted(base | battery_extra)
