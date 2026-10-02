"""Google must finish streaming after expansion before capture can proceed."""
import asyncio

import pytest

from app.scanner.adapters import google_aio as google
from app.scanner.adapters.base import AdapterError, CaptchaError


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


class ConsentButton:
    def __init__(self, label="Принять все", shown=True): self.label, self.shown, self.clicked, self.hidden = label, shown, False, False
    async def wait_for(self, **_):
        if not self.hidden: raise RuntimeError("still visible")


class ConsentPage:
    def __init__(self, label="Принять все", delayed=False, buttons=None):
        self.url, self.delayed, self.calls = "https://www.google.com/", delayed, 0
        self.buttons = buttons or [ConsentButton(label)]
        self.button = self.buttons[0]
    async def goto(self, *_args, **_kwargs): pass
    def get_by_role(self, role, name, exact=False):
        buttons = [button for button in self.buttons if role == "button" and name.fullmatch(button.label)]
        if buttons:
            class Buttons:
                async def count(_):
                    self.calls += 1
                    return 0 if self.delayed and self.calls == 1 else len(buttons)
                def nth(_, index): return buttons[index]
            return Buttons()
        class Missing:
            async def count(self): return 0
            def nth(self, _): return self
        return Missing()


def test_home_accepts_only_exact_visible_consent(monkeypatch):
    async def visible(button, *_): return button.shown
    async def click(button, *_): button.clicked = button.hidden = True
    monkeypatch.setattr(google, "visible", visible)
    monkeypatch.setattr(google, "safe_click", click)
    page = ConsentPage("Accept all")
    assert asyncio.run(google.GoogleAIOAdapter()._home(page)) and page.button.clicked


def test_home_waits_for_delayed_consent_button(monkeypatch):
    async def visible(button, *_): return button.shown
    async def click(button, *_): button.clicked = button.hidden = True
    async def sleep(*_): pass
    monkeypatch.setattr(google, "visible", visible)
    monkeypatch.setattr(google, "safe_click", click)
    monkeypatch.setattr(google.asyncio, "sleep", sleep)
    page = ConsentPage(delayed=True)
    assert asyncio.run(google.GoogleAIOAdapter()._home(page)) and page.button.clicked


@pytest.mark.parametrize("label", ["Принять все", "Accept all"])
def test_home_accepts_exact_visible_russian_and_english_consent(monkeypatch, label):
    async def visible(button, *_): return button.shown
    async def click(button, *_): button.clicked = button.hidden = True
    monkeypatch.setattr(google, "visible", visible)
    monkeypatch.setattr(google, "safe_click", click)
    page = ConsentPage(label)
    assert asyncio.run(google.GoogleAIOAdapter()._home(page)) and page.button.clicked


def test_home_ignores_missing_hidden_and_unrelated_consent(monkeypatch):
    clock = Clock()
    async def visible(button, *_): return button.shown
    monkeypatch.setattr(google, "visible", visible)
    monkeypatch.setattr(google.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(google.asyncio, "sleep", clock.sleep)
    buttons = [ConsentButton("Accept all", shown=False), ConsentButton("Accept all settings")]
    page = ConsentPage(buttons=buttons)
    assert asyncio.run(google.GoogleAIOAdapter()._home(page))
    assert not any(button.clicked for button in buttons)


def test_home_skips_hidden_exact_button_for_visible_one(monkeypatch):
    async def visible(button, *_): return button.shown
    async def click(button, *_): button.clicked = button.hidden = True
    monkeypatch.setattr(google, "visible", visible)
    monkeypatch.setattr(google, "safe_click", click)
    hidden, shown = ConsentButton("Accept all", shown=False), ConsentButton("Accept all")
    page = ConsentPage(buttons=[hidden, shown])
    assert asyncio.run(google.GoogleAIOAdapter()._home(page))
    assert not hidden.clicked and shown.clicked


def test_undismissed_consent_stops_before_typing(monkeypatch):
    async def visible(button, *_): return button.shown
    async def click(button, *_): button.clicked = True
    typed = False
    async def type_like_human(*_):
        nonlocal typed
        typed = True
    monkeypatch.setattr(google, "visible", visible)
    monkeypatch.setattr(google, "safe_click", click)
    monkeypatch.setattr(google.humanize, "type_like_human", type_like_human)
    with pytest.raises(AdapterError, match="cookies dialog"):
        asyncio.run(google.GoogleAIOAdapter().ask(ConsentPage(), "query", None))
    assert not typed


def test_home_preserves_captcha_before_and_after_consent(monkeypatch):
    adapter = google.GoogleAIOAdapter()
    initial = ConsentPage()
    initial.url += "sorry/"
    assert not asyncio.run(adapter.ensure_ready(initial)).ok
    with pytest.raises(CaptchaError):
        asyncio.run(adapter._home(initial))

    async def visible(button, *_): return button.shown
    async def click(button, *_):
        button.clicked = button.hidden = True
        page.url += "sorry/"
    monkeypatch.setattr(google, "visible", visible)
    monkeypatch.setattr(google, "safe_click", click)
    page = ConsentPage()
    assert not asyncio.run(adapter.ensure_ready(page)).ok
    page = ConsentPage()
    with pytest.raises(CaptchaError):
        asyncio.run(adapter._home(page))


def test_ask_recovery_uses_home_handler(monkeypatch):
    adapter, calls = google.GoogleAIOAdapter(), []
    async def home(page, **_): calls.append(page)
    async def focus(page, selector, service, *, recover): await recover()
    async def type_like_human(*_, **__): pass
    async def wait_overview(*_): return False
    monkeypatch.setattr(adapter, "_home", home)
    monkeypatch.setattr(google, "focus_input", focus)
    monkeypatch.setattr(google.humanize, "type_like_human", type_like_human)
    monkeypatch.setattr(adapter, "_wait_overview", wait_overview)
    class AskPage:
        url = "https://www.google.com/"
        class keyboard:
            @staticmethod
            async def press(*_): pass
        async def wait_for_load_state(self, **_): pass
    page = AskPage()
    asyncio.run(adapter.ask(page, "query", None))
    assert calls == [page, page]


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
