"""Per-worker render cache for the test suite (FWK94).

`render_project(dest, data)` is a drop-in for
`framework_cli.copier_runner.render_project`: it renders each distinct answer-set
ONCE into a process-local cache, then `copytree`s a fresh, independent copy into
`dest`. The suite issues 283 `render_project` calls spanning ~20 distinct answer-sets;
this collapses the redundant copier renders (~1.15s each) to one render per answer-set
per worker, with each caller still getting its own mutable tree (a ~0.08s copytree on a
hit) so there is no shared-base aliasing — every caller may freely mutate its tree.

Per-process by construction: the module-level cache lives in each xdist worker process,
so there is no cross-worker on-disk sharing (which would reintroduce the realize_cached
copytree-vs-git-GC race at process granularity). The cached tree is git-free — a render
produces no `.git` — so that race cannot occur here at all; the ~11 git-init callers run
`git init` on their own copy as before.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from framework_cli.copier_runner import render_project as _render_project

# Module-level → one instance per process → per xdist worker. Tests run serially within a
# worker, so no lock is needed.
_cache: dict[tuple, Path] = {}
_cache_root: Path | None = None


@atexit.register
def _cleanup() -> None:
    """Reap the per-process cache dir at worker exit (this box's /tmp is a small tmpfs)."""
    if _cache_root is not None:
        shutil.rmtree(_cache_root, ignore_errors=True)


def _key(data: Mapping[str, object]) -> tuple:
    """A hashable, order-insensitive freeze of an answer-set.

    The render is deterministic given `data` (the only injected non-`data` input is
    `render_date`, which defaults to today and is constant within a run; callers that
    pass it explicitly carry it in `data`), so equal answer-sets share a cached base.
    """

    def freeze(value: object) -> object:
        if isinstance(value, Mapping):
            return tuple(sorted((k, freeze(v)) for k, v in value.items()))
        if isinstance(value, (list, tuple)):
            return tuple(freeze(v) for v in value)
        return value

    return freeze(data)  # type: ignore[return-value]


def _base_for(data: Mapping[str, object]) -> Path:
    """Return the cached, rendered base tree for `data`, rendering it once on first use."""
    global _cache_root
    key = _key(data)
    base = _cache.get(key)
    if base is None:
        if _cache_root is None:
            _cache_root = Path(tempfile.mkdtemp(prefix="fwk-render-cache-"))
        base = _cache_root / f"base-{len(_cache)}"
        _render_project(base, data)
        _cache[key] = base
    return base


def render_project(dest: Path, data: Mapping[str, object]) -> None:
    """Drop-in for copier_runner.render_project: copytree a fresh cached base into `dest`."""
    base = _base_for(data)
    shutil.copytree(base, Path(dest), dirs_exist_ok=True, symlinks=True)
