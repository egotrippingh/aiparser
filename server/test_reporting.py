import io
import json
from datetime import datetime, timezone

from openpyxl import load_workbook
from server.test_control import setup
from server.models import CloudResult, ControlProject, make_session_factory


def seed_report(tmp_path):
    client, owner, other, devices, url = setup(tmp_path)
    project = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'geosoft-dent.ru', 'brand_name': 'ESTUS',
        'queries': [{'text': '=Original equipment?', 'group_tag': 'Brand'}, {'text': 'Dental tools'}, {'text': 'Not checked', 'group_tag': 'Brand'}],
        'config': {'services': ['google_aio', 'chatgpt'], 'brand_domains': ['www.geosoft-dent.ru']},
    }).json()
    _, sessions = make_session_factory(url)
    ids = []
    with sessions() as db:
        user_id = db.get(ControlProject, project['id']).user_id
        for i, (query, day, service, status, kinds) in enumerate([
            (0, '2026-09-01', 'google_aio', 'not_found', []),
            (0, '2026-09-01', 'google_aio', 'found', ['text']),  # retry replaces older result
            (1, '2026-09-01', 'google_aio', 'found', ['marketplace']),
            (0, '2026-09-01', 'chatgpt', 'error', []),
            (0, '2026-09-03', 'google_aio', 'not_found', []),
            (1, '2026-09-03', 'google_aio', 'skipped', []),
            (0, '2026-09-03', 'chatgpt', 'found', ['text']),
        ], 1):
            q = project['queries'][query]
            row = CloudResult(user_id=user_id, device_id='a'*32, local_result_id=i, local_project_id=1,
                project_name=project['name'], brand_name='ESTUS', query_text=q['text'], group_tag=q['group_tag'],
                query_id=q['id'], project_id=project['id'], service=service, scan_date=day, status=status,
                mention_types_json=json.dumps(kinds), sources_json=json.dumps(['https://geosoft-dent.ru/item', 'https://catalog.test/product', 'javascript:alert(1)']),
                evidence_quote='=Untrusted quote', answer_text='Original answer')
            db.add(row); db.flush(); ids.append(row.id)
        db.commit()
    return client, owner, other, devices, project, ids, url


def test_calendar_daily_dedup_filters_and_comparison(tmp_path):
    client, owner, other, devices, project, ids, _ = seed_report(tmp_path)
    base = f"/api/v1/control/projects/{project['id']}/mentions"
    args = {'date_from':'2026-09-01','date_to':'2026-09-03'}
    res = client.get(base, headers=owner, params=args)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data['summary'] == {'found':3,'checked':4,'issues':1,'skipped':1,'visibility_pct':75.0}
    assert data['timeline'][1]['visibility_pct'] is None
    assert data['rows'][0]['cells']['2026-09-01']['google_aio']['id'] == ids[1]
    assert data['rows'][2]['cells'] == {}
    assert data['comparison']['delta'] == -50
    filtered = client.get(base, headers=owner, params={**args,'include_cards':'false','group':''}).json()
    assert filtered['summary']['found'] == 0 and filtered['summary']['checked'] == 1
    assert filtered['total'] == 1
    assert filtered['rows'][0]['cells']['2026-09-01']['google_aio']['found'] is False
    filtered = client.get(base, headers=owner, params={**args,'service':'chatgpt','search':'Original'}).json()
    assert filtered['summary']['checked'] == 1 and filtered['summary']['issues'] == 1
    assert filtered['services'] == ['chatgpt']
    page = client.get(base, headers=owner, params={**args,'limit':1,'offset':1,'date_limit':1,'date_offset':1}).json()
    assert page['total'] == 3 and len(page['rows']) == 1
    assert page['visible_dates'] == ['2026-09-01']
    assert page['summary'] == data['summary']
    comparison = client.get(base, headers=owner, params={**args,'compare':'true','date_to':'2026-09-02'}).json()
    assert comparison['visible_dates'] == ['2026-09-01','2026-09-02']
    assert comparison['comparison']['delta'] is None
    assert comparison['comparison']['to']['checked'] == 0
    for params in ({'date_from':'2026-09-04','date_to':'2026-09-01'}, {'date_from':'2020-01-01','date_to':'2026-01-01'}, {'service':'invalid'}):
        assert client.get(base, headers=owner, params=params).status_code == 422
    assert client.get(base, headers=other).status_code == 404
    assert client.get(base, headers=devices[0]).status_code == 403
    detail = client.get(f'{base}/results/{ids[1]}', headers=owner).json()
    assert detail['answer_text'] == 'Original answer'
    assert client.get(f'{base}/results/{ids[1]}', headers=other).status_code == 404
    assert client.get(f'{base}/export/mentions', headers=other).status_code == 404


def test_exports_use_all_filtered_rows_and_safe_text(tmp_path):
    client, owner, _, _, project, _, _ = seed_report(tmp_path)
    base = f"/api/v1/control/projects/{project['id']}/mentions/export"
    args = {'date_from':'2026-09-01','date_to':'2026-09-03','offset':1,'limit':1,'include_cards':'false'}
    res = client.get(base+'/mentions', headers=owner, params=args)
    assert res.status_code == 200, res.text
    wb = load_workbook(io.BytesIO(res.content))
    ws = wb['Упоминаемость']
    assert ws.max_row == 4 and ws.max_column == 6
    assert ws['A2'].value == '=Original equipment?' and ws['A2'].data_type == 's'
    assert ws['C3'].value == 'Карточки исключены'
    assert ws['C4'].value == 'Не проверялось'
    res = client.get(base+'/sources', headers=owner, params={**args, 'group':'Brand'})
    assert res.status_code == 200, res.text
    wb = load_workbook(io.BytesIO(res.content))
    rows = list(wb['Внешние источники'].values)[1:]
    assert rows and all(row[1] == 'catalog.test' for row in rows)
    assert all(row[5] == 'Brand' for row in rows)
    assert wb['Внешние источники']['G2'].data_type == 's'

def test_multiple_systems_filter_statistics_matrix_and_exports(tmp_path):
    client, owner, _, _, project, _, url = seed_report(tmp_path)
    _, sessions = make_session_factory(url)
    with sessions() as db:
        p = db.get(ControlProject, project['id'])
        config = json.loads(p.config_json)
        config['services'] = ['google_aio', 'chatgpt', 'perplexity', 'alice']
        p.config_json = json.dumps(config)
        for i, service in enumerate(['perplexity', 'alice'], 20):
            q = project['queries'][0]
            db.add(CloudResult(user_id=p.user_id, device_id='a'*32, local_result_id=i, local_project_id=1,
                project_id=p.id, query_id=q['id'], project_name=p.name, brand_name=p.brand_name,
                query_text=q['text'], group_tag='Brand', service=service,
                scan_date='2026-09-02' if service == 'perplexity' else '2026-09-01', status='found',
                sources_json='["https://external.test/page"]'))
        db.commit()
    base = f"/api/v1/control/projects/{project['id']}/mentions"
    args = {'date_from': '2026-09-01', 'date_to': '2026-09-03', 'services': 'google_aio,chatgpt,alice'}
    res = client.get(base, headers=owner, params=args)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data['services'] == ['google_aio', 'chatgpt', 'alice']
    assert data['available_services'] == ['google_aio', 'chatgpt', 'perplexity', 'alice']
    assert data['summary']['checked'] == 5 and data['summary']['found'] == 4
    assert data['summary']['visibility_pct'] == 80
    assert data['dates'] == ['2026-09-01', '2026-09-02', '2026-09-03']
    assert data['timeline'][1]['visibility_pct'] is None
    assert all('perplexity' not in day['services'] for day in data['timeline'])
    assert all('perplexity' not in cells for q in data['rows'] for cells in q['cells'].values())
    compared = client.get(base, headers=owner, params={**args, 'compare':'true'}).json()
    assert compared['comparison']['from']['checked'] == 3
    assert compared['comparison']['delta'] == -50
    for kind in ('mentions', 'sources'):
        res = client.get(base+'/export/'+kind, headers=owner, params=args)
        assert res.status_code == 200, res.text
        wb = load_workbook(io.BytesIO(res.content))
        assert not any('Perplexity' in str(cell) for ws in wb for row in ws.values for cell in row)
        assert any('Алиса AI' in str(cell) for ws in wb for row in ws.values for cell in row)
        if kind == 'mentions':
            assert any(str(cell).startswith('2026-09-02') for cell in next(wb['Упоминаемость'].values))
    for selected in ('', 'invalid', 'google_aio,unknown', 'google_aio,'):
        assert client.get(base, headers=owner, params={**args,'services':selected}).status_code == 422
    assert client.get(base, headers=owner, params={**args,'service':'chatgpt'}).status_code == 422
    single = client.get(base, headers=owner, params={**args,'services':'alice,alice'}).json()
    assert single['services'] == ['alice'] and single['summary']['checked'] == 1


def test_filtered_service_keeps_empty_selected_date_and_export_label(tmp_path):
    client, owner, _, _, project, _, _ = seed_report(tmp_path)
    base = f"/api/v1/control/projects/{project['id']}/mentions"
    args = {'date_from': '2026-09-02', 'date_to': '2026-09-02', 'services': 'chatgpt'}
    data = client.get(base, headers=owner, params=args).json()
    assert data['dates'] == data['visible_dates'] == ['2026-09-02']
    assert data['services'] == ['chatgpt'] and data['summary']['checked'] == 0
    assert all(row['cells'] == {} for row in data['rows'])
    wb = load_workbook(io.BytesIO(client.get(base + '/export/mentions', headers=owner, params=args).content))
    assert wb['Упоминаемость']['C2'].value == 'Не проверялось'


def test_report_default_period_ends_today(tmp_path, monkeypatch):
    from server import reporting
    monkeypatch.setattr(reporting, 'utcnow', lambda: datetime(2026, 10, 2, 21, 30, tzinfo=timezone.utc))
    client, owner, _, _, project, _, _ = seed_report(tmp_path)
    data = client.get(f"/api/v1/control/projects/{project['id']}/mentions", headers=owner).json()
    assert data['date_to'] == '2026-10-02'
