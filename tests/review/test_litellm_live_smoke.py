"""Live end-to-end smoke for the LiteLLM backend seam (Plan 27, Task 7).

These exercise the REAL transports through the new litellm seam — the only thing
that catches the ``MAX_ARG_STRLEN`` / large-input-via-stdin class and real prompt
caching (mocks cannot). Both are gated behind ``RUN_LIVE_SMOKE=1``.

- ``test_live_subagent_large_input`` drives the full
  ``litellm.anthropic_messages(model="claude-cli/...")`` → ``ClaudeCliLLM`` →
  ``claude -p`` path with a >128 KB diff. It uses the local ``claude`` CLI
  subscription, so it needs NO API key — only the CLI on PATH.
- ``test_live_api_caching`` drives the ``anthropic/`` provider and asserts a cache
  hit on a repeated call; it additionally needs ``ANTHROPIC_EVAL_API_KEY``.
"""

from __future__ import annotations

import os
import shutil

import pytest

from framework_cli.review.context import Bundle
from framework_cli.review.registry import get_agent
from framework_cli.review.runner import run_agent

_LIVE = os.environ.get("RUN_LIVE_SMOKE") == "1"

# A diff comfortably over Linux MAX_ARG_STRLEN (~128 KB) so the system/diff content
# MUST travel via the temp file + stdin, never as an argv element.
_BIG_DIFF = "diff --git a/pad.py b/pad.py\n--- a/pad.py\n+++ b/pad.py\n" + (
    "+# padding line to exceed the 128KB single-arg limit\n" * 4000
)


@pytest.mark.skipif(
    not _LIVE or shutil.which("claude") is None,
    reason="live subagent smoke: set RUN_LIVE_SMOKE=1 with the `claude` CLI on PATH",
)
def test_live_subagent_large_input() -> None:
    """Full subscription path must survive a >128 KB diff and return parseable findings."""
    from framework_cli.review.backend import SubagentBackend

    assert len(_BIG_DIFF) > 131072, "diff must exceed MAX_ARG_STRLEN to be a real test"
    findings = run_agent(
        Bundle(diff=_BIG_DIFF), get_agent("security"), SubagentBackend()
    )
    assert isinstance(
        findings, list
    )  # did not blow up on argv length; produced findings


@pytest.mark.skipif(
    not _LIVE or not os.environ.get("ANTHROPIC_EVAL_API_KEY"),
    reason="live api caching smoke: set RUN_LIVE_SMOKE=1 with ANTHROPIC_EVAL_API_KEY",
)
def test_live_api_caching() -> None:
    """The anthropic/ provider must return a cache hit on a repeated identical call."""
    from framework_cli.review.backend import ApiBackend

    backend = ApiBackend(api_key=os.environ["ANTHROPIC_EVAL_API_KEY"])
    spec = get_agent("security")
    bundle = Bundle(diff=_BIG_DIFF)
    rep1: dict = {}
    rep2: dict = {}
    run_agent(bundle, spec, backend, report=rep1)
    run_agent(bundle, spec, backend, report=rep2)
    assert rep2["usage"]["cache_read_input_tokens"] > 0, (
        f"expected a cache hit on the repeat call; got usage {rep2.get('usage')!r}"
    )
