"""Google must finish streaming after expansion before capture can proceed."""
import asyncio

import pytest

from app.scanner.adapters import google_aio as google
from app.scanner.adapters.base import AdapterError


class Clock:
    now = 0.0
    def monotonic(self): return self.now
    async def sleep(self, seconds): self.now += seconds


class Box:
    def __init__(self, page): self.page = page
    @property
    def first(self): return self
    async def inner_text(self, **_): return self.page.text()


class Page:
    def __init__(self, text):
        self.text, self.expanded = text, False
        self.mouse = self
    def locator(self, selector):
        assert selector == google._S["answer_container"]
        return Box(self)
    async def move(self, *_): pass


def wait(monkeypatch, page, clock, *, appeared=True, timeout=15.0, expansion=None):
    async def visible(*_): return appeared
    async def expand(_):
        page.expanded = True
        return expansion() if expansion else False
    async def debug(*_): pass
    monkeypatch.setattr(google, "visible", visible)
    monkeypatch.setattr(google.GoogleAIOAdapter, "_expand", lambda self, p: expand(p))
    monkeypatch.setattr(google, "dump_debug_html", debug)
    monkeypatch.setattr(google, "_SETTLE_TIMEOUT", timeout)
    monkeypatch.setattr(google.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(google.asyncio, "sleep", clock.sleep)
    return asyncio.run(google.GoogleAIOAdapter()._wait_overview(page))


def test_long_generation_pause_resets_quiet_time_after_expansion(monkeypatch):
    clock = Clock()
    page = Page(lambda: "x" * (80 if clock.now < 4 else 140))
    assert wait(monkeypatch, page, clock)
    assert page.expanded and clock.now >= 9.0


def test_same_length_replacement_resets_quiet_time(monkeypatch):
    clock = Clock()
    page = Page(lambda: ("a" if clock.now < 1.2 else "b") * 80)
    assert wait(monkeypatch, page, clock)
    assert clock.now >= 6.2


def test_unfinished_overview_errors_and_absent_overview_is_valid(monkeypatch):
    clock = Clock()
    page = Page(lambda: "x" * (80 + int(clock.now)))
    with pytest.raises(AdapterError, match="не стабилизировался"):
        wait(monkeypatch, page, clock, timeout=6)
    assert not wait(monkeypatch, page, clock, appeared=False)


def test_markerless_completed_answer_finishes_after_quiet_period(monkeypatch):
    clock = Clock()
    page = Page(lambda: "x" * 80)
    assert wait(monkeypatch, page, clock)
    assert 5.0 <= clock.now < 5.5


def test_late_expand_control_is_clicked_and_new_cards_settle(monkeypatch):
    clock = Clock()
    cards = []
    page = Page(lambda: "x" * 80 + ("cards" if cards else ""))
    def expand():
        if clock.now >= 1 and not cards:
            cards.append(True)
            return True
        return False
    assert wait(monkeypatch, page, clock, expansion=expand)
    assert cards and clock.now >= 10.0
