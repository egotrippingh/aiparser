import uuid
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from server.app import create_app
from server.control import schedule_tick
from server.models import AgentDevice, ControlRun, ControlProject, make_session_factory


@pytest.fixture(autouse=True)
def provider_key(monkeypatch):
    monkeypatch.setenv('SCRAPELESS_API_KEY', 'fake-key')


def seed_legacy_run(client, owner, project, request_id):
    """A frozen pre-migration agent run; new runs are deliberately server-only."""
    from server.scan_feedback import learning_context
    with client.app.state.payment_sessions() as db:
        source = db.get(ControlProject, project['id'])
        snapshot = json.loads(json.dumps(project))
        snapshot['cloud_services'] = []
        context = learning_context(source)
        if context:
            snapshot['feedback_enabled'] = True
            snapshot['scan_feedback_context'] = context
            snapshot['config']['brand_clarification'] = 'Учитывай размеченные владельцем примеры'
        row = ControlRun(id=uuid.uuid4().hex, user_id=source.user_id, project_id=source.id,
            device_id=source.device_id or db.scalar(select(AgentDevice.device_id).where(AgentDevice.user_id == source.user_id)),
            phase='agent', active_project_key=source.id,
            request_key=f"manual:{source.id}:{request_id}", snapshot_json=json.dumps(snapshot),
            progress_json='{}')
        db.add(row)
        db.commit()
        return row.id


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


def test_runs_keep_old_active_checks_outside_recent_history_limit(tmp_path):
    client, owner, other, devices, _ = setup(tmp_path)
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Project', 'brand_name': 'Brand', 'queries': [{'text': 'question'}],
        'config': {'services': ['chatgpt']},
    }).json()
    with client.app.state.payment_sessions() as db:
        source = db.get(ControlProject, project['id'])
        for index in range(103):
            db.add(ControlRun(id=f'{index:032x}', user_id=source.user_id, project_id=source.id,
                phase='cloud', state='paused' if index < 2 else 'done', desired_state='running',
                snapshot_json=json.dumps({**project, 'cloud_services': ['chatgpt']}),
                request_key=f'history-{index}', progress_json='{"cloud_done":1}',
                created_at=datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(minutes=index)))
        db.commit()
    route = '/api/v1/control/runs'
    rows = client.get(route, headers=owner).json()
    assert {row['id'] for row in rows if row['state'] == 'paused'} == {f'{index:032x}' for index in range(2)}
    assert len(rows) == 102 and len({row['id'] for row in rows}) == 102
    assert len([row for row in rows if row['state'] == 'done']) == 100
    assert all(row['progress']['done'] == 1 for row in rows)
    assert client.get(route, headers=other).json() == []
    assert client.get(route, headers=devices[0]).status_code == 403
    assert client.get(route).status_code == 401


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
    assert client.post('/api/v1/control/projects', headers=owner, json=bad).status_code == 201
    launch = {'request_id': uuid.uuid4().hex}
    seed_legacy_run(client, owner, project, launch['request_id'])
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


def test_yandex_run_uses_server_without_device_capability(tmp_path, monkeypatch):
    client, owner, _, devices, _ = setup(tmp_path)
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'SERP', 'brand_name': 'Brand', 'device_id': 'a'*32,
        'queries': [{'text': 'question'}], 'config': {'services': ['yandex_neuro']},
    }).json()
    endpoint = f"/api/v1/control/projects/{project['id']}/runs"
    assert client.post(endpoint, headers=owner, json={'request_id': uuid.uuid4().hex}).status_code == 422
    monkeypatch.setenv('AIPARSER_XMLRIVER_USER', 'test-user')
    monkeypatch.setenv('AIPARSER_XMLRIVER_KEY', 'test-key')
    run = client.post(endpoint, headers=owner, json={'request_id': uuid.uuid4().hex})
    assert run.status_code == 201, run.text
    assert run.json()['phase'] == 'cloud'
    assert run.json()['device_id'] is None
    assert client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run'] is None


def test_legacy_yandex_run_remains_agent_owned(tmp_path):
    import json
    client, owner, _, devices, url = setup(tmp_path)
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Legacy', 'brand_name': 'Brand', 'device_id': 'a'*32,
        'queries': [{'text': 'question'}], 'config': {'services': ['yandex_neuro']},
    }).json()
    _, sessions = make_session_factory(url)
    with sessions() as db:
        run = ControlRun(id=uuid.uuid4().hex, user_id=client.get('/api/v1/me', headers=owner).json()['id'],
            project_id=project['id'], device_id='a'*32, phase='agent', active_project_key=project['id'],
            request_key='legacy:' + uuid.uuid4().hex, snapshot_json=json.dumps(project),
            progress_json='{}')
        db.add(run)
        db.commit()
        run_id = run.id
    capabilities = {'capture_backends': {'yandex_neuro': 'xmlriver'},
                    'provider_configured': {'yandex_neuro': True}}
    job = client.post('/api/v1/control/agent/poll', headers=devices[0],
                      json={'capabilities': capabilities}).json()['run']
    assert job['id'] == run_id and job['snapshot']['config']['services'] == ['yandex_neuro']
    key = f"{run_id}:{project['queries'][0]['id']}:yandex_neuro"
    assert client.post('/api/v1/checks/reserve', headers=devices[0],
                       json={'check_ids': [key]}).status_code == 402


def test_schedule_runs_on_server_and_deduplicates(tmp_path):
    client, owner, _, devices, url = setup(tmp_path)
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Scheduled', 'brand_name': 'Brand', 'device_id': 'a'*32,
        'queries': [{'text': 'question'}], 'config': {'services': ['chatgpt']},
        'schedule': {'enabled': True, 'device_id': 'b'*32,
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
        assert rows[0].device_id is None and rows[0].phase == 'cloud'
        assert rows[0].project_id == project['id']
    assert client.post('/api/v1/control/agent/poll', headers=devices[0], json={}).json()['run'] is None
    # Server work is independent of PC presence and is not marked missed.
    schedule_tick(sessions, due + timedelta(hours=25))
    with sessions() as db:
        assert len(list(db.scalars(select(ControlRun)))) == 1
        assert list(db.scalars(select(ControlRun)))[0].state == 'queued'


@pytest.mark.parametrize('year,month,last,numbered', [
    (2028, 2, 29, []), (2029, 2, 28, [28]), (2028, 4, 30, []), (2028, 12, 31, []),
])
def test_last_day_schedule_uses_local_month_and_deduplicates(tmp_path, year, month, last, numbered):
    client, owner, _, _, url = setup(tmp_path)
    response = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Last day', 'brand_name': 'Brand', 'queries': [{'text': 'question'}],
        'config': {'services': ['chatgpt']},
        'schedule': {'enabled': True, 'month_days': numbered, 'last_day': True,
                     'time': '00:30', 'timezone': 'Asia/Vladivostok'},
    })
    assert response.status_code == 201, response.text
    project = response.json()
    assert project['schedule']['last_day'] is True
    _, sessions = make_session_factory(url)
    due = datetime(year, month, last - 1, 14, 30, tzinfo=timezone.utc)
    schedule_tick(sessions, due - timedelta(minutes=1))
    assert client.get('/api/v1/control/runs', headers=owner).json() == []
    # The first tick may occur the next local day/month; still execute the due slot.
    catch_up = due + timedelta(hours=23, minutes=45)
    schedule_tick(sessions, catch_up)
    with sessions() as db:
        rows = list(db.scalars(select(ControlRun)))
        assert len(rows) == 1
        assert rows[0].project_id == project['id']
        assert rows[0].scheduled_for.replace(tzinfo=timezone.utc) == due
        assert json.loads(rows[0].snapshot_json)['schedule']['last_day'] is True
        # Release the active-project lock so it cannot mask duplicate slot creation.
        rows[0].state, rows[0].active_project_key = 'done', None
        db.commit()
    schedule_tick(sessions, catch_up)
    schedule_tick(sessions, due + timedelta(hours=24))
    with sessions() as db:
        assert len(list(db.scalars(select(ControlRun)))) == 1


def test_schedule_choice_validation_and_legacy_effective_from(tmp_path):
    client, owner, _, _, url = setup(tmp_path)
    body = {'name': 'Legacy schedule', 'brand_name': 'Brand', 'config': {'services': ['chatgpt']},
            'schedule': {'enabled': True, 'month_days': [31]}}
    project = client.post('/api/v1/control/projects', headers=owner, json=body).json()
    _, sessions = make_session_factory(url)
    with sessions() as db:
        row = db.get(ControlProject, project['id'])
        schedule = json.loads(row.schedule_json)
        schedule.pop('last_day', None)
        schedule['effective_from'] = '2020-01-01T00:00:00+00:00'
        row.schedule_json = json.dumps(schedule)
        db.commit()
    body.update(revision=project['revision'], name='Renamed')
    assert client.put(f"/api/v1/control/projects/{project['id']}", headers=owner, json=body).status_code == 200
    with sessions() as db:
        schedule = json.loads(db.get(ControlProject, project['id']).schedule_json)
        assert schedule['effective_from'] == '2020-01-01T00:00:00+00:00'
        assert schedule['month_days'] == [31] and schedule['last_day'] is False
    for schedule in ({'enabled': True, 'month_days': []},
                     {'last_day': True, 'month_days': [0]},
                     {'last_day': True, 'month_days': [32]},
                     {'last_day': True, 'month_days': [1, 1]}):
        assert client.post('/api/v1/control/projects', headers=owner,
                           json={**body, 'schedule': schedule}).status_code == 422
    assert client.post('/api/v1/control/projects', headers=owner,
                       json={**body, 'schedule': {'enabled': False, 'month_days': []}}).status_code == 201


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
        'config':{'services':['chatgpt'],'browser_mode':'headless'},
    }).json()
    request_id = uuid.uuid4().hex
    seed_legacy_run(client, owner, project, request_id)
    run = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owner,
        json={'request_id':request_id}).json()
    assert client.post('/api/v1/control/agent/poll',headers=devices[0],
        json={'capabilities':{'installed':False}}).json()['run'] is None
    job = client.post('/api/v1/control/agent/poll',headers=devices[0],json={}).json()['run']
    local_id, managed = control_agent.materialize({**job,'created_at':'2026-09-26T23:00:00+00:00'}, user_id)
    assert managed['date'] == '2026-09-27'
    assert repo.get_project(local_id)['deep_check_depth'] == 0
    qid = repo.list_queries(local_id, only_active=True)[0]['id']
    query_id = managed['query_map'][str(qid)]
    check_id = f"{run['id']}:{query_id}:chatgpt"
    assert client.post('/api/v1/checks/reserve',headers=devices[1],json={'check_ids':[check_id]}).status_code == 403
    assert client.post('/api/v1/checks/reserve',headers=devices[0],json={'check_ids':['arbitrary']}).status_code == 403
    res = client.post('/api/v1/checks/reserve',headers=devices[0],json={'check_ids':[check_id]})
    assert res.status_code == 200, res.text
    assert res.json()['price_kopeks'] == 0
    assert client.post(f'/api/v1/checks/{check_id}/complete',headers=devices[1],json={'status':'found'}).status_code == 403
    assert client.post(f'/api/v1/checks/{check_id}/complete',headers=devices[0],json={'status':'found'}).status_code == 200
    scan_id = repo.create_scan(local_id, ['chatgpt'], {
        'billing_run_id':run['id'],'billing_user_id':user_id,'cloud_job_id':run['id'],
        'cloud_project_id':project['id'],'cloud_query_map':managed['query_map'],'cloud_queries':managed['queries']})
    repo.save_result(scan_id,qid,'chatgpt','found',answer_text='ESTUS',mention_types=['text'])
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
