import pytest

from framework_cli.dispatch import classify


@pytest.mark.parametrize(
    "command,kind",
    [
        ("new", "advancing"),
        ("upgrade", "advancing"),
        ("integrity", "cwd_project"),
        ("restore", "cwd_project"),
        ("upskill", "arg_project"),
        ("downskill", "arg_project"),
        ("check", "self"),
        ("eval", "self"),
        ("review-aggregate", "self"),
        (None, "self"),
        ("totally-unknown", "self"),
    ],
)
def test_classify(command, kind):
    assert classify(command) == kind
