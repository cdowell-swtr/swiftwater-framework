from __future__ import annotations

import os
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from framework_cli.review.context import Bundle
from framework_cli.review.findings import Finding, parse_findings
from framework_cli.review.registry import AgentSpec
from framework_cli.review.request import build_review_request

_MAX_TOKENS = 4096


def _usage_dict(resp: Any) -> dict[str, int]:
    u = getattr(resp, "usage", None)
    return {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0)
        or 0,
    }


def run_agent(
    bundle: Bundle, spec: AgentSpec, client: Any, *, report: dict | None = None
) -> list[Finding]:
    """Call the LLM with `spec`'s prompt over an assembled `bundle`; return findings.

    System blocks, in cache-prefix order: (1) the diff — identical across agents on the
    same target, so its cache prefix is shared; (2) optional per-agent context files; (3)
    the agent prompt. A diff-only bundle omits block 2, byte-identical to the legacy call.
    """
    req = build_review_request(bundle, spec, root=Path.cwd())

    t0 = perf_counter()
    message = client.messages.create(
        model=req.model,
        max_tokens=_MAX_TOKENS,
        system=req.system,
        messages=[{"role": "user", "content": req.user_message}],
    )
    text = "".join(
        block.text
        for block in message.content
        if getattr(block, "type", None) == "text"
    )
    if report is not None:
        report["usage"] = _usage_dict(message)
        report["latency_ms"] = int((perf_counter() - t0) * 1000)
        report["stop_reason"] = getattr(message, "stop_reason", None)
        report["raw_text"] = text
        report["turns"] = 1
        report["tool_calls"] = []
    return parse_findings(text)


EVAL_KEY_ENV = "ANTHROPIC_EVAL_API_KEY"
RUNTIME_KEY_ENV = "ANTHROPIC_RUNTIME_API_KEY"

# The Anthropic SDK default is 2 retries. Reviews (eval + the `framework review`
# builder path) fire large-context agents back-to-back and burst over a tight
# per-minute input-token (ITPM) tier, returning 429. Give the SDK a larger retry
# budget so it absorbs those transient rate limits via its exponential backoff
# (which respects the Retry-After header, self-pacing under the limit) instead of
# hard-aborting. A genuinely sustained failure still propagates once exhausted.
DEFAULT_MAX_RETRIES = 8  # ~minutes of backoff ceiling; absorbs a ~169% ITPM burst
# Upper bound: a misconfigured huge value would back off for hours/days, masking a
# sustained outage instead of absorbing a transient burst.
MAX_RETRIES_CAP = 20


def _warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr, flush=True)


def _max_retries() -> int:
    """Anthropic client retry budget, from ``ANTHROPIC_MAX_RETRIES``.

    Falls back to ``DEFAULT_MAX_RETRIES`` for an unset/invalid/non-positive value
    and clamps anything above ``MAX_RETRIES_CAP`` — warning (to stderr) on the
    misconfigured cases so an ignored override is visible rather than silent.
    """
    raw = os.environ.get("ANTHROPIC_MAX_RETRIES", "").strip()
    if not raw:  # unset/empty — normal path, use the default silently
        return DEFAULT_MAX_RETRIES
    try:
        n = int(raw)
    except ValueError:
        _warn(
            f"ignoring non-integer ANTHROPIC_MAX_RETRIES={raw!r}; "
            f"using default {DEFAULT_MAX_RETRIES}"
        )
        return DEFAULT_MAX_RETRIES
    if n <= 0:  # 0/negative would disable retries — defeats the backoff purpose
        _warn(
            f"ANTHROPIC_MAX_RETRIES={n} would disable retry backoff; "
            f"using default {DEFAULT_MAX_RETRIES}"
        )
        return DEFAULT_MAX_RETRIES
    if n > MAX_RETRIES_CAP:
        _warn(
            f"ANTHROPIC_MAX_RETRIES={n} exceeds the cap; clamping to {MAX_RETRIES_CAP}"
        )
        return MAX_RETRIES_CAP
    return n


def default_client(api_key_env: str) -> Any:
    import anthropic

    return anthropic.Anthropic(
        api_key=os.environ.get(api_key_env), max_retries=_max_retries()
    )
