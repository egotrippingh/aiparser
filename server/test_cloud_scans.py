import asyncio
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import StatementError

from server.ai import AIError, AIResult, AIRetryAfter
from server.app import create_app
from server.checks import complete_check
from server.cloud_scans import _analyze_saved, cloud_tick, worker
from server.control import schedule_tick
from server.models import Check, CloudResult, ControlProject, ControlRun, LedgerEntry, ServerCapture, User, Wallet, make_session_factory, utcnow
from shared.errors import ProviderQuotaError
from shared.xmlriver import CollectionCancelled, ProviderThrottleError


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


@pytest.fixture(autouse=True)
def reset_collector(monkeypatch):
    async def fake_limits():
        return {'google_aio': 1, 'yandex_neuro': 1}
    monkeypatch.setattr('server.cloud_scans.account_limits', fake_limits)
    monkeypatch.setattr(Collector, 'answer', {
        'shown': True, 'main_text': 'Brand is recommended', 'cards_text': '',
        'answer_text': 'Brand is recommended', 'html': '<p>Brand is recommended</p>',
        'content': ['Brand is recommended'], 'sources': [], 'source_cards': [], 'products': []})
    monkeypatch.setattr(Collector, 'calls', [])


def setup(tmp_path, monkeypatch, *, ai=None, admin=True, database_url=None):
    monkeypatch.setenv('AIPARSER_XMLRIVER_USER', 'test-user')
    monkeypatch.setenv('AIPARSER_XMLRIVER_KEY', 'test-key')
    url = database_url or f"sqlite:///{tmp_path / 'cloud.db'}"
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


@pytest.fixture
def postgres_url():
    base = os.environ.get('AIRATE_TEST_POSTGRES_URL')
    if not base:
        pytest.skip('Set AIRATE_TEST_POSTGRES_URL for disposable PostgreSQL concurrency checks')
    schema = 'airate_stream_' + uuid.uuid4().hex
    engine = create_engine(base)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(base).update_query_dict({'options': f'-csearch_path={schema}'})
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


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


def test_historical_supplier_errors_are_masked_at_public_boundaries(tmp_path, monkeypatch):
    client, owner, other, _, sessions = setup(tmp_path, monkeypatch)
    project, run = project_and_run(client, owner)
    assert tick(sessions)
    with sessions() as db:
        stored_run = db.get(ControlRun, run['id'])
        stored_run.error = 'XMLRiver 500; XMLreaver retry'
        progress = json.loads(stored_run.progress_json)
        progress['provider_error'] = 'XMLRiver timeout'
        stored_run.progress_json = json.dumps(progress)
        row = db.scalar(select(CloudResult))
        row.error_message = 'XMLRiver upstream error'
        row.answer_text = 'The original answer mentions XMLRiver as ordinary evidence'
        result_id = row.id
        db.commit()
    runs = client.get('/api/v1/control/runs', headers=owner).json()
    assert 'XMLRiver' not in runs[0]['error'] and 'XMLreaver' not in runs[0]['error']
    assert 'XMLRiver' not in json.dumps(runs[0]['progress'])
    detail = client.get(f"/api/v1/control/projects/{project['id']}/mentions/results/{result_id}", headers=owner)
    assert detail.status_code == 200
    assert 'XMLRiver' not in detail.json()['error_message']
    assert 'XMLRiver' in detail.json()['answer_text']
    report = client.get('/api/v1/reports', headers=owner, params={'project': project['id']})
    assert report.status_code == 200
    assert 'XMLRiver' not in report.json()['results'][0]['error_message']
    assert client.get(f"/api/v1/control/projects/{project['id']}/mentions/results/{result_id}",
        headers=other).status_code == 404
    with sessions() as db:
        assert db.get(ControlRun, run['id']).error.startswith('XMLRiver')
        assert db.get(CloudResult, result_id).error_message.startswith('XMLRiver')


def test_model_preflight_scopes_identical_check_ids_to_run_owner(tmp_path, monkeypatch):
    ai = FakeAI()
    client, owner, _, owner_id, sessions = setup(tmp_path, monkeypatch, ai=ai)
    _, run = project_and_run(client, owner)
    with sessions() as db:
        foreign_id = db.scalar(select(User.id).where(User.email == 'other@test.example'))
        check_id = run['id'] + ':same-query:google_aio'
        stored = db.get(ControlRun, run['id'])
        stored.lease_token = 'owner-token'
        stored.lease_until = utcnow() + timedelta(minutes=5)
        stored.state = 'running'
        db.add_all([Check(user_id=owner_id, client_check_id=check_id, price_kopeks=0),
                    Check(user_id=foreign_id, client_check_id=check_id, price_kopeks=0)])
        db.commit()
    assert _analyze_saved(sessions, run['id'], 'owner-token', check_id,
        [{'type': 'text', 'text': 'No match'}], ai)['raw']
    with sessions() as db:
        owner_check = db.scalar(select(Check).where(Check.user_id == owner_id,
            Check.client_check_id == check_id))
        foreign_check = db.scalar(select(Check).where(Check.user_id == foreign_id,
            Check.client_check_id == check_id))
        assert owner_check.analysis_attempts == 1 and owner_check.analysis_json
        assert foreign_check.analysis_attempts == 0 and foreign_check.analysis_json is None


def test_long_check_ledger_references_are_bounded_distinct_and_idempotent(tmp_path, monkeypatch):
    _, _, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    ids = ['x' * 90, 'y' * 90, 'short-id']
    with sessions() as db:
        user = db.get(User, user_id)
        db.get(Wallet, user_id).balance_kopeks = 500
        db.add_all(Check(user_id=user_id, client_check_id=key, price_kopeks=120,
            analysis_json='{"found": false}') for key in ids)
        db.commit()
        for key in ids:
            complete_check(db, user, key, 'not_found')
            complete_check(db, user, key, 'not_found')
        refs = [entry.reference for entry in db.scalars(select(LedgerEntry)).all()]
        assert len(refs) == len(set(refs)) == 3
        assert all(len(ref) <= 100 for ref in refs)
        assert f'check:{user_id}:short-id' in refs
        assert db.get(Wallet, user_id).balance_kopeks == 140


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


def test_model_cooldown_without_http_does_not_spend_attempt_budget(tmp_path, monkeypatch):
    class CoolingAI(FakeAI):
        cooling = True
        calls = 0
        def analyze(self, system, content):
            self.calls += 1
            if self.cooling:
                self.cooling = False
                raise AIRetryAfter(1, 429, sent=False)
            return super().analyze(system, content)

    ai = CoolingAI()
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai)
    Collector.answer = {**Collector.answer, 'main_text': 'No match',
                        'answer_text': 'No match', 'content': ['No match']}
    _, run = project_and_run(client, owner)
    assert tick(sessions, ai)
    with sessions() as db:
        check = db.scalar(select(Check))
        assert check.analysis_attempts == 1 and check.analysis_json
        assert db.get(ControlRun, run['id']).state == 'done'
        assert len(db.scalars(select(ServerCapture)).all()) == 1
    assert ai.calls == 2


@pytest.mark.parametrize('status,sent,expected_attempts', [(429, True, 2), (402, False, 1)])
def test_transient_model_limit_waits_and_recovers_without_manual_resume(
        tmp_path, monkeypatch, status, sent, expected_attempts):
    class RateAI(FakeAI):
        calls = 0
        def analyze(self, system, content):
            self.calls += 1
            if self.calls == 1:
                raise AIRetryAfter(1, status, sent=sent)
            return super().analyze(system, content)

    ai = RateAI()
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai)
    Collector.answer = {**Collector.answer, 'main_text': 'No match',
                        'answer_text': 'No match', 'content': ['No match']}
    _, run = project_and_run(client, owner)
    assert tick(sessions, ai)
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'done'
        assert db.scalar(select(Check)).analysis_attempts == expected_attempts
        assert len(db.scalars(select(ServerCapture)).all()) == 1
    assert ai.calls == 2 and Collector.calls == [('google_aio', 'question')]


def test_stop_during_model_cooldown_prevents_another_paid_call(tmp_path, monkeypatch):
    rate_seen = threading.Event()
    class RateAI(FakeAI):
        calls = 0
        def analyze(self, system, content):
            self.calls += 1
            rate_seen.set()
            raise AIRetryAfter(2, 429, sent=True)

    ai = RateAI()
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai)
    Collector.answer = {**Collector.answer, 'main_text': 'No match',
                        'answer_text': 'No match', 'content': ['No match']}
    _, run = project_and_run(client, owner)
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(tick(sessions, ai)))
    thread.start()
    assert rate_seen.wait(5)
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={'action': 'stop'}).status_code == 200
    thread.join(5)
    assert not thread.is_alive() and outcome == [True] and ai.calls == 1
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert db.scalar(select(Check)).status == 'released'


def test_model_rate_retries_stop_at_four_actual_attempts(tmp_path, monkeypatch):
    class RateAI(FakeAI):
        calls = 0
        def analyze(self, system, content):
            self.calls += 1
            raise AIRetryAfter(0, 429, sent=True)

    ai = RateAI()
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai)
    Collector.answer = {**Collector.answer, 'main_text': 'No match',
                        'answer_text': 'No match', 'content': ['No match']}
    _, run = project_and_run(client, owner)
    assert tick(sessions, ai)
    assert ai.calls == 4 and Collector.calls == [('google_aio', 'question')]
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'done'
        assert db.scalar(select(Check)).analysis_attempts == 4
        assert db.scalar(select(CloudResult)).status == 'error'


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
        n = len(calls)
        return AIResult(raw, ai.model, {'cost': n / 10000, 'prompt_tokens': 10 * n,
            'completion_tokens': 5 * n, 'total_tokens': 15 * n})
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
        check = db.scalar(select(Check))
        assert check.analysis_attempts == 2
        assert json.loads(check.analysis_usage_json) == {'cost': pytest.approx(0.0003),
            'prompt_tokens': 30, 'completion_tokens': 15, 'total_tokens': 45}
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
        n = calls.count('arbitrate')
        return AIResult(raw, ai.arbiter_model, {'cost': n / 10000, 'prompt_tokens': 10 * n,
            'completion_tokens': 5 * n, 'total_tokens': 15 * n})
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
        assert json.loads(check.arbitration_usage_json) == {'cost': pytest.approx(0.0003),
            'prompt_tokens': 30, 'completion_tokens': 15, 'total_tokens': 45}
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 1
    Collector.answer = answer


@pytest.mark.parametrize('failure', ['malformed', 'bad_schema', 'ai_error'])
def test_primary_attempt_budget_finishes_error_without_charge(tmp_path, monkeypatch, failure):
    ai = FakeAI()
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, ai=ai, admin=False)
    monkeypatch.setattr(Collector, 'answer', {**Collector.answer,
        'main_text': 'No name', 'answer_text': 'No name'})
    Collector.calls = []
    _, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    calls = []
    def fail_analyze(system, content):
        calls.append('analyze')
        if failure == 'ai_error':
            raise AIError('unavailable')
        raw = '{"found": false, "mention_types": 7}' if failure == 'bad_schema' else 'malformed'
        return AIResult(raw, ai.model, {'cost': 0.0001})
    ai.analyze = fail_analyze
    for attempt in range(4):
        if attempt:
            assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                json={'action': 'resume'}).status_code == 200
        assert tick(sessions, ai)
        with sessions() as db:
            assert db.get(ControlRun, run['id']).state == ('done' if attempt == 3 else 'paused')
    assert len(calls) == 4 and Collector.calls == [('google_aio', 'question')]
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={'action': 'resume'}).status_code == 409
    assert not tick(sessions, ai)
    with sessions() as db:
        check = db.scalar(select(Check))
        assert check.analysis_attempts == 4 and check.status == 'released'
        assert db.scalar(select(CloudResult)).status == 'error'
        assert len(db.scalars(select(ServerCapture)).all()) == 1
        assert db.get(Wallet, user_id).balance_kopeks == 500
        assert db.scalar(select(LedgerEntry).where(LedgerEntry.kind == 'check')) is None


@pytest.mark.parametrize('failure', ['malformed', 'bad_schema', 'ai_error'])
def test_arbiter_attempt_budget_finishes_error_with_one_charge(tmp_path, monkeypatch, failure):
    ai = FakeAI()
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, ai=ai, admin=False)
    monkeypatch.setattr(Collector, 'answer', {**Collector.answer,
        'main_text': 'No name', 'answer_text': 'No name'})
    Collector.calls = []
    _, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    calls = []
    def found_analyze(system, content):
        calls.append('analyze')
        return AIResult('{"found": true, "confidence": 0.9}', ai.model, {})
    def fail_arbitrate(system, content):
        calls.append('arbitrate')
        if failure == 'ai_error':
            raise AIError('unavailable')
        raw = '{"found": false, "mention_types": 7}' if failure == 'bad_schema' else 'malformed'
        return AIResult(raw, ai.arbiter_model, {'cost': 0.0001})
    ai.analyze, ai.arbitrate = found_analyze, fail_arbitrate
    for attempt in range(4):
        if attempt:
            assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                json={'action': 'resume'}).status_code == 200
        assert tick(sessions, ai)
        with sessions() as db:
            assert db.get(ControlRun, run['id']).state == ('done' if attempt == 3 else 'paused')
    assert calls == ['analyze', 'arbitrate', 'arbitrate', 'arbitrate', 'arbitrate']
    assert Collector.calls == [('google_aio', 'question')]
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={'action': 'resume'}).status_code == 409
    assert not tick(sessions, ai)
    with sessions() as db:
        check = db.scalar(select(Check))
        assert check.analysis_attempts == 1 and check.arbitration_attempts == 4
        assert check.status == 'settled'
        assert db.scalar(select(CloudResult)).status == 'error'
        assert len(db.scalars(select(ServerCapture)).all()) == 1
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 1


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


def test_stop_reuses_cached_verdict_without_another_model_or_charge(tmp_path, monkeypatch):
    import server.cloud_scans as scans
    ai = FakeAI()
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, ai=ai, admin=False)
    _, run = project_and_run(client, owner)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        query_id = json.loads(db.get(ControlRun, run['id']).snapshot_json)['queries'][0]['id']
        key = f"{run['id']}:{query_id}:google_aio"
        db.add(Check(user_id=user_id, client_check_id=key, price_kopeks=120,
            analysis_attempts=1, analysis_json='{"found": false, "confidence": 0.9}',
            analysis_model=ai.model))
        payload = {**Collector.answer, 'main_text': 'No name', 'answer_text': 'No name'}
        db.add(ServerCapture(run_id=run['id'], query_id=query_id, service='google_aio',
            check_id=key, answer_json=json.dumps(payload)))
        db.commit()
    original = scans._process_saved_pair
    async def stop_before_drain(*args, **kwargs):
        assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
            json={'action': 'stop'}).status_code == 200
        return await original(*args, **kwargs)
    monkeypatch.setattr(scans, '_process_saved_pair', stop_before_drain)
    def no_model(*args):
        raise AssertionError('cached verdict must not call a model')
    ai.analyze = ai.arbitrate = no_model
    assert asyncio.run(cloud_tick(sessions, ai, 120, Collector,
        prefetch_limits={'google_aio': 10}))
    assert not tick(sessions, ai)
    assert Collector.calls == []
    with sessions() as db:
        assert db.scalar(select(CloudResult)).status == 'not_found'
        assert db.scalar(select(Check)).analysis_attempts == 1
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 1


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

    async def fail_tick(*args, **kwargs):
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


def test_worker_database_wait_does_not_delay_server_heartbeat(monkeypatch):
    entered = threading.Event()
    finished = threading.Event()

    def blocked_claim(sessions, blocked_services=()):
        entered.set()
        time.sleep(0.6)  # Simulate a bounded SQL lock held by another request.
        finished.set()
        return None

    monkeypatch.setattr('server.cloud_scans._claim', blocked_claim)

    async def scenario():
        task = asyncio.create_task(worker(None, None, 120))
        try:
            start = asyncio.get_running_loop().time()
            await asyncio.sleep(0.05)
            heartbeat_delay = asyncio.get_running_loop().time() - start
            assert heartbeat_delay < 0.25
            assert await asyncio.to_thread(entered.wait, 1)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert finished.is_set()

    asyncio.run(scenario())


def test_lifespan_waits_for_current_cloud_tick_before_closing_ai(tmp_path, monkeypatch):
    ai = FakeAI()
    client, _, _, _, _ = setup(tmp_path, monkeypatch, ai=ai)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    closed = threading.Event()

    async def blocked_tick(*args, **kwargs):
        entered.set()
        release.wait(2)
        assert kwargs['shutdown_event'].is_set()
        finished.set()
        return False

    def close_ai():
        assert finished.is_set()
        closed.set()

    monkeypatch.setattr('server.cloud_scans.cloud_tick', blocked_tick)
    ai.close = close_ai
    with client:
        assert entered.wait(1)
        timer = threading.Timer(0.1, release.set)
        timer.start()
    timer.join(1)
    assert closed.is_set()


def test_batch_prefetch_overlaps_and_respects_engine_caps(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    _, run = project_and_run(client, owner, services=('google_aio', 'yandex_neuro'),
        queries=[{'text': f'q{i}'} for i in range(3)])

    class BatchCollector(Collector):
        active = peak = 0
        calls = []
        attempts = []

        def __init__(self, service, geo, *, max_attempts=3):
            super().__init__(service, geo)
            self.attempts.append(max_attempts)

        async def collect(self, query, *, should_continue=None):
            assert should_continue()
            self.calls.append((self.service, query))
            type(self).active += 1
            type(self).peak = max(type(self).peak, type(self).active)
            await asyncio.sleep(0.05)
            type(self).active -= 1
            return dict(self.answer)

    limits = {'google_aio': 2, 'yandex_neuro': 2}
    def batch_tick():
        return asyncio.run(cloud_tick(sessions, None, 120, BatchCollector, prefetch_limits=limits))

    assert batch_tick()
    assert BatchCollector.peak == 4
    assert sorted(BatchCollector.attempts) == [6] * 6
    assert sorted(BatchCollector.calls) == sorted([(service, f'q{i}')
        for service in limits for i in range(3)])
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'done'
        assert len(db.scalars(select(ServerCapture)).all()) == 6
        assert len(db.scalars(select(CloudResult)).all()) == 6
    assert not batch_tick()
    assert max(BatchCollector.attempts) == 6


def test_batch_hard_caps_ten_requests_per_engine(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    project_and_run(client, owner, services=('google_aio', 'yandex_neuro'),
        queries=[{'text': f'q{i}'} for i in range(11)])

    class CappedCollector(Collector):
        calls = []
        active = {'google_aio': 0, 'yandex_neuro': 0}
        peak = {'google_aio': 0, 'yandex_neuro': 0}

        def __init__(self, service, geo, *, max_attempts):
            assert max_attempts == 6
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            self.calls.append((self.service, query))
            type(self).active[self.service] += 1
            type(self).peak[self.service] = max(type(self).peak[self.service],
                type(self).active[self.service])
            await asyncio.sleep(0.01)
            type(self).active[self.service] -= 1
            return dict(self.answer)

    assert asyncio.run(cloud_tick(sessions, None, 120, CappedCollector,
        prefetch_limits={'google_aio': 100, 'yandex_neuro': 100}))
    assert sum(service == 'google_aio' for service, _ in CappedCollector.calls) == 11
    assert sum(service == 'yandex_neuro' for service, _ in CappedCollector.calls) == 11
    assert CappedCollector.peak == {'google_aio': 10, 'yandex_neuro': 10}
    with sessions() as db:
        assert len(db.scalars(select(ServerCapture)).all()) == 22


def test_partial_batch_crash_drains_later_saved_answer_first(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    _, run = project_and_run(client, owner, queries=[{'text': 'q0'}, {'text': 'q1'}])

    class PartialCollector(Collector):
        calls = []

        def __init__(self, service, geo, *, max_attempts=3):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            self.calls.append(query)
            if query == 'q0':
                raise CollectionCancelled('interrupted before response')
            return dict(self.answer)

    assert asyncio.run(cloud_tick(sessions, None, 120, PartialCollector,
        prefetch_limits={'google_aio': 2}))
    assert PartialCollector.calls == ['q0', 'q1']
    with sessions() as db:
        captures = db.scalars(select(ServerCapture)).all()
        results = db.scalars(select(CloudResult)).all()
        assert len(captures) == len(results) == 1
        assert results[0].query_text == 'q1'
        assert db.get(ControlRun, run['id']).state == 'running'


def test_batch_unexpected_failure_drains_sibling_without_false_result(tmp_path, monkeypatch, caplog):
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    _, run = project_and_run(client, owner, queries=[{'text': 'q0'}, {'text': 'q1'}])
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()

    class FailingCollector(Collector):
        calls = []

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            self.calls.append(query)
            if query == 'q0':
                await asyncio.sleep(0.01)
                raise RuntimeError('PRIVATE_ANSWER_SENTINEL')
            await asyncio.sleep(0.05)
            return dict(self.answer)

    with caplog.at_level(logging.ERROR, logger='server.cloud_scans'):
        assert asyncio.run(cloud_tick(sessions, None, 120, FailingCollector,
            prefetch_limits={'google_aio': 2}))
    assert 'PRIVATE_ANSWER_SENTINEL' not in caplog.text
    assert FailingCollector.calls == ['q0', 'q1']
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'paused'
        assert len(db.scalars(select(ServerCapture)).all()) == 1
        assert db.scalar(select(ServerCapture)).service == 'google_aio'
        assert [result.query_text for result in db.scalars(select(CloudResult)).all()] == ['q1']
        assert sorted(check.status for check in db.scalars(select(Check)).all()) == ['reserved', 'settled']
        assert db.get(Wallet, user_id).balance_kopeks == 380
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={'action': 'resume'}).status_code == 200
    assert asyncio.run(cloud_tick(sessions, None, 120, FailingCollector,
        prefetch_limits={'google_aio': 2}))
    assert FailingCollector.calls == ['q0', 'q1', 'q0']  # Saved q1 is never recollected.
    with sessions() as db:
        assert db.scalar(select(CloudResult)).query_text == 'q1'
        assert db.get(Wallet, user_id).balance_kopeks == 380


def test_batch_save_failure_still_persists_other_answers(tmp_path, monkeypatch, caplog):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    _, run = project_and_run(client, owner, queries=[{'text': 'q0'}, {'text': 'q1'}])
    with sessions() as db:
        q0_id = json.loads(db.get(ControlRun, run['id']).snapshot_json)['queries'][0]['id']
    original_commit = sessions.class_.commit
    failed = False

    def fail_first_capture(db):
        nonlocal failed
        if not failed and any(isinstance(row, ServerCapture) and row.query_id == q0_id for row in db.new):
            failed = True
            raise RuntimeError('PRIVATE_ANSWER_SENTINEL')
        return original_commit(db)

    monkeypatch.setattr(sessions.class_, 'commit', fail_first_capture)

    class SaveCollector(Collector):
        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            if query == 'q1':
                await asyncio.sleep(0.02)
            return dict(self.answer)

    with caplog.at_level(logging.ERROR, logger='server.cloud_scans'):
        assert asyncio.run(cloud_tick(sessions, None, 120, SaveCollector,
            prefetch_limits={'google_aio': 2}))
    assert failed
    assert 'PRIVATE_ANSWER_SENTINEL' not in caplog.text
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'paused'
        assert len(db.scalars(select(ServerCapture)).all()) == 1
        assert [result.query_text for result in db.scalars(select(CloudResult)).all()] == ['q1']
        assert sorted(check.status for check in db.scalars(select(Check)).all()) == ['reserved', 'settled']


def test_batch_commits_first_response_while_last_request_waits(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    project_and_run(client, owner, queries=[{'text': 'q0'}, {'text': 'q1'}])
    release = asyncio.Event()

    class SlowCollector(Collector):
        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            if query == 'q1':
                await release.wait()
            return dict(self.answer)

    async def scenario():
        task = asyncio.create_task(cloud_tick(sessions, None, 120, SlowCollector,
            prefetch_limits={'google_aio': 2}))
        try:
            for _ in range(100):
                with sessions() as db:
                    if len(db.scalars(select(ServerCapture)).all()) == 1:
                        break
                await asyncio.sleep(0.01)
            else:
                raise AssertionError('first response was not committed while sibling waited')
        finally:
            release.set()
        assert await task
    asyncio.run(scenario())


def test_throttled_engine_does_not_stop_healthy_engine_refill(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    _, run = project_and_run(client, owner, services=('yandex_neuro', 'google_aio'),
        queries=[{'text': f'q{i}'} for i in range(3)])
    class ThrottleCollector(Collector):
        calls = []
        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)
        async def collect(self, query, *, should_continue=None):
            self.calls.append((self.service, query))
            if self.service == 'yandex_neuro':
                raise ProviderThrottleError('test throttle')
            await asyncio.sleep(0.01)
            return dict(self.answer)
    assert asyncio.run(cloud_tick(sessions, None, 120, ThrottleCollector,
        prefetch_limits={'google_aio': 1, 'yandex_neuro': 1}, cooldowns={}))
    assert [q for service, q in ThrottleCollector.calls if service == 'google_aio'] == ['q0', 'q1', 'q2']
    assert [q for service, q in ThrottleCollector.calls if service == 'yandex_neuro'] == ['q0']
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'paused'
        results = db.scalars(select(CloudResult).where(CloudResult.service == 'google_aio')).all()
        assert len(results) == 3 and all(result.status == 'found' for result in results)


def test_throttled_engine_cools_down_across_runs_without_blocking_other_engine(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    _, first = project_and_run(client, owner, services=('yandex_neuro',),
        queries=[{'text': 'first-yandex'}])
    _, second = project_and_run(client, owner, services=('yandex_neuro', 'google_aio'),
        queries=[{'text': 'second'}])
    now = [1000.0]
    cooldowns = {}

    class ThrottleCollector(Collector):
        calls = []

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            self.calls.append((self.service, query))
            if query == 'first-yandex':
                raise ProviderThrottleError('XMLRiver throttled')
            return dict(self.answer)

    def batch_tick():
        return asyncio.run(cloud_tick(sessions, None, 120, ThrottleCollector,
            prefetch_limits={'google_aio': 10, 'yandex_neuro': 10},
            cooldowns=cooldowns, clock=lambda: now[0]))

    assert batch_tick()
    assert cooldowns == {'yandex_neuro': 1600.0}
    assert ThrottleCollector.calls == [('yandex_neuro', 'first-yandex')]
    with sessions() as db:
        assert db.get(ControlRun, first['id']).state == 'paused'
        assert db.scalar(select(CloudResult).where(CloudResult.run_id == first['id'])).status == 'limit_reached'
    assert batch_tick()
    assert ThrottleCollector.calls == [('yandex_neuro', 'first-yandex'), ('google_aio', 'second')]
    assert not batch_tick()  # Only the cooled-down Yandex pair is pending.
    now[0] += 601
    assert batch_tick()
    assert ThrottleCollector.calls[-1] == ('yandex_neuro', 'second')
    with sessions() as db:
        assert db.get(ControlRun, second['id']).state == 'done'
        assert len(db.scalars(select(CloudResult).where(CloudResult.run_id == second['id'])).all()) == 2


def test_throttled_older_runs_do_not_starve_google_after_twenty(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    for index in range(21):
        project_and_run(client, owner, services=('yandex_neuro',),
            queries=[{'text': f'blocked-{index}'}])
    _, google = project_and_run(client, owner, services=('google_aio',),
        queries=[{'text': 'eligible-google'}])

    class GoogleCollector(Collector):
        calls = []

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            self.calls.append((self.service, query))
            return dict(self.answer)

    assert asyncio.run(cloud_tick(sessions, None, 120, GoogleCollector,
        prefetch_limits={'google_aio': 10, 'yandex_neuro': 10},
        cooldowns={'yandex_neuro': 1600.0}, clock=lambda: 1000.0))
    assert GoogleCollector.calls == [('google_aio', 'eligible-google')]
    with sessions() as db:
        assert db.get(ControlRun, google['id']).state == 'done'


def test_fast_capture_is_analyzed_while_sibling_provider_waits(tmp_path, monkeypatch):
    ai = FakeAI()
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai)
    _, run = project_and_run(client, owner, queries=[{'text': 'fast'}, {'text': 'slow'}])
    release = asyncio.Event()
    model_started = threading.Event()
    answer = {**Collector.answer, 'main_text': 'No match', 'answer_text': 'No match',
              'content': ['No match']}

    class StreamingCollector(Collector):
        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            if query == 'slow':
                await release.wait()
            return dict(answer)

    def analyze(system, content):
        model_started.set()
        return AIResult('{"found": false, "confidence": 0.9}', ai.model, {})
    ai.analyze = analyze

    async def scenario():
        task = asyncio.create_task(cloud_tick(sessions, ai, 120, StreamingCollector,
            prefetch_limits={'google_aio': 2}))
        try:
            started_early = await asyncio.to_thread(model_started.wait, 0.7)
            with sessions() as db:
                captured_early = len(db.scalars(select(ServerCapture)).all()) == 1
        finally:
            release.set()
        assert await task
        assert started_early and captured_early
    asyncio.run(scenario())
    with sessions() as db:
        assert db.scalar(select(CloudResult).where(CloudResult.run_id == run['id'],
            CloudResult.query_text == 'fast')) is not None


def test_each_engine_refills_while_other_engine_waits(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    project_and_run(client, owner, services=('google_aio', 'yandex_neuro'),
        queries=[{'text': 'q0'}, {'text': 'q1'}])
    release_yandex = asyncio.Event()
    second_google_started = asyncio.Event()

    class RefillCollector(Collector):
        calls = []

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            self.calls.append((self.service, query))
            if self.service == 'yandex_neuro' and query == 'q0':
                await release_yandex.wait()
            if self.service == 'google_aio' and query == 'q1':
                second_google_started.set()
            return dict(self.answer)

    async def scenario():
        task = asyncio.create_task(cloud_tick(sessions, None, 120, RefillCollector,
            prefetch_limits={'google_aio': 1, 'yandex_neuro': 1}))
        try:
            try:
                await asyncio.wait_for(second_google_started.wait(), 0.7)
                refilled_early = True
            except asyncio.TimeoutError:
                refilled_early = False
        finally:
            release_yandex.set()
        assert await task
        assert refilled_early
    asyncio.run(scenario())


def test_stop_during_batch_drains_all_saved_and_releases_unstarted(tmp_path, monkeypatch):
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    _, run = project_and_run(client, owner, queries=[{'text': f'q{i}'} for i in range(4)])
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()

    class StopCollector(Collector):
        calls = []
        started = 0

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            assert should_continue()
            self.calls.append(query)
            type(self).started += 1
            while type(self).started < 3:
                await asyncio.sleep(0)
            if query == 'q0':
                assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                    json={'action': 'stop'}).status_code == 200
            await asyncio.sleep(0)
            return dict(self.answer)

    def batch_tick():
        return asyncio.run(cloud_tick(sessions, None, 120, StopCollector,
            prefetch_limits={'google_aio': 3}))

    assert batch_tick()
    assert sorted(StopCollector.calls) == ['q0', 'q1', 'q2']
    with sessions() as db:
        assert len(db.scalars(select(ServerCapture)).all()) == 3
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert len(db.scalars(select(CloudResult)).all()) == 3
        assert all(row.status == 'settled' for row in db.scalars(select(Check)).all())
        assert db.get(Wallet, user_id).balance_kopeks == 140
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 3
    assert not batch_tick()


def test_batch_pause_preserves_other_answers_for_resume(tmp_path, monkeypatch):
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch)
    _, run = project_and_run(client, owner, queries=[{'text': 'q0'}, {'text': 'q1'}])

    class PauseCollector(Collector):
        calls = []
        started = 0

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            assert should_continue()
            self.calls.append(query)
            type(self).started += 1
            while type(self).started < 2:
                await asyncio.sleep(0)
            if query == 'q0':
                assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                    json={'action': 'pause'}).status_code == 200
            return dict(self.answer)

    def batch_tick():
        return asyncio.run(cloud_tick(sessions, None, 120, PauseCollector,
            prefetch_limits={'google_aio': 2}))

    assert batch_tick()
    with sessions() as db:
        assert len(db.scalars(select(ServerCapture)).all()) == 2
        assert db.get(ControlRun, run['id']).state == 'paused'
    assert sorted(PauseCollector.calls) == ['q0', 'q1']
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={'action': 'resume'}).status_code == 200
    assert batch_tick()
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'done'
        assert len(db.scalars(select(CloudResult)).all()) == 2
    assert sorted(PauseCollector.calls) == ['q0', 'q1']


def test_batch_reserves_only_affordable_checks_before_provider_calls(tmp_path, monkeypatch):
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    _, run = project_and_run(client, owner, queries=[{'text': f'q{i}'} for i in range(3)])
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 250
        db.commit()

    class PaidCollector(Collector):
        calls = []

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            assert should_continue()
            self.calls.append(query)
            return dict(self.answer)

    def batch_tick():
        return asyncio.run(cloud_tick(sessions, None, 120, PaidCollector,
            prefetch_limits={'google_aio': 3}))

    assert batch_tick()
    assert PaidCollector.calls == ['q0', 'q1']
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'paused'
        assert len(db.scalars(select(ServerCapture)).all()) == 2
        assert len(db.scalars(select(CloudResult)).all()) == 2
        assert db.get(Wallet, user_id).balance_kopeks == 10
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 2


def test_shutdown_stops_retry_but_preserves_inflight_answer_and_reservation(tmp_path, monkeypatch):
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    _, run = project_and_run(client, owner, queries=[{'text': 'q0'}, {'text': 'q1'}])
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    shutdown = threading.Event()

    class ShutdownCollector(Collector):
        calls = []

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            self.calls.append(query)
            assert should_continue()
            if query == 'q0':
                shutdown.set()  # The current provider response still arrives.
                assert not should_continue()
                return dict(self.answer)
            raise AssertionError('shutdown started another HTTP request')

    assert asyncio.run(cloud_tick(sessions, None, 120, ShutdownCollector,
        prefetch_limits={'google_aio': 2}, shutdown_event=shutdown))
    assert ShutdownCollector.calls == ['q0']
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'running'
        assert db.get(ControlRun, run['id']).lease_token is None
        assert len(db.scalars(select(ServerCapture)).all()) == 1
        assert len(db.scalars(select(Check)).all()) == 2
        assert all(check.status == 'reserved' for check in db.scalars(select(Check)).all())
        assert db.get(Wallet, user_id).balance_kopeks == 500

    class ResumeCollector(Collector):
        calls = []

        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            self.calls.append(query)
            return dict(self.answer)

    assert asyncio.run(cloud_tick(sessions, None, 120, ResumeCollector,
        prefetch_limits={'google_aio': 2}))
    assert ResumeCollector.calls == ['q1']
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'done'
        assert len(db.scalars(select(CloudResult)).all()) == 2
        assert db.get(Wallet, user_id).balance_kopeks == 260
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 2


def test_postgres_twenty_models_overlap_while_collection_keeps_running(
        tmp_path, monkeypatch, postgres_url):
    started = threading.Event()
    release = threading.Event()
    guard = threading.Lock()
    active = peak = calls = 0

    class BlockingAI(FakeAI):
        def analyze(self, system, content):
            nonlocal active, peak, calls
            with guard:
                active += 1
                calls += 1
                peak = max(peak, active)
                if active == 20:
                    started.set()
            try:
                assert release.wait(15)
                return super().analyze(system, content)
            finally:
                with guard:
                    active -= 1

    class FastCollector(Collector):
        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            return {**self.answer, 'main_text': 'No match', 'answer_text': 'No match',
                    'content': ['No match']}

    ai = BlockingAI()
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai, database_url=postgres_url)
    _, run = project_and_run(client, owner, services=('google_aio', 'yandex_neuro'),
        queries=[{'text': f'q{i}'} for i in range(11)])
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(asyncio.run(cloud_tick(
        sessions, ai, 120, FastCollector, prefetch_limits={'google_aio': 10, 'yandex_neuro': 10}))))
    thread.start()
    try:
        assert started.wait(12), f'only {calls} model calls overlapped'
        with sessions() as db:
            assert len(db.scalars(select(ServerCapture)).all()) == 22
            assert len(db.scalars(select(CloudResult)).all()) == 0
        assert peak == 20
    finally:
        release.set()
        thread.join(20)
    assert not thread.is_alive() and outcome == [True]
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'done'
        assert len(db.scalars(select(CloudResult)).all()) == 22
    assert calls == 22 and peak == 20


def test_postgres_stale_model_cache_is_settled_once_by_new_owner(
        tmp_path, monkeypatch, postgres_url):
    started = threading.Event()
    release = threading.Event()
    calls = []

    class BlockingAI(FakeAI):
        def analyze(self, system, content):
            calls.append('model')
            started.set()
            assert release.wait(10)
            return super().analyze(system, content)

    class FastCollector(Collector):
        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            return {**self.answer, 'main_text': 'No match', 'answer_text': 'No match',
                    'content': ['No match']}

    ai = BlockingAI()
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, ai=ai,
        admin=False, database_url=postgres_url)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    _, run = project_and_run(client, owner)
    outcomes = []
    def run_tick():
        outcomes.append(asyncio.run(cloud_tick(sessions, ai, 120, FastCollector,
            prefetch_limits={'google_aio': 1})))
    first = threading.Thread(target=run_tick)
    second = threading.Thread(target=run_tick)
    first.start()
    try:
        assert started.wait(8)
        with sessions() as db:
            db.get(ControlRun, run['id']).lease_until = utcnow() - timedelta(seconds=1)
            db.commit()
        second.start()
        for _ in range(100):
            with sessions() as db:
                if db.get(ControlRun, run['id']).lease_until > utcnow():
                    break
            time.sleep(0.01)
        else:
            raise AssertionError('new worker did not take over expired lease')
    finally:
        release.set()
        first.join(15)
        if second.ident:
            second.join(15)
    assert not first.is_alive() and not second.is_alive()
    assert sorted(outcomes) == [False, True]
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'done'
        assert len(db.scalars(select(CloudResult)).all()) == 1
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 1
    assert calls == ['model']


def test_postgres_stop_drains_inflight_captures_without_new_collection(
        tmp_path, monkeypatch, postgres_url):
    started = threading.Event()
    release = threading.Event()
    guard = threading.Lock()
    count = 0
    calls = []

    class StopCollector(Collector):
        def __init__(self, service, geo, *, max_attempts):
            super().__init__(service, geo)

        async def collect(self, query, *, should_continue=None):
            nonlocal count
            calls.append(query)
            with guard:
                count += 1
                if count == 2:
                    started.set()
            assert await asyncio.to_thread(release.wait, 10)
            return dict(self.answer)

    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False,
        database_url=postgres_url)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    _, run = project_and_run(client, owner, queries=[{'text': f'q{i}'} for i in range(3)])
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(asyncio.run(cloud_tick(
        sessions, None, 120, StopCollector, prefetch_limits={'google_aio': 2}))))
    thread.start()
    try:
        assert started.wait(8)
        assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
            json={'action': 'stop'}).status_code == 200
    finally:
        release.set()
        thread.join(15)
    assert not thread.is_alive() and outcome == [True] and sorted(calls) == ['q0', 'q1']
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert len(db.scalars(select(ServerCapture)).all()) == 2
        assert len(db.scalars(select(CloudResult)).all()) == 2
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.kind == 'check')).all()) == 2
        assert db.get(Wallet, user_id).balance_kopeks == 260
