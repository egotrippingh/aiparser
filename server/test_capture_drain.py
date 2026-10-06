"""Cancellation drains reserved checks only within the existing device/lease boundary."""
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from server.app import create_app
from server.models import AgentDevice, ControlRun, Wallet, make_session_factory, utcnow
from server.test_app import FakeArbiterAI


def setup(tmp_path):
    url = f"sqlite:///{tmp_path / 'drain.db'}"
    ai = FakeArbiterAI()
    client = TestClient(create_app(database_url=url, ai_client=ai))
    owners, devices = [], []
    for i in range(2):
        user = client.post('/api/v1/auth/register', json={
            'email': f'owner{i}@test.example', 'password': 'long-test-password-123'}).json()
        owner = {'Authorization': 'Bearer ' + user['token']}
        owners.append(owner)
        devices.append({'Authorization': 'Bearer ' + client.post('/api/v1/control/agent/enroll',
            headers=owner, json={'device_id': str(i) * 32, 'name': 'PC'}).json()['token']})
    other_device = {'Authorization': 'Bearer ' + client.post('/api/v1/control/agent/enroll',
        headers=owners[0], json={'device_id': 'a' * 32, 'name': 'Other PC'}).json()['token']}
    _, sessions = make_session_factory(url)
    with sessions() as db:
        for wallet in db.scalars(select(Wallet)): wallet.balance_kopeks = 10000
        db.commit()
    project = client.post('/api/v1/control/projects', headers=owners[0], json={
        'name': 'Project', 'brand_name': 'Brand', 'device_id': '0' * 32,
        'queries': [{'text': 'first'}, {'text': 'second'}], 'config': {'services': ['chatgpt']}}).json()
    run = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owners[0],
                      json={'request_id': uuid.uuid4().hex}).json()
    job = client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run']
    keys = [f"{run['id']}:{q['id']}:chatgpt" for q in job['snapshot']['queries']]
    assert client.post('/api/v1/checks/reserve', headers=devices[0], json={'check_ids': [keys[0]]}).status_code == 200
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owners[0], json={'action': 'stop'}).status_code == 200
    return client, owners, devices, other_device, sessions, run['id'], keys, ai


def test_cancelled_live_reserved_and_settled_replay_is_idempotent(tmp_path):
    client, owners, devices, wrong, sessions, run_id, keys, ai = setup(tmp_path)
    body = {'system': 'Check the brand mention in the AI answer and return a JSON verdict.',
            'content': [{'type': 'text', 'text': 'Brand answer'}]}
    for endpoint in ('analyze', 'arbitrate'):
        path = f'/api/v1/checks/{keys[0]}/{endpoint}'
        assert client.post(path, headers=devices[1], json=body).status_code == 403
        assert client.post(path, headers=wrong, json=body).status_code == 403
        assert client.post(path, headers=owners[1], json=body).status_code == 404
        for _ in range(2): assert client.post(path, headers=devices[0], json=body).status_code == 200
    # Cancelled runs cannot create new reservations or analyze nonexistent checks.
    assert client.post('/api/v1/checks/reserve', headers=devices[0], json={'check_ids': [keys[1]]}).status_code == 409
    assert client.post(f'/api/v1/checks/{keys[1]}/analyze', headers=devices[0], json=body).status_code == 404
    for _ in range(2):
        assert client.post(f'/api/v1/checks/{keys[0]}/complete', headers=devices[0], json={'status': 'found'}).json()['status'] == 'settled'
    for endpoint in ('analyze', 'arbitrate'):
        assert client.post(f'/api/v1/checks/{keys[0]}/{endpoint}', headers=devices[0], json=body).status_code == 200
    assert ai.calls == 1 and ai.arbiter_calls == 1
    assert client.get('/api/v1/wallet', headers=owners[0]).json()['balance_kopeks'] == 9880
    with sessions() as db:
        run = db.get(ControlRun, run_id)
        run.state = 'paused'
        db.commit()
    assert client.post(f'/api/v1/checks/{keys[0]}/analyze', headers=devices[0], json=body).status_code == 200
    assert client.post(f'/api/v1/control/runs/{run_id}/command', headers=owners[0],
                       json={'action': 'resume'}).status_code == 200
    job = client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run']
    held = client.post(f'/api/v1/control/agent/runs/{run_id}', headers=devices[0], json={
        'lease_token': job['lease_token'], 'state': 'paused', 'progress': {'pending_analysis': 1},
        'error': 'Answers saved; resume analysis'})
    assert held.status_code == 200 and held.json()['desired_state'] == 'paused'
    assert client.post(f'/api/v1/control/runs/{run_id}/command', headers=owners[0],
                       json={'action': 'resume'}).status_code == 200
    assert client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run']['desired_state'] == 'running'


@pytest.mark.parametrize('boundary', ['terminal', 'expired', 'missing', 'revoked'])
def test_cancelled_drain_rejects_invalid_authorization(tmp_path, boundary):
    client, _, devices, _, sessions, run_id, keys, ai = setup(tmp_path)
    with sessions() as db:
        run = db.get(ControlRun, run_id)
        if boundary == 'terminal': run.state = 'cancelled'
        elif boundary == 'expired': run.lease_until = utcnow() - timedelta(seconds=1)
        elif boundary == 'missing': run.lease_until = None
        else: db.scalar(select(AgentDevice).where(AgentDevice.device_id == '0' * 32)).revoked = True
        db.commit()
    for endpoint in ('analyze', 'arbitrate'):
        response = client.post(f'/api/v1/checks/{keys[0]}/{endpoint}', headers=devices[0],
            json={'system': 'Check the brand mention in the AI answer and return a JSON verdict.',
                  'content': [{'type': 'text', 'text': 'answer'}]})
        assert response.status_code == (401 if boundary == 'revoked' else 409), response.text
    assert ai.calls == ai.arbiter_calls == 0
