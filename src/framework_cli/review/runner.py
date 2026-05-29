from __future__ import annotations

from typing import Any

from framework_cli.review.context import Bundle
from framework_cli.review.findings import Finding, parse_findings
from framework_cli.review.registry import AgentSpec

_MAX_TOKENS = 4096


def run_agent(bundle: Bundle, spec: AgentSpec, client: Any) -> list[Finding]:
    """Call the LLM with `spec`'s prompt over an assembled `bundle`; return findings.

    System blocks, in cache-prefix order: (1) the diff — identical across agents on the
    same target, so its cache prefix is shared; (2) optional per-agent context files; (3)
    the agent prompt. A diff-only bundle omits block 2, byte-identical to the legacy call.
    """
    system: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": f"Review this unified diff:\n\n{bundle.diff}",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if bundle.context_files:
        joined = "\n\n".join(
            f"=== {path} ===\n{content}" for path, content in bundle.context_files
        )
        note = "\n\n[context truncated to fit the budget]" if bundle.truncated else ""
        system.append(
            {
                "type": "text",
                "text": f"Relevant repository files for context:\n\n{joined}{note}",
                "cache_control": {"type": "ephemeral"},
            }
        )
    system.append({"type": "text", "text": spec.prompt})

    message = client.messages.create(
        model=spec.model,
        max_tokens=_MAX_TOKENS,
        system=system,
        messages=[
            {"role": "user", "content": "Return your findings as a JSON array only."}
        ],
    )
    text = "".join(
        block.text
        for block in message.content
        if getattr(block, "type", None) == "text"
    )
    return parse_findings(text)


def default_client() -> Any:  # pragma: no cover - thin SDK wrapper
    import anthropic

    return anthropic.Anthropic()
