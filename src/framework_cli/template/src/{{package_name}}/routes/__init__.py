"""Route autodiscovery.

`include_routers(app)` includes every APIRouter exposed as `router` by a module in this
package, in a deterministic (sorted) order. A route-adding battery drops a
`routes/<name>.py` exposing `router` and it is wired automatically — no edit to main.py.
"""

import importlib
import pkgutil

from fastapi import APIRouter, FastAPI


def include_routers(app: FastAPI) -> None:
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{__name__}.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
