import asyncio
from types import SimpleNamespace

import pytest

from app.scanner import humanize


class Texts:
    def __init__(self, values): self.values = iter(values)
    @property
    def last(self): return self
    async def inner_text(self, **_kwargs): return next(self.values)


def clocked(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(humanize.asyncio, "get_event_loop", lambda: SimpleNamespace(time=lambda: now[0]))
    async def sleep(seconds): now[0] += seconds
    monkeypatch.setattr(humanize.asyncio, "sleep", sleep)


def test_settling_detects_equal_length_edits(monkeypatch):
    clocked(monkeypatch)
    answer = Texts(["aa", "bb", "bb", "bb"])
    page = SimpleNamespace(locator=lambda _selector: answer)
    assert asyncio.run(humanize.wait_until_settled(page, "answer", quiet_for=.2, timeout=1, poll=.1)) == "bb"


def test_settling_times_out_when_text_keeps_growing(monkeypatch):
    clocked(monkeypatch)
    answer = Texts(["a", "ab", "abc", "abcd", "abcde"])
    page = SimpleNamespace(locator=lambda _selector: answer)
    with pytest.raises(humanize.AnswerNotSettledError):
        asyncio.run(humanize.wait_until_settled(page, "answer", timeout=.3, poll=.1))


def test_settling_returns_stable_full_text(monkeypatch):
    clocked(monkeypatch)
    answer = Texts(["complete", "complete", "complete"])
    page = SimpleNamespace(locator=lambda _selector: answer)
    assert asyncio.run(humanize.wait_until_settled(page, "answer", quiet_for=.1, timeout=1, poll=.1)) == "complete"
