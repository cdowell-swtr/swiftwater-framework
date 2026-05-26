from collections.abc import Mapping
from typing import Any

from pymongo.database import Database

_COLLECTION = "documents"


def insert_document(db: Database, doc: Mapping[str, Any]) -> str:
    return str(db[_COLLECTION].insert_one(dict(doc)).inserted_id)


def find_documents(
    db: Database,
    query: Mapping[str, Any] | None = None,
) -> list[dict]:
    return list(db[_COLLECTION].find(dict(query or {}), {"_id": 0}))
