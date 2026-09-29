"""The four real capture paths keep display URLs out of analysis text."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.scanner.adapters import alice, chatgpt, google_aio, perplexity


@pytest.mark.parametrize('module,kind', [
    (chatgpt, 'ChatGPTAdapter'), (perplexity, 'PerplexityAdapter'),
    (alice, 'AliceAdapter'), (google_aio, 'GoogleAIOAdapter'),
])
def test_capture_saves_display_but_keeps_plain_analysis(monkeypatch, module, kind):
    raw = 'A useful company recommendation without the URL brand. ' * 2
    display = '[Company](<https://source.test/UrlBrand>)'
    parts = dict(raw=raw.strip(), display=display, main=raw.strip(), cards='Card company',
                 display_main=display, display_cards='Card company')
    page = MagicMock()
    page.inner_text = AsyncMock(return_value=raw)
    page.locator.return_value.first.inner_text = AsyncMock(return_value=raw)
    page.locator.return_value.last.inner_text = AsyncMock(return_value=raw)
    page.locator.return_value.count = AsyncMock(return_value=1)
    page.mouse.move = AsyncMock()
    reader = AsyncMock(return_value=parts)
    monkeypatch.setattr(module, 'readable', reader)
    monkeypatch.setattr(module.shot, 'full_shot', AsyncMock(return_value=b'shot'))
    adapter = getattr(module, kind)()
    monkeypatch.setattr(adapter, '_extract_sources', AsyncMock(return_value=['https://source.test/UrlBrand']))
    if module is perplexity:
        monkeypatch.setattr(adapter, '_raise_if_blocked', AsyncMock())
        monkeypatch.setattr(adapter, '_sources_shot', AsyncMock(return_value=None))
    if module in (alice, google_aio):
        monkeypatch.setattr(adapter, '_screenshot', AsyncMock(return_value=b'shot'))
    capture = asyncio.run(adapter.capture(page))
    assert display in capture.answer_text
    assert capture.extra['main_text'] == raw.strip()
    if module in (alice, google_aio):
        assert capture.extra['plain_text'] == f'{raw.strip()}\n\n{module.CARDS_MARK}\nCard company'
        assert capture.extra['cards_text'] == 'Card company'
        assert reader.call_args.args[1] == ('alice' if module is alice else 'google')
    else:
        assert capture.extra['plain_text'] == raw.strip()
    assert 'UrlBrand' not in capture.extra['main_text']
    assert 'UrlBrand' not in capture.extra['plain_text']
    assert capture.sources == ['https://source.test/UrlBrand']
