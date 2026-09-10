"""Сетевые клиенты приложения и обход кривого системного прокси Windows.

Проблема, подтверждённая на машине пользователя 09.09.2026. Python читает
настройки прокси из реестра Windows (WinINET) и отдаёт их так:

    {'http': 'http://127.0.0.1:10809', 'https': 'https://127.0.0.1:10809'}

Схема у второй записи — `https`, хотя сам прокси-сервер (клиент VPN) говорит
по обычному HTTP. httpx честно пытается установить TLS-соединение с
HTTP-прокси и падает мгновенно с ConnectError. Внешне это выглядит как «нет
интернета», хотя интернет есть: тот же адрес прекрасно открывается, если
прокси не использовать вовсе или обратиться к нему по http.

Отсюда два разных клиента:

* `direct_client` — принципиально мимо прокси (`trust_env=False`). Для
  страниц-источников: это в основном российские сайты, им VPN не нужен, а
  лишний прыжок только добавляет задержек и зависит от того, поднят ли
  туннель в данную секунду.
* `proxied_client` — через системный прокси с исправленной схемой. Для
  OpenRouter, который из России без VPN может быть недоступен.
"""

from __future__ import annotations

import logging
import urllib.request

import httpx

log = logging.getLogger("aiparser.net")

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
)


def system_proxy() -> str | None:
    """Системный прокси с починенной схемой, либо None, если его нет.

    Возвращаем один URL: httpx умеет принимать `proxy=` строкой и направлять
    туда весь трафик, а разделять http/https-прокси в нашем случае незачем —
    это один и тот же локальный порт.
    """
    proxies = urllib.request.getproxies()
    raw = proxies.get("https") or proxies.get("http")
    if not raw:
        return None

    # Вот та самая починка: прокси-сервер слушает обычный HTTP, какую бы
    # схему ни записал в реестр WinINET.
    if raw.startswith("https://"):
        raw = "http://" + raw[len("https://"):]
    return raw


def direct_client(*, timeout: float = 12.0, **kwargs) -> httpx.AsyncClient:
    """Клиент в обход прокси — для чужих страниц-источников."""
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        **kwargs.pop("headers", {}),
    }
    return httpx.AsyncClient(
        headers=headers, timeout=timeout, follow_redirects=True, trust_env=False, **kwargs
    )


def proxied_client(*, timeout: float = 45.0, **kwargs) -> httpx.AsyncClient:
    """Клиент через системный прокси (если он есть) — для внешних API."""
    proxy = system_proxy()
    if proxy:
        log.debug("Использую системный прокси: %s", proxy)
    # trust_env=False плюс явный proxy: иначе httpx снова возьмёт из окружения
    # ту же битую схему и всё сломается ровно там, где мы это чиним.
    return httpx.AsyncClient(timeout=timeout, trust_env=False, proxy=proxy, **kwargs)
