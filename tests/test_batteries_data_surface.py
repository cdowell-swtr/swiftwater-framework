import pytest
from framework_cli.batteries import battery_names, get_battery

# The declared backup disposition for every battery. A new battery added without an entry
# here fails this test — forcing the author to consciously classify its data surface.
EXPECTED_DATA = {
    "webhooks": "none",
    "llm": "none",
    "agents": "none",
    "claudesubscriptioncli": "none",
    "websockets": "none",
    "workers": "rebuildable",  # redisdata: broker/result backend, rebuildable
    "graphql": "none",
    "pgvector": "postgres-extension",  # vector data in pgdata; restore needs the extension image
    "mongodb": "store",  # mongodata: a new durable store, dumped via mongodump
    "timescaledb": "postgres-extension",
    "age": "postgres-extension",
    "redis": "rebuildable",  # redisdata: cache/sessions, rebuildable
    "react": "rebuildable",  # frontend_node_modules: build cache
    "consumers": "none",
    "docs": "none",
    "multitenantauth": "none",  # control-plane DB co-located in pgdata (core backup)
}


def test_every_battery_declares_a_data_surface():
    assert set(battery_names()) == set(EXPECTED_DATA), (
        "a battery was added/removed without updating EXPECTED_DATA — classify its data surface"
    )


@pytest.mark.parametrize("name", battery_names())
def test_battery_data_matches_expected(name):
    assert get_battery(name).data == EXPECTED_DATA[name]
