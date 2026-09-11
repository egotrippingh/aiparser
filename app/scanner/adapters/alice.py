"""Адаптер Алисы AI (alice.yandex.ru).

Все селекторы сняты вживую 28.08.2026 на реальном залогиненном аккаунте —
включая источники (получено 30 живых ссылок на реальный ответ). Это React-
приложение с осмысленными `data-testid` по всей разметке — гораздо
устойчивее сгенерированных Radix-id, с которыми пришлось иметь дело у
Perplexity.

Ключевой нюанс верстки: у контейнера сообщения пользователя и контейнера
ответа Алисы testid РАЗНЫЙ (``message-bubble-container-from-user`` против
``message-bubble-container``), а вот у самого пузыря с текстом внутри —
ОДИНАКОВЫЙ (``message-bubble`` у обоих). Поэтому текст ответа снимается
именно с контейнера, а не с пузыря, и именно поэтому перед каждым запросом
обязательно жмём «Новый чат»: без этого на странице накопится несколько
`message-bubble-container` (по одному на каждый ответ Алисы за сессию), и
селектор перестанет быть однозначным.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.scanner import humanize
from app.scanner.adapters.base import (
    AdapterError,
    Capture,
    ReadyState,
    dump_debug_html,
    load_selectors,
    focus_input,
    ensure_blank,
    safe_click,
    visible,
)

log = logging.getLogger("aiparser.adapters.alice")

_S = load_selectors()["alice"]

# Внутренняя навигация Алисы, которая иногда попадает в a[href^='http']
# рядом с источниками (например, ссылка на Промптхаб в шапке) — не источник
# ответа, отсеиваем так же, как у Perplexity. yandex.ru целиком НЕ блокируем:
# живой прогон 28.08.2026 показал настоящие источники на yandex.ru/maps/org/…
# — режем только заведомо служебные пути (/legal/…), не весь домен.
_CHROME_HOSTS = ("alice.yandex.ru",)
# 11.09.2026: первым «источником» в каждом ответе оказывался рекламный баннер
# самой Алисы (360.yandex.ru/business/alice-business/?utm_source=alisa_ai…).
# Промо-ссылки Яндекса помечены utm_source=alisa_ai — по нему и режем.
_CHROME_PATH_MARKERS = ("/legal/", "utm_source=alisa_ai", "/business/alice-business")

# Короче — это не ответ, а статус вроде «Ищу в интернете…» или обрыв.
_MIN_ANSWER_CHARS = 60
# Ответ готов, если текст не меняется столько секунд (или раньше — если уже
# появилась строка действий с кнопкой «Источники» и текст стоит хотя бы 1 с).
_QUIET_SEC = 3.0
_DONE_QUIET_SEC = 1.0
_ANSWER_TIMEOUT = 120.0


def _is_chrome_link(url: str) -> bool:
    return any(h in url for h in _CHROME_HOSTS) or any(m in url for m in _CHROME_PATH_MARKERS)


class AliceAdapter:
    service_id = "alice"
    display_name = "Алиса AI"
    requires_auth = True

    async def ensure_ready(self, page) -> ReadyState:
        await page.goto(_S["home_url"], wait_until="domcontentloaded")

        try:
            marker = page.locator(_S["logged_in_marker"])
            if not await visible(marker.first, 6000):
                return ReadyState(ok=False, reason="auth_required")
        except Exception:
            return ReadyState(ok=False, reason="auth_required")

        return ReadyState(ok=True)

    async def ask(self, page, query: str, region: str | None, *, speed: float = 1.0) -> None:
        # Новый чат перед каждым запросом — и чтобы предыдущий контекст не
        # влиял на ответ, и чтобы answer_container оставался однозначным
        # (см. заметку в модуле).
        try:
            new_chat = page.locator(_S["new_chat_button"])
            if await visible(new_chat.first, 3000):
                await safe_click(new_chat.first)
                await humanize.sleep(0.4 * speed, 0.9 * speed)
        except Exception:
            pass

        await ensure_blank(
            page, _S["answer_container"], self.service_id,
            recover=lambda: page.goto(_S["home_url"], wait_until="domcontentloaded"),
        )
        await focus_input(
            page, _S["input"], self.service_id,
            recover=lambda: page.goto(_S["home_url"], wait_until="domcontentloaded"),
        )
        await humanize.type_like_human(page, _S["input"], query, speed=speed, click=False)
        await page.keyboard.press("Enter")

        # На запросах, где Алиса реально ищет в интернете, она сперва
        # какое-то время показывает статусы («Ищу … в интернете…»,
        # «Анализирую информацию…») ВНУТРИ chat_container — если какой-то
        # из них продержится дольше quiet_for, детекция «текст перестал
        # расти» сработает по чужому тексту раньше, чем ответ вообще
        # появится в DOM (живой прогон 28.08.2026 поймал это на запросе
        # «Оптторг24 отзывы»). Поэтому сперва ждём появления самого
        # контейнера ответа, и только потом следим за стабилизацией именно
        # его текста, а не всего чата целиком.
        await self._wait_answer(page)
        await humanize.scroll_through(page, speed=speed)

    async def _wait_answer(self, page) -> None:
        """Ждёт, пока ответ Алисы допишется.

        Следим за ПЕРВЫМ контейнером ответа, а не за последним, как общий
        humanize.wait_until_settled. Замер 11.09.2026: по ходу ответа Алиса
        добавляет второй message-bubble-container — рекламный блок «Промо»,
        поначалу пустой. Ожидание смотрело на него: пустой контейнер не
        «затихал» никогда, и запрос стоял до таймаута (155–160 с вместо
        30), а если реклама успевала отрисоваться — «затихал» через
        несколько секунд, пока сам ответ ещё дописывался. После «Новый чат»
        ответ на странице один, и он всегда первый.

        Готовность — текст не меняется _QUIET_SEC секунд. Если под ответом
        уже появилась кнопка «Источники» (строка действий рисуется только
        по окончании), хватает секунды тишины.
        """
        answer = page.locator(_S["answer_container"]).first
        try:
            await answer.wait_for(state="attached", timeout=90000)
        except Exception:
            return  # capture() сам обработает отсутствие ответа как ошибку

        done = page.locator(_S["sources_button"])
        deadline = time.monotonic() + _ANSWER_TIMEOUT
        last, since = -1, time.monotonic()
        while time.monotonic() < deadline:
            try:
                n = len(await answer.inner_text(timeout=3000))
            except Exception:
                n = 0
            if n != last:
                last, since = n, time.monotonic()
            elif n >= _MIN_ANSWER_CHARS:
                quiet = time.monotonic() - since
                if quiet >= _QUIET_SEC or (quiet >= _DONE_QUIET_SEC and await done.count()):
                    return
            await asyncio.sleep(0.5)
        log.warning("Ответ Алисы не затих за %.0f с — читаю как есть (%s символов)", _ANSWER_TIMEOUT, last)

    async def capture(self, page) -> Capture:
        answer = page.locator(_S["answer_container"]).first
        try:
            answer_text = (await answer.inner_text(timeout=5000)).strip()
        except Exception as exc:
            await dump_debug_html(page, "alice_no_answer")
            raise AdapterError(f"Не найден контейнер ответа Алисы: {exc}") from exc

        if len(answer_text) < _MIN_ANSWER_CHARS:
            await dump_debug_html(page, "alice_short_answer")
            raise AdapterError(f"Ответ Алисы подозрительно короткий ({len(answer_text)} символов): {answer_text!r}")

        # Скриншот — до панели источников: она открывается сбоку и сужает
        # колонку ответа. Снимаем сам ответ целиком, а не видимую часть окна:
        # после прокрутки в окне оставался только хвост ответа (11.09.2026).
        screenshot = await self._screenshot(page, answer)
        sources = await self._extract_sources(page)

        return Capture(screenshot_bytes=screenshot, answer_text=answer_text, sources=sources)

    async def _screenshot(self, page, answer) -> bytes:
        try:
            return await answer.screenshot(type="jpeg", quality=80, timeout=8000)
        except Exception as exc:
            log.info("Скриншот ответа Алисы не снялся (%s) — снимаю окно", exc)
            return await page.screenshot(type="jpeg", quality=80, full_page=False)

    async def _extract_sources(self, page) -> list[str]:
        try:
            btn = page.locator(_S["sources_button"])
            if not await visible(btn.last, 2000):
                return []
            await safe_click(btn.last)
            await humanize.sleep(0.5, 1.0)

            hrefs = await page.locator("a[href^='http']").evaluate_all("els => els.map(e => e.href)")
            seen, out = set(), []
            for h in hrefs:
                if h in seen or _is_chrome_link(h):
                    continue
                seen.add(h)
                out.append(h)
            return out
        except Exception as exc:
            log.info("Не удалось извлечь источники Алисы: %s", exc)
            await dump_debug_html(page, "alice_sources_exception")
            return []
