"""Cross-account regressions for project sharing, using disposable state only."""
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from server.app import create_app
from server.models import (Check, CloudResult, ControlProject, ControlRun, ProjectMember,
                           Screenshot, ServerCapture, User, Wallet, make_session_factory)
from server.test_accounts import register_account
from server.test_brand_recompute import feature_setup
from server.test_cloud_scans import postgres_url, setup as cloud_setup
from server.test_control import setup
from server.test_reporting import seed_report


@pytest.fixture(autouse=True)
def fake_provider(monkeypatch):
    monkeypatch.setenv('SCRAPELESS_API_KEY', 'fake-key')


def test_shared_evidence_requires_this_project_run_and_preserves_owner_legacy(tmp_path):
    _, owner, member, devices, project, ids, url = seed_report(tmp_path)
    signed = []

    class Storage:
        def download_url(self, key):
            signed.append(key)
            return 'https://screenshots.example.test/' + key

    client = TestClient(create_app(database_url=url, screenshot_storage=Storage()))
    private = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Private B', 'brand_name': 'Private', 'queries': [{'text': 'private'}],
        'config': {'services': ['google_aio']},
    }).json()
    other_private = client.post('/api/v1/control/projects', headers=member, json={
        'name': 'Other owner C', 'brand_name': 'Other', 'queries': [{'text': 'other'}],
        'config': {'services': ['google_aio']},
    }).json()
    base = f"/api/v1/control/projects/{project['id']}"
    assert client.put(base + '/members', headers=owner,
                      json={'email': 'other@test.example', 'role': 'viewer'}).status_code == 200
    _, sessions = make_session_factory(url)
    query_id = project['queries'][0]['id']
    with sessions() as db:
        for marker, source in (('a', project), ('b', private), ('c', other_private)):
            owner_id = db.get(ControlProject, source['id']).user_id
            run_id = marker * 32
            key = f'{run_id}:{query_id}:google_aio'
            db.add(ControlRun(id=run_id, user_id=owner_id, project_id=source['id'],
                              state='done', request_key='evidence-' + marker,
                              snapshot_json=json.dumps(source), progress_json='{}'))
            check = Check(user_id=owner_id, client_check_id=key, price_kopeks=120,
                          status='settled', analysis_json=json.dumps({'project': marker}))
            db.add(check)
            db.flush()
            db.add(Screenshot(check_id=check.id, object_key='proof-' + marker, size_bytes=100))
            db.add(ServerCapture(run_id=run_id, query_id=query_id, service='google_aio',
                                 check_id=key, answer_json=json.dumps({
                                     'shown': True, 'content': [marker], 'products': [], 'source_cards': []})))
        row = db.get(CloudResult, ids[1])
        row.run_id = 'a' * 32
        row.check_id = f"{row.run_id}:{query_id}:google_aio"
        db.commit()
    detail_url = base + f'/mentions/results/{ids[1]}'
    for suffix in ('', '/overview', '/export/mentions', '/export/sources', '/overview/export/sources'):
        assert client.get(base + '/mentions' + suffix, headers=member,
                          params={'date_from': '2026-09-01', 'date_to': '2026-09-03'}).status_code == 200
    detail = client.get(detail_url, headers=member)
    assert detail.status_code == 200 and detail.headers['cache-control'] == 'no-store'
    assert detail.json()['analysis'] == {'project': 'a'}
    assert detail.json()['answer_evidence']['content'] == ['a']
    shot = client.get(detail_url + '/screenshot', headers=member)
    assert shot.status_code == 200 and shot.json()['url'].endswith('/proof-a')
    assert shot.headers['cache-control'] == 'no-store'
    assert client.get(detail_url, headers=devices[0]).status_code == 403
    # Both forged project-bound and unbound historical references must stay private.
    for marker, forged_run in (('b', 'b' * 32), ('b', None), ('c', 'c' * 32)):
        with sessions() as db:
            row = db.get(CloudResult, ids[1])
            row.run_id = forged_run
            row.check_id = f"{marker * 32}:{query_id}:google_aio"
            db.commit()
        hidden = client.get(detail_url, headers=member).json()
        assert hidden['analysis'] is None and hidden['arbitration'] is None
        assert hidden['answer_evidence'] is None and not hidden['has_screenshot']
        assert hidden['check_id'] is None
        assert client.get(detail_url + '/screenshot', headers=member).status_code == 404
        expected_owner_analysis = {'project': 'b'} if marker == 'b' else None
        assert client.get(detail_url, headers=owner).json()['analysis'] == expected_owner_analysis
        if marker == 'b':
            owner_shot = client.get(detail_url + '/screenshot', headers=owner)
            assert owner_shot.status_code == 200 and owner_shot.json()['url'].endswith('/proof-b')
    assert signed == ['proof-a', 'proof-b', 'proof-b']
    # A revoked participant cannot read even a previously valid result.
    assert client.delete(base + '/members/other@test.example', headers=owner).status_code == 200
    assert client.get(detail_url, headers=member).status_code == 404


def test_editor_command_observes_worker_transition_before_locked_read(tmp_path, monkeypatch):
    client, owner, editor, _, url = setup(tmp_path)
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Shared', 'brand_name': 'Brand', 'queries': [{'text': 'question'}],
        'config': {'services': ['chatgpt']},
    }).json()
    base = f"/api/v1/control/projects/{project['id']}"
    assert client.put(base + '/members', headers=owner,
                      json={'email': 'other@test.example', 'role': 'editor'}).status_code == 200
    _, sessions = make_session_factory(url)
    run_id = uuid.uuid4().hex
    with sessions() as db:
        db.add(ControlRun(id=run_id, user_id=db.get(ControlProject, project['id']).user_id,
                          project_id=project['id'], phase='cloud', active_project_key=project['id'],
                          request_key='worker-transition', snapshot_json=json.dumps(project), progress_json='{}'))
        db.commit()
    from server.control import project_access as real_access

    def worker_claims_before_project_lock(db, user_id, project_id, **kwargs):
        with sessions() as worker:
            run = worker.get(ControlRun, run_id)
            run.state, run.lease_token = 'running', 'live-worker'
            worker.commit()
        return real_access(db, user_id, project_id, **kwargs)

    monkeypatch.setattr('server.control.project_access', worker_claims_before_project_lock)
    response = client.post(f'/api/v1/control/runs/{run_id}/command', headers=editor, json={'action': 'stop'})
    assert response.status_code == 200, response.text
    with sessions() as db:
        run = db.get(ControlRun, run_id)
        assert (run.state, run.desired_state, run.lease_token, run.active_project_key) == (
            'running', 'cancelled', 'live-worker', project['id'])


def test_shared_scan_feature_and_pricing_follow_owner_not_editor(tmp_path, monkeypatch):
    original_uuid = uuid.uuid4
    client, eligible, sessions = feature_setup(tmp_path, monkeypatch, admin=True)
    monkeypatch.setattr('server.app.uuid.uuid4', original_uuid)
    registered = register_account(client, json={'email': 'ordinary@test.example', 'password': 'long-test-password-123'})
    ordinary = {'Authorization': 'Bearer ' + registered.json()['token']}
    body = {'name': 'Owner feature', 'brand_name': 'Brand', 'queries': [{'text': 'question'}],
            'config': {'services': ['chatgpt'], 'brand_clarification': 'Owner clarification'}}
    project = client.post('/api/v1/control/projects', headers=eligible, json=body).json()
    base = f"/api/v1/control/projects/{project['id']}"
    assert client.put(base + '/members', headers=eligible,
                      json={'email': 'ordinary@test.example', 'role': 'editor'}).status_code == 200
    assert client.get(base, headers=ordinary).json()['brand_clarifications_enabled']
    launched = client.post(base + '/runs', headers=ordinary, json={'request_id': original_uuid().hex})
    assert launched.status_code == 201, launched.text
    with sessions() as db:
        assert json.loads(db.get(ControlRun, launched.json()['id']).snapshot_json)['config']['brand_clarification'] == 'Owner clarification'
        db.get(Wallet, registered.json()['user']['id']).balance_kopeks = 1000
        db.commit()
    body['config'].pop('brand_clarification')
    project = client.post('/api/v1/control/projects', headers=ordinary, json=body).json()
    base = f"/api/v1/control/projects/{project['id']}"
    assert client.put(base + '/members', headers=ordinary,
                      json={'email': 'admin@test.example', 'role': 'editor'}).status_code == 200
    shared = client.get(base, headers=eligible).json()
    assert shared['brand_clarifications_enabled']
    shared['config']['brand_clarification'] = 'Clarification for ordinary owner'
    writable = {key: shared[key] for key in ('revision', 'name', 'brand_name', 'device_id', 'config', 'schedule', 'queries')}
    assert client.put(base, headers=eligible, json=writable).status_code == 200
    quote = client.get(base + '/quote', headers=eligible).json()
    assert quote['unit_kopeks'] == quote['total_kopeks'] == 200
    launched = client.post(base + '/runs', headers=eligible, json={'request_id': original_uuid().hex})
    assert launched.status_code == 201, launched.text
    with sessions() as db:
        run = db.get(ControlRun, launched.json()['id'])
        assert run.user_id == registered.json()['user']['id']
        assert json.loads(run.snapshot_json)['config']['brand_clarification'] == 'Clarification for ordinary owner'


@pytest.mark.parametrize(('operation', 'downgrade'), [('save', False), ('launch', True), ('command', True)])
def test_postgres_membership_change_serializes_editor_write(tmp_path, monkeypatch, postgres_url, operation, downgrade):
    client, owner, editor, owner_id, sessions = cloud_setup(
        tmp_path, monkeypatch, database_url=postgres_url)
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Shared', 'brand_name': 'Brand', 'queries': [{'text': 'question'}],
        'config': {'services': ['chatgpt']},
    }).json()
    base = f"/api/v1/control/projects/{project['id']}"
    assert client.put(base + '/members', headers=owner,
                      json={'email': 'other@test.example', 'role': 'editor'}).status_code == 200
    run_id = uuid.uuid4().hex
    with sessions() as db:
        editor_id = db.scalar(select(User.id).where(User.email == 'other@test.example'))
        if operation == 'command':
            db.add(ControlRun(id=run_id, user_id=owner_id, project_id=project['id'],
                              request_key='locked-command', snapshot_json=json.dumps(project), progress_json='{}'))
            db.commit()
    entered = threading.Event()
    app_engine = client.app.state.payment_sessions.kw['bind']

    def about_to_lock(connection, cursor, statement, parameters, context, executemany):
        if 'control_projects' in statement and 'FOR UPDATE' in statement:
            entered.set()

    def editor_write():
        if operation == 'save':
            writable = {key: project[key] for key in ('revision', 'name', 'brand_name', 'device_id', 'config', 'schedule', 'queries')}
            return client.put(base, headers=editor, json={**writable, 'name': 'Unauthorized change'})
        if operation == 'launch':
            return client.post(base + '/runs', headers=editor, json={'request_id': uuid.uuid4().hex})
        return client.post(f'/api/v1/control/runs/{run_id}/command', headers=editor, json={'action': 'stop'})

    with sessions() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.scalar(select(ControlProject).where(ControlProject.id == project['id']).with_for_update())
        member = blocker.get(ProjectMember, (project['id'], editor_id))
        if downgrade:
            member.role = 'viewer'
        else:
            blocker.delete(member)
        blocker.flush()
        event.listen(app_engine, 'before_cursor_execute', about_to_lock)
        future = pool.submit(editor_write)
        try:
            assert entered.wait(10), 'Editor write did not acquire the project mutex'
            assert not future.done(), 'Editor write bypassed the locked membership change'
            blocker.commit()
            response = future.result(timeout=15)
            assert response.status_code == 404, response.text
        finally:
            blocker.rollback()
            event.remove(app_engine, 'before_cursor_execute', about_to_lock)
    with sessions() as db:
        assert db.get(ControlProject, project['id']).name == 'Shared'
        assert list(db.scalars(select(Check.id))) == []
        runs = list(db.scalars(select(ControlRun)))
        assert len(runs) == (1 if operation == 'command' else 0)
        assert all(run.desired_state == 'running' and run.state == 'queued' for run in runs)
