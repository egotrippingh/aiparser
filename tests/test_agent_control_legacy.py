"""Manual compatibility check for the retired desktop agent."""
import uuid
from server.test_control import setup, seed_legacy_run
from server.models import make_session_factory

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
