"""Адаптер Google AI Overview.

Все селекторы сняты вживую 28.08.2026. Прямой заход по URL результатов
(``/search?q=...``) на холодном профиле дважды подряд поймал антибот-редирект
на ``google.com/sorry/`` — обязателен человекоподобный путь: сначала главная
страница, потом печать в поле поиска и Enter. Профиль был вручную «прогрет»
пользователем (капча решена руками один раз, сделано несколько обычных
запросов) — после этого автоматический заход проходит нормально.

``#m-x-content`` — контейнер блока AI Overview, подтверждён дважды на одном и
том же запросе с разным исходом (один раз блок показался, один раз нет) —
это подтверждённая недетерминированность самого Google (блок генерируется не
всегда, вероятностно), а не нестабильность селектора: когда блок был, id
воспроизвёлся оба раза. Отсутствие блока — валидный результат ``skipped``,
как и предполагает план, а не ошибка адаптера.
"""

from __future__ import annotations

import logging

from app.scanner import humanize
from app.scanner.adapters.base import (
    Capture,
    CaptchaError,
    ReadyState,
    dump_debug_html,
    load_selectors,
    focus_input,
)

log = logging.getLogger("aiparser.adapters.google_aio")

_S = load_selectors()["google_aio"]


class GoogleAIOAdapter:
    service_id = "google_aio"
    display_name = "Google AI Overview"
    requires_auth = False

    async def ensure_ready(self, page) -> ReadyState:
        await page.goto(_S["home_url"], wait_until="domcontentloaded")
        if _S["captcha_url_marker"] in page.url:
            return ReadyState(ok=False, reason="captcha")
        return ReadyState(ok=True)

    async def ask(self, page, query: str, region: str | None, *, speed: float = 1.0) -> None:
        # Google — поисковик, а не чат: чистое состояние под новый запрос это
        # и есть главная страница, поэтому переход сюда неизбежен (в отличие
        # от чатов, где хватает SPA-клика «Новый чат»). Заход именно с
        # главной, а не сразу на /search?q=, обязателен: прямой URL на
        # холодном профиле даёт антибот-редирект (проверено 28.08.2026).
        await page.goto(_S["home_url"], wait_until="domcontentloaded")
        if _S["captcha_url_marker"] in page.url:
            raise CaptchaError(f"Google показал антибот-страницу: {page.url[:120]}")

        await focus_input(
            page, _S["input"], self.service_id,
            recover=lambda: page.goto(_S["home_url"], wait_until="domcontentloaded"),
        )
        await humanize.type_like_human(page, _S["input"], query, speed=speed, click=False)
        await page.keyboard.press("Enter")

        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        # AI Overview у Google — не потоковая генерация в духе чата, а часть
        # обычной навигации страницы: networkidle обычно уже застаёт готовый
        # блок, но живые прогоны показали, что рендер догоняет ещё секунду-
        # две после этого — короткая страховка вместо wait_until_settled,
        # которая тут не к месту (нет постоянно растущего текстового узла).
        await humanize.sleep(1.5 * speed, 2.5 * speed)

        if _S["captcha_url_marker"] in page.url:
            await dump_debug_html(page, "google_captcha")
            raise CaptchaError(f"Google показал антибот-страницу: {page.url[:120]}")

    async def capture(self, page) -> Capture:
        screenshot = await page.screenshot(type="jpeg", quality=80, full_page=False)

        count = await page.locator(_S["answer_container"]).count()
        if count == 0:
            # Валидный результат: блок AI Overview не сгенерирован для этого
            # запроса. Не ошибка — see module docstring.
            return Capture(screenshot_bytes=screenshot, answer_text="", sources=[], shown=False)

        try:
            answer_text = await page.locator(_S["answer_container"]).inner_text(timeout=5000)
        except Exception as exc:
            await dump_debug_html(page, "google_aio_read_failed")
            log.info("Блок AI Overview найден, но не читается: %s", exc)
            return Capture(screenshot_bytes=screenshot, answer_text="", sources=[], shown=False)

        sources = await self._extract_sources(page)
        return Capture(screenshot_bytes=screenshot, answer_text=answer_text.strip(), sources=sources)

    async def _extract_sources(self, page) -> list[str]:
        try:
            hrefs = await page.locator(_S["answer_container"]).locator(
                "a[href^='http']"
            ).evaluate_all("els => els.map(e => e.href)")
            seen, out = set(), []
            for h in hrefs:
                if h in seen or "google.com" in h or "google.ru" in h:
                    continue
                seen.add(h)
                out.append(h)
            return out
        except Exception as exc:
            log.info("Не удалось извлечь источники Google AI Overview: %s", exc)
            return []
