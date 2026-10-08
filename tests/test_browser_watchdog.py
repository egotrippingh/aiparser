import asyncio
from contextlib import asynccontextmanager

import pytest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.scanner import orchestrator as scan
from app.scanner.adapters.base import ReadyState
from app.scanner import browser
from app.api import scans as scans_api
from app.db import repo
from app.detect.llm import LLMVerdict
from test_scan_pipeline import setup, run


class Adapter:
    async def ask(self, *_args, **_kwargs):
        await asyncio.Event().wait()

    async def capture(self, *_args):
        await asyncio.Event().wait()


def test_hung_browser_task_times_out_and_stop_cancels_it(monkeypatch):
    async def scenario():
        ctl = scan.ScanController(1, 1, 1, "2026-10-07")
        monkeypatch.setattr(scan, "_BROWSER_TASK_TIMEOUT", 0.01)
        monkeypatch.setattr(scan, "_BROWSER_CANCEL_GRACE", 0)
        with pytest.raises(scan.BrowserTaskTimeout, match="ask exceeded"):
            await scan._ask_and_capture(Adapter(), object(), {}, {"id": 7, "text": "secret"}, "alice", 1, ctl)
        assert not ctl.browser_tasks and not ctl.browser_phase
    asyncio.run(scenario())


def test_snapshot_exposes_phase_without_query_text():
    async def scenario():
        ctl, entered, release = scan.ScanController(1, 1, 1, "2026-10-07"), asyncio.Event(), asyncio.Event()
        class ReadyAdapter(Adapter):
            async def ask(self, *_args, **_kwargs):
                entered.set()
                await release.wait()
        task = asyncio.create_task(scan._ask_and_capture(ReadyAdapter(), object(), {}, {"id": 7, "text": "secret"}, "alice", 1, ctl))
        await entered.wait()
        state = ctl.snapshot()["browser_task"]
        assert state["service"] == "alice" and state["query_id"] == 7 and state["phase"] == "ask"
        assert "text" not in state and state["phase_timeout_sec"] == scan._BROWSER_TASK_TIMEOUT
        ctl.stop()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not ctl.browser_tasks
    asyncio.run(scenario())


def test_timeout_ends_service_without_submitting_remaining_prompt(monkeypatch):
    async def scenario():
        ctl = scan.ScanController(1, 1, 2, "2026-10-07")
        ctl.per_service["alice"] = {"done": 0, "total": 2, "state": "running", "started": 0}
        calls = []
        class ServiceAdapter:
            async def ensure_ready(self, _page): return ReadyState(ok=True)
        @asynccontextmanager
        async def context(*_args, **_kwargs):
            yield type("Context", (), {"pages": [type("Page", (), {"is_closed": lambda self: False})()]})()
        async def timed(*_args, **_kwargs):
            calls.append(_args[1]["id"])
            return "browser_timeout"
        monkeypatch.setattr(scan, "get_adapter", lambda _: ServiceAdapter())
        monkeypatch.setattr(scan, "service_context", context)
        monkeypatch.setattr(scan, "_run_one", timed)
        monkeypatch.setattr(scan, "_record_auth_state", lambda *_args: None)
        await scan._run_service({}, "alice", [{"id": 1}, {"id": 2}], {"typing_speed": 1, "delay_min_sec": 0, "delay_max_sec": 0, "break_every_n": 0, "adaptive_pacing": None}, "", "", "never", ctl)
        assert calls == [1] and ctl.done == 1 and ctl.per_service["alice"]["state"] == "failed"
    asyncio.run(scenario())


def test_stop_during_browser_ask_drains_saved_analysis(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, adapter = setup(tmp_path, monkeypatch, count=2)
    async def scenario():
        analyzing, asking, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        cancelled = []
        async def ask(_page, text, *_args, **_kwargs):
            asked.append(text)
            if len(asked) == 2:
                asking.set()
                await asyncio.Event().wait()
        async def analyze(**_kwargs):
            analyzing.set()
            try: await release.wait()
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
            return LLMVerdict(found=True, model='fake')
        monkeypatch.setattr(adapter, 'ask', ask)
        monkeypatch.setattr(scan.llm_mod, 'evaluate', analyze)
        task = asyncio.create_task(run(project, items, settings, ctl))
        await asyncio.wait_for(asyncio.gather(analyzing.wait(), asking.wait()), 1)
        await scans_api.stop_scan(ctl.scan_id)
        await asyncio.sleep(0)
        assert not cancelled and not task.done()
        release.set()
        await asyncio.wait_for(task, 1)
        assert not cancelled and repo.get_scan(ctl.scan_id)['status'] == 'stopped'
        assert len(repo.results_for_scan(ctl.scan_id)) == 1
        assert not repo.pending_captures(ctl.scan_id) and ctl.state == 'finished'
    asyncio.run(scenario())


def test_capture_completion_racing_stop_is_committed_once(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, adapter = setup(tmp_path, monkeypatch, count=1)
    original = adapter.capture
    async def capture(page):
        cap = await original(page)
        asyncio.get_running_loop().call_soon(ctl.stop)
        return cap
    monkeypatch.setattr(adapter, 'capture', capture)
    asyncio.run(run(project, items, settings, ctl))
    assert len(asked) == 1 and len(repo.results_for_scan(ctl.scan_id)) == 1
    assert not repo.pending_captures(ctl.scan_id)
    assert repo.get_scan(ctl.scan_id)['status'] == 'stopped'


def test_hung_capture_records_error_and_leaves_tail_pending(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, adapter = setup(tmp_path, monkeypatch, count=2)
    async def capture(_page): await asyncio.Event().wait()
    monkeypatch.setattr(adapter, 'capture', capture)
    monkeypatch.setattr(scan, '_BROWSER_TASK_TIMEOUT', .01)
    monkeypatch.setattr(scan, '_BROWSER_CANCEL_GRACE', .01)
    asyncio.run(run(project, items, settings, ctl))
    rows = repo.results_for_scan(ctl.scan_id)
    assert len(asked) == len(rows) == 1 and rows[0]['status'] == 'error'
    assert 'capture exceeded' in rows[0]['error_message']
    assert repo.get_scan(ctl.scan_id)['status'] == 'failed'


@pytest.mark.parametrize('action', ['timeout', 'parent_cancel', 'stop'])
def test_resistant_browser_task_remains_owned_until_done(monkeypatch, action):
    async def scenario():
        ctl, entered, release = scan.ScanController(1, 1, 1, '2026-10-07'), asyncio.Event(), asyncio.Event()
        class Resistant(Adapter):
            async def ask(self, *_args, **_kwargs):
                entered.set()
                while not release.is_set():
                    try: await release.wait()
                    except asyncio.CancelledError: pass
            async def capture(self, *_args): return object()
        monkeypatch.setattr(scan, '_BROWSER_TASK_TIMEOUT', .01)
        monkeypatch.setattr(scan, '_BROWSER_CANCEL_GRACE', .01)
        wrapper = asyncio.create_task(scan._ask_and_capture(Resistant(), object(), {}, {'id': 1, 'text': 'q'}, 'alice', 1, ctl))
        await entered.wait()
        if action == 'parent_cancel': wrapper.cancel()
        if action == 'stop': ctl.stop()
        with pytest.raises(scan.BrowserTaskTimeout if action == 'timeout' else asyncio.CancelledError):
            await asyncio.wait_for(wrapper, .2)
        await asyncio.sleep(0)
        assert len(ctl.browser_tasks) == 1 and not next(iter(ctl.browser_tasks)).done()
        release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(*ctl.browser_tasks, return_exceptions=True), 1)
        assert all(isinstance(value, asyncio.CancelledError) for value in outcomes)
        await asyncio.sleep(0)
        assert not ctl.browser_tasks
    asyncio.run(scenario())


def test_parallel_browser_phases_are_owned_by_each_service():
    async def scenario():
        ctl, one, two, release = scan.ScanController(1, 1, 2, '2026-10-07'), asyncio.Event(), asyncio.Event(), asyncio.Event()
        class Capturing(Adapter):
            async def ask(self, *_args, **_kwargs): pass
            async def capture(self, *_args):
                one.set(); await release.wait()
        class Asking(Adapter):
            async def ask(self, *_args, **_kwargs):
                two.set(); await release.wait()
            async def capture(self, *_args): return None
        tasks = [asyncio.create_task(scan._ask_and_capture(a, object(), {}, {'id': i, 'text': 'q'}, s, 1, ctl))
                 for i, s, a in [(1, 'alice', Capturing()), (2, 'google_aio', Asking())]]
        await asyncio.gather(one.wait(), two.wait())
        states = ctl.snapshot()['browser_tasks']
        assert states['alice']['phase'] == 'capture' and states['google_aio']['phase'] == 'ask'
        release.set(); await asyncio.gather(*tasks)
    asyncio.run(scenario())


def test_bounded_close_observes_errors_and_preserves_body_error(monkeypatch):
    class Manager:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return object()
        async def __aexit__(self, *_args): raise RuntimeError('close failed')
    monkeypatch.setattr(browser, 'AsyncCamoufox', Manager)
    async def scenario():
        with pytest.raises(RuntimeError, match='close failed'):
            async with browser._bounded_camoufox({}, Path('owned-profile')): pass
        async def close(self, *_args): pass
        monkeypatch.setattr(Manager, '__aexit__', close)
        with pytest.raises(ValueError, match='body failed'):
            async with browser._bounded_camoufox({}, Path('owned-profile')):
                raise ValueError('body failed')
    asyncio.run(scenario())


def test_resistant_close_is_bounded_and_cleanup_is_profile_scoped(monkeypatch):
    async def scenario():
        release, closing, killed = asyncio.Event(), [], []
        class Manager:
            def __init__(self, **_kwargs): pass
            async def __aenter__(self): return object()
            async def __aexit__(self, *_args):
                closing.append(asyncio.current_task())
                while not release.is_set():
                    try: await release.wait()
                    except asyncio.CancelledError: pass
        wait = asyncio.wait
        async def short_wait(tasks, **kwargs): return await wait(tasks, timeout=.01)
        async def kill(profile): killed.append(profile)
        monkeypatch.setattr(browser, 'AsyncCamoufox', Manager)
        monkeypatch.setattr(browser.asyncio, 'wait', short_wait)
        monkeypatch.setattr(browser, '_kill_processes_for_profile', kill)
        profile = Path('owned-profile')
        async with browser._bounded_camoufox({}, profile): pass
        assert killed == [profile] and closing and not closing[0].done()
        release.set(); await asyncio.gather(*closing)
    asyncio.run(asyncio.wait_for(scenario(), 1))


def test_http_stop_cancels_browser_task_on_its_own_event_loop(monkeypatch):
    app = FastAPI(); app.include_router(scans_api.router)
    tasks = []
    @app.post('/qa/start')
    async def start():
        ctl = scan.ScanController(55, 1, 1, '2026-10-07')
        entered = asyncio.Event()
        class Asking(Adapter):
            async def ask(self, *_args, **_kwargs):
                entered.set(); await asyncio.Event().wait()
        task = asyncio.create_task(scan._ask_and_capture(Asking(), object(), {}, {'id': 1, 'text': 'q'}, 'alice', 1, ctl))
        tasks.append(task)
        scan._active[55] = ctl
        asyncio.get_running_loop().set_debug(True)
        await entered.wait()
        return {'ok': True}
    monkeypatch.setattr(scan, '_active', {})
    with TestClient(app) as client:
        assert client.post('/qa/start').status_code == 200
        assert client.post('/api/scans/55/stop').json() == {'ok': True}
        assert scan._active[55].stop_signal.is_set()


def test_stop_during_capture_preserves_evidence_until_sources_complete(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, adapter = setup(tmp_path, monkeypatch, count=1)
    async def scenario():
        captured, sources = asyncio.Event(), asyncio.Event()
        original = adapter.capture
        async def capture(page):
            cap = await original(page)
            captured.set()
            await sources.wait()
            return cap
        monkeypatch.setattr(adapter, 'capture', capture)
        monkeypatch.setattr(scan, '_BROWSER_TASK_TIMEOUT', 1)
        monkeypatch.setattr(scan, '_BROWSER_CANCEL_GRACE', .01)
        task = asyncio.create_task(run(project, items, settings, ctl))
        await captured.wait(); ctl.stop()
        await asyncio.sleep(.03)
        assert not task.done()  # source work may exceed cancel grace; don't lose the image
        sources.set(); await asyncio.wait_for(task, 1)
        rows = repo.results_for_scan(ctl.scan_id)
        assert len(asked) == len(rows) == 1 and rows[0]['status'] == 'found'
        assert repo.get_scan(ctl.scan_id)['status'] == 'stopped'
    asyncio.run(scenario())
