"""Alice completion waits must prefer its live stop control over quiet text."""
import asyncio

import pytest

from app.scanner.adapters import alice as alice_mod
from app.scanner.adapters.alice import AliceAdapter, _S
from app.scanner.adapters.base import AdapterError


class Clock:
    now = 0.0
    def monotonic(self): return self.now
    async def sleep(self, seconds): self.now += seconds


class Locator:
    def __init__(self, text=None, count=None): self.text, self.count_fn = text, count
    @property
    def first(self): return self
    async def wait_for(self, **_): pass
    async def inner_text(self, **_): return self.text()
    async def count(self): return self.count_fn()


class AnswerSet:
    def __init__(self, answer, promo): self.answer, self.promo = answer, promo
    @property
    def first(self): return Locator(self.answer)
    @property
    def last(self): return Locator(self.promo)


class Page:
    def __init__(self, clock, answer, generating=lambda: False, sources=lambda: 0, promo=lambda: ""):
        self.clock, self.answer = clock, answer
        self.generating, self.sources, self.promo = generating, sources, promo
    def locator(self, selector):
        if selector == _S["answer_container"]:
            return AnswerSet(self.answer, self.promo)
        if selector == _S["generating_marker"]:
            return Locator(count=lambda: int(self.generating()))
        if selector == _S["sources_button"]:
            return Locator(count=self.sources)
        raise AssertionError(selector)
    async def content(self): return "<html></html>"


def wait(monkeypatch, page, *, quiet=1.0, done=0.2, timeout=8.0):
    monkeypatch.setattr(alice_mod, "_QUIET_SEC", quiet)
    monkeypatch.setattr(alice_mod, "_DONE_QUIET_SEC", done)
    monkeypatch.setattr(alice_mod, "_ANSWER_TIMEOUT", timeout)
    monkeypatch.setattr(alice_mod.time, "monotonic", page.clock.monotonic)
    monkeypatch.setattr(alice_mod.asyncio, "sleep", page.clock.sleep)
    asyncio.run(AliceAdapter()._wait_answer(page))


def test_active_marker_blocks_quiet_text_past_quiet_threshold(monkeypatch):
    clock = Clock()
    page = Page(clock, lambda: "x" * 80, generating=lambda: clock.now < 4.0)
    wait(monkeypatch, page)
    assert clock.now >= 4.0


def test_same_length_replacement_resets_quiet_clock(monkeypatch):
    clock = Clock()
    page = Page(clock, lambda: ("a" if clock.now < 1.0 else "b") * 80)
    wait(monkeypatch, page)
    assert clock.now >= 2.0


def test_completed_marker_allows_no_source_answer(monkeypatch):
    clock = Clock()
    page = Page(clock, lambda: "x" * 80, generating=lambda: clock.now < 0.5)
    wait(monkeypatch, page)
    assert 0.5 <= clock.now < 1.5


def test_active_marker_times_out_instead_of_capturing_partial_answer(monkeypatch):
    clock = Clock()
    page = Page(clock, lambda: "x" * 80, generating=lambda: True)
    monkeypatch.setattr(alice_mod, "dump_debug_html", lambda *_: asyncio.sleep(0))
    with pytest.raises(AdapterError, match="не завершился"):
        wait(monkeypatch, page, timeout=1.1)


def test_promo_is_ignored_while_answer_grows(monkeypatch):
    clock = Clock()
    page = Page(clock, lambda: "x" * (40 if clock.now < 1.0 else 80), promo=lambda: "promo" * 80)
    wait(monkeypatch, page)
    assert clock.now >= 2.0
