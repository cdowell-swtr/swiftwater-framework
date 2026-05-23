from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Literal

from framework_cli.review.findings import Severity

ActiveWhen = Literal["always", "battery", "file-trigger"]

# Latest Sonnet (good cost/quality default; per-agent overridable).
DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    prompt: str
    block_threshold: Severity
    active_when: ActiveWhen
    model: str


def _prompt(name: str) -> str:
    return (files("framework_cli.review") / "agents" / f"{name}.md").read_text()


_SPECS: dict[str, AgentSpec] = {
    "security": AgentSpec(
        name="review-security",
        prompt=_prompt("security"),
        block_threshold="high",
        active_when="always",
        model=DEFAULT_MODEL,
    ),
}


def get_agent(name: str) -> AgentSpec:
    if name not in _SPECS:
        raise KeyError(f"unknown review agent: {name}")
    return _SPECS[name]


def agent_names() -> list[str]:
    return sorted(_SPECS)
