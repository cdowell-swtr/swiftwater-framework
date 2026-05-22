import json

from framework_cli.integrity.manifest import Entry, Manifest


def _sample() -> Manifest:
    return Manifest(
        framework_version="0.1.0",
        entries=[
            Entry(path="b.yml", cls="locked", tier="tracked", sha256="bbb"),
            Entry(path="a.yml", cls="locked", tier="tracked", sha256="aaa"),
            Entry(path=".env", cls="locked", tier="gitignored", sha256=None),
        ],
    )


def test_roundtrip_preserves_entries():
    m = _sample()
    back = Manifest.loads(m.dumps())
    assert {e.path for e in back.entries} == {"a.yml", "b.yml", ".env"}
    assert back.framework_version == "0.1.0"
    assert back.version == 1


def test_dump_is_sorted_and_self_checksummed():
    doc = json.loads(_sample().dumps())
    assert [e["path"] for e in doc["entries"]] == [".env", "a.yml", "b.yml"]
    assert doc["self_sha256"] == Manifest.loads(_sample().dumps()).self_sha256()


def test_tampering_with_an_entry_breaks_the_self_checksum():
    text = _sample().dumps()
    doc = json.loads(text)
    stored = doc["self_sha256"]
    doc["entries"][0]["sha256"] = "tampered"
    tampered = json.dumps(doc)
    # The recomputed checksum of the tampered body no longer matches the stored value.
    assert Manifest.loads(tampered).self_sha256() != stored


def test_gitignored_entry_carries_no_checksum():
    doc = json.loads(_sample().dumps())
    env = next(e for e in doc["entries"] if e["path"] == ".env")
    assert "sha256" not in env
