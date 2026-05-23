from __future__ import annotations

from typing import Any

from framework_cli.review.findings import Finding, parse_findings
from framework_cli.review.registry import AgentSpec

_MAX_DIFF_CHARS = 200_000
_MAX_TOKENS = 4096


def run_agent(diff: str, spec: AgentSpec, client: Any) -> list[Finding]:
    """Call the LLM with `spec`'s prompt over `diff`; return parsed findings.

    The diff is the first system block (a cached prefix shared across agents); the agent
    prompt is the second. `client` is an Anthropic-style client (injected for tests).
    """
    message = client.messages.create(
        model=spec.model,
        max_tokens=_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": f"Review this unified diff:\n\n{diff[:_MAX_DIFF_CHARS]}",
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": spec.prompt},
        ],
        messages=[{"role": "user", "content": "Return your findings as a JSON array only."}],
    )
    text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    return parse_findings(text)


def default_client() -> Any:  # pragma: no cover - thin SDK wrapper, exercised by the manual smoke
    import anthropic

    return anthropic.Anthropic()
