from framework_cli.migrations import (
    migration_context,
    migration_down_revisions as mdr,
    migration_head,
)


def test_empty():
    assert mdr([]) == {}


def test_single_migration_battery_chains_to_baseline():
    assert mdr(["pgvector"]) == {"pgvector": "0001"}
    assert mdr(["workers"]) == {"workers": "0001"}


def test_webhooks_then_pgvector_skips_absent_workers():
    assert mdr(["webhooks", "pgvector"]) == {"webhooks": "0001", "pgvector": "0002"}


def test_full_chain_in_canonical_order():
    got = mdr(["pgvector", "workers", "webhooks"])  # input order irrelevant
    assert got == {"webhooks": "0001", "workers": "0002", "pgvector": "0003"}


def test_non_migration_batteries_ignored():
    assert mdr(["mongodb", "graphql", "webhooks"]) == {"webhooks": "0001"}


def test_migration_head_is_last_present_battery():
    assert migration_head([]) == "0001"
    assert migration_head(["workers"]) == "0003"
    assert migration_head(["webhooks", "workers"]) == "0003"
    assert migration_head(["workers", "pgvector"]) == "0004"
    assert migration_head(["workers", "age"]) == "0006"


def test_migration_context_includes_dlq_redacted_down_revision():
    assert migration_context(["workers"])["down_revision_dlq_redacted"] == "0003"
    assert migration_context(["workers", "age"])["down_revision_dlq_redacted"] == "0006"
