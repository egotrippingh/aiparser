import asyncio
import json
import subprocess
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


def test_login_form_reports_auth_required(monkeypatch):
    page = MagicMock()
    page.goto = AsyncMock()
    monkeypatch.setattr(mod, "visible", AsyncMock(side_effect=[False, True]))
    assert asyncio.run(mod.ChatGPTAdapter().ensure_ready(page)).reason == "auth_required"


def test_completion_checks_latest_message_and_preserves_legacy(monkeypatch):
    page = MagicMock()
    page.locator.return_value.first.wait_for = AsyncMock()
    page.wait_for_function = AsyncMock()
    monkeypatch.setattr(mod.humanize, "sleep", AsyncMock())
    asyncio.run(mod.ChatGPTAdapter()._wait_done(page))
    call = page.wait_for_function.call_args
    assert call.kwargs["timeout"] == 240000
    # Run the actual DOM predicate: an older completed answer (or feedback
    # button) must not finish the currently streaming new-format answer.
    subprocess.run(["node", "-e", """
        const assert = require('node:assert/strict');
        const ready = (""" + call.args[0] + """);
        const selectors = """ + json.dumps(call.kwargs["arg"]) + """;
        const message = (modern, complete) => ({
            closest: () => modern ? {hasAttribute: () => complete} : null
        });
        let answers = [message(true, true), message(true, false)];
        let markers = [{getClientRects: () => [1], visibility: 'visible'}];
        global.document = {querySelectorAll: s => s === selectors.answer ? answers : markers};
        global.getComputedStyle = e => e;
        assert.equal(ready(selectors), false);
        answers.push({closest: () => ({hasAttribute: () => false})});
        assert.equal(ready(selectors), false); // Nested legacy match in new LI.
        answers.pop();
        answers[1] = message(true, true);
        assert.equal(ready(selectors), true);
        answers = [message(false, false)];
        assert.equal(ready(selectors), true);
        markers[0].visibility = 'hidden';
        assert.equal(ready(selectors), false);
        markers = [];
        assert.equal(ready(selectors), false);
    """], check=True, capture_output=True, text=True)


def test_completion_timeout_keeps_stabilization_fallback(monkeypatch):
    page = MagicMock()
    page.locator.return_value.first.wait_for = AsyncMock()
    page.wait_for_function = AsyncMock(side_effect=TimeoutError)
    settled = AsyncMock(return_value="Complete fallback answer")
    monkeypatch.setattr(mod.humanize, "wait_until_settled", settled)
    asyncio.run(mod.ChatGPTAdapter()._wait_done(page))
    settled.assert_awaited_once_with(page, mod._S["answer_container"], quiet_for=5.0, timeout=60.0)
