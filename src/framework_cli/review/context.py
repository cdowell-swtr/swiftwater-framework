from __future__ import annotations

from dataclasses import dataclass, field  # noqa: F401

# Model context windows (input+output tokens). Unknown models use the default.
_MODEL_CONTEXT_TOKENS: dict[str, int] = {
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-7": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
}
_DEFAULT_CONTEXT_TOKENS = 200_000
_OUTPUT_RESERVE_TOKENS = 4096  # mirrors runner._MAX_TOKENS
_MARGIN_TOKENS = 8_000  # headroom for the prompt + framing + estimate slop
_CHARS_PER_TOKEN = 4  # cheap token estimate; avoids a count-tokens round trip


@dataclass(frozen=True)
class Bundle:
    """The assembled review context: the diff plus optional full-file context."""

    diff: str
    context_files: tuple[
        tuple[str, str], ...
    ] = ()  # (relative path, content), in order
    truncated: bool = False


def context_budget_chars(model: str, *, override_tokens: int | None = None) -> int:
    """The character ceiling for an assembled bundle, derived from the model window.

    Selection (globs + changed files) is the primary control; this is the safety net.
    `override_tokens`, if set, caps the budget but never exceeds the derived ceiling.
    """
    window = _MODEL_CONTEXT_TOKENS.get(model, _DEFAULT_CONTEXT_TOKENS)
    ceiling = window - _OUTPUT_RESERVE_TOKENS - _MARGIN_TOKENS
    tokens = min(override_tokens, ceiling) if override_tokens is not None else ceiling
    return max(tokens, 0) * _CHARS_PER_TOKEN
