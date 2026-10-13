"""Lost submission callbacks and bounded recovery, with fake providers only."""
import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, update
from fastapi import HTTPException

from server import provider_tasks, scrapeless
from server.cloud_scans import _claim
from server.models import Check, CloudResult, ControlRun, ProviderAccount, ProviderTask, ServerCapture, User, Wallet, utcnow
from server.test_scrapeless import Supplier, create, tick, postgres_url  # noqa: F401


def intent(sessions, run, project, *, state='uncertain', old=False):
    _, token, _ = _claim(sessions)
    from server.checks import reserve_checks
    with sessions() as db:
        current = db.get(ControlRun, run['id'])
        db.get(Wallet, current.user_id).balance_kopeks = 500
        reserve_checks(db, db.get(User, current.user_id),
            [f"{run['id']}:{project['queries'][0]['id']}:chatgpt"], 120, None)
    task, _ = provider_tasks.admit(sessions, run['id'], token, project['queries'][0]['id'], 'chatgpt', 100)
    with sessions() as db:
        saved = db.get(ProviderTask, task.check_id)
        saved.state = state
        if old:
            saved.updated_at = utcnow() - timedelta(minutes=16)
        db.get(ControlRun, run['id']).lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    return task


def callback(client, task, **data):
    return client.post(f'/api/v1/webhooks/scrapeless/{task.check_id}/{task.submission_token}',
        json={'task_id': 'callback-id', 'status': 'success', 'task_result': {'result_text': 'Untrusted'}, **data})


@pytest.mark.parametrize('use_postgres', [False, True])
def test_unknown_submission_callback_gets_authenticated_answer_once(tmp_path, monkeypatch, request, use_postgres):
    url = request.getfixturevalue('postgres_url') if use_postgres else None
    client, _, _, user_id, sessions, project, run = create(tmp_path, monkeypatch, admin=False, database_url=url)
    task = intent(sessions, run, project)
    assert callback(client, task).status_code == 204
    assert callback(client, task).status_code == 204
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert supplier.posts == [] and supplier.gets == ['callback-id']
    with sessions() as db:
        assert db.scalar(select(CloudResult)).answer_text != 'Untrusted'
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(Check)).all()) == 1
        assert len(db.scalars(select(ServerCapture)).all()) == 1


def test_wrong_stale_or_mismatched_callback_cannot_replace_handle(tmp_path, monkeypatch):
    client, _, _, _, sessions, project, run = create(tmp_path, monkeypatch)
    task = intent(sessions, run, project)
    url = f'/api/v1/webhooks/scrapeless/{task.check_id}/'
    with sessions() as db:
        revision = db.get(ProviderAccount, 'chatgpt').revision
    assert client.post(url + '0' * 32, json={'task_id': 'evil', 'status': 'success'}).status_code == 404
    with sessions() as db:
        assert db.get(ProviderAccount, 'chatgpt').revision == revision
    assert callback(client, task, task_id='../../bad').status_code == 422
    assert callback(client, task).status_code == 204
    assert callback(client, task, task_id='different-id').status_code == 409
    provider_tasks.failed(sessions, task, uncertain=True, cooldown=0)
    with sessions() as db:
        saved = db.get(ProviderTask, task.check_id)
        assert saved.state == 'submitted' and saved.task_id == 'callback-id'


@pytest.mark.parametrize('use_postgres', [False, True])
def test_timed_out_unknown_retries_same_check_and_old_callback_is_ignored(tmp_path, monkeypatch, request, use_postgres):
    url = request.getfixturevalue('postgres_url') if use_postgres else None
    client, _, _, user_id, sessions, project, run = create(tmp_path, monkeypatch, admin=False, database_url=url)
    old = intent(sessions, run, project, old=True)
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert len(supplier.posts) == 1
    assert callback(client, old).status_code == 404
    with sessions() as db:
        saved = db.get(ProviderTask, old.check_id)
        assert saved.attempts == 2 and saved.state == 'completed'
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(Check)).all()) == 1


def test_unknown_retry_budget_frees_slot_without_reposting_forever(tmp_path, monkeypatch):
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch)
    task = intent(sessions, run, project, old=True)
    with sessions() as db:
        db.get(ProviderTask, task.check_id).attempts = 3
        db.commit()
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert supplier.posts == []
    with sessions() as db:
        assert db.get(ProviderTask, task.check_id).state == 'retry_exhausted'


def test_submit_sends_callback_and_logs_do_not_contain_capability(monkeypatch):
    url = 'https://airate.test/api/v1/webhooks/scrapeless/check/private-capability'
    def handle(request):
        assert json.loads(request.content)['webhook'] == {'url': url}
        return httpx.Response(201, json={'task_id': 'id'})
    async def run():
        async with scrapeless.ScrapelessClient(transport=httpx.MockTransport(handle)) as client:
            assert await client.submit('chatgpt', 'prompt', 'US', webhook_url=url) == 'id'
    asyncio.run(run())
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 0, '%s - "%s %s HTTP/%s" %d',
        ('127.0.0.1', 'POST', url.split('airate.test')[1], '1.1', 204), None)
    assert not scrapeless.callback_access_log(record)


@pytest.mark.parametrize('outcome', ['success', 'timeout', 'rejected', 'different-id'])
def test_early_callback_survives_post_outcomes(tmp_path, monkeypatch, outcome):
    client, _, _, _, sessions, _, _ = create(tmp_path, monkeypatch)
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://airate.test')
    class Early(Supplier):
        async def submit(self, service, prompt, country, *, webhook_url):
            self.posts.append(service)
            path = webhook_url.removeprefix('https://airate.test')
            assert client.post(path, json={'task_id': 'early-id', 'status': 'success'}).status_code == 204
            if outcome == 'timeout':
                raise scrapeless.SubmissionUnknown('Timeout')
            if outcome == 'rejected':
                raise scrapeless.Rejected(400)
            if outcome == 'different-id':
                return 'post-id'
            return 'early-id'
    supplier = Early()
    assert tick(sessions, supplier)
    if outcome == 'rejected':
        with sessions() as db:
            db.get(ControlRun, db.scalar(select(ControlRun.id))).retry_at = utcnow() - timedelta(seconds=1)
            db.commit()
        assert tick(sessions, supplier)
    assert supplier.posts == ['chatgpt']
    assert supplier.gets == ['post-id' if outcome == 'different-id' else 'early-id']
    with sessions() as db:
        assert db.scalar(select(ProviderTask)).state == 'completed'
        assert len(db.scalars(select(CloudResult)).all()) == 1


@pytest.mark.parametrize('desired', ['paused', 'cancelled'])
def test_timed_out_task_respects_pause_and_stop(tmp_path, monkeypatch, desired):
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch)
    task = intent(sessions, run, project, old=True)
    with sessions() as db:
        db.get(ControlRun, run['id']).desired_state = desired
        db.commit()
    provider_tasks.recover_scrapeless(sessions)
    supplier = Supplier()
    tick(sessions, supplier)
    assert supplier.posts == []
    with sessions() as db:
        assert db.get(ProviderTask, task.check_id).state == ('skipped' if desired == 'cancelled' else 'rejected')


def test_live_submitting_owner_is_not_replaced(tmp_path, monkeypatch):
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch)
    task = intent(sessions, run, project, state='submitting', old=True)
    with sessions() as db:
        db.get(ControlRun, run['id']).lease_until = utcnow() + timedelta(minutes=2)
        db.commit()
    provider_tasks.recover_scrapeless(sessions)
    with sessions() as db:
        saved = db.get(ProviderTask, task.check_id)
        assert saved.state == 'submitting' and saved.submission_token == task.submission_token


def test_three_lost_confirmations_stop_reposting_and_release_capacity(tmp_path, monkeypatch):
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch)
    task = intent(sessions, run, project, old=True)
    supplier = Supplier()
    supplier.unknown = True
    for _ in range(2):
        assert tick(sessions, supplier)
        with sessions() as db:
            db.get(ProviderTask, task.check_id).updated_at = utcnow() - timedelta(minutes=16)
            db.get(ControlRun, run['id']).lease_until = utcnow() - timedelta(seconds=1)
            db.get(ControlRun, run['id']).retry_at = utcnow() - timedelta(seconds=1)
            db.commit()
    assert tick(sessions, supplier)
    assert len(supplier.posts) == 2  # The original intent was attempt one.
    with sessions() as db:
        saved = db.get(ProviderTask, task.check_id)
        assert saved.attempts == 3 and saved.state == 'retry_exhausted'
        assert db.scalar(select(CloudResult)) is None


def test_postgres_callback_and_timeout_are_serialized(tmp_path, monkeypatch, postgres_url):
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch, database_url=postgres_url)
    task = intent(sessions, run, project, old=True)
    def notify():
        try:
            provider_tasks.callback(sessions, task.check_id, task.submission_token, 'race-id')
            return 204
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(2) as pool:
        notification = pool.submit(notify)
        recovery = pool.submit(provider_tasks.recover_scrapeless, sessions)
        status = notification.result(timeout=10)
        recovery.result(timeout=10)
    with sessions() as db:
        saved = db.get(ProviderTask, task.check_id)
        if status == 204:
            assert saved.task_id == 'race-id' and saved.submission_token == task.submission_token
        else:
            assert status == 404 and saved.task_id is None and saved.submission_token != task.submission_token


def test_postgres_post_confirmation_waits_for_recovery_lock(tmp_path, monkeypatch, postgres_url):
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch, database_url=postgres_url)
    task = intent(sessions, run, project, old=True)
    started = threading.Event()
    def confirm():
        started.set()
        provider_tasks.submitted(sessions, task, 'confirmed-id')
    with ThreadPoolExecutor(1) as pool:
        with sessions() as db:
            db.execute(update(ProviderAccount).where(ProviderAccount.service == 'chatgpt')
                .values(revision=ProviderAccount.revision + 1))
            future = pool.submit(confirm)
            assert started.wait(5)
            with pytest.raises(TimeoutError):
                future.result(timeout=.2)
            db.commit()
        future.result(timeout=10)
    provider_tasks.recover_scrapeless(sessions)
    with sessions() as db:
        saved = db.get(ProviderTask, task.check_id)
        assert saved.task_id == 'confirmed-id' and saved.submission_token == task.submission_token


def test_malformed_or_large_webhook_does_not_change_task(tmp_path, monkeypatch):
    client, _, _, _, sessions, project, run = create(tmp_path, monkeypatch)
    task = intent(sessions, run, project)
    path = f'/api/v1/webhooks/scrapeless/{task.check_id}/{task.submission_token}'
    assert client.post(path, content='bad-json').status_code == 422
    assert client.post(path, content=b'x' * 262145).status_code == 413
    assert callback(client, task, status='pending').status_code == 422
    with sessions() as db:
        assert db.get(ProviderTask, task.check_id).task_id is None


def test_post_total_deadline_recovers_as_unknown(monkeypatch):
    async def deadline(awaitable, *, timeout):
        assert timeout == 75
        awaitable.close()
        raise asyncio.TimeoutError
    monkeypatch.setattr(scrapeless.asyncio, 'wait_for', deadline)
    async def run():
        async with scrapeless.ScrapelessClient() as client:
            with pytest.raises(scrapeless.SubmissionUnknown):
                await client.submit('chatgpt', 'prompt', 'US')
    asyncio.run(run())
