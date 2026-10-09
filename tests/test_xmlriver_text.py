import asyncio
import base64
from types import SimpleNamespace

import httpx
import pytest

from shared import xmlriver
from shared.detection import _build_prompt
from app.detect.rules import evaluate


def payload(service, html, cards=""):
    data = base64.b64encode(html.encode()).decode()
    ai = f"<answer>{data}</answer>{cards}" if service == "google_aio" else f"<item><content>{data}</content></item>"
    return f"<yandexsearch><response><ai>{ai}</ai></response></yandexsearch>".encode()


def test_yandex_products_have_real_photos_and_stay_separate_from_prose():
    html = """<div class='FuturisMarkdown'><h2>Выбор</h2><p>Полезный совет.</p>
      <span class='FuturisFootnoteGroup'><a href='https://source.test'>Источник</a></span></div>
      <div class='EProductSnippet'><a href='https://shop.test/tuvio'><div class='EProductSnippet-Title'>Tuvio пылесос</div>
      <span class='EProductSnippet-Thumb' aria-hidden='true'><img class='EThumb-Image' aria-hidden='true' src='https://yastatic.net/photo.jpg' onerror='bad()'></span><span class='EPrice-Value'>23 455</span></a></div>"""
    markup, cards = xmlriver._parse_xml(payload("yandex_neuro", html), "yandex_neuro", include_images=True)
    result = xmlriver.evidence(markup, cards, "yandex_neuro")
    assert result["shown"] and result["main_text"] == "Выбор\n\nПолезный совет."
    assert "Tuvio" not in result["html"] and "Источник" not in result["html"]
    assert result["products"] == [{"title": "Tuvio пылесос", "url": "https://shop.test/tuvio", "image_url": "https://yastatic.net/photo.jpg", "price": "23 455"}]
    assert result["source_cards"][0]["url"] == "https://source.test"
    verdict = evaluate(result["main_text"], result["sources"], "Tuvio", [], [], card_text=result["cards_text"])
    assert verdict.found and "card" in verdict.mention_types and "text" not in verdict.mention_types
    assert result["content"][0]["tag"] == "div"


def test_google_prose_scope_sources_and_lazy_images_are_safe():
    html = """<div>Другой бренд из обычной выдачи</div><div id='m-x-content'>
      <div class='mZJni'><p>Основной ответ <a href='https://brand.test'>официальный сайт</a>.</p></div>
      <aside data-xid='aim-aside-1'><a href='https://source.test'>Источник Brand</a>
      <img src='data:image/gif;base64,x' data-src='https://images.test/photo.jpg'></aside></div>
      <script>bad()</script>"""
    markup, cards = xmlriver._parse_xml(payload("google_aio", html, "<item><title>Другой источник</title><url>https://more.test</url></item>"), "google_aio", include_images=True)
    result = xmlriver.evidence(markup, cards, "google_aio")
    assert "Другой бренд" not in result["answer_text"]
    assert result["sources"] == ["https://brand.test", "https://source.test", "https://more.test"]
    assert len(result["source_cards"]) == 2 and result["products"] == []
    assert "data:" not in markup and 'src="https://images.test/photo.jpg"' in markup


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:image/svg+xml,bad", "http://images.test/photo", "https://127.0.0.1/photo", "https://169.254.169.254/photo", "https://localhost/photo", "https://user:secret@images.test/photo"])
def test_unsafe_product_photos_are_not_rendered(url):
    assert xmlriver._image_url(url) == ""


def test_text_only_prompt_preserves_brand_after_old_truncation_and_all_sources():
    text = "Полезный ответ. " * 700 + "Нужный бренд в конце"
    prompt = _build_prompt("Brand", [], text, [f"https://source{i}.test" for i in range(20)], text_only=True)
    assert "Нужный бренд в конце" in prompt and "source19.test" in prompt
    assert "скриншота нет" in prompt


def test_collect_retries_incomplete_prose_without_browser_and_shares_http_budget(monkeypatch):
    monkeypatch.setenv("AIPARSER_XMLRIVER_USER", "test-user")
    monkeypatch.setenv("AIPARSER_XMLRIVER_KEY", "test-key")
    seen = []
    async def no_wait(_): pass
    monkeypatch.setattr(xmlriver, "asyncio", SimpleNamespace(sleep=no_wait))
    original = httpx.AsyncClient
    def reply(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(503)
        html = "<div class='EProductSnippet'>Только карточка</div>" if len(seen) == 2 else "<p>Полный ответ</p>"
        return httpx.Response(200, content=payload("yandex_neuro", html))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(reply), **kwargs))
    result = asyncio.run(xmlriver.XMLRiverClient("yandex_neuro", {"lr": "213"}).collect("Тест"))
    assert result["main_text"] == "Полный ответ" and len(seen) == 3
    assert all(r.url.params["query"] == "Тест" for r in seen)


def test_absence_and_empty_main_are_distinct():
    assert xmlriver.evidence(None, [], "google_aio")["shown"] is False
    with pytest.raises(xmlriver.XMLRiverResponseError):
        xmlriver.evidence("<div class='EProductSnippet'>Карточка</div>", [], "yandex_neuro")


def test_organization_card_without_link_is_preserved_for_viewer():
    result = xmlriver.evidence("<div class='FuturisMarkdown'>Основной ответ</div><div class='FuturisOrgCard'>Клиника Brand</div>", [], "yandex_neuro")
    assert result["source_cards"] == [{"title": "Клиника Brand", "text": "", "url": ""}]
    assert "Клиника Brand" in result["cards_text"] and "Клиника Brand" not in result["main_text"]


def test_run_stop_blocks_provider_retry_and_preserves_completed_answer(monkeypatch):
    monkeypatch.setenv("AIPARSER_XMLRIVER_USER", "test-user")
    monkeypatch.setenv("AIPARSER_XMLRIVER_KEY", "test-key")
    original = httpx.AsyncClient
    calls, running = [], [True]
    def reply(request):
        calls.append(request)
        running[0] = False
        return httpx.Response(503)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(reply), **kw))
    with pytest.raises(xmlriver.CollectionCancelled):
        asyncio.run(xmlriver.XMLRiverClient("google_aio", {}).collect("Тест", should_continue=lambda: running[0]))
    assert len(calls) == 1
    running[0] = True
    def complete(request):
        running[0] = False
        return httpx.Response(200, content=payload("google_aio", "<p>Сохранить ответ</p>"))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(complete), **kw))
    result = asyncio.run(xmlriver.XMLRiverClient("google_aio", {}).collect("Тест", should_continue=lambda: running[0]))
    assert result["main_text"] == "Сохранить ответ"


def test_yandex_empty_first_item_does_not_hide_later_answer():
    encoded = base64.b64encode(b'<p>Complete answer</p>').decode()
    data = (f'<yandexsearch><response><ai><item><content/></item>'
            f'<item><content>{encoded}</content></item></ai></response></yandexsearch>').encode()
    markup, cards = xmlriver._parse_xml(data, 'yandex_neuro')
    assert xmlriver.evidence(markup, cards, 'yandex_neuro')['main_text'] == 'Complete answer'


def test_all_yandex_answer_items_are_preserved_without_duplicates():
    contents = [base64.b64encode(html.encode()).decode() for html in ('<p>First answer</p>', '<p>Second answer</p>')]
    data = ('<yandexsearch><response><ai>' + ''.join(f'<item><content>{c}</content></item>'
            for c in [contents[0], contents[0], contents[1]]) + '</ai></response></yandexsearch>').encode()
    markup, cards = xmlriver._parse_xml(data, 'yandex_neuro')
    assert xmlriver.evidence(markup, cards, 'yandex_neuro')['main_text'] == 'First answer\n\nSecond answer'


@pytest.mark.parametrize('successful', [True, False])
def test_server_retry_budget_covers_http_xml_and_empty_ai(monkeypatch, successful):
    monkeypatch.setenv('AIPARSER_XMLRIVER_USER', 'test-user')
    monkeypatch.setenv('AIPARSER_XMLRIVER_KEY', 'test-key')
    original = httpx.AsyncClient
    calls = []
    async def no_wait(_): pass
    monkeypatch.setattr(xmlriver, 'asyncio', SimpleNamespace(sleep=no_wait))
    def reply(request):
        calls.append(request)
        if successful and len(calls) == 6:
            return httpx.Response(200, content=payload('yandex_neuro', '<p>Recovered answer</p>'))
        failures = [b'<yandexsearch><error code="500"/></yandexsearch>', b'<broken',
                    b'<yandexsearch><response><ai><item><content/></item></ai></response></yandexsearch>']
        return httpx.Response(200, content=failures[(len(calls)-1) % 3])
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(reply), **kw))
    client = xmlriver.XMLRiverClient('yandex_neuro', {}, max_attempts=6)
    if successful:
        assert asyncio.run(client.collect('question'))['main_text'] == 'Recovered answer'
    else:
        with pytest.raises(xmlriver.XMLRiverResponseError):
            asyncio.run(client.collect('question'))
    assert len(calls) == 6 and len({str(r.url) for r in calls}) == 1


@pytest.mark.parametrize('bad', [0, 7, True, '6'])
def test_invalid_retry_budget_is_rejected(bad):
    with pytest.raises(ValueError):
        xmlriver.XMLRiverClient('yandex_neuro', {}, max_attempts=bad)


@pytest.mark.parametrize('data,expected', [
    ({'threads': {'google': 10, 'yandex': 10}}, {'google_aio': 10, 'yandex_neuro': 10}),
    ({'threads': {'google': 50, 'yandex': 3}}, {'google_aio': 10, 'yandex_neuro': 3}),
    ({'threads': {'google': True, 'yandex': 'oops'}}, {'google_aio': 1, 'yandex_neuro': 1}),
    ({'threads': None}, {'google_aio': 1, 'yandex_neuro': 1}),
])
def test_account_limits_validate_provider_data(monkeypatch, data, expected):
    monkeypatch.setenv('AIPARSER_XMLRIVER_USER', 'test-user')
    monkeypatch.setenv('AIPARSER_XMLRIVER_KEY', 'test-key')
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=data)), **kw))
    assert asyncio.run(xmlriver.account_limits()) == expected


def test_account_limits_fail_closed_when_api_is_unavailable(monkeypatch):
    monkeypatch.setenv('AIPARSER_XMLRIVER_USER', 'test-user')
    monkeypatch.setenv('AIPARSER_XMLRIVER_KEY', 'test-key')
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(
        lambda request: httpx.Response(503)), **kw))
    assert asyncio.run(xmlriver.account_limits()) == {'google_aio': 1, 'yandex_neuro': 1}
