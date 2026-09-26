import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.scanner.adapters import chatgpt as mod


def test_pending_composer_recovers_after_reload(monkeypatch):
    page = MagicMock()
    page.goto = AsyncMock()
    monkeypatch.setattr(mod, "visible", AsyncMock(side_effect=[False, True]))
    asyncio.run(mod.ChatGPTAdapter()._wait_for_composer(page))
    page.goto.assert_awaited_once_with(mod._S["temporary_url"], wait_until="domcontentloaded")


def test_missing_composer_never_reports_ready(monkeypatch):
    page = MagicMock()
    page.goto = AsyncMock()
    # Profile is visible; editor fails to hydrate on both page loads.
    monkeypatch.setattr(mod, "visible", AsyncMock(side_effect=[True, False, False]))
    monkeypatch.setattr(mod, "dump_debug_html", AsyncMock())
    with pytest.raises(mod.AdapterError):
        asyncio.run(mod.ChatGPTAdapter().ensure_ready(page))
