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
import io
import logging
import time

from PIL import Image

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

# Геометрия для скриншота длинного ответа: у чата Алисы своя прокрутка внутри
# блока, а поле ввода висит поверх его низа. Помечаем прокручиваемый блок,
# чтобы потом двигать именно его, и отдаём полосу окна, где ответ виден.
_GEOMETRY_JS = """(el, inputSel) => {
  let s = el.parentElement;
  while (s && !(s.scrollHeight > s.clientHeight + 4 && /(auto|scroll)/.test(getComputedStyle(s).overflowY))) {
    s = s.parentElement;
  }
  document.querySelectorAll('[data-aimt-scroller]').forEach(x => x.removeAttribute('data-aimt-scroller'));
  if (s) s.setAttribute('data-aimt-scroller', '1');
  const sr = s ? s.getBoundingClientRect() : { top: 0, bottom: innerHeight };
  const inp = document.querySelector(inputSel);
  const bar = inp ? (inp.closest('[data-testid="standalone-input"]') || inp) : null;
  const barTop = bar ? bar.getBoundingClientRect().top : innerHeight;
  const top = Math.max(sr.top, 0);
  const bottom = Math.min(sr.bottom, barTop, innerHeight);
  return { hasScroller: !!s, height: el.getBoundingClientRect().height, top, bottom };
}"""

# Прокрутить чат так, чтобы точка ответа `offset` оказалась у верхнего края
# видимой полосы; вернуть, где ответ оказался на самом деле (у конца чата
# прокрутка упирается в предел).
_SCROLL_JS = """(el, a) => {
  const s = document.querySelector('[data-aimt-scroller]');
  if (s) s.scrollTop += (el.getBoundingClientRect().top + a.offset) - a.top;
  const r = el.getBoundingClientRect();
  return { x: r.left, width: r.width, top: r.top };
}"""

_MAX_SLICES = 15


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

    async def _new_chat(self, page) -> None:
        """Новый пустой чат — переходом на главную, а не кликом по «Новый чат».

        11.09.2026 клик по кнопке в боковой панели однажды попал в соседний
        пункт «Оживить фото»: открылась Студия, где нет поля ввода, запрос ушёл
        в никуда, и проверка 4,5 минуты ждала ответа, прежде чем записать
        ошибку. Главная Алисы всегда открывает пустой чат — как временный
        чат ChatGPT по адресу; пара секунд загрузки того стоит.
        """
        await page.goto(_S["home_url"], wait_until="domcontentloaded")
        await visible(page.locator(_S["input"]).first, 20000)

    async def ask(self, page, query: str, region: str | None, *, speed: float = 1.0) -> None:
        # Новый чат перед каждым запросом — и чтобы предыдущий контекст не
        # влиял на ответ, и чтобы answer_container оставался однозначным
        # (см. заметку в модуле).
        await self._new_chat(page)
        await humanize.sleep(0.4 * speed, 0.9 * speed)

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
        """Скриншот ответа целиком.

        Короткий ответ — одним снимком элемента. Длинный в окно не влезает, а
        чат Алисы прокручивается внутри своего блока: Firefox рисует только
        видимую часть, и снимок элемента выходил наполовину чёрным — пропадал
        как раз верх ответа (11.09.2026). Такой ответ снимаем кусками,
        прокручивая чат, и склеиваем.
        """
        try:
            await page.mouse.move(5, 5)  # всплывающие карточки ссылок не должны попасть в кадр
            geo = await answer.evaluate(_GEOMETRY_JS, _S["input"])
            if not geo["hasScroller"] or geo["height"] <= geo["bottom"] - geo["top"]:
                return await answer.screenshot(type="jpeg", quality=80, timeout=8000)
            return await self._stitch(page, answer, geo)
        except Exception as exc:
            log.info("Скриншот ответа Алисы не снялся (%s) — снимаю окно", exc)
            return await page.screenshot(type="jpeg", quality=80, full_page=False)

    async def _stitch(self, page, answer, geo: dict) -> bytes:
        total = geo["height"]
        slices: list[bytes] = []
        offset = 0.0
        while offset < total - 1 and len(slices) < _MAX_SLICES:
            r = await answer.evaluate(_SCROLL_JS, {"offset": offset, "top": geo["top"]})
            await asyncio.sleep(0.3)  # дать дорисоваться после прокрутки
            y = max(geo["top"], r["top"] + offset)
            h = min(total - offset, geo["bottom"] - y)
            if h < 1:
                break
            slices.append(await page.screenshot(
                type="png", clip={"x": r["x"], "y": y, "width": r["width"], "height": h},
            ))
            offset += h
        return _glue(slices)

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


def _glue(slices: list[bytes]) -> bytes:
    """Склеивает куски скриншота сверху вниз в один JPEG."""
    images = [Image.open(io.BytesIO(b)).convert("RGB") for b in slices]
    out = Image.new("RGB", (max(i.width for i in images), sum(i.height for i in images)), "white")
    y = 0
    for im in images:
        out.paste(im, (0, y))
        y += im.height
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=80)
    return buf.getvalue()
