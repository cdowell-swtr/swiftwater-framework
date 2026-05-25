from __future__ import annotations

import datetime

import strawberry
from graphql.validation import NoSchemaIntrospectionCustomRule
from strawberry.extensions import AddValidationRules, SchemaExtension

from ..db import repository
from ..db.models import Item as ItemModel


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
    """Build the schema. Introspection is disabled in production via a validation rule;
    Task 4 will prepend the metrics extension."""
    extensions: list[type[SchemaExtension] | AddValidationRules] = []
    if disable_introspection:
        extensions.append(AddValidationRules([NoSchemaIntrospectionCustomRule]))
    return strawberry.Schema(query=Query, mutation=Mutation, extensions=extensions)


# Introspectable schema for SDL export (scripts/export-graphql-schema.sh) + the contract diff.
schema = build_schema(disable_introspection=False)
