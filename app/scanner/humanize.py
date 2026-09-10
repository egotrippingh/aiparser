"""Человекоподобное поведение в браузере.

Camoufox сам по себе маскирует отпечаток, но ритм действий выдаёт бота не
меньше: мгновенная вставка текста, отправка через 5 мс после фокуса, ноль
скроллов. Здесь собран весь тайминг, чтобы он был в одном месте и правился
одной ручкой.
"""

from __future__ import annotations

import asyncio
import random

# Профили скорости. Ускорение — это размен на живучесть аккаунтов, поэтому
# режим выбирается осознанно в настройках, а выбранные значения кладутся в
# settings_snapshot скана: задним числом видно, в каком режиме собраны данные.
# "typing" — множитель к базовой задержке между символами.
PROFILES: dict[str, dict[str, float]] = {
    "careful":  {"delay_min_sec": 8, "delay_max_sec": 25, "break_every_n": 12, "typing": 1.0},
    "balanced": {"delay_min_sec": 4, "delay_max_sec": 10, "break_every_n": 25, "typing": 0.63},
    "fast":     {"delay_min_sec": 2, "delay_max_sec": 5,  "break_every_n": 0,  "typing": 0.40},
}
DEFAULT_PROFILE = "balanced"


def profile(name: str | None) -> dict[str, float]:
    return PROFILES.get(name or DEFAULT_PROFILE, PROFILES[DEFAULT_PROFILE])


# Паузы после знаков препинания — человек тут думает, а не печатает ровно.
_PAUSE_AFTER = {",": (0.12, 0.30), ".": (0.18, 0.45), "?": (0.20, 0.50), " ": (0.0, 0.06)}


async def sleep(lo: float, hi: float) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


async def type_like_human(
    page, selector: str, text: str, *, typo_chance: float = 0.03, speed: float = 1.0, click: bool = True
) -> None:
    """Печатает текст в поле посимвольно, с паузами и редкими опечатками.

    Опечатка с последующим backspace — самый дешёвый способ сломать идеально
    ровный интервал между нажатиями, по которому антибот отличает скрипт.
    """
    # click=False — поле уже сфокусировано через adapters.base.focus_input,
    # который умеет диагностировать и чинить заблокированный ввод. Здесь же
    # таймаут короткий: ждать 30 секунд по умолчанию Playwright незачем.
    if click:
        await page.locator(selector).first.click(timeout=10000)
    await sleep(0.25 * speed, 0.6 * speed)

    for ch in text:
        if random.random() < typo_chance and ch.isalpha():
            wrong = random.choice("йцукенгшщзхфывапролджэячсмитьбю")
            await page.keyboard.type(wrong, delay=random.uniform(60, 160) * speed)
            await sleep(0.15 * speed, 0.4 * speed)
            await page.keyboard.press("Backspace")
            await sleep(0.1 * speed, 0.25 * speed)

        await page.keyboard.type(ch, delay=random.uniform(55, 175) * speed)

        lo_hi = _PAUSE_AFTER.get(ch)
        if lo_hi:
            await sleep(lo_hi[0] * speed, lo_hi[1] * speed)

    await sleep(0.4 * speed, 1.1 * speed)


async def scroll_through(page, steps: int = 4, speed: float = 1.0) -> None:
    """Прокручивает страницу вниз и обратно — так ответ дочитывают глазами."""
    for _ in range(steps):
        await page.mouse.wheel(0, random.randint(220, 520))
        await sleep(0.35 * speed, 0.9 * speed)
    await page.keyboard.press("Home")
    await sleep(0.4 * speed, 0.8 * speed)


async def between_queries(idx: int, *, lo: float = 8, hi: float = 25, break_every: int = 12) -> None:
    """Пауза между запросами плюс редкий длинный «перерыв».

    Ровный интервал в 10 секунд шесть часов подряд — это не человек. Раз в
    десяток запросов уходим на минуту-другую, как будто отвлеклись.
    """
    if break_every and idx and idx % break_every == 0:
        await sleep(60, 180)
    else:
        await sleep(lo, hi)


async def wait_until_settled(
    page,
    selector: str,
    *,
    quiet_for: float = 3.0,
    timeout: float = 120.0,
    poll: float = 0.5,
) -> str:
    """Ждёт, пока текст в контейнере перестанет расти.

    Универсальная замена ожиданию по селектору кнопки «стоп»: у ChatGPT,
    Perplexity и Нейро эта кнопка называется по-разному и переезжает от релиза
    к релизу, а вот факт «текст больше не прибавляется» одинаков везде.

    Следим за ПОСЛЕДНИМ совпадением: page.inner_text берёт первое, и если на
    странице задержался старый ответ, ожидание смотрело бы на него — именно
    так 10.09.2026 недописанные ответы ChatGPT уходили в базу.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last_len, last_change = -1, loop.time()

    while loop.time() < deadline:
        try:
            text = await page.locator(selector).last.inner_text(timeout=5000)
        except Exception:
            text = ""

        if len(text) != last_len:
            last_len = len(text)
            last_change = loop.time()
        elif last_len > 0 and loop.time() - last_change >= quiet_for:
            return text

        await asyncio.sleep(poll)

    try:
        return await page.locator(selector).last.inner_text(timeout=5000)
    except Exception:
        return ""
