import asyncio
import sqlite3
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.api import browser as api
from app.scanner import browser, orchestrator, profiles


@pytest.fixture
def login_state(monkeypatch):
    saved = {}
    monkeypatch.setattr(api, '_login_running', set())
    monkeypatch.setattr(api, '_login_status', {})
    monkeypatch.setattr(api, '_login_tasks', set())
    monkeypatch.setattr(api, 'camoufox_installed', lambda: True)
    monkeypatch.setattr(api, 'cookie_auth_state', lambda _: {'state':'ok','expires_at':None})
    monkeypatch.setattr(api.repo, 'get_setting', lambda key, *args: saved.get(key))
    monkeypatch.setattr(api.repo, 'set_setting', lambda key, value: saved.update({key:value}))
    monkeypatch.setattr(orchestrator, 'active_controller', lambda: None)
    return saved


def test_double_click_has_one_task_and_error_is_visible(login_state, monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError('Profile is locked')
    monkeypatch.setattr(api,'open_login_window',fail)
    async def scenario():
        await api.login('chatgpt')
        assert api._service_auth('chatgpt')['login_state'] == 'starting'
        assert (await api.login('chatgpt'))['already_open']
        assert len(api._login_tasks)==1
        await asyncio.gather(*api._login_tasks)
        result=api._service_auth('chatgpt')
        assert not result['login_open']
        assert result['login_state']=='error'
        assert 'Profile is locked' in result['login_error']
    asyncio.run(scenario())


def test_window_close_saves_new_session_without_faking_scan_success(login_state,monkeypatch):
    login_state['auth_state:chatgpt']='{"state":"auth_required","at":"2026-09-26T10:00:00"}'
    async def opened(*args, on_open, **kwargs):
        on_open()
        assert api._service_auth('chatgpt')['login_state']=='open'
    monkeypatch.setattr(api,'open_login_window',opened)
    async def scenario():
        await api.login('chatgpt')
        await asyncio.gather(*api._login_tasks)
        state=api._service_auth('chatgpt')
        assert state['last_login_at']
        assert state['last_scan_state']=='auth_required'
        assert state['login_state']=='closed'
    asyncio.run(scenario())


def test_navigation_timeout_keeps_window_until_user_closes(monkeypatch):
    async def scenario():
        callbacks={}
        page=MagicMock()
        page.goto=AsyncMock(side_effect=TimeoutError('network'))
        page.is_closed.return_value=False
        context=MagicMock()
        context.pages=[page]
        context.on.side_effect=lambda event, cb: callbacks.update({event:cb})
        @asynccontextmanager
        async def factory(*args,**kwargs):
            yield context
        monkeypatch.setattr(browser,'service_context',factory)
        errors=[];opened=[]
        task=asyncio.create_task(browser.open_login_window('chatgpt','https://chatgpt.com/',
            on_open=lambda:opened.append(True),on_navigation_error=errors.append))
        await asyncio.sleep(0)
        assert opened and errors and not task.done()
        callbacks['close']()
        await task
    asyncio.run(scenario())


def test_cookie_status_reads_recent_committed_wal(tmp_path):
    profile=tmp_path/'chatgpt';profile.mkdir()
    con=sqlite3.connect(profile/'cookies.sqlite')
    con.execute('pragma journal_mode=WAL')
    con.execute('pragma wal_autocheckpoint=0')
    con.execute('create table moz_cookies (host text,name text,expiry integer)')
    con.commit()
    con.execute('pragma wal_checkpoint(TRUNCATE)')
    con.execute("insert into moz_cookies values ('.chatgpt.com','__Secure-next-auth.session-token',2000000000)")
    con.commit()
    try:
        assert profiles._read_cookies(profile)==[('.chatgpt.com','__Secure-next-auth.session-token',2000000000)]
    finally:
        con.close()
