import asyncio
import json

import httpx
import pytest

from app import updates
from app.api import desktop


@pytest.fixture(autouse=True)
def clean_updater_state(monkeypatch):
    monkeypatch.setattr(updates, '__version__', '2026.9.29.2')
    monkeypatch.setattr(updates.config, 'PORTABLE', True)
    monkeypatch.setattr(updates, '_release', None)
    monkeypatch.setattr(updates, '_error', '')
    monkeypatch.setattr(updates, '_checking', False)


def test_release_validation_and_numeric_version_ordering():
    valid = {"version": "2026.9.29.3", "installer": {"size_bytes": 1, "sha256": "a" * 64},
             "portable": {"size_bytes": 2, "sha256": "b" * 64}}
    assert updates.valid_release(valid) == valid
    assert updates.version_parts("2026.9.29.10") > updates.version_parts("2026.9.29.2")
    for bad in (None, 1, "2026.9.29", "٢٠٢٦.9.29.3", "123456.9.29.3"):
        assert updates.version_parts(bad) is None
    valid["installer"]["size_bytes"] = True
    assert updates.valid_release(valid) is None


def test_update_urls_are_fixed_official_https_urls():
    assert updates.RELEASE_URL == "https://airate.tech/api/v1/agent-download"
    assert updates.INSTALLER_URL == "https://airate.tech/downloads/AIRate-Setup.exe"
    assert updates.PORTABLE_URL == "https://airate.tech/downloads/AI-Mentions-Windows.zip"


def test_http_check_handles_new_equal_redirect_and_oversized_metadata(monkeypatch):
    saved, original = {}, updates.httpx.AsyncClient
    monkeypatch.setattr(updates.repo, "get_setting", lambda key: saved.get(key))
    monkeypatch.setattr(updates.repo, "set_setting", lambda key, value, **_: saved.__setitem__(key, value))
    payload = {"release": {"version": "2026.9.29.3", "installer": {"size_bytes": 1, "sha256": "a" * 64},
                           "portable": {"size_bytes": 2, "sha256": "b" * 64}}}

    def run(response):
        updates._release = None
        updates._error = ""
        transport = httpx.MockTransport(lambda request: response)
        monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
        return asyncio.run(updates.check(manual=True))

    assert run(httpx.Response(200, json=payload))["release"]["version"] == "2026.9.29.3"
    payload["release"]["version"] = "2026.9.29.2"
    assert run(httpx.Response(200, json=payload))["release"] is None
    assert run(httpx.Response(302))["error"]
    assert run(httpx.Response(200, content=b"x" * (updates.MAX_BODY + 1)))["error"]


def test_dismisses_only_after_successful_download_open(monkeypatch):
    saved = {}
    updates._release = {"version": "2026.9.29.3", "installer": {"size_bytes": 1, "sha256": "a" * 64},
                        "portable": {"size_bytes": 2, "sha256": "b" * 64}}
    monkeypatch.setattr(updates.repo, "get_setting", lambda key: saved.get(key))
    monkeypatch.setattr(updates.repo, "set_setting", lambda key, value, **_: saved.__setitem__(key, value))
    monkeypatch.setattr(desktop.webbrowser, "open", lambda _: False)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        desktop.download_update(desktop.UpdateIn(version="2026.9.29.3", portable=True))
    assert not saved
    opened = []
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: opened.append(url) or True)
    desktop.download_update(desktop.UpdateIn(version="2026.9.29.3", portable=True))
    assert opened == [updates.PORTABLE_URL] and saved["dismissed_update_version"] == "2026.9.29.3"


def test_manual_check_waits_for_an_in_flight_check(monkeypatch):
    monkeypatch.setattr(updates.repo, "get_setting", lambda _: None)

    async def run():
        updates._checking = True
        async def finish():
            await asyncio.sleep(.01)
            updates._checking = False
        asyncio.create_task(finish())
        return await updates.check(manual=True)

    assert asyncio.run(run())["checking"] is False


def test_manual_success_rearms_only_the_checked_dismissed_release(monkeypatch):
    saved = {"dismissed_update_version": "2026.9.29.3"}
    original = updates.httpx.AsyncClient
    monkeypatch.setattr(updates.repo, "get_setting", lambda key: saved.get(key))
    monkeypatch.setattr(updates.repo, "set_setting", lambda key, value, **_: saved.__setitem__(key, value))
    release = {"version": "2026.9.29.3", "installer": {"size_bytes": 1, "sha256": "a" * 64},
               "portable": {"size_bytes": 2, "sha256": "b" * 64}}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"release": release}))
    monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    updates._release = release
    assert updates.snapshot()["release"] is None
    assert asyncio.run(updates.check(manual=True))["release"]["version"] == "2026.9.29.3"
    assert saved["dismissed_update_version"] is None
    updates.dismiss("2026.9.29.3")
    updates._release = {**release, "version": "2026.9.29.4"}
    assert updates.snapshot()["release"]["version"] == "2026.9.29.4"


def test_download_uses_local_portable_mode_not_request_body(monkeypatch):
    saved, opened = {}, []
    updates._release = {"version": "2026.9.29.3", "installer": {"size_bytes": 1, "sha256": "a" * 64},
                        "portable": {"size_bytes": 2, "sha256": "b" * 64}}
    monkeypatch.setattr(updates.repo, "get_setting", lambda key: saved.get(key))
    monkeypatch.setattr(updates.repo, "set_setting", lambda key, value, **_: saved.__setitem__(key, value))
    monkeypatch.setattr(desktop.config, "PORTABLE", False)
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: opened.append(url) or True)
    desktop.download_update(desktop.UpdateIn(version="2026.9.29.3", portable=True))
    assert opened == [updates.INSTALLER_URL]


@pytest.mark.parametrize('response', [httpx.Response(302), httpx.Response(200, json={'release': None}),
                                      httpx.Response(200, content=b'not json')])
def test_failure_or_withdrawal_does_not_resurrect_cached_dismissed_release(monkeypatch, response):
    saved = {'dismissed_update_version': '2026.9.29.3'}
    original = httpx.AsyncClient
    monkeypatch.setattr(updates.repo, 'get_setting', lambda key: saved.get(key))
    monkeypatch.setattr(updates.repo, 'set_setting', lambda key, value, **_: saved.__setitem__(key, value))
    monkeypatch.setattr(updates.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(lambda _: response), **kwargs))
    updates._release = {'version': '2026.9.29.3'}
    result = asyncio.run(updates.check(manual=True))
    assert result['release'] is None and result['error']
    assert updates.snapshot()['release'] is None
    assert saved['dismissed_update_version'] == '2026.9.29.3'


@pytest.mark.parametrize('success', [True, False])
def test_manual_waiter_rearms_only_successful_automatic_check(monkeypatch, success):
    saved = {'dismissed_update_version': '2026.9.29.3'}
    original = httpx.AsyncClient
    monkeypatch.setattr(updates.repo, 'get_setting', lambda key: saved.get(key))
    monkeypatch.setattr(updates.repo, 'set_setting', lambda key, value, **_: saved.__setitem__(key, value))
    release = {'version': '2026.9.29.3', 'installer': {'size_bytes': 1, 'sha256': 'a' * 64},
               'portable': {'size_bytes': 2, 'sha256': 'b' * 64}}
    async def scenario():
        started, finish = asyncio.Event(), asyncio.Event()
        async def request(_):
            started.set()
            await finish.wait()
            return httpx.Response(200, json={'release': release}) if success else httpx.Response(503)
        monkeypatch.setattr(updates.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(request), **kwargs))
        updates._checking, updates._release, updates._error = False, release, ''
        automatic = asyncio.create_task(updates.check())
        await started.wait()
        manual = asyncio.create_task(updates.check(manual=True))
        await asyncio.sleep(0)
        finish.set()
        await automatic
        return await manual
    result = asyncio.run(scenario())
    assert result['checking'] is False
    assert (result['release'] is not None) is success
    assert saved['dismissed_update_version'] == (None if success else '2026.9.29.3')
    assert (updates.snapshot()['release'] is not None) is success
