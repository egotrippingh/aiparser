import asyncio
import base64
import logging
from types import SimpleNamespace

import httpx
import pytest

from app.scanner.adapters.base import AdapterError, ProviderQuotaError
from app.scanner.adapters.xmlriver import XMLRiverAdapter, _parse_xml, _safe_html, geography
from app.detect.rules import evaluate


def _xml(service, html, *, cards=""):
    content = base64.b64encode(html.encode()).decode()
    block = f"<answer>{content}</answer>{cards}" if service == "google_aio" else f"<item><type>center</type><position>0</position><content>{content}</content></item>"
    return f"<yandexsearch><response><ai>{block}</ai></response></yandexsearch>".encode()


def test_google_answer_and_sources_are_separate_from_serp():
    payload = _xml("google_aio", "<div id='m-x-content'><div class='mZJni'>Совет: выбрать городскую клинику.</div><div class='bNg8Rb'>Скрытый Trouver</div></div>",
                   cards="<item><title>Trouver — источник</title><snippet>Рекламный текст</snippet><url>https://example.test/a</url></item>")
    html, cards = _parse_xml(payload, "google_aio")
    assert "Скрытый" not in html
    assert "Trouver" not in html
    assert cards == [("Trouver — источник", "Рекламный текст", "https://example.test/a")]


def test_yandex_html_is_inert_and_products_remain_classified():
    html, _ = _parse_xml(_xml("yandex_neuro", "<div class='FuturisMarkdown'>Выберите лечение.<span class='FuturisFootnoteGroup'>Trouver источник</span></div><div class='FuturisOrgCard'>Клиника Trouver</div><div class='EProductSnippet'><b>Товар Trouver</b><span class='EPrice-Value'>500 ₽</span></div><script>fetch('https://evil.test')</script><img src='https://evil.test/x'><a href='javascript:alert(1)' onclick='alert(2)'>ссылка</a>"), "yandex_neuro")
    assert all(name in html for name in ("FuturisMarkdown", "FuturisFootnoteGroup", "FuturisOrgCard", "EProductSnippet"))
    assert "500 ₽" in html
    assert "script" not in html and "fetch" not in html and "evil.test" not in html
    assert "onclick" not in html and "javascript:" not in html
    assert "ссылка" in html
    assert "скрыто" not in _safe_html("<span style='display:none'>скрыто</span><p>видно</p>")


@pytest.mark.parametrize("payload", [
    b"<broken", b"<!DOCTYPE foo><yandexsearch/>",
    b"<yandexsearch><response/></yandexsearch>",
    b"<yandexsearch><response><found>10</found><results/></response></yandexsearch>",
    b"<yandexsearch><response><ai><present>1</present></ai></response></yandexsearch>",
    b"<yandexsearch><response><ai><answer>%%%bad</answer></ai></response></yandexsearch>",
])
def test_partial_or_invalid_ai_is_error(payload):
    with pytest.raises(AdapterError):
        _parse_xml(payload, "google_aio")


def test_absent_ai_is_skipped_and_balance_is_quota():
    completed = b"<results><grouping><group><doc><url>https://example.test</url></doc></group></grouping></results>"
    assert _parse_xml(b"<yandexsearch><response><found>10</found>" + completed + b"</response></yandexsearch>", "google_aio") == (None, [])
    assert _parse_xml(b"<yandexsearch><response><ai><present>0</present></ai>" + completed + b"</response></yandexsearch>", "google_aio") == (None, [])
    assert _parse_xml(b"<yandexsearch><response><found>0</found><results/></response></yandexsearch>", "google_aio") == (None, [])
    with pytest.raises(ProviderQuotaError):
        _parse_xml(b"<yandexsearch><response><error code='200'>key in text is ignored</error></response></yandexsearch>", "google_aio")


def test_geography_is_explicit_for_non_moscow(monkeypatch):
    assert geography("google_aio", "213")["loc"] == "1011969"
    assert geography("google_aio", "213")["lr"] == "RU"
    assert geography("yandex_neuro", "54")["lr"] == "54"
    with pytest.raises(ValueError):
        geography("google_aio", "54")
    monkeypatch.setenv("AIPARSER_XMLRIVER_GOOGLE_REGION", "54")
    monkeypatch.setenv("AIPARSER_XMLRIVER_GOOGLE_LOC", "1000000")
    assert geography("google_aio", "54")["loc"] == "1000000"


def test_api_readiness_does_not_inherit_browser_success(monkeypatch):
    from app.api import browser
    monkeypatch.setenv("AIPARSER_XMLRIVER_USER", "synthetic-user")
    monkeypatch.setenv("AIPARSER_XMLRIVER_KEY", "synthetic-secret")
    monkeypatch.setattr(browser.repo, "get_setting", lambda key: '{"state":"ok","at":"2026-01-01"}' if key == "auth_state:google_aio" else None)
    state = browser._service_auth("google_aio")
    assert state["api_configured"] is True and state["last_scan_state"] is None


def test_transient_xml_retries_and_secret_never_enters_error(monkeypatch, caplog):
    monkeypatch.setenv("AIPARSER_XMLRIVER_USER", "synthetic-user")
    monkeypatch.setenv("AIPARSER_XMLRIVER_KEY", "synthetic-secret")
    seen = []
    def reply(request):
        seen.append(request)
        return httpx.Response(200, content=(b"<yandexsearch><response><error code='500'>temporary</error></response></yandexsearch>"
                                            if len(seen) < 3 else _xml("google_aio", "<p>Основной совет</p>")))
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(reply), **kwargs))
    caplog.set_level(logging.INFO, logger="httpx")
    async def no_wait(_): pass
    monkeypatch.setattr("shared.xmlriver.asyncio.sleep", no_wait)
    adapter = XMLRiverAdapter("google_aio", geography("google_aio", "213"))
    asyncio.run(adapter.ask(None, "вопрос", "213"))
    assert len(seen) == 3 and adapter.html == "<p>Основной совет</p>"
    assert seen[0].url.params["ai"] == "1" and seen[0].url.params["loc"] == "1011969"
    assert seen[0].url.params["device"] == "desktop" and seen[0].url.params["groupby"] == "10"
    assert "XMLRiver HTTP request (URL redacted)" in caplog.text
    assert "synthetic-secret" not in caplog.text and "synthetic-user" not in caplog.text and "вопрос" not in caplog.text
    def fail(_):
        raise httpx.ConnectError("synthetic-secret", request=seen[0])
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(fail), **kwargs))
    with pytest.raises(AdapterError) as error:
        asyncio.run(adapter.ask(None, "вопрос", "213"))
    assert "synthetic-secret" not in str(error.value)


@pytest.fixture
def provider_replies(monkeypatch):
    monkeypatch.setenv("AIPARSER_XMLRIVER_USER", "synthetic-user")
    monkeypatch.setenv("AIPARSER_XMLRIVER_KEY", "synthetic-secret")
    client = httpx.AsyncClient
    calls, waits = [], []

    def install(responses):
        def reply(request):
            calls.append(request)
            return responses[min(len(calls) - 1, len(responses) - 1)]
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(reply), **kwargs))

    async def no_wait(delay):
        waits.append(delay)
    monkeypatch.setattr("shared.xmlriver.asyncio", SimpleNamespace(sleep=no_wait))
    return install, calls, waits


@pytest.mark.parametrize("service", ["google_aio", "yandex_neuro"])
@pytest.mark.parametrize("bad", [
    b"<broken", b"<yandexsearch><response/></yandexsearch>",
    b"<yandexsearch><response><ai><present>1</present></ai></response></yandexsearch>",
    b"<yandexsearch><response><ai><answer>%%%bad</answer><item><content>%%%bad</content></item></ai></response></yandexsearch>",
])
def test_invalid_response_is_recollected_before_returning(service, bad, provider_replies):
    install, calls, waits = provider_replies
    install([httpx.Response(200, content=bad), httpx.Response(200, content=_xml(service, "<p>Корректный совет</p>"))])
    adapter = XMLRiverAdapter(service, geography(service, "213"))
    asyncio.run(adapter.ask(None, "вопрос", "213"))
    assert len(calls) == 2 and waits == [1]
    assert adapter.html == "<p>Корректный совет</p>"
    assert calls[0].url == calls[1].url


def test_repeated_invalid_response_stops_after_three_attempts(provider_replies):
    install, calls, waits = provider_replies
    install([httpx.Response(200, content=b"<broken")])
    adapter = XMLRiverAdapter("google_aio", geography("google_aio", "213"))
    with pytest.raises(AdapterError, match="повреждённый XML"):
        asyncio.run(adapter.ask(None, "вопрос", "213"))
    assert len(calls) == 3 and waits == [1, 2]
    assert adapter.html is None and adapter.cards == []


@pytest.mark.parametrize("response", [
    httpx.Response(429), httpx.Response(400),
    httpx.Response(200, content=b"<yandexsearch><error code='200'/></yandexsearch>"),
    httpx.Response(200, content=b"<yandexsearch><error code='115'/></yandexsearch>"),
    httpx.Response(200, content=b"<yandexsearch><error code='31'/></yandexsearch>"),
])
def test_access_and_quota_errors_do_not_retry(response, provider_replies):
    install, calls, waits = provider_replies
    install([response])
    adapter = XMLRiverAdapter("google_aio", geography("google_aio", "213"))
    with pytest.raises(AdapterError):
        asyncio.run(adapter.ask(None, "вопрос", "213"))
    assert len(calls) == 1 and waits == []


@pytest.mark.parametrize("response", [
    httpx.Response(429),
    httpx.Response(200, content=b"<yandexsearch><error code='115'/></yandexsearch>"),
])
def test_throttle_has_ten_minute_cooldown_without_retry(response, provider_replies):
    from shared.xmlriver import ProviderThrottleError
    install, calls, waits = provider_replies
    install([response])
    adapter = XMLRiverAdapter("google_aio", geography("google_aio", "213"))
    with pytest.raises(ProviderThrottleError) as failure:
        asyncio.run(adapter.ask(None, "вопрос", "213"))
    assert isinstance(failure.value, ProviderQuotaError)
    assert failure.value.retry_after == 600
    assert len(calls) == 1 and waits == []


def test_retry_wait_is_cancellable(provider_replies, monkeypatch):
    install, calls, _ = provider_replies
    install([httpx.Response(200, content=b"<broken")])
    async def check():
        waiting = asyncio.Event()
        async def blocked(_):
            waiting.set()
            await asyncio.Event().wait()
        monkeypatch.setattr("shared.xmlriver.asyncio.sleep", blocked)
        adapter = XMLRiverAdapter("google_aio", geography("google_aio", "213"))
        task = asyncio.create_task(adapter.ask(None, "вопрос", "213"))
        try:
            await asyncio.wait_for(waiting.wait(), 1)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert len(calls) == 1
    asyncio.run(check())


@pytest.mark.parametrize("stop_at", ["capture", "retry_wait"])
def test_stop_prevents_recollection_of_empty_capture(stop_at, provider_replies, monkeypatch):
    from app.scanner import orchestrator as scan
    from app.scanner.adapters.xmlriver import XMLRiverResponseError

    install, calls, _ = provider_replies
    install([httpx.Response(200, content=_xml("google_aio", "<p>Ответ</p>"))])
    async def check():
        ctl = scan.ScanController(1, 1, 1, "2026-10-09")
        adapter = XMLRiverAdapter("google_aio", geography("google_aio", "213"))
        waiting = asyncio.Event()
        async def empty(_):
            if stop_at == "capture":
                ctl.stop()
            raise XMLRiverResponseError("XMLRiver: AI-блок есть, но основной текст пуст")
        async def blocked(_):
            assert ctl.browser_phase["google_aio"]["phase"] == "ask"
            waiting.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(adapter, "capture", empty)
        monkeypatch.setattr("shared.xmlriver.asyncio.sleep", blocked)
        task = asyncio.create_task(scan._ask_and_capture(adapter, None, {"region_code": "213"},
                                                         {"id": 1, "text": "вопрос"}, "google_aio", 1, ctl))
        try:
            if stop_at == "retry_wait":
                await asyncio.wait_for(waiting.wait(), 1)
                ctl.stop()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1)
            assert len(calls) == 1
        finally:
            task.cancel()
    asyncio.run(check())


@pytest.mark.parametrize("service", ["google_aio", "yandex_neuro"])
@pytest.mark.parametrize("ending", ["valid", "invalid", "absent"])
def test_empty_main_recollection_shares_request_budget(service, ending, provider_replies):
    from camoufox import pkgman
    from playwright.async_api import async_playwright
    from app.scanner.browser_install import available_browser
    from app.scanner import orchestrator as scan

    binary = available_browser()
    if binary is None:
        pytest.skip("Camoufox binary is not installed")
    install, calls, waits = provider_replies
    empty = _xml(service, "<aside data-xid='aim-aside-1' class='FuturisOrgCard'>Только карточка</aside>")
    last = {"valid": _xml(service, "<p>Основной совет</p>"), "invalid": empty,
            "absent": b"<yandexsearch><response><found>0</found><results/></response></yandexsearch>"}[ending]
    install([httpx.Response(503), httpx.Response(200, content=empty), httpx.Response(200, content=last)])

    async def check():
        async with async_playwright() as playwright:
            browser = await playwright.firefox.launch(executable_path=str(pkgman.launch_path(binary)), headless=True)
            try:
                page = await browser.new_page()
                adapter = XMLRiverAdapter(service, geography(service, "213"))
                ctl = scan.ScanController(1, 1, 1, "2026-10-09")
                async def collect():
                    return await scan._ask_and_capture(adapter, page, {"region_code": "213"},
                                                       {"id": 1, "text": "вопрос"}, service, 1, ctl)
                if ending == "invalid":
                    with pytest.raises(AdapterError, match="основной текст пуст"):
                        await collect()
                else:
                    captured = await collect()
                    assert captured.shown == (ending == "valid")
                    assert captured.answer_text == ("Основной совет" if ending == "valid" else "")
                assert len(calls) == 3 and waits == [1, 2]
                assert len({str(call.url) for call in calls}) == 1
            finally:
                await browser.close()
    asyncio.run(check())


def test_offline_browser_capture_separates_cards_and_blocks_provider_resources():
    from camoufox import pkgman
    from playwright.async_api import async_playwright
    from app.scanner.browser_install import available_browser

    binary = available_browser()
    if binary is None:
        pytest.skip("Camoufox binary is not installed")

    async def check():
        async with async_playwright() as playwright:
            browser = await playwright.firefox.launch(executable_path=str(pkgman.launch_path(binary)), headless=True)
            try:
                page = await browser.new_page()
                requests = []
                page.on("request", lambda request: requests.append(request.url))
                yandex = XMLRiverAdapter("yandex_neuro", geography("yandex_neuro", "213"))
                yandex.html = _safe_html("""<section><div class='FuturisMarkdown'>Главный совет.
                  <span class='FuturisFootnoteGroup'><a href='https://source.test/x'>Trouver источник</a></span></div>
                  <div class='FuturisOrgCard'>Клиника OrgBrand</div>
                  <div class='EProductSnippet'>Товар Trouver <span class='EPrice-Value'>500 ₽</span></div>
                  <script>fetch('https://evil.test/steal')</script><img src='https://evil.test/pixel'></section>""")
                captured = await yandex.capture(page)
                assert captured.screenshot_bytes.startswith(b"\xff\xd8")
                assert "Trouver" not in captured.extra["main_text"]
                assert "Главный совет" in captured.extra["main_text"]
                assert all(word in captured.extra["cards_text"] for word in ("Trouver источник", "Клиника OrgBrand", "Товар Trouver", "500 ₽"))
                assert captured.sources == ["https://source.test/x"]
                verdict = evaluate(captured.extra["main_text"], captured.sources, "OrgBrand", [], [],
                                   card_text=captured.extra["cards_text"])
                assert verdict.found and verdict.mention_types == ["card"]

                google = XMLRiverAdapter("google_aio", geography("google_aio", "213"))
                google.html = _safe_html("<div id='m-x-content'><div class='mZJni'>Основная рекомендация.</div><aside data-xid='aim-aside-1'><a href='https://source.test/y'>Trouver карточка</a></aside></div>")
                google.cards = [("Trouver заголовок", "Сниппет источника", "https://source.test/y")]
                captured = await google.capture(page)
                assert captured.screenshot_bytes.startswith(b"\xff\xd8")
                assert captured.extra["main_text"] == "Основная рекомендация."
                assert "Trouver" in captured.extra["cards_text"]
                assert captured.sources == ["https://source.test/y"]
                assert requests == []
            finally:
                await browser.close()

    asyncio.run(check())
