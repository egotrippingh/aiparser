"""Глубокая проверка источников: ищем бренд на страницах, которые цитирует ИИ.

Зачем это вообще нужно. Клиент-оптовик может не называться в самом ответе
нейросети, но фигурировать как поставщик на странице магазина-перекупщика,
которую этот ответ цитирует как источник. Для задачи «видим ли мы бренд в
ИИ-выдаче» такое упоминание засчитывается — именно из-за подобных случаев
одной проверки вхождения строки в текст ответа мало.

Почему обычный HTTP, а не браузер. Страницу можно было бы открывать в том же
Camoufox — надёжнее по части JS-рендера. Но на базе в 100 запросов × 4 сервиса
проверка трёх источников на каждый «не найдено» — это порядка тысячи загрузок:
браузером вышло бы около полутора часов сверху, обычными запросами
параллельно — минут двенадцать. Каталоги, отзовики и карточки магазинов, ради
которых всё затевалось, отдают имена поставщиков в серверной вёрстке, так что
цена в виде непрогруженных SPA здесь оправдана. Если попадётся сайт, который
без JS не отдаёт ничего, мы просто не найдём там бренд — это ложноотрицательный
результат, а не ложноположительный, и статистика от него не завышается.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from app import net
from app.detect import rules
from app.detect.brand import normalize_host, registrable_domain, same_site

log = logging.getLogger("aiparser.deep")

# Страницу больше этого не читаем: попадаются каталоги на несколько мегабайт,
# а бренд, если он там есть, встречается задолго до конца документа.
MAX_BYTES = 2_000_000

_TAG_RE = re.compile(r"<[^>]+>")
_DROP_RE = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.S | re.I)
_WS_RE = re.compile(r"\s+")


@dataclass
class DeepHit:
    found: bool
    url: str | None = None
    quote: str | None = None
    matched_forms: list[str] = field(default_factory=list)


def html_to_text(html: str) -> str:
    """Грубое извлечение видимого текста.

    Полноценный парсер здесь не нужен: нам не важна структура документа, важно
    лишь встречается ли в нём имя бренда. Скрипты и стили выкидываем отдельно —
    иначе в «текст» попадут строковые литералы из JS и дадут ложные совпадения.
    """
    html = _DROP_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def pick_sources(sources: list[str], brand_domains: list[str], depth: int) -> list[str]:
    """Отбирает страницы, которые имеет смысл открывать.

    Собственные домены бренда пропускаем: если ответ уже сослался на сайт
    клиента, это поймал `rules.check_links`, и открывать страницу незачем.
    """
    if depth <= 0:
        return []

    out: list[str] = []
    seen: set[str] = set()

    for url in sources:
        try:
            host = normalize_host(urlparse(url).hostname or "")
        except ValueError:
            continue
        if not host:
            continue
        site = registrable_domain(host)
        if site in seen or any(same_site(host, d) for d in brand_domains):
            continue
        seen.add(site)           # по одной странице с сайта — остальные дадут то же
        out.append(url)
        if len(out) >= depth:
            break

    return out


async def _fetch(client: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return ""            # pdf/картинка/архив — читать нечего
        return html_to_text(resp.text[:MAX_BYTES])
    except Exception as exc:
        log.info("Глубокая проверка: %s не открылась (%s)", url[:80], type(exc).__name__)
        return ""


async def check_sources(
    sources: list[str],
    brand_name: str,
    aliases: list[str],
    brand_domains: list[str],
    *,
    depth: int,
    # 8 секунд, а не больше: страницы тянутся параллельно, поэтому время на
    # запрос упирается в самую медленную из них. Замер на реальных источниках
    # 09.09.2026 показал, что редкие «тяжёлые» страницы выбирали весь таймаут
    # и в одиночку поднимали среднее с 3 до 5.4 секунд, ничего не добавляя к
    # результату.
    timeout: float = 8.0,
) -> DeepHit:
    """Открывает до `depth` страниц-источников и ищет на них бренд."""
    if depth <= 0 or not sources:
        return DeepHit(found=False)

    urls = pick_sources(sources, brand_domains, depth)
    if not urls:
        return DeepHit(found=False)

    # Проверку сертификатов НЕ отключаем: мы ходим по произвольным чужим
    # страницам, и битый сертификат — повод пропустить страницу, а не повод
    # ослабить TLS во всём приложении. Потеря данных тут пренебрежимо мала.
    # direct_client идёт мимо системного прокси — см. app/net.py.
    async with net.direct_client(timeout=timeout) as client:
        texts = await asyncio.gather(*(_fetch(client, u) for u in urls))

    for url, text in zip(urls, texts):
        if not text:
            continue
        verdict = rules.check_text(text, brand_name, aliases)
        if verdict.found:
            log.info("Глубокая проверка: бренд найден на %s", url[:80])
            return DeepHit(
                found=True,
                url=url,
                quote=verdict.evidence_quote,
                matched_forms=verdict.matched_forms,
            )

    return DeepHit(found=False)
