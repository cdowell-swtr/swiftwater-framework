"""Enumeration rules for FWK29 — extract canonical operational-surface keys from a
rendered project tree. Closed-world: only the surface classes with a rule here are
enumerated; in-app code paths are deliberately NOT covered (see registry.py docstring).
"""

import re
from pathlib import Path

import yaml

_COMPOSE_DIR = Path("infra/compose")
_DOCKER_DIR = Path("infra/docker")
_SCRIPT_DIRS = (Path("scripts"), Path("infra/deploy"))
_WORKFLOWS_DIR = Path(".github/workflows")
_PRECOMMIT = Path(".pre-commit-config.yaml")
_CLAUDE_HOOKS_DIR = Path(".claude/hooks")

_FROM_AS = re.compile(r"^FROM\s+\S+\s+AS\s+(\S+)", re.MULTILINE | re.IGNORECASE)


def _overlays(root: Path) -> set[str]:
    d = root / _COMPOSE_DIR
    return {f"overlay:{p.name}" for p in d.glob("*.yml")} if d.is_dir() else set()


def _services(root: Path) -> set[str]:
    keys: set[str] = set()
    d = root / _COMPOSE_DIR
    if not d.is_dir():
        return keys
    for p in d.glob("*.yml"):
        data = yaml.safe_load(p.read_text()) or {}
        for svc in data.get("services") or {}:
            keys.add(f"service:{p.name}:{svc}")
    return keys


def _docker_stages(root: Path) -> set[str]:
    keys: set[str] = set()
    d = root / _DOCKER_DIR
    if not d.is_dir():
        return keys
    for p in d.glob("*Dockerfile*"):
        for stage in _FROM_AS.findall(p.read_text()):
            keys.add(f"docker-stage:{p.name}:{stage}")
    return keys


def _scripts(root: Path) -> set[str]:
    keys: set[str] = set()
    for base in _SCRIPT_DIRS:
        d = root / base
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.is_file() and p.suffix in {".sh", ".py"}:
                keys.add(f"script:{p.relative_to(root).as_posix()}")
    return keys


def _workflow_jobs(root: Path) -> set[str]:
    keys: set[str] = set()
    d = root / _WORKFLOWS_DIR
    if not d.is_dir():
        return keys
    for p in d.glob("*.yml"):
        data = yaml.safe_load(p.read_text()) or {}
        for job in data.get("jobs") or {}:
            keys.add(f"job:{p.name}:{job}")
    return keys


def _hooks(root: Path) -> set[str]:
    keys: set[str] = set()
    pc = root / _PRECOMMIT
    if pc.is_file():
        data = yaml.safe_load(pc.read_text()) or {}
        for repo in data.get("repos") or []:
            for hook in repo.get("hooks") or []:
                hook_id = hook.get("id")
                if hook_id:
                    keys.add(f"hook:{hook_id}")
    hd = root / _CLAUDE_HOOKS_DIR
    if hd.is_dir():
        for p in hd.glob("*"):
            if p.is_file():
                keys.add(f"hook:.claude:{p.name}")
    return keys


def enumerate_surfaces(root: Path) -> set[str]:
    """All canonical operational-surface keys in the rendered project at ``root``."""
    return (
        _overlays(root)
        | _services(root)
        | _docker_stages(root)
        | _scripts(root)
        | _workflow_jobs(root)
        | _hooks(root)
    )
