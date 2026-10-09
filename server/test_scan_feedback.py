import json

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update

from server.models import Check, CloudResult, ControlProject, ControlRun, User, make_session_factory
from server.scan_feedback import KEY, analysis_content, learning_context
from server.test_reporting import seed_report


def test_feedback_ownership_validation_and_removal(tmp_path):
    client, owner, other, devices, project, ids, url = seed_report(tmp_path)
    base = f"/api/v1/control/projects/{project['id']}/mentions/results/{ids[1]}"
    assert client.put(base + '/feedback', headers=other, json={'label': 'false_positive'}).status_code == 404
    assert client.put(base + '/feedback', headers=devices[0], json={'label': 'false_positive'}).status_code == 403
    assert client.put(base + '/feedback', headers=owner, json={'label': 'missed'}).status_code == 422
    assert client.put(base + '/feedback', headers=owner, json={'label': 'false_positive', 'comment': 'x' * 401}).status_code == 422
    response = client.put(base + '/feedback', headers=owner, json={'label': 'false_positive', 'comment': 'Other company'})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['status'] == 'found'  # raw result is preserved
    assert client.get(base, headers=owner).json()['feedback']['comment'] == 'Other company'
    _, sessions = make_session_factory(url)
    with sessions() as db:
        row = db.get(ControlProject, project['id'])
        assert 'Other company' in learning_context(row)
        row.brand_name = 'Different Brand'
        db.commit()
        assert learning_context(row) == ''
    assert client.put(base + '/feedback', headers=owner, json={'label': None}).json()['feedback'] is None


def test_generic_design_roles_are_not_neighbours_expert_mentions():
    from app.detect.rules import evaluate
    # Representative anonymized answer: roles/services do not identify a company.
    answer = ('Кто участвует в реализации проекта: комплектатор интерьера, прораб, '
              'строительные бригады, производители мебели и менеджер проекта. '
              'Дизайнер оставляет за собой авторский надзор и контроль концепции. '
              'Партнёры отвечают за подбор и закупку, логистику и приёмку, организацию монтажа.')
    sources = ['https://interior.example/design/komplektator', 'https://school.example/media/design/contracts']
    for brand in ('Neighbours Expert', 'Neighbors Expert', 'Neighbors'):
        result = evaluate(answer, sources, brand, [], ['neighbors-expert.ru'])
        assert not result.found, result
        positive = evaluate(answer + ' Обратитесь в ' + brand + '.', sources, brand, [], ['neighbors-expert.ru'])
        assert positive.found and 'text' in positive.mention_types


def test_feedback_survives_editor_update_and_freezes_in_run(tmp_path):
    client, owner, _, devices, project, ids, url = seed_report(tmp_path)
    base = f"/api/v1/control/projects/{project['id']}"
    response = client.put(f'{base}/mentions/results/{ids[1]}/feedback', headers=owner,
                          json={'label': 'false_positive', 'comment': 'A generic word is not this brand'})
    assert response.status_code == 200
    current = client.get(base, headers=owner).json()
    assert KEY not in current['config']
    current['name'] = 'Renamed project'
    current['config']['services'] = ['chatgpt']
    body = {k: current[k] for k in ('revision', 'name', 'brand_name', 'device_id', 'config', 'queries', 'schedule')}
    assert client.put(base, headers=owner, json=body).status_code == 200
    _, sessions = make_session_factory(url)
    with sessions() as db:
        assert len(json.loads(db.get(ControlProject, project['id']).config_json)[KEY]) == 1
    launch = client.post(base + '/runs', headers=owner, json={'request_id': 'a' * 32, 'device_id': 'a' * 32})
    assert launch.status_code == 422
    heartbeat = {'capabilities': {'brand_clarification': True}, 'local_time_zone': 'Europe/Moscow'}
    res = client.post('/api/v1/control/agent/poll', headers=devices[0], json=heartbeat)
    assert res.status_code == 200, res.text
    launch = client.post(base + '/runs', headers=owner, json={'request_id': 'b' * 32, 'device_id': 'a' * 32})
    assert launch.status_code == 201, launch.text
    with sessions() as db:
        run = db.get(ControlRun, launch.json()['id'])
        snapshot = json.loads(run.snapshot_json)
        assert snapshot['feedback_enabled'] is True
        assert 'generic word' in snapshot['scan_feedback_context']
        assert len(snapshot['config']['brand_clarification']) <= 2000
        check = Check(user_id=run.user_id, client_check_id=f"{run.id}:{project['queries'][0]['id']}:chatgpt", price_kopeks=120)
        content = [{'type': 'text', 'text': 'New answer'}]
        enriched = analysis_content(db, check, content)
        assert 'generic word' in enriched[0]['text'] and enriched[1:] == content
        check.user_id = 'different-owner'
        assert analysis_content(db, check, content) == content
    assert client.put(f'{base}/mentions/results/{ids[1]}/feedback', headers=owner, json={'label': None}).status_code == 200
    with sessions() as db:
        assert 'generic word' in json.loads(db.get(ControlRun, launch.json()['id']).snapshot_json)['scan_feedback_context']
    res = client.post('/api/v1/control/agent/poll', headers=devices[0], json=heartbeat)
    assert res.status_code == 200, res.text
    assert res.json()['run']['id'] == launch.json()['id']


def test_admin_review_all_accounts_without_disclosing_credentials(tmp_path):
    client, owner, other, devices, project, ids, url = seed_report(tmp_path)
    route = '/api/v1/admin/scan-results'
    assert client.get(route).status_code == 401
    assert client.get(route, headers=owner).status_code == 403
    _, sessions = make_session_factory(url)
    with sessions() as db:
        admin = db.scalar(select(User).where(User.email == 'other@test.example'))
        admin.is_admin = True
        row = db.get(CloudResult, ids[1])
        row.check_id = 'same-client-id'
        db.add(Check(user_id=row.user_id, client_check_id=row.check_id, price_kopeks=0,
                     analysis_json='{"found": true, "reasoning": "Owner analysis"}', analysis_model='model'))
        db.add(Check(user_id=admin.id, client_check_id=row.check_id, price_kopeks=0,
                     analysis_json='{"reasoning": "Other account private reasoning"}'))
        db.commit()
    response = client.get(route, headers=other, params={'search': 'owner@test.example', 'status': 'found', 'limit': 1})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['total'] == 3 and len(response.json()['results']) == 1
    assert 'answer_text' not in response.json()['results'][0]
    assert client.get(route, headers=devices[0]).status_code == 403
    assert client.get(route + f'/{ids[1]}', headers=owner).status_code == 403
    detail = client.get(route + f'/{ids[1]}', headers=other).json()
    assert detail['answer_text'] == 'Original answer'
    assert detail['analysis']['reasoning'] == 'Owner analysis'
    assert 'private reasoning' not in json.dumps(detail)
    assert client.get(route, headers=other, params={'search': '%'}).json()['total'] == 0
    assert client.get(route, headers=other, params={'limit': 101}).status_code == 422
    assert client.get(route + '/999999', headers=other).status_code == 404


def test_learning_bounds_and_correct_label_does_not_force_analysis(tmp_path):
    client, owner, _, _, project, ids, url = seed_report(tmp_path)
    base = f"/api/v1/control/projects/{project['id']}/mentions/results/{ids[1]}/feedback"
    _, sessions = make_session_factory(url)
    with sessions() as db:
        db.get(CloudResult, ids[1]).answer_text = 'A' * 20000
        db.commit()
    assert client.put(base, headers=owner, json={'label': 'correct'}).status_code == 200
    with sessions() as db:
        assert learning_context(db.get(ControlProject, project['id'])) == ''
    assert client.put(base, headers=owner, json={'label': 'false_positive'}).status_code == 200
    with sessions() as db:
        row = db.get(ControlProject, project['id'])
        config = json.loads(row.config_json)
        example = config[KEY][0]
        assert len(example['answer']) == 1800
        config[KEY] = [{**example, 'result_id': i} for i in range(100, 120)]
        row.config_json = json.dumps(config)
        db.commit()
        assert len(json.loads(learning_context(row).split('\n', 1)[1])) == 6
    assert client.put(base, headers=owner, json={'label': 'false_positive'}).status_code == 422


def test_feedback_conflict_preserves_winning_write_and_rejects_stale_editor(tmp_path, monkeypatch):
    client, owner, _, _, project, ids, url = seed_report(tmp_path)
    base = f"/api/v1/control/projects/{project['id']}"
    stale = client.get(base, headers=owner).json()
    endpoint = f'{base}/mentions/results/{ids[1]}/feedback'
    execute = Session.execute
    interleaved = False
    def overlapping_write(self, statement, *args, **kwargs):
        nonlocal interleaved
        if isinstance(statement, Update) and statement.table.name == 'control_projects' and not interleaved:
            interleaved = True
            winner = client.put(endpoint, headers=owner, json={'label': 'correct', 'comment': 'Winning write'})
            assert winner.status_code == 200, winner.text
        return execute(self, statement, *args, **kwargs)
    monkeypatch.setattr(Session, 'execute', overlapping_write)
    assert client.put(endpoint, headers=owner, json={'label': 'false_positive'}).status_code == 409
    assert client.get(endpoint.removesuffix('/feedback'), headers=owner).json()['feedback']['comment'] == 'Winning write'
    body = {k: stale[k] for k in ('revision', 'name', 'brand_name', 'device_id', 'config', 'queries', 'schedule')}
    assert client.put(base, headers=owner, json=body).status_code == 409


def test_managed_endpoints_use_frozen_examples_and_admin_screenshot_owner(tmp_path, monkeypatch):
    from server.ai import AIResult
    from server.app import create_app
    from server.models import Screenshot
    class AI:
        model = 'test-primary'
        arbiter_model = 'test-arbiter'
        def __init__(self):
            self.contents = []
        def analyze(self, system, content):
            self.contents.append(content)
            return AIResult('{"found": true, "reasoning": "Test"}', self.model, {})
        def arbitrate(self, system, content):
            self.contents.append(content)
            return AIResult('{"found": false, "reasoning": "Test"}', self.arbiter_model, {})
    class Storage:
        def download_url(self, key):
            return 'https://storage.test/' + key
    ai = AI()
    monkeypatch.setattr('server.test_control.create_app', lambda **kw: create_app(**kw, ai_client=ai, screenshot_storage=Storage()))
    client, owner, other, devices, project, ids, url = seed_report(tmp_path)
    _, sessions = make_session_factory(url)
    with sessions() as db:
        db.scalar(select(User).where(User.email == 'owner@test.example')).is_admin = True
        db.commit()
    base = f"/api/v1/control/projects/{project['id']}"
    current = client.get(base, headers=owner).json()
    current['config']['services'] = ['chatgpt']
    body = {k: current[k] for k in ('revision', 'name', 'brand_name', 'device_id', 'config', 'queries', 'schedule')}
    assert client.put(base, headers=owner, json=body).status_code == 200
    feedback = f'{base}/mentions/results/{ids[1]}/feedback'
    assert client.put(feedback, headers=owner, json={'label': 'false_positive', 'comment': 'Not the same brand'}).status_code == 200
    client.post('/api/v1/control/agent/poll', headers=devices[0], json={'capabilities': {'brand_clarification': True}})
    launched = client.post(base + '/runs', headers=owner, json={'request_id': 'c' * 32, 'device_id': 'a' * 32})
    assert launched.status_code == 201, launched.text
    run = client.post('/api/v1/control/agent/poll', headers=devices[0], json={'capabilities': {'brand_clarification': True}}).json()['run']
    check_id = f"{run['id']}:{project['queries'][0]['id']}:chatgpt"
    assert client.post('/api/v1/checks/reserve', headers=devices[0], json={'check_ids': [check_id]}).status_code == 200
    assert client.put(feedback, headers=owner, json={'label': None}).status_code == 200
    body = {'system': 'Untrusted client prompt; server chooses its own system instructions.',
            'content': [{'type': 'text', 'text': 'New answer'}]}
    for stage in ('analyze', 'arbitrate'):
        endpoint = f'/api/v1/checks/{check_id}/{stage}'
        assert client.post(endpoint, headers=devices[1], json=body).status_code == 403
        assert client.post(endpoint, headers=other, json=body).status_code == 404
        response = client.post(endpoint, headers=devices[0], json=body)
        assert response.status_code == 200, response.text
        assert 'Not the same brand' in ai.contents[-1][0]['text']
        assert ai.contents[-1][1:] == body['content']
    with sessions() as db:
        result = db.get(CloudResult, ids[1])
        result.check_id = check_id
        check = db.scalar(select(Check).where(Check.user_id == result.user_id, Check.client_check_id == check_id))
        check_pk = check.id
        db.add(Screenshot(check_id=check.id, object_key='owner-shot', size_bytes=10))
        outsider = db.scalar(select(User).where(User.email == 'other@test.example'))
        db.add(Check(user_id=outsider.id, client_check_id=check_id, price_kopeks=0))
        db.flush()
        foreign = db.scalar(select(Check).where(Check.user_id == outsider.id, Check.client_check_id == check_id))
        db.add(Screenshot(check_id=foreign.id, object_key='foreign-shot', size_bytes=10))
        db.commit()
    shot = f'/api/v1/admin/scan-results/{ids[1]}/screenshot'
    assert client.get(shot, headers=other).status_code == 403
    assert client.get(shot, headers=devices[0]).status_code == 403
    response = client.get(shot, headers=owner)
    assert response.status_code == 200 and response.json()['url'] == 'https://storage.test/owner-shot'
    assert response.headers['cache-control'] == 'no-store'
    with sessions() as db:
        from datetime import timedelta
        from server.models import utcnow
        db.get(Screenshot, check_pk).created_at = utcnow() - timedelta(days=91)
        db.commit()
    assert client.get(shot, headers=owner).status_code == 404
