from framework_cli.review.config import (
    read_backend_choice,
    write_backend_choice,
    clear_backend_choice,
)


def test_write_read_clear_roundtrip(tmp_path):
    assert read_backend_choice(tmp_path) is None
    write_backend_choice(tmp_path, "subagent")
    assert read_backend_choice(tmp_path) == "subagent"
    write_backend_choice(tmp_path, "api")
    assert read_backend_choice(tmp_path) == "api"
    clear_backend_choice(tmp_path)
    assert read_backend_choice(tmp_path) is None


def test_read_ignores_malformed_toml(tmp_path):
    (tmp_path / ".framework").mkdir()
    (tmp_path / ".framework" / "review.toml").write_text("not = [valid")
    assert read_backend_choice(tmp_path) is None  # fail-open, never crashes a review


def test_write_rejects_unknown_backend(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        write_backend_choice(tmp_path, "gpt")
