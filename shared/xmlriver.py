"""XMLRiver HTTP/XML collection shared by the account server and legacy agent."""

from __future__ import annotations

import asyncio
import base64
import binascii
from html import escape
from html.parser import HTMLParser
import logging
import os
import re
import ipaddress
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import httpx

from shared.errors import AdapterError, ProviderQuotaError

GOOGLE_URL = "https://xmlriver.com/search/xml"
YANDEX_URL = "https://xmlriver.com/search_yandex/xml"
CARDS_MARK = "— Карточки источников —"
_RETRY_CODES = {"110", "111", "500"}
_AUTH_CODES = {"31", "42", "45"}
_CARD_SELECTOR = ("[data-xid^='aim-aside'], .FuturisGPTMessage-SourcesItem, "
                  ".FuturisSource, .FuturisFootnoteGroup, .FuturisFootnote, .FuturisOrgCard, .EProductSnippet, "
                  "[class*='Promo'], [class*='promo']")


class XMLRiverResponseError(AdapterError):
    """Transient provider failure or unusable answer eligible for recollection."""


class CollectionCancelled(AdapterError):
    """The owning run stopped before the next paid provider request."""


class _RedactXMLRiver(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if "xmlriver.com/" in record.getMessage().lower():
            record.msg, record.args, record.exc_info = "XMLRiver HTTP request (URL redacted)", (), None
        return True


for _logger in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2"):
    logging.getLogger(_logger).addFilter(_RedactXMLRiver())


def configured() -> bool:
    return bool(os.environ.get("AIPARSER_XMLRIVER_USER") and os.environ.get("AIPARSER_XMLRIVER_KEY"))


async def account_limits() -> dict[str, int]:
    limits = {"google_aio": 1, "yandex_neuro": 1}
    if not configured():
        return limits
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get("https://xmlriver.com/api/get_info/", params={
                "user": os.environ["AIPARSER_XMLRIVER_USER"], "key": os.environ["AIPARSER_XMLRIVER_KEY"]})
        response.raise_for_status()
        data = response.json()
        threads = data.get("threads") if isinstance(data, dict) else None
        if isinstance(threads, dict):
            for service, engine in (("google_aio", "google"), ("yandex_neuro", "yandex")):
                value = threads.get(engine)
                # One VPS worker owns these slots; cap memory/in-flight response size.
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    limits[service] = min(value, 10)
    except (httpx.HTTPError, ValueError):
        pass  # Unknown account capacity permits only one request per engine.
    return limits


def geography(service_id: str, region: str) -> dict[str, str]:
    if not region.isdecimal():
        raise ValueError("Регион проекта должен быть числовым кодом Яндекса")
    if service_id == "yandex_neuro":
        return {"lr": region, "domain": "ru", "lang": "ru", "page": "0"}
    if region == "213":
        return {"loc": "1011969", "country": "2643", "domain": "143", "lr": "RU", "page": "1"}
    matching = os.environ.get("AIPARSER_XMLRIVER_GOOGLE_REGION")
    loc = os.environ.get("AIPARSER_XMLRIVER_GOOGLE_LOC")
    if matching != region or not loc or not loc.isdecimal():
        raise ValueError("Для региона проекта укажите соответствующие AIPARSER_XMLRIVER_GOOGLE_REGION и AIPARSER_XMLRIVER_GOOGLE_LOC")
    return {"loc": loc, "country": "2643", "domain": "143", "lr": "RU", "page": "1"}


def _safe_url(raw: str | None) -> str:
    if not raw or len(raw) > 2000 or any(ord(char) < 32 for char in raw):
        return ""
    try:
        url = urlsplit(raw.strip())
    except ValueError:
        return ""
    return raw.strip() if url.scheme in ("http", "https") and url.hostname and not url.username and not url.password else ""


def _image_url(raw: str | None) -> str:
    value = _safe_url(raw)
    if not value:
        return ""
    url = urlsplit(value)
    host = url.hostname.lower()
    if url.scheme != "https" or host == "localhost" or host.endswith((".localhost", ".local")) or "." not in host:
        return ""
    try:
        if not ipaddress.ip_address(host).is_global:
            return ""
    except ValueError:
        pass
    return value


class _SafeHTML(HTMLParser):
    """Allow only inert markup. Provider attributes and styles never enter the browser."""

    _tags = {"a", "article", "aside", "b", "blockquote", "br", "code", "dd", "div", "dl", "dt",
             "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "li", "ol", "p", "pre",
             "s", "section", "small", "span", "strong", "table", "tbody", "td", "th", "thead", "tr", "u", "ul"}
    _void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _blocked = {"head", "title", "script", "style", "noscript", "template", "svg", "math", "iframe", "object", "embed", "form", "button", "input"}

    def __init__(self, *, include_images: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.include_images = include_images
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool, bool]] = []
        self.blocked = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        # Yandex marks visible product thumbnails as decorative for screen readers.
        decorative_photo = self.include_images and ("EProductSnippet-Thumb" in (values.get("class") or "").split() or
                                                   (tag == "img" and "EThumb-Image" in (values.get("class") or "").split()))
        hidden = (tag in self._blocked or "hidden" in values or (values.get("aria-hidden") == "true" and not decorative_photo) or
                  bool(set((values.get("class") or "").split()) & {"bNg8Rb", "MheKwc"}) or
                  bool(re.search(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)", values.get("style") or "", re.I)) or
                  self.blocked > 0)
        allowed = (tag in self._tags or (tag == "img" and self.include_images)) and not hidden
        if tag not in self._void:
            self.stack.append((tag, allowed, hidden))
        if hidden and tag not in self._void:
            self.blocked += 1
        if not allowed:
            return
        classes = " ".join(re.findall(r"[A-Za-z0-9_-]+", values.get("class") or ""))[:300]
        attr = f' class="{escape(classes, quote=True)}"' if classes else ""
        xid = values.get("data-xid") or ""
        if xid.startswith("aim-aside"):
            attr += f' data-xid="{escape(xid[:100], quote=True)}"'
        if values.get("id") == "m-x-content":
            attr += ' id="m-x-content"'
        href = _safe_url(values.get("href")) if tag == "a" else ""
        if href:
            attr += f' href="{escape(href, quote=True)}"'
        if tag == "img":
            src = _image_url(values.get("data-src")) or _image_url(values.get("src"))
            if not src:
                return
            attr += f' src="{escape(src, quote=True)}" alt="{escape((values.get("alt") or "")[:500], quote=True)}"'
        self.parts.append(f"<{tag}{attr}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._void:
            return
        if not self.stack:
            return
        if self.stack[-1][0] != tag:
            return
        opened, allowed, hidden = self.stack.pop()
        if hidden:
            self.blocked -= 1
        if allowed:
            self.parts.append(f"</{opened}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked:
            self.parts.append(escape(data))


def _safe_html(raw: str, *, include_images: bool = False) -> str:
    parser = _SafeHTML(include_images=include_images)
    parser.feed(raw)
    parser.close()
    return "".join(parser.parts)


def _parse_xml(payload: bytes, service_id: str, *, include_images: bool = False) -> tuple[str | None, list[tuple[str, str, str]]]:
    if len(payload) > 5_000_000 or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise AdapterError("XMLRiver: недопустимый XML")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise XMLRiverResponseError("XMLRiver: повреждённый XML") from exc
    error = root.find(".//error")
    if error is not None:
        code = error.get("code") or error.findtext("code") or ""
        if code == "200":
            raise ProviderQuotaError("XMLRiver: закончился баланс")
        if code == "115":
            raise ProviderQuotaError("XMLRiver: временная блокировка из-за частоты запросов")
        if code in _AUTH_CODES:
            raise AdapterError(f"XMLRiver: ошибка доступа {code}")
        if code in _RETRY_CODES:
            raise XMLRiverResponseError(f"XMLRiver: ошибка API {code}")
        raise AdapterError(f"XMLRiver: ошибка API {code or 'unknown'}")
    if root.tag != "yandexsearch" or root.find("response") is None:
        raise XMLRiverResponseError("XMLRiver: неполный ответ")
    response = root.find("response")
    ai = response.find("ai")
    if ai is None or ai.findtext("present") == "0":
        results = response.find("results")
        if results is None or (results.find(".//doc") is None and response.findtext("found") != "0"):
            raise XMLRiverResponseError("XMLRiver: неполная поисковая выдача без AI-блока")
        return None, []
    cards: list[tuple[str, str, str]] = []
    if service_id == "google_aio":
        encoded = ai.findtext("answer")
        if not encoded:
            raise XMLRiverResponseError("XMLRiver: AI-блок есть, но ответ отсутствует")
        encoded_parts = [encoded]
        for item in ai.findall("item"):
            cards.append((item.findtext("title") or "", item.findtext("snippet") or "", item.findtext("url") or ""))
    else:
        encoded_parts = list(dict.fromkeys(content.strip() for item in ai.findall("item")
                                          if (content := item.findtext("content")) and content.strip()))
        if not encoded_parts:
            raise XMLRiverResponseError("XMLRiver: AI-блок есть, но содержимое отсутствует")
    try:
        html = "".join(base64.b64decode(part.strip(), validate=True).decode("utf-8") for part in encoded_parts)
    except (binascii.Error, UnicodeError) as exc:
        raise XMLRiverResponseError("XMLRiver: некорректный HTML ответа") from exc
    if not html.strip():
        raise XMLRiverResponseError("XMLRiver: пустой HTML ответа")
    return _safe_html(html, include_images=include_images), cards


@dataclass
class _Node:
    tag: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    children: list = field(default_factory=list)

    @property
    def classes(self):
        return set(self.attrs.get("class", "").split())


class _Tree(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]
        self.count = 0
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        self.count += 1
        if len(self.stack) > 128 or self.count > 50_000:
            raise XMLRiverResponseError("XMLRiver: слишком сложная структура ответа")
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in _SafeHTML._void:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _walk(node):
    yield node
    for child in node.children:
        if isinstance(child, _Node):
            yield from _walk(child)


def _card(node):
    return (node.attrs.get("data-xid", "").startswith("aim-aside") or
            bool(node.classes & {"FuturisGPTMessage-SourcesItem", "FuturisSource", "FuturisFootnoteGroup",
                                 "FuturisFootnote", "FuturisOrgCard", "EProductSnippet"}) or
            any("promo" in c.lower() for c in node.classes))


def _outer(node, predicate):
    if predicate(node):
        return [node]
    return [match for child in node.children if isinstance(child, _Node) for match in _outer(child, predicate)]


_BLOCKS = {"article", "aside", "blockquote", "dd", "div", "dl", "dt", "h1", "h2", "h3", "h4", "h5", "h6",
           "li", "ol", "p", "pre", "section", "table", "tr", "ul"}


def _text(node, *, omit_cards=False):
    if omit_cards and _card(node):
        return ""
    parts = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag == "br":
            parts.append("\n")
        else:
            value = _text(child, omit_cards=omit_cards)
            parts.append(f"\n{value}\n" if child.tag in _BLOCKS else value)
    return "".join(parts)


def _plain(node, *, omit_cards=False):
    lines = [re.sub(r"[\t\r\f\v ]+", " ", line).strip() for line in _text(node, omit_cards=omit_cards).split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _markup(node, *, omit_cards=False):
    if omit_cards and _card(node):
        return ""
    content = "".join(escape(c) if isinstance(c, str) else _markup(c, omit_cards=omit_cards) for c in node.children)
    if not node.tag:
        return content
    # Structure and safe links only: provider classes never affect the cabinet UI.
    attrs = "".join(f' {k}="{escape(v, quote=True)}"' for k, v in node.attrs.items() if k in ("href", "src", "alt"))
    return f"<{node.tag}{attrs}>" + ("" if node.tag in _SafeHTML._void else content + f"</{node.tag}>")


def _content(node):
    if _card(node):
        return []
    children = []
    for child in node.children:
        children.extend([child] if isinstance(child, str) else _content(child))
    if not node.tag:
        return children
    return [{"tag": node.tag, "children": children, **({"href": node.attrs["href"]} if node.attrs.get("href") else {})}]


def evidence(markup: str | None, cards: list[tuple[str, str, str]], service_id: str) -> dict:
    """Preserve prose, cards and real product photos without a browser."""
    empty = {"shown": False, "main_text": "", "cards_text": "", "answer_text": "", "html": "", "content": [],
             "sources": [], "source_cards": [], "products": []}
    if markup is None:
        return empty
    root = _Tree(markup).root
    if service_id == "google_aio":
        root = next((n for n in _walk(root) if n.attrs.get("id") == "m-x-content"), root)
    prose_class = "mZJni" if service_id == "google_aio" else "FuturisMarkdown"
    prose = _outer(root, lambda n: prose_class in n.classes)
    prose = prose or [root]
    main = "\n\n".join(filter(None, (_plain(n, omit_cards=True) for n in prose)))
    if not main:
        raise XMLRiverResponseError("XMLRiver: AI-блок есть, но основной текст пуст")
    main_html = "".join(_markup(n, omit_cards=True) for n in prose)
    card_nodes = _outer(root, _card)
    cards_text = "\n\n".join(filter(None, [_plain(n) for n in card_nodes] +
        ["\n".join(filter(None, [title, snippet])) for title, snippet, _ in cards]))
    if len(main) + len(cards_text) > 60_000:
        raise XMLRiverResponseError("XMLRiver: текст ответа превышает допустимый размер")
    products = []
    for node in _outer(root, lambda n: "EProductSnippet" in n.classes):
        nodes = list(_walk(node))
        title = next((_plain(n) for n in nodes if "EProductSnippet-Title" in n.classes), "")
        url = next((_safe_url(n.attrs.get("href")) for n in nodes if n.tag == "a" and _safe_url(n.attrs.get("href"))), "")
        image = next((_image_url(n.attrs.get("src")) for n in nodes if n.tag == "img" and _image_url(n.attrs.get("src"))), "")
        price = next((_plain(n) for n in nodes if "EPrice-Value" in n.classes), "")
        currency = next((_plain(n) for n in nodes if "EPrice-Currency" in n.classes), "")
        if price and currency and currency not in price:
            price += " " + currency
        title = title or _plain(node)
        item = {"title": title[:2000], "url": url, "image_url": image, "price": price[:100]}
        if item not in products:
            products.append(item)
    source_cards = [{"title": t, "text": s, "url": _safe_url(u)} for t, s, u in cards]
    for node in card_nodes:
        if "EProductSnippet" in node.classes or _outer(node, lambda n: "EProductSnippet" in n.classes):
            continue
        links = [n for n in _walk(node) if n.tag == "a" and _safe_url(n.attrs.get("href"))]
        if not links:
            text = _plain(node)
            if text:
                source_cards.append({"title": text, "text": "", "url": ""})
        for link in links:
            item = {"title": _plain(link), "text": _plain(node), "url": _safe_url(link.attrs["href"])}
            if item not in source_cards:
                source_cards.append(item)
    sources = list(dict.fromkeys(filter(None, [_safe_url(n.attrs.get("href")) for n in _walk(root) if n.tag == "a"] +
                                         [_safe_url(u) for _, _, u in cards])))
    if len(sources) > 50 or len(products) > 100 or len(source_cards) > 100:
        raise XMLRiverResponseError("XMLRiver: слишком много карточек или источников")
    return {"shown": True, "main_text": main, "cards_text": cards_text,
            "answer_text": f"{main}\n\n{CARDS_MARK}\n{cards_text}" if cards_text else main,
            "html": main_html, "content": [item for n in prose for item in _content(n)],
            "sources": sources, "source_cards": source_cards, "products": products}


class XMLRiverClient:
    requires_auth = False

    def __init__(self, service_id: str, geo: dict[str, str], *, include_images: bool = True,
                 max_attempts: int = 3) -> None:
        if type(max_attempts) is not int or not 1 <= max_attempts <= 6:
            raise ValueError("XMLRiver retry budget must be an integer between 1 and 6")
        self.max_attempts = max_attempts
        self.service_id = service_id
        self.include_images = include_images
        self.display_name = "Google AI Overview" if service_id == "google_aio" else "Яндекс Нейро"
        self.geo = geo
        self.html: str | None = None
        self.cards: list[tuple[str, str, str]] = []
        self._query: str | None = None
        self._attempts = 0
        self._should_continue: Callable[[], bool] | None = None

    def _check_continue(self) -> None:
        if self._should_continue is not None and not self._should_continue():
            raise CollectionCancelled("XMLRiver: сбор приостановлен")

    async def collect(self, query: str, *, should_continue: Callable[[], bool] | None = None) -> dict:
        if not configured():
            raise AdapterError("XMLRiver: доступ к API не настроен")
        self._should_continue = should_continue
        started = time.monotonic()
        try:
            await self.ask(None, query, None)
            while True:
                try:
                    result = evidence(self.html, self.cards, self.service_id)
                    result["collection"] = {"attempts": self._attempts,
                                            "elapsed_ms": round((time.monotonic() - started) * 1000)}
                    return result
                except XMLRiverResponseError:
                    if not await self.retry():
                        raise
        finally:
            self._should_continue = None

    async def ask(self, page, query: str, region: str | None, *, speed: float = 1.0) -> None:
        self.html = None
        self.cards = []
        self._query = query
        self._attempts = 0
        await self._request()

    async def retry(self) -> bool:
        # Capture validation and HTTP/XML failures share one paid-request budget.
        if self._query is None or self._attempts >= self.max_attempts:
            return False
        self._check_continue()
        self.html, self.cards = None, []
        await asyncio.sleep(self._attempts)
        await self._request()
        return True

    async def _request(self) -> None:
        params = {**self.geo, "query": self._query, "ai": "1", "device": "desktop", "groupby": "10",
                  "user": os.environ["AIPARSER_XMLRIVER_USER"], "key": os.environ["AIPARSER_XMLRIVER_KEY"]}
        endpoint = GOOGLE_URL if self.service_id == "google_aio" else YANDEX_URL
        while self._attempts < self.max_attempts:
            self._check_continue()
            self._attempts += 1
            try:
                async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
                    response = await client.get(endpoint, params=params)
                if response.status_code == 429:
                    raise ProviderQuotaError("XMLRiver: временная блокировка из-за частоты запросов")
                if response.status_code in (500, 502, 503, 504):
                    raise XMLRiverResponseError(f"XMLRiver: HTTP {response.status_code}")
                if response.status_code != 200:
                    raise AdapterError(f"XMLRiver: HTTP {response.status_code}")
                self.html, self.cards = _parse_xml(response.content, self.service_id, include_images=self.include_images)
                return
            except XMLRiverResponseError:
                if self._attempts >= self.max_attempts:
                    raise
            except (httpx.TransportError, httpx.TimeoutException):
                if self._attempts >= self.max_attempts:
                    raise AdapterError("XMLRiver: ошибка сети или таймаут") from None
            await asyncio.sleep(self._attempts)
