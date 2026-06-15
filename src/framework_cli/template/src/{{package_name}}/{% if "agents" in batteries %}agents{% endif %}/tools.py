"""Tool registry + read-only Item tools for the agent loop.

Read-only by design: tools query the existing items table directly (no repository writes,
no mutating tools), so the LLM can inspect domain data but never change it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ..db.models import Item
from ..db.repository import list_items


@dataclass
class ToolContext:
    session: Session | None


ToolHandler = Callable[[dict[str, Any], ToolContext], str]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any], ctx: ToolContext) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"error: unknown tool {name!r}"
        return tool.handler(args, ctx)


def _get_item(args: dict[str, Any], ctx: ToolContext) -> str:
    if ctx.session is None:
        return "error: no database session"
    item = ctx.session.get(Item, int(args["id"]))
    if item is None:
        return f"item {args['id']} not found"
    return json.dumps({"id": item.id, "name": item.name})


def _search_items(args: dict[str, Any], ctx: ToolContext) -> str:
    if ctx.session is None:
        return "error: no database session"
    query = str(args.get("query", "")).lower()
    matches = [
        {"id": i.id, "name": i.name}
        for i in list_items(ctx.session, limit=100)
        if query in i.name.lower()
    ]
    return json.dumps(matches)


def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="get_item",
            description="Fetch a single item by its integer id.",
            parameters={
                "type": "object",
                "properties": {"id": {"type": "integer"}},
                "required": ["id"],
            },
            handler=_get_item,
        )
    )
    reg.register(
        Tool(
            name="search_items",
            description="Search items whose name contains the query substring.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=_search_items,
        )
    )
    return reg
