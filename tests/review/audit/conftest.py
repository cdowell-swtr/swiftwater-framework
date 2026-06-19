"""A `.messages.create`-shaped stub so audit-pipeline tests need no key/quota."""

from __future__ import annotations

import pytest

from framework_cli.review.backend import Message, TextBlock


class _StubMessages:
    def __init__(
        self, scripted
    ):  # scripted: list[str] OR callable(system, messages)->str
        self._scripted = scripted
        self._i = 0
        self.calls = []

    def create(self, *, model, max_tokens, system, messages, tools=None):
        self.calls.append({"model": model, "system": system, "messages": messages})
        if callable(self._scripted):
            text = self._scripted(system, messages)
        else:
            text = self._scripted[min(self._i, len(self._scripted) - 1)]
            self._i += 1
        return Message(content=[TextBlock(text=text)], stop_reason="end_turn")


class StubBackend:
    def __init__(self, scripted):
        self.messages = _StubMessages(scripted)


@pytest.fixture
def stub_backend():
    return StubBackend
