from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from ..config.settings import get_settings


@lru_cache
def get_client() -> MongoClient:
    return MongoClient(get_settings().mongo_url)


def get_db() -> Database:
    return get_client().get_default_database()
