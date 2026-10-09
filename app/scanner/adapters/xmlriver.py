"""XMLRiver SERP AI blocks, rendered locally for the existing Capture contract."""

from __future__ import annotations

import asyncio
import base64
import binascii
from html import escape
from html.parser import HTMLParser
import logging
import os
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import httpx

from app.scanner.adapters.base import AdapterError, Capture, ProviderQuotaError, ReadyState

GOOGLE_URL = "https://xmlriver.com/search/xml"
YANDEX_URL = "https://xmlriver.com/search_yandex/xml"
CARDS_MARK = "— Карточки источников —"
_RETRY_CODES = {"110", "111", "500"}
_AUTH_CODES = {"31", "42", "45"}
_CARD_SELECTOR = ("[data-xid^='aim-aside'], .FuturisGPTMessage-SourcesItem, "
                  ".FuturisSource, .FuturisFootnoteGroup, .FuturisFootnote, .FuturisOrgCard, .EProductSnippet, "
                  "[class*='Promo'], [class*='promo']")


class _RedactXMLRiver(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if "xmlriver.com/" in record.getMessage().lower():
            record.msg, record.args, record.exc_info = "XMLRiver HTTP request (URL redacted)", (), None
        return True


for _logger in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2"):
    logging.getLogger(_logger).addFilter(_RedactXMLRiver())


def configured() -> bool:
    return bool(os.environ.get("AIPARSER_XMLRIVER_USER") and os.environ.get("AIPARSER_XMLRIVER_KEY"))


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


class _SafeHTML(HTMLParser):
    """Allow only inert markup. Provider attributes and styles never enter the browser."""

    _tags = {"a", "article", "aside", "b", "blockquote", "br", "code", "dd", "div", "dl", "dt",
             "em", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "li", "ol", "p", "pre",
             "s", "section", "small", "span", "strong", "table", "tbody", "td", "th", "thead", "tr", "u", "ul"}
    _void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _blocked = {"head", "title", "script", "style", "noscript", "template", "svg", "math", "iframe", "object", "embed", "form", "button", "input"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool, bool]] = []
        self.blocked = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        hidden = (tag in self._blocked or "hidden" in values or values.get("aria-hidden") == "true" or
                  bool(set((values.get("class") or "").split()) & {"bNg8Rb", "MheKwc"}) or
                  bool(re.search(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)", values.get("style") or "", re.I)) or
                  self.blocked > 0)
        allowed = tag in self._tags and not hidden
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


def _safe_html(raw: str) -> str:
    parser = _SafeHTML()
    parser.feed(raw)
    parser.close()
    return "".join(parser.parts)


def _parse_xml(payload: bytes, service_id: str) -> tuple[str | None, list[tuple[str, str, str]]]:
    if len(payload) > 5_000_000 or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise AdapterError("XMLRiver: недопустимый XML")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise AdapterError("XMLRiver: повреждённый XML") from exc
    error = root.find(".//error")
    if error is not None:
        code = error.get("code") or error.findtext("code") or ""
        if code == "200":
            raise ProviderQuotaError("XMLRiver: закончился баланс")
        if code == "115":
            raise ProviderQuotaError("XMLRiver: временная блокировка из-за частоты запросов")
        if code in _AUTH_CODES:
            raise AdapterError(f"XMLRiver: ошибка доступа {code}")
        raise AdapterError(f"XMLRiver: ошибка API {code or 'unknown'}")
    if root.tag != "yandexsearch" or root.find("response") is None:
        raise AdapterError("XMLRiver: неполный ответ")
    response = root.find("response")
    ai = response.find("ai")
    if ai is None or ai.findtext("present") == "0":
        results = response.find("results")
        if results is None or (results.find(".//doc") is None and response.findtext("found") != "0"):
            raise AdapterError("XMLRiver: неполная поисковая выдача без AI-блока")
        return None, []
    cards: list[tuple[str, str, str]] = []
    if service_id == "google_aio":
        encoded = ai.findtext("answer")
        if not encoded:
            raise AdapterError("XMLRiver: AI-блок есть, но ответ отсутствует")
        for item in ai.findall("item"):
            cards.append((item.findtext("title") or "", item.findtext("snippet") or "", item.findtext("url") or ""))
    else:
        items = ai.findall("item")
        if not items:
            raise AdapterError("XMLRiver: AI-блок есть, но содержимое отсутствует")
        encoded = items[0].findtext("content")
        if not encoded:
            raise AdapterError("XMLRiver: AI-блок есть, но содержимое отсутствует")
    try:
        html = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeError) as exc:
        raise AdapterError("XMLRiver: некорректный HTML ответа") from exc
    if not html.strip():
        raise AdapterError("XMLRiver: пустой HTML ответа")
    return _safe_html(html), cards


class XMLRiverAdapter:
    requires_auth = False

    def __init__(self, service_id: str, geo: dict[str, str]) -> None:
        self.service_id = service_id
        self.display_name = "Google AI Overview" if service_id == "google_aio" else "Яндекс Нейро"
        self.geo = geo
        self.html: str | None = None
        self.cards: list[tuple[str, str, str]] = []

    async def ensure_ready(self, page) -> ReadyState:
        if not configured():
            raise AdapterError("XMLRiver: укажите AIPARSER_XMLRIVER_USER и AIPARSER_XMLRIVER_KEY")
        return ReadyState(ok=True)

    async def ask(self, page, query: str, region: str | None, *, speed: float = 1.0) -> None:
        self.html = None
        self.cards = []
        params = {**self.geo, "query": query, "ai": "1", "device": "desktop", "groupby": "10",
                  "user": os.environ["AIPARSER_XMLRIVER_USER"], "key": os.environ["AIPARSER_XMLRIVER_KEY"]}
        endpoint = GOOGLE_URL if self.service_id == "google_aio" else YANDEX_URL
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
                    response = await client.get(endpoint, params=params)
                if response.status_code == 429:
                    raise ProviderQuotaError("XMLRiver: временная блокировка из-за частоты запросов")
                if response.status_code in (500, 502, 503, 504):
                    if attempt < 2:
                        await asyncio.sleep(attempt + 1)
                        continue
                    raise AdapterError(f"XMLRiver: HTTP {response.status_code}")
                if response.status_code != 200:
                    raise AdapterError(f"XMLRiver: HTTP {response.status_code}")
                try:
                    self.html, self.cards = _parse_xml(response.content, self.service_id)
                    return
                except AdapterError as exc:
                    if str(exc).removeprefix("XMLRiver: ошибка API ") in _RETRY_CODES and attempt < 2:
                        await asyncio.sleep(attempt + 1)
                        continue
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt == 2:
                    raise AdapterError("XMLRiver: ошибка сети или таймаут") from None
                await asyncio.sleep(attempt + 1)

    async def capture(self, page) -> Capture:
        if self.html is None:
            await page.set_content("<main><h1>XMLRiver</h1><p>AI-блок не показан</p></main>")
            return Capture(screenshot_bytes=await page.screenshot(type="jpeg", quality=80), answer_text="", shown=False)
        await page.route("**/*", lambda route: route.abort())
        document = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
                    "<style>body{font:16px/1.5 Arial,sans-serif;color:#222;background:#fff;margin:32px;max-width:1000px}"
                    "article{max-width:850px}aside{border-top:1px solid #ccc;margin-top:24px;padding-top:16px}"
                    "a{color:#1766aa}</style><header>XMLRiver · локальное представление AI-блока</header>"
                    f"<article id='answer'>{self.html}</article>")
        if self.cards:
            document += "<aside id='api-cards'><h2>Карточки источников</h2>" + "".join(
                f"<p><a href='{escape(_safe_url(url), quote=True)}'>{escape(title)}</a><br>{escape(snippet)}</p>"
                for title, snippet, url in self.cards) + "</aside>"
        await page.set_content(document)
        answer = page.locator("#answer")
        if self.service_id == "google_aio":
            # XMLRiver sometimes wraps the AI block in a full SERP document.
            await answer.evaluate("""el => {
              const block = el.querySelector('#m-x-content');
              if (block) el.replaceChildren(block);
            }""")
        # Keep only the AI prose in main. Provider cards, products and promos are separate evidence.
        main_and_cards = await answer.evaluate("""(el, selector) => {
          const cards = [...el.querySelectorAll(selector)].filter(n => !n.parentElement.closest(selector));
          const main = el.cloneNode(true);
          main.querySelectorAll(selector).forEach(n => n.remove());
          main.style.position = 'absolute'; main.style.left = '-20000px';
          document.body.append(main);
          const text = main.innerText.trim(); main.remove();
          return {main: text, cards: cards.map(n => n.innerText.trim()).filter(Boolean).join('\\n\\n')};
        }""", _CARD_SELECTOR)
        main = main_and_cards["main"].strip()
        cards = main_and_cards["cards"].strip()
        if self.service_id == "yandex_neuro":
            markdown = answer.locator(".FuturisMarkdown")
            if await markdown.count():
                main = "\n\n".join(await markdown.evaluate_all("""(nodes, selector) => nodes
                  .filter(n => !n.parentElement.closest('.FuturisMarkdown'))
                  .map(n => { const clone = n.cloneNode(true); clone.querySelectorAll(selector).forEach(c => c.remove());
                    clone.style.position = 'absolute'; clone.style.left = '-20000px'; document.body.append(clone);
                    const text = clone.innerText.trim(); clone.remove(); return text; }).filter(Boolean)""", _CARD_SELECTOR)).strip()
        else:
            prose = answer.locator(".mZJni")
            if await prose.count():
                main = "\n\n".join(await prose.evaluate_all("""(nodes, selector) => nodes
                  .filter(n => !n.parentElement.closest('.mZJni'))
                  .map(n => { const clone = n.cloneNode(true); clone.querySelectorAll(selector).forEach(c => c.remove());
                    clone.style.position = 'absolute'; clone.style.left = '-20000px'; document.body.append(clone);
                    const text = clone.innerText.trim(); clone.remove(); return text; }).filter(Boolean)""", _CARD_SELECTOR)).strip()
            cards = "\n\n".join(filter(None, [cards, *["\n".join(filter(None, (t, s))) for t, s, _ in self.cards]]))
        if not main:
            raise AdapterError("XMLRiver: AI-блок есть, но основной текст пуст")
        sources = list(dict.fromkeys(filter(None, [*await answer.locator("a[href]").evaluate_all("els => els.map(a => a.href)"),
                                                 *[_safe_url(url) for _, _, url in self.cards]])))
        sources = [url for url in sources if _safe_url(url)]
        display = f"{main}\n\n{CARDS_MARK}\n{cards}" if cards else main
        return Capture(screenshot_bytes=await page.screenshot(type="jpeg", quality=80, full_page=True),
                       answer_text=display, sources=sources,
                       extra={"main_text": main, "cards_text": cards, "plain_text": display})
