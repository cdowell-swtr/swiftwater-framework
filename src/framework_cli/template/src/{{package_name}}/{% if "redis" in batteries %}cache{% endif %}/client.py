from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from redis import Redis

from ..config.settings import get_settings

# Dedicated logical DB for the app cache keyspace — kept separate from Celery's broker (/0)
# and result backend (/1) so a cache flush never touches Celery state.
_CACHE_DB = 3


@lru_cache
def get_redis() -> Redis:
    # redis-py honors the DB in the URL path over a db= kwarg, so substitute the path
    # explicitly to land on the dedicated cache DB regardless of how redis_url is written.
    parts = urlparse(get_settings().redis_url)
    url = urlunparse(parts._replace(path=f"/{_CACHE_DB}"))
    return Redis.from_url(url, decode_responses=True)
