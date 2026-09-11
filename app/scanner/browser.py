"""Camoufox context factory: один персистентный профиль на сервис.

Аккаунт ChatGPT (или кука Perplexity) один на всё приложение — профиль
привязан к `service_id`, а не к проекту, иначе на каждый новый проект
пришлось бы логиниться заново.

Режим фиксирован планом: видимое окно, последовательно, один контекст в
моменте. Никакого headless и никакой параллельности — это осознанный размен
скорости на выживаемость сессий и подробно объяснён в плане.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from camoufox.async_api import AsyncCamoufox
from camoufox.exceptions import InvalidIP, InvalidProxy, NotInstalledGeoIPExtra, UnknownIPLocation

from app import config

log = logging.getLogger("aiparser.browser")

# Camoufox рекомендует не выбиваться из распределения реального трафика:
# Windows — самая частая ОС у обычных пользователей, редкие конфигурации
# (Linux + нестандартное разрешение) чаще ловят капчу.
_DEFAULT_LAUNCH = dict(
    os="windows",
    humanize=True,
    headless=False,
    # Обязателен даже без явного прокси: синхронизирует часовой пояс и
    # локаль с реальным исходящим IP (в т.ч. с системным VPN). Рассинхрон
    # timezone/IP — один из самых грубых сигналов бота.
    geoip=True,
    # НЕ полагаемся на то, что locale подтянется из geoip: когда geoip не
    # смог определить IP (см. _looks_like_geoip_failure — с нынешним VPN
    # это происходит стабильно), Camoufox остаётся без сигнала локали, и
    # живой прогон 28.08.2026 показал результат — интерфейс Perplexity
    # отрендерился по-английски. Все текстовые селекторы (кнопки, вкладки)
    # в selectors.json написаны под русский UI, и подмена языка ломает их
    # молча — печать в этом же прогоне оборвалась на середине запроса,
    # судя по всему, из-за баннера cookie на английском, который не
    # опознала «Отклонить необязательные». Фиксируем локаль явно и
    # безусловно — она не зависит от того, удался ли geoip.
    locale="ru-RU",
)

# Окна Camoufox открыты на рабочем столе пользователя, и он закрывает их
# своими окнами. Firefox считает полностью перекрытое окно скрытым (window
# occlusion tracking) и душит в нём таймеры и отрисовку — ответ нейросети в
# таком окне не дорисовывается. Живой скан 11.09.2026 стоял по 4–6 минут и
# пошёл дальше через 15 секунд после того, как перекрывавшее окно свернули.
# Свёрнутое окно Firefox всё равно притормаживает — поэтому только перекрытие.
_FIREFOX_PREFS = {
    "widget.windows.window_occlusion_tracking.enabled": False,
    "dom.min_background_timeout_value": 4,
    "dom.min_background_timeout_value_without_budget_throttling": 4,
    "dom.timeout.enable_budget_timer_throttling": False,
}
# issue #537 (github.com/daijro/camoufox/issues/537) описывает битые символы в
# persistent-контексте и советует extra_http_headers={"accept-encoding": "identity"}.
# Намеренно НЕ включаем это по умолчанию: настоящий Firefox всегда шлёт
# "gzip, deflate, br, zstd", а принудительный identity — сам по себе сигнал
# рассинхрона для антибота. Включать только если баг реально воспроизведётся
# на используемой версии Camoufox.


# Кэш результата geoip на время сессии приложения. geoip=True заставляет
# Camoufox сходить за публичным IP через системный прокси/VPN; если тот
# недоступен, запуск падает ДО открытия окна, и мы поднимаем браузер второй
# раз уже без geoip. На VPN пользователя это происходит стабильно — то есть
# каждый сервис платил полным лишним запуском браузера. Один раз выяснив, что
# geoip не резолвится, дальше не пробуем.
_geoip_works: bool | None = None


def reset_geoip_cache() -> None:
    """Сбросить кэш — например, когда пользователь поменял VPN и хочет заново."""
    global _geoip_works
    _geoip_works = None


def camoufox_installed() -> bool:
    try:
        from camoufox.pkgman import camoufox_path

        camoufox_path(download_if_missing=False)
        return True
    except Exception:
        return False


class BrowserUnavailable(RuntimeError):
    """Camoufox ещё не скачан — нужно пройти мастер первого запуска."""


@asynccontextmanager
async def service_context(service_id: str, *, window: tuple[int, int] = (1360, 900)) -> AsyncGenerator:
    """Персистентный контекст для одного сервиса; вкладку открывает вызывающий код."""
    if not camoufox_installed():
        raise BrowserUnavailable(
            "Браузер Camoufox не установлен. Откройте Настройки → «Скачать браузер»."
        )

    profile = config.profile_dir(service_id)
    log.info("launching camoufox for %s (profile=%s)", service_id, profile)

    global _geoip_works

    # Копия настроек на каждый запуск: Camoufox дописывает в этот словарь свои ключи.
    launch = dict(persistent_context=True, user_data_dir=str(profile), window=window,
                  firefox_user_prefs=dict(_FIREFOX_PREFS), **_DEFAULT_LAUNCH)
    if _geoip_works is False:
        # Уже знаем, что geoip в этой сессии не работает — не тратим на него
        # ещё один запуск браузера.
        launch["geoip"] = False

    try:
        try:
            async with AsyncCamoufox(**launch) as context:
                if launch.get("geoip") is not False:
                    _geoip_works = True
                yield context
        except Exception as exc:
            # geoip=True требует сходить в интернет за публичным IP (через
            # системный прокси/VPN, если он есть). Если в моменте прокси
            # недоступен, Camoufox бросает ошибку ДО открытия окна — весь скан
            # падает из-за одной неудачной геолокации, хотя сам браузер рабочий.
            # Это реальный сценарий: у пользователя VPN, который планом же и
            # предусмотрен как основной способ сети, а не гипотетический риск.
            if not _looks_like_geoip_failure(exc):
                raise
            _geoip_works = False
            log.warning(
                "geoip=True не смог определить IP (%s) — перезапускаю %s без geoip. "
                "Часовой пояс браузера может не совпасть с реальным IP. "
                "Дальнейшие запуски в этой сессии сразу идут без geoip.",
                exc, service_id,
            )
            async with AsyncCamoufox(**{**launch, "geoip": False}) as context:
                yield context
    finally:
        # Подстраховка независимо от того, как завершился контекст (успешно,
        # с ошибкой, из-за того что пользователь закрыл окно руками). Живые
        # прогоны 28.08.2026 дважды показали: мультипроцессный Firefox иногда
        # не убивает все дочерние процессы (GPU/RDD/content) сразу же после
        # закрытия окна, и `parent.lock` остаётся занят минутами — следующий
        # запуск валится с «Failed to launch the browser process». Штатное
        # закрытие через __aexit__ выше не гарантирует этого — проверяем
        # явно и, если не отпустило само, добиваем процессы руками.
        await _ensure_profile_released(profile)


# Все варианты, которыми Camoufox сигналит о провале geoip-резолва: не смог
# получить публичный IP (сеть/прокси недоступны в моменте — InvalidIP),
# прокси задан, но недоступен (InvalidProxy), IP получен, но geoip2 не смог
# определить локацию (UnknownIPLocation), либо экстра geoip2 не установлена
# (NotInstalledGeoIPExtra — на случай, если requirements разъедутся).
_GEOIP_EXCEPTIONS: tuple[type[Exception], ...] = (
    InvalidIP, InvalidProxy, UnknownIPLocation, NotInstalledGeoIPExtra,
)


def _looks_like_geoip_failure(exc: Exception) -> bool:
    return isinstance(exc, _GEOIP_EXCEPTIONS)


def _lock_is_free(lock: Path) -> bool:
    """Открываемость на дозапись — простой и надёжный тест «никто не держит файл» на Windows."""
    try:
        with open(lock, "a"):
            return True
    except OSError:
        return False


async def _kill_processes_for_profile(profile: Path) -> None:
    """Прибивает camoufox.exe, в командной строке которых путь именно этого профиля.

    Чужие профили (других сервисов) не трогает — фильтр по CommandLine, не
    по имени процесса. Требует PowerShell 5.1+ с Get-CimInstance, что на
    целевой Windows 10/11 есть из коробки.
    """
    needle = str(profile).replace("'", "''")
    script = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.Name -eq 'camoufox.exe' -and $_.CommandLine -like '*{needle}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", script,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
    except Exception:
        log.warning("Не удалось принудительно завершить процессы Camoufox для %s", profile, exc_info=True)


async def _ensure_profile_released(profile: Path, timeout: float = 6.0) -> None:
    """Ждёт освобождения профиля и, если не дождалась, добивает процессы руками.

    Нормальный путь — lock освобождается сам за доли секунды после закрытия
    контекста, и цикл ниже проходит один раз без задержки. Ветка с
    принудительным убийством — редкий, но реально наблюдавшийся случай.
    """
    lock = profile / "parent.lock"
    if not lock.exists() or _lock_is_free(lock):
        return

    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if _lock_is_free(lock):
            return
        await asyncio.sleep(0.5)

    if _lock_is_free(lock):
        return

    log.warning(
        "Профиль %s не освободился за %.0fс после закрытия браузера — "
        "принудительно завершаю зависшие процессы Camoufox",
        profile, timeout,
    )
    await _kill_processes_for_profile(profile)


async def open_login_window(service_id: str, login_url: str) -> None:
    """Открывает окно на странице логина и ждёт, пока пользователь его не закроет.

    Закрытие окна — единственный сигнал готовности, который не зависит от
    вёрстки конкретного сервиса. Пользователь логинится сам, ровно как в
    обычном браузере.

    Событие "close" самой СТРАНИЦЫ у Playwright ловится надёжнее, чем
    закрытие контекста в мультипроцессном Firefox, поэтому ждём именно его,
    а контекст после этого закрываем явно сами. Даже так живые прогоны
    28.08.2026 дважды показали дочерние процессы (GPU/RDD/content),
    пережившие оба этих шага, — от них страхует `_ensure_profile_released`
    внутри `service_context`, который прибивает зависшее принудительно.
    """
    entered = False
    try:
        async with service_context(service_id) as context:
            entered = True
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(login_url, wait_until="domcontentloaded")
            try:
                await page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass
    except Exception:
        if not entered:
            # Браузер не запустился вообще (не установлен, сбой Camoufox) —
            # это настоящая ошибка, её нужно показать пользователю, а не
            # проглатывать молча.
            raise
        # Штатный путь: закрытие контекста при выходе из `async with` уже
        # само по себе закрыто явным вызовом выше — сюда попадает разве что
        # повторная попытка закрыть уже закрытый контекст в __aexit__.
