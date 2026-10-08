"""Actual endpoint/worker concurrency checks; no accounts, browsers or scans."""
import asyncio
from pathlib import Path
import threading
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import billing, control_agent, updates, __version__
from app.api import browser, desktop
from app.scanner import orchestrator


FUTURE_VERSION = __version__.rsplit(".",1)[0]+"."+str(int(__version__.rsplit(".",1)[1])+1)

@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for name, value in {'_applying': False, '_activity': 0, '_progress': None,
                        '_error': '', '_handoff_error': '', '_release': None,
                        '_installer': None, '_watcher': None, '_abort_path': None,
                        '_abort_failed': False}.items():
        monkeypatch.setattr(updates, name, value)
    monkeypatch.setattr(orchestrator, '_scan_start_lock', asyncio.Lock())
    monkeypatch.setattr(orchestrator, 'active_controller', lambda: None)
    monkeypatch.setattr(control_agent, '_work_tasks', set())
    monkeypatch.setattr(control_agent, 'STATE', {})
    monkeypatch.setattr(desktop, 'STATE', {})
    monkeypatch.setattr(desktop, 'login_task', None)
    monkeypatch.setattr(updates.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(updates.config, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(billing, 'enabled', lambda: True)
    monkeypatch.setattr(billing, 'token', lambda: 'fixture-device-token')
    monkeypatch.setattr(desktop, 'device_id', lambda: 'fixture-device')
    monkeypatch.setattr(desktop.window_control, 'shutdown_ready', lambda: True)
    monkeypatch.setattr(browser, 'status', lambda: {'installed': True, 'installing': False,
                        'services': {}, 'logins_in_progress': []})
    saved = {}
    monkeypatch.setattr(updates.repo, 'get_setting', lambda key, default=None: saved.get(key, default))
    monkeypatch.setattr(updates.repo, 'set_setting', lambda key, value, **_: saved.__setitem__(key, value))
    async def unexpected_metadata():
        raise AssertionError('Update passed preflight during admitted work')
    monkeypatch.setattr(updates, '_latest', unexpected_metadata)


async def rejected_update():
    with pytest.raises(HTTPException) as error:
        await desktop.download_update(desktop.UpdateIn(version=FUTURE_VERSION))
    assert error.value.status_code == 409
    assert not updates.busy()


def test_connect_start_is_admitted_before_browser_or_exchange(monkeypatch):
    opened = []
    monkeypatch.setattr(desktop.webbrowser, 'open', lambda url: opened.append(url) or True)

    async def scenario():
        entered, reply, exchange = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def request(method, path, **kwargs):
            if path == '/control/connect/start':
                entered.set()
                await reply.wait()
                return {'id': 'fixture-id', 'secret': 'fixture-secret', 'path': '/fixture-login'}
            assert path == '/control/connect/exchange'
            await exchange.wait()
            return {'pending': True}
        monkeypatch.setattr(billing, '_request', request)
        task = asyncio.create_task(desktop.login())
        await entered.wait()
        assert desktop.login_task is None and updates.working() and not opened
        await rejected_update()
        reply.set()
        assert await task == {'pending': True}
        assert opened and desktop.login_task and not updates.working()
        await rejected_update()
        await desktop.cancel_login()
    asyncio.run(scenario())


def test_inflight_poll_blocks_update_and_hands_off_to_tracked_work(monkeypatch):
    monkeypatch.setattr(control_agent, 'enroll', AsyncMock())
    monkeypatch.setattr(control_agent, 'import_projects', AsyncMock())
    monkeypatch.setattr(billing, 'identity', AsyncMock(return_value={'id': 'fixture-owner'}))

    async def scenario():
        polling, reply, syncing, finish = (asyncio.Event() for _ in range(4))
        async def request(method, path, **kwargs):
            if path == '/control/agent/poll':
                polling.set()
                await reply.wait()
                return {'run': None, 'name': 'fixture-device'}
            assert path == '/wallet'
            return {'available_kopeks': 1000}
        async def maintenance(_):
            syncing.set()
            await finish.wait()
        monkeypatch.setattr(billing, '_request', request)
        monkeypatch.setattr(control_agent, 'maintenance', maintenance)
        task = asyncio.create_task(control_agent.run_agent())
        try:
            await polling.wait()
            assert updates.working()
            await rejected_update()
            reply.set()
            await syncing.wait()
            assert not updates.working() and control_agent.work_in_progress()
            await rejected_update()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert not updates.working() and not control_agent.work_in_progress()
    asyncio.run(scenario())


def test_reserved_update_does_not_poll_or_open_login(monkeypatch):
    request = AsyncMock()
    monkeypatch.setattr(billing, '_request', request)
    monkeypatch.setattr(control_agent, 'enroll', AsyncMock())
    async def scenario():
        assert updates.reserve()
        worker = asyncio.create_task(control_agent.run_agent())
        try:
            await asyncio.sleep(.01)
            with pytest.raises(HTTPException) as error:
                await desktop.login()
            assert error.value.status_code == 409
            assert not updates.working()
            request.assert_not_awaited()
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(scenario())


def test_password_enrollment_keeps_admission_through_temporary_token_revocation(monkeypatch):
    stored = []
    monkeypatch.setattr(desktop, 'store_token', lambda token, **_kwargs: stored.append(token))
    async def scenario():
        phases = ('/auth/login', '/control/agent/enroll', '/auth/logout')
        entered = {path: asyncio.Event() for path in phases}
        release = {path: asyncio.Event() for path in phases}
        async def request(method, path, **kwargs):
            entered[path].set()
            await release[path].wait()
            if path == '/auth/login':
                return {'token': 'fixture-temporary-token', 'user': {'id': 'fixture-user'}}
            if path == '/control/agent/enroll':
                return {'token': 'fixture-device-token'}
            return {'ok': True}
        monkeypatch.setattr(billing, '_request', request)
        task = asyncio.create_task(desktop.password_login(desktop.PasswordIn(email='fixture@example.test', password='fixture')))
        try:
            for path in phases:
                await entered[path].wait()
                assert updates.working(), path
                await rejected_update()
                release[path].set()
            assert await task == {'ok': True}
            assert stored == ['fixture-device-token'] and not updates.working()
        finally:
            for event in release.values(): event.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['timeout', 'abort_denied', 'handoff_denied'])
def test_shutdown_timeout_after_successful_apply_waits_for_installer_before_retry(monkeypatch, tmp_path, failure):
    release = {'version': FUTURE_VERSION, 'installer': {'size_bytes': 1, 'sha256': 'a' * 64},
               'portable': {'size_bytes': 1, 'sha256': 'b' * 64}}
    wait_started, exited = threading.Event(), threading.Event()
    async def latest(): return release
    async def download(_release, target): target.write_bytes(b'fixture')
    class Process:
        def poll(self): return None
        def wait(self):
            wait_started.set()
            assert exited.wait(2), 'fixture installer was not released'
    def spawn(argv, **_):
        ack = Path(next(value.split('=', 1)[1] for value in argv if value.startswith('/UPDATEACK=')))
        ack.write_text('READY')
        return Process()
    monkeypatch.setattr(updates, '_latest', latest)
    monkeypatch.setattr(updates, '_download', download)
    monkeypatch.setattr(updates.subprocess, 'Popen', spawn)
    stage = tmp_path / 'airate-update-timeout'
    stage.mkdir()
    monkeypatch.setattr(updates.tempfile, 'mkdtemp', lambda **_: str(stage))
    if failure != 'timeout':
        original_touch = Path.touch
        def denied_abort(path, *args, **kwargs):
            if path == stage / 'abort': raise PermissionError('fixture abort write denied')
            return original_touch(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'touch', denied_abort)
    try:
        if failure == 'handoff_denied':
            with pytest.raises(ValueError, match='завершение'):
                asyncio.run(updates.apply(FUTURE_VERSION, lambda: False))
        else:
            asyncio.run(updates.apply(FUTURE_VERSION, lambda: True))
            assert updates.busy() and not wait_started.is_set()
            updates.shutdown_failed('fixture shutdown timed out')
        assert (stage / 'abort').exists() is (failure == 'timeout')
        assert wait_started.wait(1)
        assert updates.busy(), 'retry enabled while old installer still alive'
        updates.shutdown_failed('fixture shutdown timed out')
        watcher = updates._watcher
        quit_wait = threading.Thread(target=updates.wait_failed_cancellation)
        quit_wait.start()
        if failure != 'timeout':
            quit_wait.join(.05)
            assert quit_wait.is_alive(), 'parent exit allowed while cancellation failed'
        else:
            quit_wait.join(1)
            assert not quit_wait.is_alive()
        exited.set()
        watcher.join(1)
        quit_wait.join(1)
        assert not quit_wait.is_alive()
        assert not watcher.is_alive() and not updates.busy()
        assert updates.snapshot()['error'] == 'fixture shutdown timed out'
    finally:
        exited.set()
        if updates._watcher: updates._watcher.join(1)


def test_partial_download_is_removed_without_launching_installer(monkeypatch, tmp_path):
    stage = tmp_path / 'airate-update-partial'
    stage.mkdir()
    monkeypatch.setattr(updates.tempfile, 'mkdtemp', lambda **_: str(stage))
    monkeypatch.setattr(updates.tempfile, 'gettempdir', lambda: str(tmp_path))
    async def latest(): return {'version': FUTURE_VERSION}
    async def failed_download(_, target):
        target.write_bytes(b'partial untrusted payload')
        raise ValueError('download interrupted')
    launched = []
    monkeypatch.setattr(updates, '_latest', latest)
    monkeypatch.setattr(updates, '_download', failed_download)
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda *args, **kwargs: launched.append(args))
    with pytest.raises(ValueError, match='interrupted'):
        asyncio.run(updates.apply(FUTURE_VERSION, lambda: True))
    assert not stage.exists() and not launched and not updates.busy()
