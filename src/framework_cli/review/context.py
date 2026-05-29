from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from framework_cli.review.diff import changed_files
from framework_cli.review.registry import ContextPolicy

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


@dataclass(frozen=True)
class ReviewTarget:
    """A review target. The ONLY target-specific artifact: the runner/assembler are blind to it."""

    root: Path
    active: tuple[str, ...] = field(
        default_factory=tuple
    )  # agent names active for this target


def generated_project_target(root: Path, active: tuple[str, ...]) -> ReviewTarget:
    """The shipped-use target: a checked-out generated project at `root`."""
    return ReviewTarget(root=root, active=tuple(active))


# The review agents applicable to the framework's OWN CLI/tooling source (a Python
# Copier-wrapper CLI). App-domain agents (observability*, api-design, contracts,
# accessibility, usability, data-integrity, privacy, compliance, performance) don't apply.
FRAMEWORK_AGENTS: tuple[str, ...] = (
    "application-logic",
    "architecture",
    "dependency",
    "documentation",
    "security",
    "test-quality",
)


def framework_target(root: Path) -> ReviewTarget:
    """The dogfooding target: the framework repo reviews its own source. Every applicable
    agent runs agentic-for-all (see the CLI's --target framework path)."""
    return ReviewTarget(root=root, active=FRAMEWORK_AGENTS)


def assemble(diff: str, root: Path, policy: ContextPolicy, *, model: str) -> Bundle:
    """Assemble the review bundle for `policy` against the tree at `root`.

    Priority order under the budget: the diff (always), then full content of changed
    files, then files matching `context_globs`. On overflow we stop adding and mark the
    bundle truncated — the diff is never dropped.
    """
    if policy.strategy != "bundle":
        return Bundle(diff=diff)

    budget = context_budget_chars(model, override_tokens=policy.max_context_tokens)
    used = len(diff)
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(rel: str) -> None:
        if rel not in seen:
            seen.add(rel)
            ordered.append(rel)

    for rel in changed_files(diff):
        _add(rel)
    for pattern in policy.context_globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                _add(str(path.relative_to(root)))

    files: list[tuple[str, str]] = []
    truncated = False
    for rel in ordered:
        fp = root / rel
        if not fp.is_file():
            continue
        content = fp.read_text(errors="replace")
        if used + len(content) > budget:
            truncated = True
            break  # respect priority: stop rather than skip-ahead to smaller files
        files.append((rel, content))
        used += len(content)

    return Bundle(diff=diff, context_files=tuple(files), truncated=truncated)
