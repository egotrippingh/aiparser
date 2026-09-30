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

Доводка 11.09.2026 по живой разведке на 5 запросах:

* Блок генерируется после загрузки выдачи — от 1 до ~6 секунд, и первые
  мгновения в контейнере то один заголовок «Обзор от ИИ», то промежуточный
  текст. Фиксированной паузы мало: ждём, пока текст перестанет меняться.
* Блок свёрнут, под ним кнопка «Развернуть». Основной текст в DOM есть и в
  свёрнутом виде, но часть карточек источников появляется только после
  раскрытия (на «Neighbors отзывы…» среди них была карточка с брендом), а
  скриншот свёрнутого блока показывает лишь его верх. Поэтому раскрываем и
  снимаем скриншот самого блока целиком.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.scanner import humanize
from app.scanner.adapters import shot
from app.scanner.adapters.readable import readable
from app.scanner.adapters.base import (
    AdapterError,
    Capture,
    CaptchaError,
    ReadyState,
    dump_debug_html,
    focus_input,
    load_selectors,
    safe_click,
    visible,
)

log = logging.getLogger("aiparser.adapters.google_aio")

_S = load_selectors()["google_aio"]

# Короче этого в контейнере только заголовок «Обзор от ИИ»: блок показался,
# но ответ ещё не сгенерирован.
_MIN_CHARS = 60
# Сколько ждать появления блока после загрузки выдачи.
_APPEAR_MS = 8000
# Live long answers paused past 1.5 s. No completion marker exists in every
# Google DOM variant, so retain a conservative quiet interval after expansion.
# ponytail: quiet-time heuristic; use a completion flag when verified across variants.
_QUIET_SEC = 5.0
_SETTLE_TIMEOUT = 60.0

CARDS_MARK = "— Карточки источников —"

# Текст ответа и колонка карточек источников справа (разметка 11.09.2026):
# контейнер data-xid="aim-aside-…"; страховка на случай смены атрибута —
# правило по месту: блок правее середины с несколькими внешними ссылками.
#
# Ссылки ВНУТРИ абзацев карточками не считаем. Живые проверки 11.09.2026:
# обёртка data-icl-uuid — это сами фразы ИИ со ссылкой (в «карточки» уехали
# абзацы ответа), а ссылка с подписью «Предварительный просмотр ссылки» —
# слова ИИ, оформленные ссылкой («…на официальном сайте Neighbors»). Лучше
# засчитать редкую подпись предпросмотра как текст, чем выбросить из текста
# слова ИИ. Кусок, не найденный в тексте дословно, не трогаем.


def _strip_heading(text: str) -> str:
    heading = _S.get("aio_heading_text") or ""
    return text[len(heading):].lstrip() if heading and text.startswith(heading) else text


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

        if _S["captcha_url_marker"] in page.url:
            await dump_debug_html(page, "google_captcha")
            raise CaptchaError(f"Google показал антибот-страницу: {page.url[:120]}")

        await self._wait_overview(page)

    async def _wait_overview(self, page) -> bool:
        """Ждёт блок AI Overview и стабилизации его текста. False — блока нет."""
        box = page.locator(_S["answer_container"]).first
        if not await visible(box, _APPEAR_MS):
            return False

        await self._expand(page)
        await page.mouse.move(5, 5)
        deadline = time.monotonic() + _SETTLE_TIMEOUT
        last, since = None, time.monotonic()
        while time.monotonic() < deadline:
            try:
                text = await box.inner_text(timeout=2000)
            except Exception:
                text = ""
            if text != last:
                last, since = text, time.monotonic()
            elif len(text) >= _MIN_CHARS and time.monotonic() - since >= _QUIET_SEC:
                # The expand control can arrive after the initial heading.
                if await self._expand(page):
                    await page.mouse.move(5, 5)
                    last, since = None, time.monotonic()
                    continue
                return True
            await asyncio.sleep(0.3)
        await dump_debug_html(page, "google_aio_incomplete")
        raise AdapterError("AI Overview не стабилизировался — частичный ответ не сохранён")

    async def _expand(self, page) -> bool:
        """Жмёт «Развернуть» под блоком, если он свёрнут."""
        btn = page.locator(_S["expand_button"])
        try:
            if not await btn.count():
                return False
            await btn.first.scroll_into_view_if_needed(timeout=3000)
            await safe_click(btn.first)
            await humanize.sleep(0.8, 1.4)
            return True
        except Exception as exc:
            # Не раскрылся — текст всё равно в DOM, теряем только хвост
            # карточек источников и полноту скриншота. Не повод ронять запрос.
            log.info("Не удалось раскрыть AI Overview: %s", exc)
            return False

    async def capture(self, page) -> Capture:
        box = page.locator(_S["answer_container"])
        if await box.count() == 0:
            # Валидный результат: блок AI Overview не сгенерирован для этого
            # запроса. Не ошибка — see module docstring.
            screenshot = await page.screenshot(type="jpeg", quality=80, full_page=False)
            return Capture(screenshot_bytes=screenshot, answer_text="", sources=[], shown=False)

        # Курсор после клика «Развернуть» стоит над ответом, и Google
        # показывает всплывающее превью ссылки «сайт / заголовок» — оно
        # попадало в текст ответа (живая проверка 11.09.2026: «Отзывы о
        # «Neighbors…» в хвосте текста дала бы text вместо card).
        await page.mouse.move(5, 5)
        await asyncio.sleep(0.5)
        try:
            parts = await readable(box.first, "google")
        except Exception as exc:
            await dump_debug_html(page, "google_aio_read_failed")
            raise AdapterError(f"Блок AI Overview есть, но не читается: {exc}") from exc

        main = _strip_heading(parts["main"].strip())
        cards = parts["cards"].strip()

        if len(main) < _MIN_CHARS:
            # Блок показался, а ответ так и не сгенерировался. Это не «Google
            # не показал AI Overview» (skipped — валидный результат), а
            # недополученные данные: ошибка, которую дозапуск возьмёт заново.
            await dump_debug_html(page, "google_aio_empty")
            raise AdapterError(f"AI Overview показался, но ответ не сгенерировался ({len(main)} символов)")

        # В базу — всё, что видел пользователь, но карточки отделены пометкой:
        # в карточке запроса видно, где слова ИИ, а где чужие заголовки.
        answer_text = f"{main}\n\n{CARDS_MARK}\n{cards}" if cards else main
        display_main = _strip_heading(parts["display_main"].strip())
        display_cards = parts["display_cards"].strip()
        displayed = f"{display_main}\n\n{CARDS_MARK}\n{display_cards}" if display_cards else display_main
        sources = await self._extract_sources(page)
        screenshot = await self._screenshot(page, box.first)
        return Capture(
            screenshot_bytes=screenshot, answer_text=displayed or answer_text, sources=sources,
            extra={"main_text": main, "cards_text": cards, "plain_text": answer_text},
        )

    async def _screenshot(self, page, box) -> bytes:
        """Скриншот самого блока — раскрытого, целиком; при сбое — видимой части страницы."""
        try:
            # Мышь над ссылкой-источником раскрывает всплывающую карточку, и
            # она попадала в кадр поверх ответа (скан 24, 11.09.2026).
            await page.mouse.move(5, 5)
            await asyncio.sleep(0.4)
            # Раскрытый блок выше окна — снимаем кусками с прокруткой и
            # склеиваем, иначе в кадр попадает только его верх.
            return await shot.full_shot(page, box)
        except Exception as exc:
            log.info("Скриншот блока AI Overview не снялся (%s) — снимаю страницу", exc)
            return await page.screenshot(type="jpeg", quality=80, full_page=False)

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
