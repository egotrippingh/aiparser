"""Legacy desktop XMLRiver adapter; account scans use shared text collection."""
from html import escape
import asyncio
import httpx

from shared.xmlriver import (XMLRiverClient, XMLRiverResponseError, configured, geography,
                            _parse_xml, _safe_html, _safe_url, _CARD_SELECTOR, CARDS_MARK)
from app.scanner.adapters.base import AdapterError, Capture, ProviderQuotaError, ReadyState


class XMLRiverAdapter(XMLRiverClient):
    def __init__(self, service_id: str, geo: dict[str, str]) -> None:
        super().__init__(service_id, geo, include_images=False)

    async def ensure_ready(self, page) -> ReadyState:
        if not configured():
            raise AdapterError("XMLRiver: укажите AIPARSER_XMLRIVER_USER и AIPARSER_XMLRIVER_KEY")
        return ReadyState(ok=True)

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
            raise XMLRiverResponseError("XMLRiver: AI-блок есть, но основной текст пуст")
        sources = list(dict.fromkeys(filter(None, [*await answer.locator("a[href]").evaluate_all("els => els.map(a => a.href)"),
                                                 *[_safe_url(url) for _, _, url in self.cards]])))
        sources = [url for url in sources if _safe_url(url)]
        display = f"{main}\n\n{CARDS_MARK}\n{cards}" if cards else main
        return Capture(screenshot_bytes=await page.screenshot(type="jpeg", quality=80, full_page=True),
                       answer_text=display, sources=sources,
                       extra={"main_text": main, "cards_text": cards, "plain_text": display})
