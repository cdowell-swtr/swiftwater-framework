from framework_cli.self_bump import BumpDecision, decide_bump


def d(installed, target, *, uv=True, tty=True, flag=False) -> BumpDecision:
    return decide_bump(
        installed_tag=installed,
        target_tag=target,
        is_uv_tool=uv,
        is_tty=tty,
        bump_flag=flag,
    )


def test_proceed_when_target_not_newer():
    assert d("0.2.11", "v0.2.11").action == "proceed"
    assert d("0.2.11", "v0.2.8").action == "proceed"


def test_refuse_when_not_uv_tool_install():
    dec = d("0.2.8", "v0.2.11", uv=False)
    assert dec.action == "refuse"
    assert "uv tool install" in dec.message and "@v0.2.11" in dec.message


def test_bump_when_flag_set_even_non_tty():
    assert d("0.2.8", "v0.2.11", tty=False, flag=True).action == "bump"


def test_prompt_when_uv_tool_and_tty():
    assert d("0.2.8", "v0.2.11", tty=True, flag=False).action == "prompt"


def test_refuse_when_non_interactive_and_no_flag():
    dec = d("0.2.8", "v0.2.11", tty=False, flag=False)
    assert dec.action == "refuse"
    assert "--bump-cli" in dec.message
