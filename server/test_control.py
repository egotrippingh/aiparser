import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from server.app import create_app
from server.control import schedule_tick
from server.models import ControlRun, make_session_factory


def setup(tmp_path):
    url = f"sqlite:///{tmp_path / 'control.db'}"
    client = TestClient(create_app(database_url=url))
    def register(email):
        res = client.post('/api/v1/auth/register', json={'email': email, 'password': 'long-test-password-123'})
        assert res.status_code == 201, res.text
        return {'Authorization': 'Bearer '+res.json()['token']}
    owner, other = register('owner@test.example'), register('other@test.example')
    devices = []
    for char in ('a', 'b'):
        res = client.post('/api/v1/control/agent/enroll', headers=owner, json={'device_id': char*32, 'name': 'PC '+char})
        assert res.status_code == 200, res.text
        devices.append({'Authorization': 'Bearer '+res.json()['token']})
    return client, owner, other, devices, url


def test_device_assignment_ownership_and_durable_queue(tmp_path):
    client, owner, other, devices, url = setup(tmp_path)
    body = {'name': 'Project', 'brand_name': 'Brand', 'device_id': 'a'*32,
            'queries': [{'text': 'where to buy Brand'}], 'config': {'services': ['chatgpt']}}
    res = client.post('/api/v1/control/projects', headers=owner, json=body)
    assert res.status_code == 201, res.text
    project = res.json()
    assert client.get('/api/v1/control/projects', headers=other).json() == []
    assert client.get('/api/v1/control/projects', headers=devices[0]).status_code == 403
    bad = {**body, 'device_id': 'c'*32}
    assert client.post('/api/v1/control/projects', headers=owner, json=bad).status_code == 422
    launch = {'request_id': uuid.uuid4().hex}
    res = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owner, json=launch)
    assert res.status_code == 201, res.text
    run = res.json()
    same = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owner, json=launch)
    assert same.json()['id'] == run['id']
    assert client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owner,
                       json={'request_id': uuid.uuid4().hex}).status_code == 409
    assert client.post('/api/v1/control/agent/poll', headers=devices[1], json={}).json()['run'] is None
    claimed = client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run']
    assert claimed['id'] == run['id']
    assert client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run']['lease_token'] == claimed['lease_token']
    # Editing the project cannot alter an in-flight run's query snapshot.
    changed = {k: project[k] for k in ('revision','name','brand_name','device_id','config','schedule','queries')}
    changed['queries'] = [{'text': 'different question'}]
    assert client.put(f"/api/v1/control/projects/{project['id']}", headers=owner, json=changed).status_code == 200
    assert client.put(f"/api/v1/control/projects/{project['id']}", headers=owner, json=changed).status_code == 409
    again = client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run']
    assert again['snapshot']['queries'][0]['text'] == 'where to buy Brand'
    payload = {'lease_token': claimed['lease_token'], 'state': 'done', 'progress': {'done': 1}}
    assert client.post(f"/api/v1/control/agent/runs/{run['id']}", headers=devices[1], json=payload).status_code == 404
    assert client.post(f"/api/v1/control/agent/runs/{run['id']}", headers=devices[0], json=payload).status_code == 200
    assert client.get('/api/v1/control/runs', headers=owner).json()[0]['state'] == 'done'


def test_schedule_uses_selected_pc_timezone_and_deduplicates(tmp_path):
    client, owner, _, devices, url = setup(tmp_path)
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Scheduled', 'brand_name': 'Brand', 'device_id': 'a'*32,
        'queries': [{'text': 'question'}], 'schedule': {'enabled': True, 'device_id': 'b'*32,
            'month_days': [1, 15, 31], 'time': '12:30', 'timezone': 'Europe/Moscow'},
    }).json()
    _, sessions = make_session_factory(url)
    now = datetime.now(timezone.utc)
    year = now.year + 1
    before = datetime(year, 4, 15, 9, 29, tzinfo=timezone.utc)
    schedule_tick(sessions, before)
    assert client.get('/api/v1/control/runs', headers=owner).json() == []
    due = before + timedelta(minutes=1)
    schedule_tick(sessions, due); schedule_tick(sessions, due)
    with sessions() as db:
        rows = list(db.scalars(select(ControlRun)))
        assert len(rows) == 1
        assert rows[0].device_id == 'b'*32
        assert rows[0].project_id == project['id']
    assert client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run'] is None
    # Offline work expires once; repeated ticks do not resurrect the same slot.
    schedule_tick(sessions, due + timedelta(hours=25))
    with sessions() as db:
        assert list(db.scalars(select(ControlRun)))[0].state == 'missed'


def test_browser_device_login_one_use_and_revocation(tmp_path):
    client, owner, _, _, _ = setup(tmp_path)
    res = client.post('/api/v1/control/connect/start', json={'device_id': 'd'*32, 'name': 'New PC'})
    assert res.status_code == 200, res.text
    req = res.json(); exchange = {k: req[k] for k in ('id','secret')}
    assert client.post('/api/v1/control/connect/exchange', json=exchange).json()['pending']
    assert client.post(f"/api/v1/control/connect/{req['id']}/approve", headers=owner).status_code == 200
    token = client.post('/api/v1/control/connect/exchange', json=exchange).json()['token']
    assert client.post('/api/v1/control/connect/exchange', json=exchange).status_code == 410
    headers = {'Authorization': 'Bearer '+token}
    assert client.get('/api/v1/me', headers=headers).status_code == 200
    assert client.delete('/api/v1/control/devices/'+'d'*32, headers=owner).status_code == 200
    assert client.get('/api/v1/me', headers=headers).status_code == 401
    renewed = client.post('/api/v1/control/agent/enroll', headers=owner,
        json={'device_id': 'd'*32, 'name': 'New PC'}).json()['token']
    assert client.get('/api/v1/me', headers=headers).status_code == 401
    fresh = {'Authorization': 'Bearer '+renewed}
    assert client.patch('/api/v1/control/devices/'+'d'*32, headers=owner,
        json={'device_id':'d'*32,'name':'Москва — рабочий ПК'}).status_code == 200
    assert client.post('/api/v1/control/agent/poll', headers=fresh, json={}).json()['name'] == 'Москва — рабочий ПК'
    assert client.post('/api/v1/auth/logout', headers=fresh).status_code == 200
    assert client.get('/api/v1/me', headers=fresh).status_code == 401


def test_website_to_desktop_and_shared_report(tmp_path, monkeypatch):
    import asyncio
    import json
    import threading
    from app import config, control_agent, agent
    from app.db import repo
    from server.models import User
    client, owner, other, devices, url = setup(tmp_path)
    user_id = client.get('/api/v1/me', headers=owner).json()['id']
    _, sessions = make_session_factory(url)
    with sessions() as db:
        db.get(User, user_id).is_admin = True
        db.commit()
    monkeypatch.setattr(config, 'DB_PATH', tmp_path / 'desktop.db')
    monkeypatch.setattr(repo, '_local', threading.local())
    repo.init_db()
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name':'geosoft-dent.ru', 'brand_name':'ESTUS', 'device_id':'a'*32,
        'queries':[{'text':'Где купить ESTUS?', 'group_tag':'Общие'}],
        'config':{'services':['google_aio'],'browser_mode':'headless'},
    }).json()
    run = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owner,
        json={'request_id':uuid.uuid4().hex}).json()
    assert client.post('/api/v1/control/agent/poll',headers=devices[0],
        json={'capabilities':{'installed':False}}).json()['run'] is None
    job = client.post('/api/v1/control/agent/poll',headers=devices[0],json={}).json()['run']
    local_id, managed = control_agent.materialize({**job,'created_at':'2026-09-26T23:00:00+00:00'}, user_id)
    assert managed['date'] == '2026-09-27'
    assert repo.get_project(local_id)['deep_check_depth'] == 0
    qid = repo.list_queries(local_id, only_active=True)[0]['id']
    query_id = managed['query_map'][str(qid)]
    check_id = f"{run['id']}:{query_id}:google_aio"
    assert client.post('/api/v1/checks/reserve',headers=devices[1],json={'check_ids':[check_id]}).status_code == 403
    assert client.post('/api/v1/checks/reserve',headers=devices[0],json={'check_ids':['arbitrary']}).status_code == 403
    res = client.post('/api/v1/checks/reserve',headers=devices[0],json={'check_ids':[check_id]})
    assert res.status_code == 200, res.text
    assert res.json()['price_kopeks'] == 0
    assert client.post(f'/api/v1/checks/{check_id}/complete',headers=devices[1],json={'status':'found'}).status_code == 403
    assert client.post(f'/api/v1/checks/{check_id}/complete',headers=devices[0],json={'status':'found'}).status_code == 200
    scan_id = repo.create_scan(local_id, ['google_aio'], {
        'billing_run_id':run['id'],'billing_user_id':user_id,'cloud_job_id':run['id'],
        'cloud_project_id':project['id'],'cloud_query_map':managed['query_map'],'cloud_queries':managed['queries']})
    repo.save_result(scan_id,qid,'google_aio','found',answer_text='ESTUS',mention_types=['text'])
    row = repo.cloud_results_after(0)[0]
    row['query_text'] = 'later edited text'
    payload = agent._payload(row)
    assert payload['query_text'] == 'Где купить ESTUS?'
    res = client.post('/api/v1/agent/results',headers=devices[0],json={'device_id':'a'*32,'results':[payload]})
    assert res.status_code == 200, res.text
    report = client.get('/api/v1/reports',headers=owner,params={'project':project['id']})
    assert report.status_code == 200, report.text
    assert report.json()['results'][0]['query_text'] == 'Где купить ESTUS?'
    assert client.get('/api/v1/reports',headers=other,params={'project':project['id']}).json()['results'] == []
    # A stopped assignment cannot reserve further checks, even with a valid token.
    client.post(f"/api/v1/control/runs/{run['id']}/command",headers=owner,json={'action':'stop'})
    assert client.post('/api/v1/checks/reserve',headers=devices[0],json={'check_ids':[check_id]}).status_code == 409
    repo.conn().close()
