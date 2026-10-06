"""Durable browser answers, bounded overlap and timing; no real profiles or charges."""
import asyncio
import json
import platform
import sqlite3
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import billing, config
from app.api import projects, queries
from app.db import repo
from app.detect.llm import LLMVerdict
from app.scanner import orchestrator as scan
from app.scanner.adapters.base import ProviderQuotaError, ReadyState


def setup(tmp_path, monkeypatch, count=6, services=('chatgpt',)):
    monkeypatch.setattr(platform, 'node', lambda: 'test-device')
    monkeypatch.setattr(repo, '_local', threading.local())
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'scan.db')
    monkeypatch.setattr(config, 'screenshot_dir', lambda *_: tmp_path)
    monkeypatch.setattr(billing, 'enabled', lambda: False)
    monkeypatch.setattr(scan.imaging, 'to_webp', lambda raw: raw)
    monkeypatch.setattr(scan, '_active', {})
    repo.init_db()
    pid = repo.create_project('Project', 'Brand', parallel_scan=True, brand_clarification='original identity')
    repo.add_queries(pid, [f'question {n}' for n in range(count)])
    project, items = repo.get_project(pid), repo.list_queries(pid)
    settings = scan._settings_snapshot(list(services))
    settings.update(managed_llm=False, adaptive_pacing={'version': 1, 'ceiling_sec': 0})
    settings['per_service_timing'] = {svc: {'typing_speed': 0, 'delay_min_sec': 0,
                                         'delay_max_sec': 0, 'break_every_n': 0} for svc in services}
    sid = repo.create_scan(pid, list(services), settings)
    ctl = scan.ScanController(sid, pid, len(items) * len(services), '2026-10-06')
    scan._active[sid] = ctl
    asked = []

    class Adapter:
        throttled = False
        async def ensure_ready(self, page): return ReadyState(ok=True)
        async def ask(self, page, text, *_args, **_kwargs): asked.append(text)
        async def capture(self, page):
            return SimpleNamespace(shown=True, answer_text='Brand answer', sources=['https://example.test'],
                                   extra={'main_text': 'Brand answer', 'cards_text': 'card'}, screenshot_bytes=b'image')
    adapter = Adapter()
    page = SimpleNamespace(is_closed=lambda: False)
    @asynccontextmanager
    async def browser(*_args, **_kwargs):
        yield SimpleNamespace(pages=[page])
    async def verdict(**_kwargs): return LLMVerdict(found=True, model='fake')
    monkeypatch.setattr(scan, 'get_adapter', lambda _: adapter)
    monkeypatch.setattr(scan, 'service_context', browser)
    monkeypatch.setattr(scan.llm_mod, 'evaluate', verdict)
    return project, items, settings, ctl, asked, adapter


def run(project, items, settings, ctl, services=('chatgpt',)):
    return scan._run_scan(project, list(services), items, set(), settings, ctl)


def save(project, query, settings, ctl, state='pending', payer=None, check=None):
    repo.save_capture(ctl.scan_id, query['id'], 'chatgpt', project=project, query=query, settings=settings,
                      payer_id=payer, check_id=check, shown=True, answer_text='original answer', sources=[],
                      extra={'plain_text': 'original plain'}, screenshot_bytes=b'image', screenshot_path=None)
    repo.capture_state(ctl.scan_id, query['id'], 'chatgpt', state)


@pytest.mark.parametrize('action', ['pause', 'stop', 'cancel'])
def test_overlap_bounded_backlog_and_controls(tmp_path, monkeypatch, action):
    project, items, settings, ctl, asked, _ = setup(tmp_path, monkeypatch, services=('chatgpt', 'perplexity'))
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        busy = peak = 0
        async def blocked(**_kwargs):
            nonlocal busy, peak
            busy += 1
            peak = max(peak, busy)
            entered.set()
            await release.wait()
            busy -= 1
            return LLMVerdict(found=True, model='fake')
        monkeypatch.setattr(scan.llm_mod, 'evaluate', blocked)
        task = asyncio.create_task(run(project, items, settings, ctl, ('chatgpt', 'perplexity')))
        await entered.wait()
        for _ in range(30): await asyncio.sleep(0)
        assert ctl.done == 0 and 2 <= len(asked) <= 5  # 1 active + 2 waiting + 1 per producer
        assert ctl.analysis_queue.qsize() <= 2 and peak == 1
        getattr(ctl, action)() if action != 'cancel' else task.cancel()
        if action == 'cancel':
            with pytest.raises(asyncio.CancelledError): await task
            assert ctl.done == 0 and repo.pending_captures(ctl.scan_id)
            assert scan.active_controller() is None
            return
        before = len(asked)
        release.set()
        for _ in range(50): await asyncio.sleep(0)
        assert len(asked) == before
        if action == 'pause':
            assert ctl.done > 0 and not task.done() and scan.active_controller() is ctl
            ctl.resume()
        await asyncio.wait_for(task, 3)
        assert not repo.pending_captures(ctl.scan_id)
        assert scan.active_controller() is None
        assert repo.get_scan(ctl.scan_id)['status'] == ('stopped' if action == 'stop' else 'done')
    asyncio.run(scenario())


@pytest.mark.parametrize('state', ['pending', 'analyzing', 'error'])
def test_continuation_uses_frozen_inputs_without_browser(tmp_path, monkeypatch, state):
    project, items, settings, ctl, asked, _ = setup(tmp_path, monkeypatch, count=1)
    save(project, items[0], settings, ctl, state)
    repo.update_project(project['id'], brand_name='Changed', brand_clarification='changed identity')
    repo._exec('UPDATE queries SET text=? WHERE id=?', ('changed question', items[0]['id']))
    seen = []
    async def verdict(**kwargs):
        seen.append((kwargs['brand_name'], kwargs['brand_clarification'], kwargs['query'], kwargs['answer_text']))
        return LLMVerdict(found=True, model='fake')
    monkeypatch.setattr(scan.llm_mod, 'evaluate', verdict)
    asyncio.run(run(repo.get_project(project['id']), repo.list_queries(project['id']), settings, ctl))
    assert asked == [] and seen == [('Brand', 'original identity', 'question 0', 'original plain')]
    assert ctl.done == 1 and not repo.pending_captures(ctl.scan_id)


def test_raw_capture_survives_export_failure_and_retries_analysis(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, adapter = setup(tmp_path, monkeypatch, count=1)
    def failed(_raw): raise OSError('codec failed')
    monkeypatch.setattr(scan.imaging, 'to_webp', failed)
    async def one():
        return await scan._run_one(project, items[0], 'chatgpt', adapter, None, settings,
                                   0, '', 'fake', 'never', ctl)
    assert asyncio.run(one()) == 'error'
    row = repo.pending_captures(ctl.scan_id)[0]
    assert row['state'] == 'error' and row['screenshot_bytes'] == b'image'
    monkeypatch.setattr(scan.imaging, 'to_webp', lambda raw: raw)
    assert asyncio.run(one()) == 'found' and asked == ['question 0']


def test_skipped_capture_finishes_and_deletion_protects_errors(tmp_path, monkeypatch):
    project, items, settings, ctl, _, adapter = setup(tmp_path, monkeypatch, count=1)
    save(project, items[0], settings, ctl, 'error', check='run:1:chatgpt')
    repo.queue_billing('run:1:chatgpt', 'release')
    assert repo.pending_billing() == []
    for callback, args in [(projects.delete_project, (project['id'],)),
                           (queries.delete_query, (project['id'], items[0]['id']))]:
        with pytest.raises(HTTPException) as error: callback(*args)
        assert error.value.status_code == 409
    repo._exec('UPDATE captures SET shown=0')
    asyncio.run(run(project, items, settings, ctl))
    assert not repo.pending_captures(ctl.scan_id)
    assert repo.results_for_scan(ctl.scan_id)[0]['status'] == 'skipped'
    assert repo.pending_billing() == [{'check_id': 'run:1:chatgpt', 'status': 'release'}]
    repo.delete_query(items[0]['id'])
    repo.delete_project(project['id'])


def test_finalization_rolls_back_result_outboxes_and_raw_cleanup(tmp_path, monkeypatch):
    project, items, settings, ctl, _, _ = setup(tmp_path, monkeypatch, count=1)
    save(project, items[0], settings, ctl, check='run:1:chatgpt')
    repo._exec("CREATE TRIGGER fail_outbox BEFORE INSERT ON screenshot_outbox BEGIN SELECT RAISE(ABORT, 'disk'); END")
    with pytest.raises(sqlite3.IntegrityError):
        repo.finalize_capture(ctl.scan_id, items[0]['id'], 'chatgpt', 'found',
                              {'answer_text': 'answer', 'screenshot_path': 'shot.webp'}, 'run:1:chatgpt')
    assert repo.results_for_scan(ctl.scan_id) == [] and repo.pending_billing() == []
    assert repo.pending_captures(ctl.scan_id)[0]['answer_text'] == 'original answer'
    repo._exec('DROP TRIGGER fail_outbox')
    repo.finalize_capture(ctl.scan_id, items[0]['id'], 'chatgpt', 'found',
                          {'answer_text': 'answer', 'screenshot_path': 'shot.webp'}, 'run:1:chatgpt')
    assert repo.pending_billing() == [{'check_id': 'run:1:chatgpt', 'status': 'found'}]
    assert repo.pending_screenshots()[0]['local_path'] == 'shot.webp'
    assert not repo.pending_captures(ctl.scan_id)


def test_worker_fault_terminates_without_progress_or_losing_raw(tmp_path, monkeypatch):
    project, items, settings, ctl, _, _ = setup(tmp_path, monkeypatch)
    def failed(*_args): raise sqlite3.OperationalError('database unavailable')
    monkeypatch.setattr(repo, 'capture_state', failed)
    asyncio.run(asyncio.wait_for(run(project, items, settings, ctl), 3))
    assert ctl.done == 0 and scan.active_controller() is None
    assert repo.pending_captures(ctl.scan_id) and repo.get_scan(ctl.scan_id)['status'] == 'failed'


def test_pacing_feedback_deadline_and_provider_floor(monkeypatch):
    now, sleeps = [0.0], []
    monkeypatch.setattr(scan.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(scan.random, 'uniform', lambda lo, hi: lo)
    async def sleep(seconds): sleeps.append(seconds); now[0] += seconds
    monkeypatch.setattr(scan.asyncio, 'sleep', sleep)
    pacer = scan.AdaptivePacer({'ceiling_sec': 60, 'recovery_sec': 1}, 10, 15)
    pacer.completed(True, True, 1, 0)
    assert pacer.delay == 20
    now[0] = 17  # capture/queue work consumes the pause
    asyncio.run(pacer.wait())
    assert sleeps == [3]
    for n in range(2): pacer.completed(False, True, n, 0)
    assert pacer.delay == 20
    pacer.completed(False, True, 3, 0)
    assert pacer.delay == 19
    for n in range(100): pacer.completed(False, True, n, 0)
    assert pacer.delay == 10
    for n in range(100): pacer.completed(True, False, n, 0)
    assert pacer.delay == 60
    pacer.completed(False, False, 1, 0)
    assert pacer.delay == 60  # generic failure does not recover or throttle


def test_confirmed_quota_stops_browser_and_account_change_is_denied(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, adapter = setup(tmp_path, monkeypatch)
    async def quota(*_args, **_kwargs):
        asked.append('quota')
        raise ProviderQuotaError('free quota exhausted')
    monkeypatch.setattr(adapter, 'ask', quota)
    async def scenario():
        for change in (billing.logout(), billing.login('mail', 'password'), billing.login_with_code('code')):
            with pytest.raises(billing.BillingError) as error: await change
            assert error.value.status_code == 409
        await run(project, items, settings, ctl)
    asyncio.run(scenario())
    assert asked == ['quota'] and ctl.done == len(items)


def test_foreign_capture_is_retained_and_credentials_are_pinned(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, _ = setup(tmp_path, monkeypatch, count=1)
    save(project, items[0], settings, ctl, payer='other')
    asyncio.run(run(project, items, settings, ctl))
    assert not asked and ctl.done == 0 and repo.pending_captures(ctl.scan_id)
    monkeypatch.setattr(billing.secrets_store, 'unprotect', lambda x: x)
    repo.set_setting(billing.TOKEN_KEY, 'owner-token')
    context = billing.scan_bearer.set(billing.token())
    try:
        repo.set_setting(billing.TOKEN_KEY, 'replacement-token')
        assert billing.token() == 'owner-token'
    finally: billing.scan_bearer.reset(context)
    assert billing.token() == 'replacement-token'


def test_legacy_continuation_keeps_fixed_policy_and_inactive_saved_query(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, _ = setup(tmp_path, monkeypatch, count=1)
    settings.pop('adaptive_pacing')
    repo._exec('UPDATE scans SET settings_snapshot_json=?, status=? WHERE id=?',
               (json.dumps(settings), 'stopped', ctl.scan_id))
    save(project, items[0], settings, ctl, 'error')
    repo.set_query_active(items[0]['id'], False)
    scan._active.clear()
    plan = scan.plan_scan(project['id'], ['chatgpt'])
    assert (plan['total'], plan['remaining'], plan['pending_analysis']) == (1, 1, 1)
    resumable = repo.find_resumable_scan(project['id'])
    assert resumable['expected'] == resumable['remaining'] == 1
    seen = []
    async def capture_settings(_project, _services, resumed, _done, snapshot, controller):
        seen.append((resumed, snapshot))
        scan._active.clear()
    monkeypatch.setattr(scan, '_run_scan', capture_settings)
    async def scenario():
        assert await scan.start_scan(project['id'], ['chatgpt']) == ctl.scan_id
        await asyncio.sleep(0)
    asyncio.run(scenario())
    assert 'adaptive_pacing' not in seen[0][1]
    assert {q['id'] for q in seen[0][0]} == {q['id'] for q in items}
    assert asked == []


def test_managed_capture_keeps_canonical_uuid_and_reservation(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, _ = setup(tmp_path, monkeypatch, count=1)
    settings.update(managed_llm=True, billing_user_id='owner', billing_run_id='cloud-run',
                    cloud_query_map={str(items[0]['id']): 'query-uuid'}, arbiter=False)
    key = 'cloud-run:query-uuid:chatgpt'
    save(project, items[0], settings, ctl, 'analyzing', payer='owner', check=key)
    repo._exec('UPDATE scans SET settings_snapshot_json=? WHERE id=?',
               (json.dumps({**settings, 'billing_reserved_ids': [key]}), ctl.scan_id))
    repo.queue_billing(key, 'release')  # crash-left safety release must not be sent
    calls = []
    async def release(keys): calls.extend(keys)
    monkeypatch.setattr(billing, 'release', release)
    asyncio.run(billing.recover_interrupted_scans('owner'))
    assert calls == [] and repo.pending_captures(ctl.scan_id)
    seen = []
    async def verdict(**kwargs):
        seen.append(kwargs['managed_check_id'])
        return LLMVerdict(found=True, confidence=0.9, model='fake')
    monkeypatch.setattr(scan.llm_mod, 'evaluate', verdict)
    asyncio.run(run(project, items, settings, ctl))
    assert seen == [key] and not asked
    assert repo.pending_billing('owner') == [{'check_id': key, 'status': 'found'}]


@pytest.mark.parametrize('desired', ['cancelled', 'running'])
def test_managed_failed_capture_waits_for_resume_and_keeps_remaining_work(tmp_path, monkeypatch, desired):
    from app.api import browser
    project, items, settings, ctl, _, _ = setup(tmp_path, monkeypatch, count=2)
    from app import control_agent as control
    scan._active.clear()
    key = f"run:{items[0]['id']}:chatgpt"
    settings.update(billing_user_id='owner', billing_run_id='run', billing_reserved_ids=[key])
    repo._exec('UPDATE scans SET settings_snapshot_json=? WHERE id=?', (json.dumps(settings), ctl.scan_id))
    save(project, items[0], settings, ctl, 'error', payer='owner', check=key)
    repo.set_scan_status(ctl.scan_id, 'failed')
    repo.set_setting('managed_scan:job', str(ctl.scan_id))
    calls, reports = [], []
    job = {'id': 'job', 'desired_state': desired, 'total': 2}
    async def no_work(*_args, **_kwargs): pass
    async def report(_job, state, progress=None, error=None):
        reports.append(state)
        if job['desired_state'] == 'running' and state == 'paused': job['desired_state'] = 'paused'
    async def start(_job, _owner, *, drain_only=False): calls.append(drain_only)
    monkeypatch.setattr(control, 'enroll', no_work)
    monkeypatch.setattr(control, 'import_projects', no_work)
    monkeypatch.setattr(control, 'start_job', start)
    monkeypatch.setattr(control, 'update_job', report)
    monkeypatch.setattr(control.window_control, 'update_device_name', lambda _: None)
    monkeypatch.setattr(browser, 'status', lambda: {'services': [], 'installed': True, 'logins_in_progress': False})
    monkeypatch.setattr(billing, 'enabled', lambda: True)
    monkeypatch.setattr(billing, 'token', lambda: 'test-token')
    async def identity(): return {'id': 'owner'}
    monkeypatch.setattr(billing, 'identity', identity)
    async def request(*_args, **_kwargs): return {'run': job, 'name': 'PC'}
    monkeypatch.setattr(billing, '_request', request)
    original_sleep = asyncio.sleep
    iterations = 0
    async def sleep(_seconds):
        nonlocal iterations
        await original_sleep(0)
        iterations += 1
        if iterations == 2:
            assert calls == [] and reports == ['paused']  # cancelled failures must not auto-retry
            job['desired_state'] = 'running'  # explicit owner resume
        if iterations == 3: raise asyncio.CancelledError
    monkeypatch.setattr(control.asyncio, 'sleep', sleep)
    with pytest.raises(asyncio.CancelledError): asyncio.run(control.run_agent())
    assert calls == [False]  # resume completes uncaptured remainder, not just the saved subset


def test_desktop_token_replacement_is_rejected_during_startup(tmp_path, monkeypatch):
    project, _, _, _, _, _ = setup(tmp_path, monkeypatch, count=1)
    from app import control_agent as control
    scan._active.clear()
    monkeypatch.setattr(control.secrets_store, 'protect', lambda value: value)
    repo.set_setting(billing.TOKEN_KEY, 'owner-A')
    async def scenario():
        async with scan.scan_start_lock():
            with pytest.raises(billing.BillingError) as error: control.store_token('owner-B')
            assert error.value.status_code == 409
        assert repo.get_setting(billing.TOKEN_KEY) == 'owner-A'
    asyncio.run(scenario())


def test_fresh_scan_cannot_strand_a_saved_answer(tmp_path, monkeypatch):
    project, items, settings, ctl, asked, _ = setup(tmp_path, monkeypatch, count=1)
    save(project, items[0], settings, ctl, 'error')
    repo.set_scan_status(ctl.scan_id, 'failed')
    scan._active.clear()
    with pytest.raises(scan.ScanAlreadyRunning):
        asyncio.run(scan.start_scan(project['id'], ['chatgpt'], resume=False))
    with pytest.raises(scan.ScanAlreadyRunning):
        asyncio.run(scan.start_scan(project['id'], ['perplexity']))
    assert repo.latest_scan(project['id'])['id'] == ctl.scan_id and asked == []
    assert repo.find_resumable_scan(project['id'])['id'] == ctl.scan_id
