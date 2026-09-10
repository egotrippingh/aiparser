"""Контракт адаптера и утилиты, общие для всех источников.

Каждый адаптер отвечает за один сервис: подготовку страницы (логин, куки-
баннеры, капча), отправку запроса человекоподобным тайпингом и извлечение
результата. Всё, что можно вынести за пределы кода — CSS-селекторы,
URL-шаблоны — вынесено в selectors.json, чтобы правка вёрстки сервиса не
требовала пересборки приложения.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

_SELECTORS_PATH = Path(__file__).with_name("selectors.json")
_log = logging.getLogger("aiparser.adapters")


def load_selectors() -> dict:
    return json.loads(_SELECTORS_PATH.read_text(encoding="utf-8"))


async def visible(locator, timeout: float = 3000) -> bool:
    """Ждёт, пока элемент станет видимым; True/False вместо исключения.

    Замена `locator.is_visible(timeout=…)`: в установленном Playwright этот
    параметр объявлен устаревшим и ИГНОРИРУЕТСЯ — is_visible отвечает
    мгновенно. До 10.09.2026 на него полагались 12 мест в адаптерах, включая
    проверку входа у ChatGPT и Алисы: не успей страница догрузиться — сервис
    объявлялся «требует входа». Работало лишь потому, что успевала. У
    Perplexity так и терялся режим инкогнито: кнопку «не находили» за 0 с.
    """
    try:
        await locator.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:
        return False


async def safe_click(locator, *, timeout: float = 3000) -> None:
    """Клик, который переживает свёрнутое окно браузера.

    Эксперимент 10.09.2026: когда окно Camoufox свёрнуто, Firefox перестаёт
    выдавать кадры анимации (requestAnimationFrame), и Playwright не может
    дождаться «стабильности» элемента — падают и обычный click(), и
    click(force=True). Работает только DOM-метод el.click(). Он синтетический
    (isTrusted=false), поэтому это лишь запасной путь: пока окно на экране,
    клик идёт обычный, неотличимый от человеческого.
    """
    try:
        await locator.click(timeout=timeout)
    except Exception:
        _log.info("Обычный клик не прошёл (окно, видимо, свёрнуто) — кликаю через DOM")
        await locator.evaluate("el => el.click()", timeout=timeout)


async def _focus_without_click(locator) -> bool:
    """Фокус через DOM — не требует кадров анимации, работает в свёрнутом окне."""
    try:
        await locator.focus(timeout=5000)
        return bool(await locator.evaluate(
            "el => el === document.activeElement || el.contains(document.activeElement)",
            timeout=3000,
        ))
    except Exception:
        return False


_RAF_JS = """() => new Promise(res => {
    let done = false;
    requestAnimationFrame(() => { done = true; res(true); });
    setTimeout(() => { if (!done) res(false); }, 1000);
})"""


async def dump_debug_html(page, tag: str) -> None:
    """Сохраняет HTML страницы при сбое извлечения — по нему чинится selectors.json.

    Общий для всех адаптеров: правка вёрстки любого сервиса ловится одним и
    тем же способом, не нужно копировать эту функцию в каждый файл.
    """
    try:
        from app import config

        html = await page.content()
        (config.DEBUG_DIR / f"{tag}.html").write_text(html, encoding="utf-8")
    except Exception:
        _log.warning("Не удалось сохранить debug-дамп для %s", tag, exc_info=True)


async def require_input(page, selector: str, service_id: str, *, timeout: float = 15000) -> None:
    """Дожидается поля ввода; его отсутствие — это стена лимита, а не просто таймаут.

    Раньше отсутствие поля выражалось в 30-секундном таймауте клика, и такие
    таймауты копились десятками подряд, засоряя статистику статусом "error".
    Ждём меньше и называем причину своим именем, а страницу сохраняем в
    data/debug — по ней потом видно, что именно показал сервис.
    """
    try:
        await page.locator(selector).first.wait_for(state="visible", timeout=timeout)
    except Exception as exc:
        await dump_debug_html(page, f"{service_id}_no_input")
        raise ServiceUnavailableError(
            f"{service_id}: поле ввода не появилось за {timeout / 1000:.0f}с — "
            "похоже на лимит тарифа или блокировку"
        ) from exc


async def dump_debug_screenshot(page, tag: str) -> None:
    """Скриншот рядом с HTML-дампом: по вёрстке не всегда видно, что перекрыло поле."""
    try:
        from app import config

        await page.screenshot(path=str(config.DEBUG_DIR / f"{tag}.png"), full_page=False)
    except Exception:
        _log.warning("Не удалось сохранить debug-скриншот для %s", tag, exc_info=True)


_WHY_BLOCKED_JS = """el => {
    const r = el.getBoundingClientRect();
    const chain = [];
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
        const marks = [];
        if (n.getAttribute('aria-disabled') === 'true') marks.push('aria-disabled');
        if (n.hasAttribute('inert')) marks.push('inert');
        if (n.getAttribute('aria-hidden') === 'true') marks.push('aria-hidden');
        if (marks.length) chain.push(n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + '[' + marks.join(',') + ']');
    }
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    const covered = top && top !== el && !el.contains(top)
        ? top.tagName.toLowerCase() + '.' + String(top.className || '').slice(0, 50)
          + ' «' + (top.textContent || '').trim().slice(0, 70) + '»'
        : null;
    return {box: [r.x, r.y, r.width, r.height].map(Math.round), blocked_by: chain, covered_by: covered};
}"""


async def _why_blocked(page, selector: str) -> str:
    """Что мешает кликнуть по полю: блокирующий атрибут у предка или чужой элемент поверх."""
    try:
        info = await page.locator(selector).first.evaluate(_WHY_BLOCKED_JS)
        # false здесь = окно свёрнуто или закрыто другими окнами: главная
        # подтверждённая причина «видно, но не кликается».
        info["animation_frames"] = await page.evaluate(_RAF_JS)
        return json.dumps(info, ensure_ascii=False)
    except Exception as exc:
        return f"диагностика не удалась ({type(exc).__name__})"


async def focus_input(page, selector: str, service_id: str, *, recover) -> None:
    """Готовит поле ввода к печати: дожидается, кликает, один раз пробует восстановиться.

    Живой случай 09.09.2026: у ChatGPT поле было на странице и видимо, но клик
    30 секунд ждал «visible, enabled and stable» и падал — 17 раз за два
    прогона, всегда в конце длинной сессии. Этот путь не сохранял страницу и
    не считался стеной лимита, поэтому каждый такой запрос молча съедал
    полминуты, а причину установить было нечем.

    Причина установлена экспериментом 10.09.2026: окно браузера было свёрнуто
    или закрыто другими окнами, Firefox переставал выдавать кадры анимации,
    и Playwright не мог дождаться «стабильности» поля. Поэтому после обычного
    клика идёт фокус через DOM — он кадров не требует, и печать после него
    работает. Если не помогло и это — причина пишется в текст ошибки,
    страница и скриншот сохраняются в data/debug, затем Escape и `recover()`.
    Не помогло совсем — ServiceUnavailableError, и оркестратор после трёх
    таких подряд остановит сервис.
    """
    await require_input(page, selector, service_id)
    loc = page.locator(selector).first
    try:
        await loc.click(timeout=3000)
        return
    except Exception:
        pass

    if await _focus_without_click(loc):
        _log.info("%s: поле сфокусировано без клика — окно браузера, видимо, свёрнуто", service_id)
        return

    why = await _why_blocked(page, selector)
    _log.warning("%s: поле ввода видно, но не кликается — %s", service_id, why)
    await dump_debug_html(page, f"{service_id}_input_blocked")
    await dump_debug_screenshot(page, f"{service_id}_input_blocked")

    try:
        await page.keyboard.press("Escape")
        await recover()
        await require_input(page, selector, service_id)
        loc = page.locator(selector).first
        try:
            await loc.click(timeout=3000)
        except Exception:
            if not await _focus_without_click(loc):
                raise
        _log.info("%s: поле ввода разблокировано после восстановления", service_id)
        return
    except ServiceUnavailableError:
        raise
    except Exception:
        pass

    raise ServiceUnavailableError(f"{service_id}: поле ввода заблокировано и после перезагрузки — {why}")


async def ensure_blank(page, answer_selector: str, service_id: str, *, recover) -> None:
    """Проверяет, что перед запросом на странице нет ответов от прошлых запросов.

    Инвариант, которого не хватало до 10.09.2026: у ChatGPT «Новый чат» тихо
    не срабатывал, и 69 запросов платного прогона ушли в один тред. Это
    испортило данные дважды — ответы учитывали предыдущие вопросы, а
    ожидание следило за первым (старым) ответом и снимало последний
    недописанным. Теперь, если после сброса остались чужие ответы, пробуем
    `recover()`, а не вышло — запрос не отправляем вовсе: пустая строка
    «ошибка» честнее, чем правдоподобный, но загрязнённый результат.
    """
    loc = page.locator(answer_selector)
    for _ in range(6):                 # SPA-переход может выгружать старый DOM не мгновенно
        if await loc.count() == 0:
            return
        await asyncio.sleep(0.5)

    _log.warning("%s: после сброса на странице остались старые ответы — перезагружаю", service_id)
    await recover()
    n = await loc.count()
    if n:
        raise AdapterError(
            f"{service_id}: не удалось открыть чистый чат — на странице {n} старых ответов; "
            "запрос не отправлен, чтобы не смешать контекст"
        )


@dataclass
class ReadyState:
    ok: bool
    reason: str | None = None   # "auth_required" | "captcha" | None


@dataclass
class Capture:
    screenshot_bytes: bytes
    answer_text: str
    sources: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    shown: bool = True  # False — блок ИИ-ответа не появился (валидный результат, не ошибка)


class SearchAdapter(Protocol):
    service_id: str
    display_name: str
    requires_auth: bool

    async def ensure_ready(self, page) -> ReadyState:
        """Открывает сессию сервиса: переход на сайт, куки-баннер, проверка логина.

        Вызывается ОДИН РАЗ на сервис, а не на каждый запрос: полная
        перезагрузка сайта перед каждым запросом стоила ~6 секунд и была
        главным источником «бесконечных перезапусков браузера».
        """
        ...

    async def ask(self, page, query: str, region: str | None, *, speed: float = 1.0) -> None:
        """Приводит страницу в чистое состояние под новый запрос и отправляет его.

        Поскольку `ensure_ready` больше не вызывается перед каждым запросом,
        сброс состояния — обязанность самого адаптера: для чатов это «Новый
        чат», для поисковиков — переход на главную.

        Бросает ServiceUnavailableError, если поле ввода не появилось: это
        признак стены лимита, а не повод молча ждать таймаут.
        """
        ...

    async def capture(self, page) -> Capture:
        """Снимает скриншот, текст ответа и список источников."""
        ...


class AdapterError(RuntimeError):
    """Адаптер не смог довести шаг до конца — техническая ошибка, не капча и не авторизация."""


class AuthRequiredError(AdapterError):
    """Стена логина обнаружена уже ПОСЛЕ ensure_ready — например, инлайн-плейсхолдер
    в самом контейнере ответа вместо отдельного модального окна (у Perplexity
    28.08.2026 нашлись оба варианта одновременно). Оркестратор сохраняет такой
    результат как status="auth_required", а не "error" — это не сбой, а
    честный сигнал «нужно перелогиниться», который иначе тихо просочился бы
    в статистику как not_found и занизил бы видимость бренда."""


class ServiceUnavailableError(AdapterError):
    """Сервис сейчас не принимает запросы — чаще всего упёрлись в лимит тарифа.

    Наблюдаемый признак, по которому это ловится: поле ввода исчезает со
    страницы. Именно так это выглядело в реальном прогоне 28.08.2026 —
    Perplexity отдал 44 ответа, ChatGPT 41, после чего оба показывали страницу
    без поля ввода до конца прогона (56 и 59 подряд одинаковых таймаутов по
    30 секунд каждый). Через три дня квота сбросилась сама и поле вернулось —
    то есть стена временная, а не поломка.

    Оркестратор, поймав это подряд несколько раз, прекращает сервис целиком:
    смысла добивать оставшиеся запросы нет, а стоит это полчаса таймаутов.
    """


class CaptchaError(AdapterError):
    """Антибот показал капчу/интерстишл вместо результата (у Google это редирект
    на google.com/sorry/ — живой прогон 28.08.2026 поймал это дважды подряд на
    свежем профиле). Оркестратор сохраняет статус "captcha", а не "error" —
    это отдельная, ожидаемая причина отсутствия данных, не сбой кода."""
