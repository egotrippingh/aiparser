"""Адаптер ChatGPT (chatgpt.com).

Селекторы сняты вживую 28.08.2026 на реальном залогиненном аккаунте:
``#prompt-textarea`` (ProseMirror, contenteditable) и
``[data-message-author-role="assistant"]`` — известный по множеству других
инструментов устойчивый паттерн разметки ChatGPT, не привязанный к
сгенерированным id.

Источники НЕ проверены живьём: обычный ответ без включённого веб-поиска их
не показывает, а решение искать ли в интернете ChatGPT принимает сам по
запросу. `_extract_sources` просто собирает все `<a href>` внутри ответа —
сработает само, когда модель реально процитирует источники.
"""

from __future__ import annotations

import logging

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

log = logging.getLogger("aiparser.adapters.chatgpt")

_S = load_selectors()["chatgpt"]

# Короче этого настоящих ответов на наши запросы не бывает: у бесплатного
# прогона 28.08 самый короткий был 647 символов, а заглушки вида «Думаю» —
# 5–150.
_MIN_ANSWER_CHARS = 60


class ChatGPTAdapter:
    service_id = "chatgpt"
    display_name = "ChatGPT"
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
        # Новый чат перед каждым запросом: контекст предыдущего не должен
        # влиять на ответ (план прямо это требует), и заодно это единственный
        # способ гарантировать, что answer_container останется однозначным.
        # Это SPA-клик, а не перезагрузка сайта — сам сайт грузится один раз
        # в ensure_ready на весь сервис.
        await self._new_chat(page)
        await humanize.sleep(0.5 * speed, 1.0 * speed)

        await focus_input(
            page, _S["input"], self.service_id,
            recover=lambda: page.goto(_S["temporary_url"], wait_until="domcontentloaded"),
        )
        await humanize.type_like_human(page, _S["input"], query, speed=speed, click=False)
        await page.keyboard.press("Enter")

        # Как и у Алисы (см. её адаптер): на запросах с веб-поиском ChatGPT
        # тоже проходит через промежуточные статусы до появления самого
        # сообщения-ответа — ждём сначала контейнер, потом стабилизацию
        # именно его текста, а не всего треда целиком.
        await self._wait_done(page)
        await humanize.scroll_through(page, speed=speed)

    async def _new_chat(self, page) -> None:
        """Новый пустой ВРЕМЕННЫЙ чат перед каждым запросом.

        Переход по адресу временного чата, а не клик по «Новый чат»: кнопок
        с этим testid две — в узкой полосе и в развёрнутом сайдбаре, — и
        первую перекрывает сайдбар. Клик 30 секунд ждал и падал, исключение
        глоталось, и весь платный прогон 09–10.09.2026 шёл одним тредом.

        Временный чат, а не обычный, — по двум причинам. Он не оседает в
        истории аккаунта (иначе сотня мусорных чатов после каждого прогона), и
        в нём, по словам самого ChatGPT, не учитываются память и
        пользовательские инструкции: ответ ближе к тому, что увидит новый
        пользователь, а не хозяин аккаунта со своей персонализацией.
        """
        async def fresh():
            await page.goto(_S["temporary_url"], wait_until="domcontentloaded")
            await visible(page.locator(_S["input"]).first, 20000)

        await fresh()
        if not await visible(page.get_by_role("button", name=_S["temporary_active_label"]), 5000):
            # Данные важнее чистоты истории: запрос уходит, но это видно в логе.
            log.warning("ChatGPT: временный чат не включился — запрос сохранится в истории "
                        "и может учесть персонализацию аккаунта")
        await ensure_blank(page, _S["answer_container"], self.service_id, recover=fresh)

    async def _wait_done(self, page) -> None:
        """Ждёт, пока ответ реально дописан.

        Признак — кнопка «оценить» под ответом: появляется только по
        завершении (проверено 10.09.2026 на платном аккаунте). «Текст перестал
        расти» здесь не годится: рассуждающая модель дольше трёх секунд
        показывает «Думаю» и «Поиск на N сайтах», и такие заглушки уходили в
        базу как ответ.
        """
        try:
            await page.locator(_S["answer_container"]).first.wait_for(state="attached", timeout=90000)
        except Exception:
            return  # capture() честно упадёт на отсутствии ответа
        try:
            await page.locator(_S["done_marker"]).last.wait_for(state="visible", timeout=240000)
            await humanize.sleep(0.8, 1.5)
        except Exception:
            log.warning("ChatGPT: признак завершения не появился за 4 минуты — снимаю по стабилизации текста")
            await humanize.wait_until_settled(page, _S["answer_container"], quiet_for=5.0, timeout=60.0)

    async def capture(self, page) -> Capture:
        try:
            # Locator.last, а не page.inner_text(selector): последний надёжнее
            # строгого режима Playwright, который упал бы при более чем одном
            # совпадении, если клик по «новому чату» вдруг не сработал.
            answer_text = await page.locator(_S["answer_container"]).last.inner_text(timeout=5000)
        except Exception as exc:
            await dump_debug_html(page, "chatgpt_no_answer")
            raise AdapterError(f"Не найден контейнер ответа ChatGPT: {exc}") from exc

        # Страховка от недождавшегося ответа: при любом сбое ожидания лучше
        # «ошибка» и перепроверка, чем заглушка «Думаю» в роли ответа и ложное
        # «не найдено» в статистике.
        if len(answer_text.strip()) < _MIN_ANSWER_CHARS:
            await dump_debug_html(page, "chatgpt_incomplete_answer")
            raise AdapterError(f"ChatGPT: ответ не дописан ({len(answer_text.strip())} симв.: "
                               f"{answer_text.strip()[:60]!r})")

        sources = await self._extract_sources(page)
        # Снимок только самого ответа. На снимке всего экрана модель OpenRouter
        # видела и вопрос, и соседние сообщения — 10.09.2026 она «нашла» бренд
        # в плашке-источнике предыдущего ответа.
        try:
            screenshot = await page.locator(_S["answer_container"]).last.screenshot(
                type="jpeg", quality=80, timeout=8000)
        except Exception:
            screenshot = await page.screenshot(type="jpeg", quality=80, full_page=False)

        return Capture(screenshot_bytes=screenshot, answer_text=answer_text.strip(), sources=sources)

    async def _extract_sources(self, page) -> list[str]:
        try:
            hrefs = await page.locator(_S["answer_container"]).last.locator(
                "a[href^='http']"
            ).evaluate_all("els => els.map(e => e.href)")
            seen, out = set(), []
            for h in hrefs:
                if h in seen:
                    continue
                seen.add(h)
                out.append(h)
            return out
        except Exception as exc:
            log.info("Не удалось извлечь источники ChatGPT: %s", exc)
            return []
