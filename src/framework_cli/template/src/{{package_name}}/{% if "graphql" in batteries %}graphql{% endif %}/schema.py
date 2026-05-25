from __future__ import annotations

import datetime
from collections.abc import Callable

import strawberry
from graphql.validation import NoSchemaIntrospectionCustomRule
from strawberry.extensions import AddValidationRules, SchemaExtension

from ..db import repository
from ..db.models import Item as ItemModel
from .extension import MetricsExtension


@strawberry.type
class Item:
    id: int
    name: str
    created_at: datetime.datetime


def _to_item(row: ItemModel) -> Item:
    return Item(id=row.id, name=row.name, created_at=row.created_at)


@strawberry.type
class Query:
    @strawberry.field
    def items(self, info: strawberry.Info) -> list[Item]:
        session = info.context["session"]
        return [_to_item(r) for r in repository.list_items(session)]


@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_item(self, info: strawberry.Info, name: str) -> Item:
        session = info.context["session"]
        return _to_item(repository.create_item(session, name))


def build_schema(*, disable_introspection: bool) -> strawberry.Schema:
    """Build the schema. MetricsExtension counts every operation; introspection is disabled
    in production via a validation rule."""
    extensions: list[type[SchemaExtension] | Callable[[], SchemaExtension]] = [
        MetricsExtension
    ]
    if disable_introspection:
        # A factory (not an instance): Schema wants type|Callable[[], SchemaExtension], and a
        # fresh instance per request also avoids Strawberry's pass-an-instance deprecation.
        extensions.append(lambda: AddValidationRules([NoSchemaIntrospectionCustomRule]))
    return strawberry.Schema(query=Query, mutation=Mutation, extensions=extensions)


# Introspectable schema for SDL export (scripts/export-graphql-schema.sh) + the contract diff.
schema = build_schema(disable_introspection=False)
