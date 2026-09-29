from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from server.app import create_app
from server.models import CloudResult, make_session_factory
from server.test_agent_dashboard import _register


def test_error_upload_and_null_only_owned_enrichment(tmp_path):
    url = f"sqlite:///{tmp_path / 'diagnostics.db'}"
    client = TestClient(create_app(database_url=url))
    owner, user_id = _register(client, "diagnostic@example.test")
    other, _ = _register(client, "foreign@example.test")
    device = "a" * 32
    for headers in (owner, other):
        assert client.post('/api/v1/agent/heartbeat', headers=headers, json={
            'device_id': device, 'name': 'QA', 'local_time_zone': 'UTC', 'active_scan': False}).status_code == 200
    row = dict(local_result_id=1, local_project_id=1, project_name='QA', brand_name='Brand',
               query_text='Query', service='perplexity', scan_date=date.today().isoformat(), status='error',
               answer_text=None, sources=[])
    def upload(value, headers=owner, device_id=device):
        return client.post('/api/v1/agent/results', headers=headers, json={'device_id': device_id, 'results': [value]})
    assert upload(row).json()['diagnostics_version'] == 1
    _, sessions = make_session_factory(url)
    def saved():
        with sessions() as db:
            r = db.scalar(select(CloudResult).where(CloudResult.user_id == user_id))
            return r.error_message, r.status, r.answer_text, r.sources_json, r.check_id
    assert saved()[0] is None
    for field, value in [('local_project_id', 2), ('query_text', 'Other'), ('scan_date', '2026-01-01'),
                         ('status', 'captcha'), ('service', 'chatgpt'), ('project_id', 'b'*32),
                         ('query_id', 'c'*32), ('run_id', 'd'*32)]:
        assert upload({**row, field: value, 'error_message': 'mismatch'}).status_code == 200
        assert saved()[0] is None
    assert upload({**row, 'error_message': 'foreign'}, other).status_code == 200
    assert saved()[0] is None
    assert upload({**row, 'error_message': 'reason', 'answer_text': 'must not overwrite',
                   'sources': ['https://example.test']}).status_code == 200
    assert saved() == ('reason', 'error', None, '[]', None)
    assert upload({**row, 'error_message': 'second'}).status_code == 200
    assert saved()[0] == 'reason'
    assert upload({**row, 'local_result_id': 2, 'error_message': 'x'*1001}).status_code == 422
    assert upload({**row, 'status': 'found', 'error_message': 'bypass'}).status_code == 422
    assert upload(row, device_id='b'*32).status_code == 409


def test_legacy_import_and_linked_insert_keep_null_payload_backfill(tmp_path):
    from server.test_control import setup
    client, owner, _, devices, url = setup(tmp_path)
    user_id = client.get('/api/v1/me', headers=owner).json()['id']
    row = dict(local_result_id=1, local_project_id=1, project_name='QA', brand_name='Brand',
               query_text='Query', service='perplexity', scan_date=date.today().isoformat(), status='error')
    def upload(value):
        res = client.post('/api/v1/agent/results', headers=devices[0], json={'device_id':'a'*32,'results':[value]})
        assert res.status_code == 200, res.text
    upload(row)
    project = client.post('/api/v1/control/agent/import', headers=devices[0], json={
        'local_project_id':1, 'project':{'name':'QA','brand_name':'Brand','queries':[{'text':'Query'}],
        'config':{'services':['perplexity']}}})
    assert project.status_code == 200, project.text
    project_id = project.json()['id']
    upload({**row,'error_message':'old imported reason'})
    upload({**row,'local_result_id':2})
    upload({**row,'local_result_id':2,'error_message':'linked insert reason'})
    _, sessions = make_session_factory(url)
    with sessions() as db:
        rows = db.scalars(select(CloudResult).where(CloudResult.user_id==user_id).order_by(CloudResult.local_result_id)).all()
        assert [r.project_id for r in rows] == [project_id,project_id]
        assert [r.error_message for r in rows] == ['old imported reason','linked insert reason']
    data=client.get('/api/v1/reports',headers=owner,params={'project':'a'*32+':1'}).json()
    assert data['results'][0]['error_message']


def test_additive_migration_preserves_existing_results(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from server.migrate import ROOT, upgrade_database

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    config = Config(str(ROOT / 'alembic.ini'))
    config.attributes['database_url'] = url
    command.upgrade(config, '20260927_browser_login')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO users (id,email,password_hash,created_at,is_admin) VALUES ('owner','qa@example.test','hash','2026-09-01',0)"))
        db.execute(text("INSERT INTO cloud_results (user_id,device_id,local_result_id,local_project_id,project_name,brand_name,query_text,service,scan_date,status,mention_types_json,answer_text,sources_json,created_at) VALUES ('owner','desktop',1,1,'QA','Brand','Query','perplexity','2026-09-01','error','[]','keep','[]','2026-09-01')"))
    upgrade_database(url)
    with engine.connect() as db:
        assert db.execute(text('SELECT answer_text,status,error_message FROM cloud_results')).one() == ('keep', 'error', None)
    engine.dispose()
