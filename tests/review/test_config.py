from framework_cli.review.config import (
    read_backend_choice,
    write_backend_choice,
    clear_backend_choice,
    resolve_backend,
    probe_availability,
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


def _avail(api_key=False, claude=False):
    return {"api_key_present": api_key, "claude_available": claude}


def test_no_intent_resolves_to_skip(tmp_path):
    r = resolve_backend(
        root=tmp_path, flag=None, env={}, availability=_avail(api_key=True, claude=True)
    )
    assert r.backend is None and r.reason == "no-intent"  # R1: presence != consent


def test_flag_api_with_key_resolves_api(tmp_path):
    r = resolve_backend(
        root=tmp_path, flag="api", env={}, availability=_avail(api_key=True)
    )
    assert r.backend == "api"


def test_flag_api_without_key_skips_no_fallback(tmp_path):
    r = resolve_backend(
        root=tmp_path,
        flag="api",
        env={},
        availability=_avail(api_key=False, claude=True),
    )
    assert (
        r.backend is None and r.reason == "api-unavailable"
    )  # R2: does NOT use claude


def test_flag_subagent_without_claude_skips_no_fallback(tmp_path):
    r = resolve_backend(
        root=tmp_path,
        flag="subagent",
        env={},
        availability=_avail(api_key=True, claude=False),
    )
    assert (
        r.backend is None and r.reason == "subagent-unavailable"
    )  # R2: does NOT spend key


def test_env_overrides_config_but_flag_wins(tmp_path):
    write_backend_choice(tmp_path, "subagent")
    r = resolve_backend(
        root=tmp_path,
        flag=None,
        env={"FRAMEWORK_REVIEW_BACKEND": "api"},
        availability=_avail(api_key=True, claude=True),
    )
    assert r.backend == "api"
    r2 = resolve_backend(
        root=tmp_path,
        flag="subagent",
        env={"FRAMEWORK_REVIEW_BACKEND": "api"},
        availability=_avail(api_key=True, claude=True),
    )
    assert r2.backend == "subagent"


def test_garbage_env_value_resolves_to_no_intent(tmp_path):
    # Env is the unvalidated external surface; a junk value must NOT spend — it falls
    # to no-intent (and, being cost-safe, does not silently use an available backend).
    r = resolve_backend(
        root=tmp_path,
        flag=None,
        env={"FRAMEWORK_REVIEW_BACKEND": "gpt"},
        availability=_avail(api_key=True, claude=True),
    )
    assert r.backend is None and r.reason == "no-intent"


def test_persisted_config_is_honored_as_sole_source(tmp_path):
    # The config branch of the intent chain must be the winning source when flag+env
    # are absent (guards the read_backend_choice wiring into resolve_backend).
    write_backend_choice(tmp_path, "subagent")
    r = resolve_backend(
        root=tmp_path,
        flag=None,
        env={},
        availability=_avail(claude=True),
    )
    assert r.backend == "subagent" and r.reason == "resolved"


def test_probe_detects_key_and_claude(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_RUNTIME_API_KEY", "sk-x")
    monkeypatch.setattr(
        "shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None
    )
    a = probe_availability(key_env="ANTHROPIC_RUNTIME_API_KEY")
    assert a == {"api_key_present": True, "claude_available": True}


def test_probe_no_key_no_claude(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_RUNTIME_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    a = probe_availability(key_env="ANTHROPIC_RUNTIME_API_KEY")
    assert a == {"api_key_present": False, "claude_available": False}
