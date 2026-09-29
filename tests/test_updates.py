import asyncio
import json

import httpx
import pytest

from app import updates
from app.api import desktop


@pytest.fixture(autouse=True)
def clean_updater_state(monkeypatch):
    saved = {}
    monkeypatch.setattr(updates.repo, 'get_setting', lambda key, default=None: saved.get(key, default))
    monkeypatch.setattr(updates.repo, 'set_setting', lambda key, value, **_: saved.__setitem__(key, value))
    for name, value in {'_activity': 0, '_handoff_error': '', '_abort_path': None,
                        '_installer': None, '_watcher': None, '_abort_failed': False}.items():
        monkeypatch.setattr(updates, name, value)
    monkeypatch.setattr(updates, '__version__', '2026.9.29.2')
    monkeypatch.setattr(updates.config, 'PORTABLE', True)
    monkeypatch.setattr(updates, '_release', None)
    monkeypatch.setattr(updates, '_error', '')
    monkeypatch.setattr(updates, '_checking', False)
    monkeypatch.setattr(updates, '_applying', False)
    monkeypatch.setattr(updates, '_progress', None)


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


def test_apply_uses_server_version_only_and_does_not_dismiss(monkeypatch):
    seen = []
    async def apply(version, shutdown, *, reserved=False):
        seen.append((version, shutdown, reserved))
        return {"ok": True}
    monkeypatch.setattr(desktop.updates, "reserve", lambda: True)
    monkeypatch.setattr(desktop.window_control, "shutdown_ready", lambda: True)
    monkeypatch.setattr(desktop.updates, "apply", apply)
    assert asyncio.run(desktop.download_update(desktop.UpdateIn(version="2026.9.29.3", portable=True))) == {"ok": True}
    assert seen[0][0] == "2026.9.29.3" and seen[0][2] is True


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


def test_apply_failure_is_returned_as_conflict(monkeypatch):
    async def apply(*_, **__):
        raise ValueError("проверка не прошла")
    monkeypatch.setattr(desktop.updates, "reserve", lambda: True)
    monkeypatch.setattr(desktop.window_control, "shutdown_ready", lambda: True)
    monkeypatch.setattr(desktop.updates, "apply", apply)
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        asyncio.run(desktop.download_update(desktop.UpdateIn(version="2026.9.29.3")))



@pytest.mark.parametrize("response, expected", [
    (httpx.Response(302), "Не удалось скачать обновление"),
    (httpx.Response(200, content=b"ab"), "Контрольная сумма обновления не совпадает"),
    (httpx.Response(200, content=b"abc"), "Контрольная сумма обновления не совпадает"),
])
def test_installer_download_rejects_redirect_truncation_and_hash(tmp_path, monkeypatch, response, expected):
    original = updates.httpx.AsyncClient
    monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(lambda _: response), **kwargs))
    release = {"installer": {"size_bytes": 3, "sha256": "a" * 64}}
    with pytest.raises(ValueError, match=expected):
        asyncio.run(updates._download(release, tmp_path / "setup.exe"))


def test_installer_download_uses_identity_encoding_and_exact_digest(tmp_path, monkeypatch):
    body = b"abc"
    seen = []
    original = updates.httpx.AsyncClient
    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=body)
    monkeypatch.setattr(updates.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs))
    release = {"installer": {"size_bytes": len(body), "sha256": __import__("hashlib").sha256(body).hexdigest()}}
    asyncio.run(updates._download(release, tmp_path / "setup.exe"))
    assert (tmp_path / "setup.exe").read_bytes() == body
    assert seen[0].headers["accept-encoding"] == "identity"


def test_reserve_is_single_operation_and_requires_frozen_writable_target(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.config, "BASE_DIR", tmp_path)
    assert updates.reserve() is True
    assert updates.reserve() is False



def test_stop_server_requests_exit_and_joins(monkeypatch):
    from app import main
    server = type("Server", (), {"should_exit": False})()
    class Thread:
        alive = True
        def join(self, timeout):
            self.timeout = timeout
            self.alive = False
        def is_alive(self): return self.alive
    thread = Thread()
    monkeypatch.setattr(main, "_server", server)
    assert main._stop_server(thread, .1)
    assert server.should_exit and thread.timeout == .1

def test_activity_blocks_update_reservation(monkeypatch):
    async def scenario():
        async with updates.activity():
            assert updates.working()
            with pytest.raises(ValueError, match="дождитесь"):
                updates.reserve()
        assert not updates.working()
    asyncio.run(scenario())


def test_stage_creation_failure_releases_update_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.config, "BASE_DIR", tmp_path)
    assert updates.reserve() and updates.busy()
    monkeypatch.setattr(updates.tempfile, "mkdtemp", lambda **_: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        asyncio.run(updates.apply("2026.9.29.3", lambda: True, reserved=True))
    assert not updates.busy()

def test_apply_waits_for_installer_ack_before_requesting_shutdown(tmp_path, monkeypatch):
    release = {"version": "2026.9.29.6", "installer": {"size_bytes": 1, "sha256": "a" * 64},
               "portable": {"size_bytes": 1, "sha256": "b" * 64}}
    calls = []
    async def latest(): return release
    async def download(_release, path): path.write_bytes(b"x")
    def spawn(argv, **kwargs):
        calls.append((argv, kwargs))
        next(value for value in argv if value.startswith("/UPDATEACK=")).split("=", 1)[1]
        from pathlib import Path
        Path(next(value for value in argv if value.startswith("/UPDATEACK=")).split("=", 1)[1]).write_text("READY")
        return type("Process", (), {"poll": lambda self: None})()
    monkeypatch.setattr(updates, "_latest", latest)
    monkeypatch.setattr(updates, "_download", download)
    monkeypatch.setattr(updates.subprocess, "Popen", spawn)
    monkeypatch.setattr(updates.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updates.config, "BASE_DIR", tmp_path)
    (tmp_path / "installed-mode.txt").touch()
    shutdown = lambda: calls.append(("shutdown", {})) or True
    updates._applying = False
    asyncio.run(updates.apply("2026.9.29.6", shutdown))
    assert calls[-1][0] == "shutdown"
    argv = calls[0][0]
    assert any(x == f"/DIR={tmp_path}" for x in argv) and any(x == "/UPDATEMODE=installed" for x in argv)


def test_consumed_success_result_removes_only_our_temp_stage(tmp_path, monkeypatch):
    stage = tmp_path / "airate-update-test"
    stage.mkdir()
    (stage / "result.json").write_text("ready:2026.9.29.2", encoding="utf-8")
    saved = {"update_stage": str(stage)}
    monkeypatch.setattr(updates.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(updates.repo, "get_setting", lambda key: saved.get(key))
    monkeypatch.setattr(updates.repo, "set_setting", lambda key, value, **_: saved.__setitem__(key, value))
    updates.consume_previous_result()
    assert not stage.exists() and saved["update_stage"] is None and saved["update_stage_ready"] is None


def test_unrecognized_stage_path_is_never_deleted(tmp_path, monkeypatch):
    stage = tmp_path / "unrelated"
    stage.mkdir()
    (stage / "result.json").write_text("ready:2026.9.29.2", encoding="utf-8")
    monkeypatch.setattr(updates.repo, "get_setting", lambda _: str(stage))
    monkeypatch.setattr(updates.tempfile, "gettempdir", lambda: str(tmp_path))
    updates.consume_previous_result()
    assert stage.exists()


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
