"""Ожидание ответа Алисы: следить за самим ответом, а не за рекламой под ним.

Замер 11.09.2026: по ходу ответа Алиса добавляет второй контейнер сообщения —
рекламный «Промо», поначалу пустой. Общее ожидание смотрело на последний
контейнер и либо стояло до таймаута (пустая реклама не «затихает»), либо
заканчивалось раньше ответа (готовая реклама затихает сразу). Здесь страница
ненастоящая: первый контейнер «печатает» ответ, второй — реклама.
"""

import asyncio
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scanner.adapters import alice as alice_mod  # noqa: E402
from app.scanner.adapters.alice import AliceAdapter, _S  # noqa: E402

# Для теста — короткие пороги, логика та же.
alice_mod._QUIET_SEC = 0.6
alice_mod._DONE_QUIET_SEC = 0.2
alice_mod._ANSWER_TIMEOUT = 10.0


class Growing:
    """Текст, который растёт до full за grow_sec, потом стоит."""

    def __init__(self, full: str, grow_sec: float) -> None:
        self.full, self.grow_sec, self.t0 = full, grow_sec, time.monotonic()

    def text(self) -> str:
        k = min(1.0, (time.monotonic() - self.t0) / self.grow_sec) if self.grow_sec else 1.0
        return self.full[: int(len(self.full) * k)]


class FakeLocator:
    def __init__(self, items: list, done: bool = False) -> None:
        self.items, self.done = items, done

    @property
    def first(self) -> "FakeLocator":
        return FakeLocator(self.items[:1])

    @property
    def last(self) -> "FakeLocator":
        return FakeLocator(self.items[-1:])

    async def wait_for(self, **_) -> None:
        return None

    async def inner_text(self, **_) -> str:
        return self.items[0].text() if self.items else ""

    async def count(self) -> int:
        return len(self.items)


class LazyButton:
    """Как настоящий локатор Playwright: count() каждый раз смотрит страницу заново."""

    def __init__(self, shown) -> None:
        self.shown = shown

    async def count(self) -> int:
        return 1 if self.shown() else 0


class FakePage:
    def __init__(self, answer: Growing, promo: Growing, sources_button_after: float | None) -> None:
        self.answer, self.promo = answer, promo
        self.sources_after = sources_button_after
        self.t0 = time.monotonic()

    def locator(self, sel: str):
        if sel == _S["answer_container"]:
            return FakeLocator([self.answer, self.promo])
        if sel == _S["sources_button"]:
            return LazyButton(
                lambda: self.sources_after is not None and time.monotonic() - self.t0 >= self.sources_after
            )
        raise AssertionError(sel)


ANSWER = "Да, Neighbors действительно сотрудничает с дизайнерами. " * 20


def _wait(page) -> float:
    t0 = time.monotonic()
    asyncio.run(AliceAdapter()._wait_answer(page))
    return time.monotonic() - t0


def test_empty_promo_does_not_stall_until_timeout():
    page = FakePage(Growing(ANSWER, 1.0), Growing("", 0), sources_button_after=None)
    took = _wait(page)
    assert took < 3.0, f"ждал {took:.1f} с — смотрел на пустую рекламу"
    assert page.answer.text() == ANSWER


def test_ready_promo_does_not_end_wait_before_answer():
    page = FakePage(Growing(ANSWER, 1.5), Growing("Большой выбор услуг по дизайну. Промо" * 3, 0), None)
    took = _wait(page)
    assert took >= 1.5, f"закончил через {took:.1f} с — раньше, чем дописался ответ"


def test_sources_button_shortens_wait():
    # Страницы создаются прямо перед ожиданием: у каждой свои часы. Порог
    # «тишины без кнопки» поднят до 2 с, чтобы разница с «секундой после
    # кнопки» была заметно больше шага опроса в полсекунды.
    saved = alice_mod._QUIET_SEC
    alice_mod._QUIET_SEC = 2.0
    try:
        fast = _wait(FakePage(Growing(ANSWER, 0.5), Growing("", 0), sources_button_after=0.5))
        slow = _wait(FakePage(Growing(ANSWER, 0.5), Growing("", 0), sources_button_after=None))
    finally:
        alice_mod._QUIET_SEC = saved
    assert fast + 0.8 < slow, f"с кнопкой {fast:.1f} с, без неё {slow:.1f} с"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
