from pathlib import Path

from framework_cli.integrity.hashing import sha256_bytes, sha256_file


def test_sha256_bytes_is_stable():
    # Known SHA-256 of b"abc".
    assert sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_file_matches_bytes(tmp_path: Path):
    f = tmp_path / "x.txt"
    f.write_bytes(b"hello world")
    assert sha256_file(f) == sha256_bytes(b"hello world")
