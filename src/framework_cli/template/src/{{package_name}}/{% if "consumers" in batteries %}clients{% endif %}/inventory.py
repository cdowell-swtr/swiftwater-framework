import httpx


def get_stock(base_url: str, item_id: int) -> int:
    """Fetch an item's stock level from the downstream inventory service.

    base_url is injected (the app passes settings.inventory_url; the consumer Pact
    test passes the mock server URL) so the call is contract-testable in isolation.
    """
    res = httpx.get(f"{base_url.rstrip('/')}/inventory/{item_id}", timeout=5.0)
    res.raise_for_status()
    return int(res.json()["in_stock"])
