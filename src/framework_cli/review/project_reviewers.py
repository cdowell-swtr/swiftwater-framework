"""Discover + register a generated project's OWN review agents (FWK119 — the
consumer half of FWK48).

A generated project can add custom reviewers with **zero framework changes** via a
file convention under `.framework/reviewers/`:

    .framework/reviewers/<name>.md      # the domain prompt (same shape as agents/<name>.md)
    .framework/reviewers/<name>.toml    # block_threshold / active_when / model / trigger_globs / context
    .framework/reviewers/fixtures/<name>/{good,bad}/<case>/change.patch [+ expect.json]

Discovery is pure; registration overlays the specs onto the registry so BOTH
`framework audit --target project` and `reviewer-audit --target project` resolve
them through the existing get_agent/active_agents paths — no extra plumbing. The
audit calibrates them against their own fixtures via FWK118's `--fixtures-root
.framework/reviewers/fixtures`.

**Rookie-free invariant:** a project with no `.framework/reviewers/` directory
behaves exactly as today — discovery returns [] and registration is a no-op.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, cast

from framework_cli.review import registry
from framework_cli.review.registry import (
    DEFAULT_MODEL,
    ActiveWhen,
    AgentSpec,
    ContextPolicy,
)

PROJECT_REVIEWERS_DIR = Path(".framework") / "reviewers"

_NAME_RE = re.compile(r"^[a-z0-9-]+$")
_SEVERITIES = ("critical", "high", "medium", "low", "info")
_ACTIVE_WHEN: tuple[ActiveWhen, ...] = ("always", "battery", "file-trigger")
_STRATEGIES = ("diff", "bundle", "agentic")


def _spec_from_config(name: str, prompt: str, cfg: dict[str, Any]) -> AgentSpec:
    bt = cfg.get("block_threshold")
    if isinstance(bt, str) and bt.strip().lower() in ("", "none", "null"):
        bt = None
    if bt is not None and bt not in _SEVERITIES:
        raise ValueError(
            f"project reviewer {name!r}: block_threshold must be one of "
            f"{_SEVERITIES} or null (got {bt!r})"
        )

    active_when = cfg.get("active_when", "always")
    if active_when not in _ACTIVE_WHEN:
        raise ValueError(
            f"project reviewer {name!r}: active_when must be one of {_ACTIVE_WHEN} "
            f"(got {active_when!r})"
        )

    ctx = cfg.get("context", {}) or {}
    strategy = ctx.get("strategy", "diff")
    if strategy not in _STRATEGIES:
        raise ValueError(
            f"project reviewer {name!r}: context.strategy must be one of "
            f"{_STRATEGIES} (got {strategy!r})"
        )
    context = ContextPolicy(
        strategy=cast("Any", strategy),
        context_globs=tuple(ctx.get("globs", ()) or ()),
    )

    globs = cfg.get("trigger_globs")
    return AgentSpec(
        name=name,
        prompt=prompt,
        block_threshold=cast("Any", bt),
        active_when=cast("ActiveWhen", active_when),
        model=str(cfg.get("model", DEFAULT_MODEL)),
        trigger_globs=tuple(globs) if globs else None,
        context=context,
        framework_only=False,
    )


def discover_project_reviewers(root: Path) -> list[AgentSpec]:
    """Parse every `.framework/reviewers/<name>.md` (+ optional `<name>.toml`) under
    `root` into an AgentSpec. Pure — no registry mutation. Returns [] when the
    directory is absent (the rookie-free no-op)."""
    rdir = root / PROJECT_REVIEWERS_DIR
    if not rdir.is_dir():
        return []
    specs: list[AgentSpec] = []
    for md in sorted(rdir.glob("*.md")):
        name = md.stem
        if name.startswith("_"):
            continue  # idea-stage drafts, mirroring the framework's `_proposed-` convention
        if not _NAME_RE.match(name):
            raise ValueError(
                f"project reviewer file {md.name!r}: name must match ^[a-z0-9-]+$"
            )
        toml_f = md.with_suffix(".toml")
        cfg = tomllib.loads(toml_f.read_text()) if toml_f.exists() else {}
        specs.append(_spec_from_config(name, md.read_text(), cfg))
    return specs


def register_project_reviewers(root: Path) -> list[str]:
    """Overlay the project's discovered reviewers onto the registry so the existing
    get_agent/active_agents/agent_names paths resolve them. Idempotent for an
    identical spec (safe to call once per command, even if re-entered); a name that
    collides with a DIFFERENT existing agent (a built-in) is a loud error — never a
    silent shadow."""
    names: list[str] = []
    for spec in discover_project_reviewers(root):
        existing = registry._SPECS.get(spec.name)
        if existing is not None and existing != spec:
            raise ValueError(
                f"project reviewer {spec.name!r} collides with an existing review "
                "agent; rename it (built-in agent names are reserved)"
            )
        registry._SPECS[spec.name] = spec
        names.append(spec.name)
    return names
