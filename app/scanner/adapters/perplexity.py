"""Адаптер Perplexity — пилотный сервис (см. этап 3 плана).

Селекторы сняты вживую через Playwright-инспекцию 28.08.2026:
``#ask-input`` — поле ввода (реальный DOM id, не сгенерированный), и
``.prose`` — контейнер текста ответа (класс Tailwind Typography, устойчивее
сгенерированных Radix-id, которые у вкладок меняются от рендера к рендеру).

Что подтверждено вживую: поле ввода, отправка по Enter, стена логина у
анонимных сессий, контейнер текста ответа. Что НЕ подтверждено (нет доступа к
реально залогиненному ответу на момент написания): точная разметка карточек
источников на вкладке «Ссылки». При первом реальном скане после логина стоит
свериться с дампом в data/debug — helper ``dump_debug_html`` сохраняет HTML
страницы при любой непредвиденной ошибке извлечения.
"""

from __future__ import annotations

import logging

from app.scanner import humanize
from app.scanner.adapters.base import (
    AdapterError,
    AuthRequiredError,
    Capture,
    ReadyState,
    dump_debug_html,
    load_selectors,
    focus_input,
    ensure_blank,
    safe_click,
    visible,
)

log = logging.getLogger("aiparser.adapters.perplexity")

_S = load_selectors()["perplexity"]


class PerplexityAdapter:
    service_id = "perplexity"
    display_name = "Perplexity"
    requires_auth = True  # см. app/services.py — это лишь подсказка для UI

    async def ensure_ready(self, page) -> ReadyState:
        await page.goto(_S["home_url"], wait_until="domcontentloaded")

        # Куки-баннер — одноразовый на профиль, но проверяем каждый раз:
        # дешевле одного лишнего клика, чем пропустить его после сброса кук.
        try:
            reject = page.get_by_role("button", name=_S["cookie_dialog_reject_button"])
            if await visible(reject, 3000):
                await safe_click(reject)
                await humanize.sleep(0.3, 0.7)
        except Exception:
            pass

        # Логин проверяем по кнопке «Войдите» в шапке — она есть только у
        # анонимных сессий. Сам факт открытия страницы ничего не гарантирует:
        # 28.08.2026 анонимная сессия открывалась нормально, а упиралась в
        # стену логина только после отправки запроса.
        try:
            signin_btn = page.get_by_role("button", name=_S["signin_nav_button"])
            if await visible(signin_btn, 3000):
                return ReadyState(ok=False, reason="auth_required")
        except Exception:
            pass

        await self._ensure_incognito(page)
        return ReadyState(ok=True)

    async def ask(self, page, query: str, region: str | None, *, speed: float = 1.0) -> None:
        await self._reset(page)
        await ensure_blank(page, _S["answer_container"], self.service_id, recover=lambda: self._reload(page))
        # Проверка дешёвая (подпись одной кнопки), а страхует от тихой потери
        # режима: после перезагрузки или разлогина Perplexity его сбрасывает.
        await self._ensure_incognito(page)
        await focus_input(page, _S["input"], self.service_id, recover=lambda: self._reload(page))
        await humanize.type_like_human(page, _S["input"], query, speed=speed, click=False)
        await page.keyboard.press("Enter")

        # Стена логина может появиться уже после отправки — сработавший
        # ensure_ready до этого её не видел.
        try:
            wall = page.get_by_text(_S["signin_wall_dialog_text"])
            # Намеренно мгновенная проверка: ждать по 4 секунды на каждом
            # запросе ради редкой стены дорого, а если модалка появится
            # позже, её выдаст отсутствие контейнера ответа ниже.
            if await wall.first.is_visible():
                raise AdapterError("Perplexity потребовал вход после отправки запроса")
        except AdapterError:
            raise
        except Exception:
            pass

        # Как и у Алисы/ChatGPT (см. их адаптеры): ждём появления самого
        # контейнера ответа, прежде чем следить за стабилизацией его текста
        # — иначе можно словить ложную «тишину» на промежуточном статусе.
        try:
            await page.locator(_S["answer_container"]).first.wait_for(state="attached", timeout=90000)
        except Exception:
            pass  # capture() сам обработает отсутствие контейнера как ошибку

        await humanize.wait_until_settled(page, _S["answer_container"], quiet_for=3.0, timeout=60.0)
        await humanize.scroll_through(page, speed=speed)

    async def _reset(self, page) -> None:
        """Возвращает страницу к пустому запросу без перезагрузки сайта.

        После ответа URL становится /search/<uuid>; чтобы задать следующий
        вопрос независимо, жмём «Новое» в сайдбаре — это SPA-переход, он на
        несколько секунд быстрее полной перезагрузки. Если ссылки нет
        (переверстали сайдбар) — честно откатываемся на goto.
        """
        try:
            link = page.get_by_role("link", name=_S["new_chat_link"], exact=True)
            if await visible(link.first, 3000):
                await safe_click(link.first)
                await humanize.sleep(0.4, 0.9)
                return
        except Exception:
            pass
        await page.goto(_S["home_url"], wait_until="domcontentloaded")

    async def _reload(self, page) -> None:
        """Полная перезагрузка — запасной путь восстановления. Инкогнито при этом
        слетает, поэтому включаем его заново, а не надеемся, что он пережил reload."""
        await page.goto(_S["home_url"], wait_until="domcontentloaded")
        await self._ensure_incognito(page)

    async def _ensure_incognito(self, page) -> None:
        """Включает режим инкогнито, если он выключен.

        Зачем: без него каждый запрос оседает отдельным тредом в истории
        аккаунта — на базе в 100 запросов это сотня мусорных чатов после
        каждого прогона. Один общий тред вместо этого не годится: Perplexity
        отвечает на следующий вопрос с учётом предыдущих, и бренд из одного
        ответа протекал бы в соседние, завышая видимость.

        Если включить не удалось (переверстали кнопку), запрос всё равно
        уходит — данные важнее чистоты истории, — но это пишется в лог, а не
        глотается молча.
        """
        try:
            # Сначала дожидаемся, пока страница оживёт: сразу после перехода
            # кнопки инкогнито ещё нет в DOM, и первый запрос 10.09.2026 из-за
            # этого ушёл в обычном режиме и осел в истории.
            await visible(page.locator(_S["input"]).first, 15000)
            active = page.get_by_role("button", name=_S["incognito_active_label"])
            if await visible(active.first, 1500):
                return
            enable = page.get_by_role("button", name=_S["incognito_enable_label"])
            if not await visible(enable.first, 3000):
                log.warning("Perplexity: кнопка инкогнито не найдена — запрос сохранится в истории")
                return
            await safe_click(enable.first)
            await active.first.wait_for(state="visible", timeout=5000)
            log.info("Perplexity: включён режим инкогнито")
        except Exception as exc:
            log.warning("Perplexity: не удалось включить инкогнито (%s) — запрос сохранится в истории",
                        type(exc).__name__)

    async def capture(self, page) -> Capture:
        try:
            answer_text = await page.inner_text(_S["answer_container"], timeout=5000)
        except Exception as exc:
            await dump_debug_html(page, "perplexity_no_answer")
            raise AdapterError(f"Не найден контейнер ответа: {exc}") from exc

        # Живой прогон 28.08.2026 показал: у стены логина Perplexity есть
        # ВТОРОЙ вариант — не только модальное окно (его ловит ask()), но и
        # инлайн-плейсхолдер прямо в контейнере ответа. Без этой проверки
        # он тихо проходил как обычный (пустой) ответ и портил статистику
        # видимости мнимым not_found.
        if answer_text.strip() == _S["signin_inline_placeholder"]:
            raise AuthRequiredError("Perplexity показал плейсхолдер входа вместо ответа")

        sources = await self._extract_sources(page)
        screenshot = await page.screenshot(type="jpeg", quality=80, full_page=False)

        return Capture(screenshot_bytes=screenshot, answer_text=answer_text.strip(), sources=sources)

    async def _extract_sources(self, page) -> list[str]:
        """Кликает вкладку «Ссылки» и берёт все внешние ссылки со страницы.

        Не целится в конкретный контейнер: живая проверка 28.08.2026 нашла
        два РАЗНЫХ вложенных набора Radix-вкладок на странице (внешний —
        Ответ/Ссылки/Изображения; внутренний, с другими id — canvas/pdf/
        citations/…), и без залогиненного ответа нельзя достоверно сказать,
        какой из них — настоящий контейнер карточек источников. Поэтому
        просто собираем все внешние ссылки и отсеиваем заведомо служебные
        (политику конфиденциальности, сам perplexity.ai) — это менее точно,
        чем прицельный селектор, зато не сломается от того, что я угадал
        неверный id. Исправить на точный селектор после первого реального
        скана — см. dump_debug_html и заметку в selectors.json.
        """
        try:
            tab = page.get_by_role("tab", name=_S["tab_sources"])
            if not await visible(tab, 2000):
                log.info("Вкладка «Ссылки» не найдена — дампаю страницу для разбора")
                await dump_debug_html(page, "perplexity_no_sources_tab")
                return []
            await safe_click(tab)
            await humanize.sleep(0.4, 0.9)

            hrefs = await page.locator("a[href^='http']").evaluate_all("els => els.map(e => e.href)")
            seen, out = set(), []
            for h in hrefs:
                if h in seen or _is_chrome_link(h):
                    continue
                seen.add(h)
                out.append(h)

            if not out:
                # Заметный случай: вкладка есть и открылась, но ни одной
                # <a href> не нашлось. Скорее всего цитаты — не ссылки, а
                # кликабельные чипы (кнопки/span с обработчиком) — тогда
                # a[href^='http'] в принципе не тот селектор. Дамп после
                # клика — единственный способ разобраться без гадания.
                log.info("Вкладка «Ссылки» открылась, но ссылок <a href> не нашлось")
                await dump_debug_html(page, "perplexity_sources_tab_empty")

            return out
        except Exception as exc:
            log.info("Не удалось извлечь источники Perplexity: %s", exc)
            await dump_debug_html(page, "perplexity_sources_exception")
            return []


_CHROME_HOSTS = ("perplexity.ai", "perplexity.com", "accounts.google.com", "appleid.apple.com")


def _is_chrome_link(url: str) -> bool:
    return any(h in url for h in _CHROME_HOSTS)
