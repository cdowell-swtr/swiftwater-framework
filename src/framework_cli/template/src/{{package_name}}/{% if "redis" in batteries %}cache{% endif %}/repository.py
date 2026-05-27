from redis import Redis


def cache_set(
    client: Redis, key: str, value: str, ttl_seconds: int | None = None
) -> None:
    client.set(key, value, ex=ttl_seconds)


def cache_get(client: Redis, key: str) -> str | None:
    return client.get(key)


def cache_delete(client: Redis, key: str) -> None:
    client.delete(key)
