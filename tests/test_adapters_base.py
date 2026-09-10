"""Тесты общих помощников адаптеров — на заглушках, без браузера.

Проверяется ровно то, что стоило реальных прогонов: запасной клик для
свёрнутого окна и ожидание, которое действительно ждёт.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scanner.adapters.base import AdapterError, ensure_blank, safe_click, visible  # noqa: E402


class FakeLocator:
    def __init__(self, *, click_ok=True, appears=True):
        self.click_ok, self.appears = click_ok, appears
        self.calls = []

    async def click(self, timeout=None, **kw):
        self.calls.append("click")
        if not self.click_ok:
            raise TimeoutError("waiting for element to be visible, enabled and stable")

    async def evaluate(self, expr, arg=None, timeout=None):
        self.calls.append(("evaluate", expr))

    async def wait_for(self, state=None, timeout=None):
        if not self.appears:
            raise TimeoutError("не появился")


def run(coro):
    return asyncio.run(coro)


def test_safe_click_uses_normal_click_when_it_works():
    loc = FakeLocator(click_ok=True)
    run(safe_click(loc))
    assert loc.calls == ["click"], "DOM-клик не должен срабатывать, пока обычный проходит"


def test_safe_click_falls_back_to_dom_click_in_minimized_window():
    loc = FakeLocator(click_ok=False)
    run(safe_click(loc))
    assert loc.calls[0] == "click"
    assert loc.calls[1] == ("evaluate", "el => el.click()")


def test_visible_true_when_element_appears():
    assert run(visible(FakeLocator(appears=True), 100)) is True


def test_visible_false_instead_of_exception():
    assert run(visible(FakeLocator(appears=False), 100)) is False


class FakeCounter:
    def __init__(self, page):
        self.page = page

    async def count(self):
        return self.page.answers


class FakePage:
    def __init__(self, answers, after_recover):
        self.answers, self.after_recover, self.recovered = answers, after_recover, 0

    def locator(self, selector):
        return FakeCounter(self)

    async def recover(self):
        self.recovered += 1
        self.answers = self.after_recover


def test_ensure_blank_passes_on_empty_page():
    page = FakePage(answers=0, after_recover=0)
    run(ensure_blank(page, "sel", "svc", recover=page.recover))
    assert page.recovered == 0


def test_ensure_blank_recovers_when_old_answers_left():
    page = FakePage(answers=2, after_recover=0)
    run(ensure_blank(page, "sel", "svc", recover=page.recover))
    assert page.recovered == 1


def test_ensure_blank_refuses_to_send_into_dirty_chat():
    """Регрессия 10.09.2026: запросы уходили в тред с чужими ответами."""
    page = FakePage(answers=3, after_recover=3)
    try:
        run(ensure_blank(page, "sel", "svc", recover=page.recover))
    except AdapterError:
        return
    raise AssertionError("запрос не должен уходить в чат со старыми ответами")


if __name__ == "__main__":
    import traceback

    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
            passed += 1
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
