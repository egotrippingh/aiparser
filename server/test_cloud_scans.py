import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import StatementError

from server.ai import AIError, AIResult
from server.app import create_app
from server.cloud_scans import cloud_tick, worker
from server.control import schedule_tick
from server.models import Check, CloudResult, ControlProject, ControlRun, LedgerEntry, ServerCapture, User, Wallet, make_session_factory, utcnow
from shared.errors import ProviderQuotaError
from shared.xmlriver import CollectionCancelled


class Collector:
    calls = []
    answer = {'shown': True, 'main_text': 'Brand is recommended', 'cards_text': '',
              'answer_text': 'Brand is recommended', 'html': '<p>Brand is recommended</p>',
              'content': ['Brand is recommended'], 'sources': [], 'source_cards': [], 'products': []}

    def __init__(self, service, geo):
        self.service = service

    async def collect(self, query, *, should_continue=None):
        self.calls.append((self.service, query))
        return dict(self.answer)


class FakeAI:
    model = 'test-primary'
    arbiter_model = 'test-arbiter'
    fail = False

    def analyze(self, system, content):
        if self.fail:
            raise AIError('unavailable')
        return AIResult('{"found": false, "confidence": 0.9}', self.model, {})

    def arbitrate(self, system, content):
        return AIResult('{"found": false, "confidence": 0.9}', self.arbiter_model, {})


def setup(tmp_path, monkeypatch, *, ai=None, admin=True):
    monkeypatch.setenv('AIPARSER_XMLRIVER_USER', 'test-user')
    monkeypatch.setenv('AIPARSER_XMLRIVER_KEY', 'test-key')
    url = f"sqlite:///{tmp_path / 'cloud.db'}"
    client = TestClient(create_app(database_url=url, ai_client=ai))
    def register(email):
        result = client.post('/api/v1/auth/register', json={'email': email, 'password': 'long-test-password-123'})
        assert result.status_code == 201, result.text
        return {'Authorization': 'Bearer ' + result.json()['token']}, result.json()['user']['id']
    owner, user_id = register('owner@test.example')
    other, _ = register('other@test.example')
    _, sessions = make_session_factory(url)
    if admin:
        with sessions() as db:
            db.get(User, user_id).is_admin = True
            db.commit()
    return client, owner, other, user_id, sessions


def project_and_run(client, owner, *, services=('google_aio',), schedule=None, queries=None, device=None):
    body = {'name': 'Project', 'brand_name': 'Brand',
            'queries': queries or [{'text': 'question'}], 'config': {'services': list(services)}}
    if schedule:
        body['schedule'] = schedule
    if device:
        body['device_id'] = device
    created = client.post('/api/v1/control/projects', headers=owner, json=body)
    assert created.status_code == 201, created.text
    project = created.json()
    launched = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owner,
                           json={'request_id': uuid.uuid4().hex})
    assert launched.status_code == 201, launched.text
    return project, launched.json()


def tick(sessions, ai=None):
    return asyncio.run(cloud_tick(sessions, ai, 120, Collector))


def test_cloud_only_durable_evidence_and_owner_scope(tmp_path, monkeypatch):
    client, owner, other, _, sessions = setup(tmp_path, monkeypatch)
    Collector.calls = []
    project, run = project_and_run(client, owner)
    assert run['device_id'] is None and run['phase'] == 'cloud'
    assert tick(sessions)
    assert Collector.calls == [('google_aio', 'question')]
    with sessions() as db:
        row = db.scalar(select(CloudResult))
        check = db.scalar(select(Check))
        assert row.status == 'found' and row.device_id is None and row.local_result_id is None
        assert check.status == 'settled' and check.price_kopeks == 0
        assert db.scalar(select(ServerCapture)).check_id == check.client_check_id
        result_id = row.id
    detail = client.get(f"/api/v1/control/projects/{project['id']}/mentions/results/{result_id}", headers=owner)
    assert detail.status_code == 200 and detail.headers['cache-control'] == 'no-store'
    assert detail.json()['answer_evidence']['content'] == ['Brand is recommended']
    assert detail.json()['highlight'] == {'names': ['Brand'], 'domains': []}
    assert detail.json()['has_screenshot'] is False
    assert client.get(f"/api/v1/control/projects/{project['id']}/mentions/results/{result_id}", headers=other).status_code == 404
    assert client.get('/api/v1/control/runs', headers=owner).json()[0]['state'] == 'done'
    assert not tick(sessions)


def test_two_cloud_services_finish_one_query(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    Collector.calls = []
    _, run = project_and_run(client, owner, services=('google_aio', 'yandex_neuro'))
    assert tick(sessions)
    assert tick(sessions)
    assert Collector.calls == [('google_aio', 'question'), ('yandex_neuro', 'question')]
    with sessions() as db:
        row = db.get(ControlRun, run['id'])
        assert row.state == 'done'
        assert json.loads(row.progress_json)['cloud_done'] == 2
        assert {result.service for result in db.scalars(select(CloudResult))} == {'google_aio', 'yandex_neuro'}


def test_insufficient_funds_blocks_provider_call(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, admin=False)
    Collector.calls = []
    _, run = project_and_run(client, owner)
    assert tick(sessions)
    assert Collector.calls == []
    with sessions() as db:
        row = db.get(ControlRun, run['id'])
        assert row.state == row.desired_state == 'paused'
        assert db.scalar(select(ServerCapture)) is None
        assert db.scalar(select(Check)) is None


def test_saved_capture_resumes_after_ai_failure_without_recollection(tmp_path, monkeypatch):
    ai = FakeAI()
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai)
    Collector.calls = []
    Collector.answer = {**Collector.answer, 'main_text': 'No relevant name',
                        'answer_text': 'No relevant name', 'content': ['No relevant name']}
    _, run = project_and_run(client, owner)
    ai.fail = True
    assert tick(sessions, ai)
    with sessions() as db:
        assert db.scalar(select(ServerCapture)) is not None
        assert db.get(ControlRun, run['id']).state == 'paused'
        assert db.scalar(select(Check)).status == 'reserved'
    assert not tick(sessions, ai)
    ai.fail = False
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                       json={'action': 'resume'}).status_code == 200
    assert tick(sessions, ai)
    assert Collector.calls == [('google_aio', 'question')]
    with sessions() as db:
        assert db.scalar(select(CloudResult)).status == 'not_found'
        assert db.scalar(select(Check)).status == 'settled'
        assert db.scalar(select(Check)).analysis_attempts == 2
    Collector.answer = {'shown': True, 'main_text': 'Brand is recommended', 'cards_text': '',
                        'answer_text': 'Brand is recommended', 'html': '<p>Brand is recommended</p>',
                        'content': ['Brand is recommended'], 'sources': [], 'source_cards': [], 'products': []}


def test_malformed_primary_verdict_retries_saved_answer_once(tmp_path, monkeypatch):
    ai = FakeAI()
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, ai=ai, admin=False)
    answer = Collector.answer
    Collector.answer = {**answer, 'main_text': 'No name', 'answer_text': 'No name'}
    Collector.calls = []
    _, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    calls = []
    def analyze(system, content):
        calls.append('analyze')
        raw = 'malformed' if len(calls) == 1 else '{"found": false, "confidence": 0.9}'
        return AIResult(raw, ai.model, {})
    ai.analyze = analyze
    assert tick(sessions, ai)
    with sessions() as db:
        check = db.scalar(select(Check))
        assert check.analysis_json is None and check.analysis_attempts == 1
        assert db.get(ControlRun, run['id']).state == 'paused'
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={'action': 'resume'}).status_code == 200
    assert tick(sessions, ai)
    assert calls == ['analyze', 'analyze']
    assert Collector.calls == [('google_aio', 'question')]
    with sessions() as db:
        assert db.scalar(select(Check)).analysis_attempts == 2
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 1
    Collector.answer = answer


def test_malformed_arbiter_verdict_retries_saved_answer_once(tmp_path, monkeypatch):
    ai = FakeAI()
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, ai=ai, admin=False)
    answer = Collector.answer
    Collector.answer = {**answer, 'main_text': 'No name', 'answer_text': 'No name'}
    Collector.calls = []
    _, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    calls = []
    def analyze(system, content):
        calls.append('analyze')
        return AIResult('{"found": true, "confidence": 0.9}', ai.model, {})
    def arbitrate(system, content):
        calls.append('arbitrate')
        raw = 'malformed' if calls.count('arbitrate') == 1 else '{"found": false, "confidence": 0.9}'
        return AIResult(raw, ai.arbiter_model, {})
    ai.analyze, ai.arbitrate = analyze, arbitrate
    assert tick(sessions, ai)
    with sessions() as db:
        check = db.scalar(select(Check))
        assert check.analysis_json and check.arbitration_json is None
        assert check.analysis_attempts == check.arbitration_attempts == 1
        assert db.get(ControlRun, run['id']).state == 'paused'
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={'action': 'resume'}).status_code == 200
    assert tick(sessions, ai)
    assert calls == ['analyze', 'arbitrate', 'arbitrate']
    assert Collector.calls == [('google_aio', 'question')]
    with sessions() as db:
        check = db.scalar(select(Check))
        assert check.analysis_attempts == 1 and check.arbitration_attempts == 2
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 1
    Collector.answer = answer


def test_mixed_waits_for_cloud_then_assigns_only_agent_services(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    device_id = 'a' * 32
    enrolled = client.post('/api/v1/control/agent/enroll', headers=owner,
                           json={'device_id': device_id, 'name': 'PC'})
    device = {'Authorization': 'Bearer ' + enrolled.json()['token']}
    project, run = project_and_run(client, owner,
        services=('google_aio', 'yandex_neuro', 'chatgpt'), device=device_id)
    assert client.post('/api/v1/control/agent/poll', headers=device, json={}).json()['run'] is None
    assert tick(sessions)
    assert client.post('/api/v1/control/agent/poll', headers=device, json={}).json()['run'] is None
    assert tick(sessions)
    job = client.post('/api/v1/control/agent/poll', headers=device, json={}).json()['run']
    assert job['id'] == run['id']
    assert job['snapshot']['config']['services'] == ['chatgpt']
    query = job['snapshot']['queries'][0]['id']
    cloud_check = f"{run['id']}:{query}:google_aio"
    assert client.post('/api/v1/checks/reserve', headers=device,
                       json={'check_ids': [cloud_check]}).status_code == 403
    forged = {'device_id': device_id, 'results': [{'project_id': project['id'], 'query_id': query,
        'run_id': run['id'], 'local_result_id': 1, 'local_project_id': 1,
        'project_name': 'Project', 'brand_name': 'Brand', 'query_text': 'question',
        'service': 'google_aio', 'scan_date': '2026-10-09', 'status': 'found',
        'check_id': cloud_check}]}
    assert client.post('/api/v1/agent/results', headers=device, json=forged).status_code == 422
    assert job['progress']['cloud_done'] == 2


def test_stale_lease_and_stop_do_not_write_duplicate_results(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    Collector.calls = []
    _, run = project_and_run(client, owner, queries=[{'text': 'one'}, {'text': 'two'}])
    assert tick(sessions)
    with sessions() as db:
        row = db.get(ControlRun, run['id'])
        row.lease_token = 'stale'
        row.lease_until = utcnow() + timedelta(minutes=2)
        db.commit()
    assert not tick(sessions)
    assert len(Collector.calls) == 1
    with sessions() as db:
        row = db.get(ControlRun, run['id'])
        row.lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                       json={'action': 'stop'}).status_code == 200
    assert tick(sessions)
    assert len(Collector.calls) == 1
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert len(db.scalars(select(ServerCapture)).all()) == 1
        assert len(db.scalars(select(CloudResult)).all()) == 1


def test_stop_during_provider_drains_current_answer_only(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    Collector.calls = []
    _, run = project_and_run(client, owner, queries=[{'text': 'one'}, {'text': 'two'}])
    original = Collector.collect
    async def stop_then_answer(self, query, *, should_continue=None):
        result = await original(self, query, should_continue=should_continue)
        assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                           json={'action': 'stop'}).status_code == 200
        return result
    monkeypatch.setattr(Collector, 'collect', stop_then_answer)
    assert tick(sessions)
    assert len(Collector.calls) == 1
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert len(db.scalars(select(ServerCapture)).all()) == 1
        assert len(db.scalars(select(CloudResult)).all()) == 1
        assert db.scalar(select(Check)).status == 'settled'


def test_revoke_device_during_mixed_cloud_capture_drains_check(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    device_id = 'b' * 32
    assert client.post('/api/v1/control/agent/enroll', headers=owner,
        json={'device_id': device_id, 'name': 'PC'}).status_code == 200
    _, run = project_and_run(client, owner,
        services=('google_aio', 'chatgpt'), device=device_id)
    original = Collector.collect

    async def revoke_then_answer(self, query, *, should_continue=None):
        answer = await original(self, query, should_continue=should_continue)
        response = client.delete(f'/api/v1/control/devices/{device_id}', headers=owner)
        assert response.status_code == 200
        with sessions() as db:
            active = db.get(ControlRun, run['id'])
            assert active.phase == 'cloud' and active.desired_state == 'cancelled'
            assert active.lease_token is not None
        return answer

    monkeypatch.setattr(Collector, 'collect', revoke_then_answer)
    assert tick(sessions)
    with sessions() as db:
        result = db.scalar(select(CloudResult))
        assert result is not None and result.service == 'google_aio'
        assert db.scalar(select(Check)).status == 'settled'
        active = db.get(ControlRun, run['id'])
        assert active.state == 'cancelled' and active.active_project_key is None


def test_pause_during_provider_drains_then_resumes_next_query(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    Collector.calls = []
    _, run = project_and_run(client, owner, queries=[{'text': 'one'}, {'text': 'two'}])
    original = Collector.collect
    async def pause_then_answer(self, query, *, should_continue=None):
        result = await original(self, query, should_continue=should_continue)
        assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                           json={'action': 'pause'}).status_code == 200
        return result
    monkeypatch.setattr(Collector, 'collect', pause_then_answer)
    assert tick(sessions)
    assert not tick(sessions)
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'paused'
    monkeypatch.setattr(Collector, 'collect', original)
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                       json={'action': 'resume'}).status_code == 200
    assert tick(sessions)
    assert Collector.calls == [('google_aio', 'one'), ('google_aio', 'two')]


def test_pause_before_provider_response_releases_then_reserves_on_resume(tmp_path, monkeypatch):
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    Collector.calls = []
    _, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    original = Collector.collect

    async def pause_before_response(self, query, *, should_continue=None):
        Collector.calls.append((self.service, query))
        assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
            json={'action': 'pause'}).status_code == 200
        assert not should_continue()
        raise CollectionCancelled('paused before response')

    monkeypatch.setattr(Collector, 'collect', pause_before_response)
    assert tick(sessions)
    with sessions() as db:
        assert db.scalar(select(Check)).status == 'released'
        assert db.scalar(select(ServerCapture)) is None
        assert db.get(Wallet, user_id).balance_kopeks == 500
    monkeypatch.setattr(Collector, 'collect', original)
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={'action': 'resume'}).status_code == 200
    assert tick(sessions)
    with sessions() as db:
        assert db.scalar(select(Check)).status == 'settled'
        assert db.scalar(select(ServerCapture)) is not None
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 1
    assert Collector.calls == [('google_aio', 'question'), ('google_aio', 'question')]


def test_crash_after_capture_reuses_answer_and_charges_once(tmp_path, monkeypatch):
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    Collector.calls = []
    _, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        query_id = json.loads(db.get(ControlRun, run['id']).snapshot_json)['queries'][0]['id']
        key = f"{run['id']}:{query_id}:google_aio"
        db.add(Check(user_id=user_id, client_check_id=key, price_kopeks=120))
        db.add(ServerCapture(run_id=run['id'], query_id=query_id, service='google_aio',
                             check_id=key, answer_json=json.dumps(Collector.answer)))
        db.commit()
    assert tick(sessions)
    assert Collector.calls == []
    assert not tick(sessions)
    with sessions() as db:
        assert db.scalar(select(Check)).status == 'settled'
        assert db.get(Wallet, user_id).balance_kopeks == 380
        entries = db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()
        assert len(entries) == 1 and entries[0].amount_kopeks == -120


def test_stale_provider_response_cannot_save_capture(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    Collector.calls = []
    _, run = project_and_run(client, owner)
    original = Collector.collect
    async def expire_during_call(self, query, *, should_continue=None):
        result = await original(self, query, should_continue=should_continue)
        with sessions() as db:
            row = db.get(ControlRun, run['id'])
            row.lease_token = 'new-owner'
            row.lease_until = utcnow() + timedelta(minutes=2)
            db.commit()
        return result
    monkeypatch.setattr(Collector, 'collect', expire_during_call)
    assert not tick(sessions)
    with sessions() as db:
        assert db.scalar(select(ServerCapture)) is None
        assert db.scalar(select(CloudResult)) is None
        assert db.scalar(select(Check)).status == 'reserved'
        db.get(ControlRun, run['id']).lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    monkeypatch.setattr(Collector, 'collect', original)
    assert tick(sessions)
    assert len(Collector.calls) == 2
    with sessions() as db:
        assert len(db.scalars(select(ServerCapture)).all()) == 1
        assert len(db.scalars(select(CloudResult)).all()) == 1


def test_provider_quota_is_not_false_absence_or_charge(tmp_path, monkeypatch):
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    project, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    async def quota(self, query, *, should_continue=None):
        raise ProviderQuotaError('quota')
    monkeypatch.setattr(Collector, 'collect', quota)
    assert tick(sessions)
    with sessions() as db:
        result = db.scalar(select(CloudResult))
        assert result.status == 'limit_reached'
        result_id = result.id
        assert db.scalar(select(Check)).status == 'released'
        assert db.get(Wallet, user_id).balance_kopeks == 500
        assert db.scalar(select(LedgerEntry).where(LedgerEntry.kind == 'check')) is None
    detail = client.get(f"/api/v1/control/projects/{project['id']}/mentions/results/{result_id}",
        headers=owner).json()
    assert detail['answer_evidence'] is None and detail['highlight'] is None
    assert detail['has_screenshot'] is False


def test_absent_ai_block_has_no_answer_evidence(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    answer = Collector.answer
    Collector.answer = {**answer, 'shown': False, 'content': []}
    project, _ = project_and_run(client, owner)
    assert tick(sessions)
    with sessions() as db:
        result = db.scalar(select(CloudResult))
        assert result.status == 'skipped'
        result_id = result.id
    detail = client.get(f"/api/v1/control/projects/{project['id']}/mentions/results/{result_id}",
        headers=owner).json()
    assert detail['answer_evidence'] is None and detail['highlight'] is None
    assert detail['has_screenshot'] is False
    Collector.answer = answer


def test_stop_after_provider_error_prevents_retry_and_releases_money(tmp_path, monkeypatch):
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    _, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    attempts = []
    async def interrupted(self, query, *, should_continue=None):
        attempts.append(query)
        assert should_continue()
        assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                           json={'action': 'stop'}).status_code == 200
        if not should_continue():
            raise CollectionCancelled('stopped')
        attempts.append('unexpected retry')
    monkeypatch.setattr(Collector, 'collect', interrupted)
    assert tick(sessions)
    assert attempts == ['question']
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert db.scalar(select(ServerCapture)) is None
        assert db.scalar(select(CloudResult)) is None
        assert db.scalar(select(Check)).status == 'released'
        assert db.get(Wallet, user_id).balance_kopeks == 500


def test_stop_during_ai_keeps_result_and_one_charge(tmp_path, monkeypatch):
    ai = FakeAI()
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, ai=ai, admin=False)
    _, run = project_and_run(client, owner, queries=[{'text': 'one'}, {'text': 'two'}])
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    Collector.calls = []
    answer = Collector.answer
    Collector.answer = {**answer, 'main_text': 'No name', 'answer_text': 'No name', 'content': ['No name']}
    def stop_during_analyze(system, content):
        assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                           json={'action': 'stop'}).status_code == 200
        return AIResult('{"found": false, "confidence": 0.9}', ai.model, {})
    ai.analyze = stop_during_analyze
    assert tick(sessions, ai)
    assert Collector.calls == [('google_aio', 'one')]
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert db.scalar(select(CloudResult)).status == 'not_found'
        assert db.scalar(select(Check)).status == 'settled'
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 1
    Collector.answer = answer


def test_stop_after_capture_avoids_new_model_call(tmp_path, monkeypatch):
    ai = FakeAI()
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, ai=ai, admin=False)
    project, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    answer = Collector.answer
    Collector.answer = {**answer, 'main_text': 'No name', 'answer_text': 'No name', 'content': ['No name']}
    original = Collector.collect
    async def stop_then_answer(self, query, *, should_continue=None):
        result = await original(self, query, should_continue=should_continue)
        assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                           json={'action': 'stop'}).status_code == 200
        return result
    monkeypatch.setattr(Collector, 'collect', stop_then_answer)
    def no_model(system, content):
        raise AssertionError('new model call after stop')
    ai.analyze = no_model
    assert tick(sessions, ai)
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert db.scalar(select(ServerCapture)) is not None
        result = db.scalar(select(CloudResult))
        assert result.status == 'error'
        result_id = result.id
        assert db.scalar(select(Check)).status == 'released'
        assert db.get(Wallet, user_id).balance_kopeks == 500
    detail = client.get(f"/api/v1/control/projects/{project['id']}/mentions/results/{result_id}",
        headers=owner).json()
    assert detail['answer_evidence']['content'] == ['No name']
    assert detail['has_screenshot'] is False
    Collector.answer = answer


def test_cloud_schedule_without_device(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    schedule = {'enabled': True, 'month_days': [15], 'time': '12:30', 'timezone': 'Europe/Moscow'}
    created = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Scheduled', 'brand_name': 'Brand', 'queries': [{'text': 'question'}],
        'config': {'services': ['google_aio']}, 'schedule': schedule})
    assert created.status_code == 201, created.text
    with sessions() as db:
        project = db.get(ControlProject, created.json()['id'])
        value = json.loads(project.schedule_json)
        value['effective_from'] = '2025-01-01T00:00:00+00:00'
        project.schedule_json = json.dumps(value)
        db.commit()
    schedule_tick(sessions, datetime(2027, 4, 15, 9, 30, tzinfo=timezone.utc))
    with sessions() as db:
        run = db.scalar(select(ControlRun))
        assert run is not None and run.phase == 'cloud' and run.device_id is None


def test_worker_log_omits_database_parameters(monkeypatch, caplog):
    secret = 'PRIVATE_ANSWER_SENTINEL'

    async def fail_tick(*args):
        raise StatementError('failed write', 'INSERT INTO server_captures',
            {'answer_json': secret}, ValueError('database error'))

    async def stop_worker(*args):
        raise asyncio.CancelledError()

    monkeypatch.setattr('server.cloud_scans.cloud_tick', fail_tick)
    monkeypatch.setattr('server.cloud_scans.asyncio.sleep', stop_worker)
    with caplog.at_level(logging.ERROR, logger='server.cloud_scans'):
        try:
            asyncio.run(worker(None, None, 120))
        except asyncio.CancelledError:
            pass
    assert 'Cloud scan tick failed' in caplog.text
    assert secret not in caplog.text
