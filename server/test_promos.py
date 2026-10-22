from server.test_accounts import register_account
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from server.checks import complete_check, reserve_checks
from server.models import Check, CloudResult, ControlRun, FreeScanBalance, LedgerEntry, PromoRedemption, User, Wallet
from server.promos import SERVICES
from server.test_cloud_scans import Collector, FakeAI, cloud_tick, postgres_url, project_and_run, setup


def create_code(client, admin, scans, code="WELCOME"):
    response = client.post('/api/v1/admin/promos', headers=admin, json={'code': code, 'scans': scans})
    assert response.status_code == 201, response.text
    return response.json()['code']


def redeem(client, headers, code="WELCOME"):
    return client.post('/api/v1/wallet/promo', headers=headers, json={'code': code})


def test_create_redeem_validation_and_access(tmp_path, monkeypatch):
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch)
    path = '/api/v1/admin/promos'
    body = {'code': 'WELCOME', 'scans': {'chatgpt': 3}}
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, headers=other, json=body).status_code == 403
    assert client.get(path, headers=other).status_code == 403
    device = client.post('/api/v1/control/agent/enroll', headers=admin,
                         json={'device_id': 'a' * 32, 'name': 'PC'}).json()
    device_headers = {'Authorization': 'Bearer ' + device['token']}
    assert client.post(path, headers=device_headers, json=body).status_code == 403
    assert redeem(client, device_headers).status_code == 403
    for scans in ({'chatgpt': -1}, {'chatgpt': 1.5}, {'chatgpt': True}, {'alice': 1}):
        assert client.post(path, headers=admin, json={**body, 'scans': scans}).status_code == 422
    counts = {s: i for i, s in enumerate(SERVICES)}
    create_code(client, admin, counts, ' welcome ')
    assert client.post(path, headers=admin, json=body).status_code == 409
    assert redeem(client, other, 'UNKNOWN').status_code == 404
    first = redeem(client, other, ' welcome ')
    assert first.status_code == 200 and first.json()['already_redeemed'] is False
    assert redeem(client, other).json()['already_redeemed'] is True
    wallet = client.get('/api/v1/wallet', headers=other).json()
    assert wallet['balance_kopeks'] == 0
    assert wallet['free_scans'] == {s: {'available': n, 'reserved': 0} for s, n in counts.items()}
    create_code(client, admin, {'chatgpt': 2}, 'SECOND')
    assert redeem(client, other, 'SECOND').status_code == 200
    assert client.get('/api/v1/wallet', headers=other).json()['free_scans']['chatgpt']['available'] == 2
    listing = client.get(path, headers=admin)
    assert listing.headers['cache-control'] == 'no-store'
    assert listing.json()['total'] == 2 and listing.json()['promos'][1]['redemptions'] == 1
    with sessions() as db:
        assert len(db.scalars(select(PromoRedemption)).all()) == 2


def test_registration_promo_is_atomic(tmp_path, monkeypatch):
    client, admin, _, _, sessions = setup(tmp_path, monkeypatch)
    create_code(client, admin, {'google_aio': 5})
    body = {'email': 'new@example.test', 'password': 'long-test-password-123', 'promo_code': 'UNKNOWN'}
    assert register_account(client, json=body).status_code == 404
    with sessions() as db:
        assert db.scalar(select(User).where(User.email == body['email'])) is None
    response = register_account(client, json={**body, 'promo_code': ' welcome '})
    assert response.status_code == 201, response.text
    headers = {'Authorization': 'Bearer ' + response.json()['token']}
    assert client.get('/api/v1/wallet', headers=headers).json()['free_scans']['google_aio']['available'] == 5
    assert register_account(client, json={**body, 'promo_code': 'WELCOME'}).status_code == 409
    assert redeem(client, headers).json()['already_redeemed'] is True


def test_reservations_refund_once_and_preserve_paid_price(tmp_path, monkeypatch):
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch)
    user_id = client.get('/api/v1/me', headers=other).json()['id']
    with sessions() as db:
        user = db.get(User, user_id)
        db.get(Wallet, user_id).balance_kopeks = 240
        db.commit()
        reserve_checks(db, user, ['paid'], 120, service='chatgpt')
    create_code(client, admin, {'chatgpt': 1})
    redeem(client, other)
    with sessions() as db:
        user = db.get(User, user_id)
        reserve_checks(db, user, ['paid'], 120, service='chatgpt')
        assert db.scalar(select(Check).where(Check.client_check_id == 'paid')).price_kopeks == 120
        reserve_checks(db, user, ['free'], 120, service='chatgpt')
        reserve_checks(db, user, ['free'], 120, service='chatgpt')
        assert db.get(FreeScanBalance, (user_id, 'chatgpt')).remaining == 0
    for _ in range(2):
        assert client.post('/api/v1/checks/release', headers=other, json={'check_ids': ['free']}).status_code == 200
    with sessions() as db:
        user = db.get(User, user_id)
        assert db.get(FreeScanBalance, (user_id, 'chatgpt')).remaining == 1
        reserve_checks(db, user, ['free'], 120, service='chatgpt')
        for _ in range(2):
            complete_check(db, user, 'free', 'error')
        assert db.get(FreeScanBalance, (user_id, 'chatgpt')).remaining == 1
        reserve_checks(db, user, ['free'], 120, service='chatgpt')
        for _ in range(2):
            complete_check(db, user, 'free', 'not_found')
        reserve_checks(db, user, ['fallback'], 120, service='chatgpt')
        complete_check(db, user, 'fallback', 'not_found')
        complete_check(db, user, 'paid', 'not_found')
        assert db.get(Wallet, user_id).balance_kopeks == 0
        assert db.get(FreeScanBalance, (user_id, 'chatgpt')).remaining == 0
        assert len(db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id)).all()) == 2
        with pytest.raises(HTTPException) as error:
            reserve_checks(db, user, ['empty'], 120, service='chatgpt')
        assert error.value.status_code == 402


def test_failed_mixed_reservation_and_unspecified_service_do_not_spend_quota(tmp_path, monkeypatch):
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch)
    user_id = client.get('/api/v1/me', headers=other).json()['id']
    create_code(client, admin, {'chatgpt': 1})
    redeem(client, other)
    with sessions() as db:
        for ids, service in ((['one', 'two'], 'chatgpt'), (['wrong'], 'gemini')):
            with pytest.raises(HTTPException) as error:
                reserve_checks(db, db.get(User, user_id), ids, 120, service=service)
            assert error.value.status_code == 402
        assert db.get(FreeScanBalance, (user_id, 'chatgpt')).remaining == 1
        assert not db.scalars(select(Check)).all()
    assert client.post('/api/v1/checks/reserve', headers=other, json={'check_ids': ['fake:chatgpt']}).status_code == 402


@pytest.mark.parametrize('service', SERVICES)
def test_matching_credit_covers_real_cloud_worker(tmp_path, monkeypatch, service):
    async def limits():
        return {s: 1 for s in SERVICES}
    monkeypatch.setattr('server.cloud_scans.account_limits', limits)
    monkeypatch.setenv('SCRAPELESS_API_KEY', 'fake-key')
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch, ai=FakeAI())
    create_code(client, admin, {service: 1})
    redeem(client, other)
    project, run = project_and_run(client, other, services=(service,), legacy=False)
    assert asyncio.run(cloud_tick(sessions, FakeAI(), 120, Collector))
    with sessions() as db:
        check = db.scalar(select(Check).where(Check.client_check_id.startswith(run['id'] + ':')))
        assert check.status == 'settled' and check.price_kopeks == 0 and check.free_scan_service == service
        assert db.get(Wallet, check.user_id).balance_kopeks == 0
        assert db.get(FreeScanBalance, (check.user_id, service)).remaining == 0


def test_stream_stop_settles_free_and_paid_and_refunds_unstarted(tmp_path, monkeypatch):
    monkeypatch.setenv('SCRAPELESS_API_KEY', 'fake-key')
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch)
    user_id = client.get('/api/v1/me', headers=other).json()['id']
    create_code(client, admin, {'google_aio': 2})
    redeem(client, other)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()
    _, run = project_and_run(client, other, legacy=False,
        queries=[{'text': f'q{i}'} for i in range(4)])

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
                assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=other,
                                   json={'action': 'stop'}).status_code == 200
                return {'shown': False}
            await asyncio.sleep(0)
            return dict(self.answer)

    assert asyncio.run(cloud_tick(sessions, None, 120, StopCollector,
                                 prefetch_limits={'google_aio': 3}))
    assert sorted(StopCollector.calls) == ['q0', 'q1', 'q2']
    with sessions() as db:
        assert db.get(ControlRun, run['id']).state == 'cancelled'
        assert len(db.scalars(select(CloudResult)).all()) == 3
        checks = db.scalars(select(Check)).all()
        assert sorted((c.status, c.price_kopeks) for c in checks) == [
            ('released', 0), ('settled', 0), ('settled', 165)]
        assert db.get(FreeScanBalance, (user_id, 'google_aio')).remaining == 1
        assert db.get(Wallet, user_id).balance_kopeks == 335
        assert len(db.scalars(select(LedgerEntry)).all()) == 1


def test_quote_free_reservation_cancel_and_stale_quote(tmp_path, monkeypatch):
    monkeypatch.setenv('SCRAPELESS_API_KEY', 'fake-key')
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch)
    create_code(client, admin, {'google_aio': 1, 'chatgpt': 1})
    redeem(client, other)
    body = {'name': 'Promo', 'brand_name': 'Brand', 'queries': [{'text': 'first'}, {'text': 'second'}],
            'config': {'services': ['google_aio', 'chatgpt']}}
    project = client.post('/api/v1/control/projects', headers=other, json=body).json()
    path = f"/api/v1/control/projects/{project['id']}"
    quote = client.get(path + '/quote', headers=other).json()
    assert quote['count'] == 4 and quote['free_count'] == 2 and quote['total_kopeks'] == 330
    launch_body = {'request_id': uuid4().hex, 'free_scans_state': quote['free_scans_state']}
    run = client.post(path + '/runs', headers=other, json=launch_body).json()
    assert client.post(path + '/runs', headers=other, json=launch_body).json()['id'] == run['id']
    wallet = client.get('/api/v1/wallet', headers=other).json()
    assert wallet['free_scans']['google_aio'] == {'available': 0, 'reserved': 1}
    second = client.post('/api/v1/control/projects', headers=other, json={**body, 'name': 'Second'}).json()
    assert client.post(f"/api/v1/control/projects/{second['id']}/runs", headers=other,
                       json={**launch_body, 'request_id': uuid4().hex}).status_code == 409
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=other, json={'action': 'stop'}).status_code == 200
    assert client.get('/api/v1/wallet', headers=other).json()['free_scans']['google_aio'] == {'available': 1, 'reserved': 0}


def test_recompute_remains_paid_with_credits(tmp_path, monkeypatch):
    from server.test_brand_recompute import FEATURE_USER, feature_setup
    from server.models import CloudResult, utcnow
    client, admin, sessions = feature_setup(tmp_path, monkeypatch, admin=True)
    create_code(client, admin, {'chatgpt': 10})
    redeem(client, admin)
    project = client.post('/api/v1/control/projects', headers=admin, json={
        'name': 'Refprom', 'brand_name': 'Refprom', 'queries': [{'text': 'question'}],
        'config': {'services': ['chatgpt'], 'brand_clarification': 'Reflo — не наш бренд'}}).json()
    today = utcnow().date().isoformat()
    with sessions() as db:
        db.get(User, FEATURE_USER).is_admin = False
        db.get(Wallet, FEATURE_USER).balance_kopeks = 0
        result = CloudResult(user_id=FEATURE_USER, project_id=project['id'],
            query_id=project['queries'][0]['id'], project_name='Refprom', brand_name='Refprom',
            query_text='question', group_tag='', service='chatgpt', scan_date=today, status='not_found',
            answer_text='Сохранённый ответ', sources_json='[]', mention_types_json='[]')
        db.add(result); db.commit()
        result_id = result.id
    path = f"/api/v1/control/projects/{project['id']}/recompute"
    assert client.get(path + '/quote', headers=admin, params={'from_date': today}).json()['total_kopeks'] == 80
    assert client.post(path + f'/{result_id}', headers=admin,
                       json={'from_date': today, 'revision': project['revision']}).status_code == 409
    with sessions() as db:
        db.get(Wallet, FEATURE_USER).balance_kopeks = 80; db.commit()
    assert client.post(path + f'/{result_id}', headers=admin,
                       json={'from_date': today, 'revision': project['revision']}).json()['charged_kopeks'] == 80
    assert client.get('/api/v1/wallet', headers=admin).json()['free_scans']['chatgpt']['available'] == 10


def test_postgres_concurrent_redemption_reserve_and_release(tmp_path, monkeypatch, postgres_url):
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch, database_url=postgres_url)
    user_id = client.get('/api/v1/me', headers=other).json()['id']
    create_code(client, admin, {'chatgpt': 1})
    barrier = Barrier(2)
    def activate(_):
        barrier.wait(timeout=10)
        return redeem(client, other).json()['already_redeemed']
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(activate, range(2))) == [False, True]
    barrier = Barrier(2)
    def reserve(index):
        with sessions() as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                reserve_checks(db, user, [f'parallel-{index}'], 120, service='chatgpt')
                return f'parallel-{index}'
            except HTTPException as exc:
                assert exc.status_code == 402
                return None
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert results.count(None) == 1
    key = next(r for r in results if r)
    barrier = Barrier(2)
    def release(_):
        with sessions() as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=10)
            return complete_check(db, user, key, 'error')
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(release, range(2))) == ['released', 'released']
    with sessions() as db:
        assert db.get(FreeScanBalance, (user_id, 'chatgpt')).remaining == 1
        assert len(db.scalars(select(PromoRedemption)).all()) == 1


def test_postgres_preloaded_check_refunds_only_once(tmp_path, monkeypatch, postgres_url):
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch, database_url=postgres_url)
    user_id = client.get('/api/v1/me', headers=other).json()['id']
    create_code(client, admin, {'chatgpt': 1})
    redeem(client, other)
    with sessions() as db:
        reserve_checks(db, db.get(User, user_id), ['preloaded'], 120, service='chatgpt')
    with sessions() as stale:
        user = stale.get(User, user_id)
        check = stale.scalar(select(Check).where(Check.user_id == user_id,
                                                Check.client_check_id == 'preloaded'))
        assert check.status == 'reserved'
        with sessions() as other_db:
            complete_check(other_db, other_db.get(User, user_id), 'preloaded', 'error')
        assert complete_check(stale, user, 'preloaded', 'skipped') == 'released'
    with sessions() as db:
        assert db.get(FreeScanBalance, (user_id, 'chatgpt')).remaining == 1


def test_additive_promo_migration_keeps_existing_check(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from server.migrate import ROOT, upgrade_database
    url = f"sqlite:///{tmp_path / 'previous.db'}"
    config = Config(str(ROOT / 'alembic.ini')); config.attributes['database_url'] = url
    command.upgrade(config, '20261012_news_provider_pauses')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO users(id,email,password_hash,is_admin,created_at) VALUES('old','old@test.example','hash',0,'2026-10-01')"))
        db.execute(text("INSERT INTO wallets(user_id,balance_kopeks) VALUES('old',12345)"))
        db.execute(text("INSERT INTO checks(user_id,client_check_id,price_kopeks,status,created_at) VALUES('old','paid',120,'reserved','2026-10-01')"))
    upgrade_database(url)
    upgrade_database(url)
    with engine.connect() as db:
        assert db.execute(text('SELECT price_kopeks,status,free_scan_service FROM checks')).one() == (120, 'reserved', None)
        assert db.execute(text('SELECT balance_kopeks FROM wallets')).scalar() == 12345
    engine.dispose()


def test_promo_conditions_validation_revision_expiry_and_existing_credits(tmp_path, monkeypatch):
    from datetime import timedelta
    from server.models import utcnow
    client, admin, other, _, sessions = setup(tmp_path, monkeypatch)
    path = '/api/v1/admin/promos'
    body = {'code':'CONTROL','scans':{'chatgpt':3},'max_redemptions':1,'expires_at':(utcnow()+timedelta(days=1)).isoformat()}
    for invalid in ({'max_redemptions':0}, {'max_redemptions':True}, {'is_active':1}, {'expires_at':'2026-10-14T12:00:00'}, {'unexpected':1}):
        assert client.post(path, headers=admin,json={**body,**invalid}).status_code == 422
    created = client.post(path,headers=admin,json=body).json()
    assert created['status'] == 'active'
    update_path = path+'/CONTROL'
    conditions = {'revision':created['revision'],'is_active':False,'max_redemptions':1,'expires_at':None}
    assert client.put(update_path,json=conditions).status_code == 401
    assert client.put(update_path,headers=other,json=conditions).status_code == 403
    device = client.post('/api/v1/control/agent/enroll',headers=admin,json={'device_id':'b'*32,'name':'Test'}).json()
    assert client.put(update_path,headers={'Authorization':'Bearer '+device['token']},json=conditions).status_code == 403
    assert redeem(client,other,'CONTROL').status_code == 200
    assert client.get(path,headers=admin).json()['promos'][0]['status'] == 'exhausted'
    disabled = client.put(update_path,headers=admin,json=conditions)
    assert disabled.status_code == 200 and disabled.json()['status'] == 'inactive'
    assert client.put(update_path,headers=admin,json=conditions).status_code == 409
    assert redeem(client,admin,'CONTROL').status_code == 422
    assert redeem(client,other,'CONTROL').json()['already_redeemed'] is True
    assert client.get('/api/v1/wallet',headers=other).json()['free_scans']['chatgpt']['available'] == 3
    body = {'revision':disabled.json()['revision'],'is_active':True,'max_redemptions':None,'expires_at':(utcnow()-timedelta(seconds=1)).isoformat()}
    expired = client.put(update_path,headers=admin,json=body).json()
    assert expired['status'] == 'expired'
    assert redeem(client,admin,'CONTROL').status_code == 422
    enabled = client.put(update_path,headers=admin,json={**body,'revision':expired['revision'],'expires_at':None})
    assert enabled.status_code == 200 and enabled.json()['status'] == 'active'
    assert redeem(client,admin,'CONTROL').status_code == 200
    assert client.put(update_path,headers=admin,json={**body,'revision':enabled.json()['revision'],'max_redemptions':1}).status_code == 422
    with sessions() as db:
        assert len(db.scalars(select(PromoRedemption)).all()) == 2


def test_postgres_global_promo_limit_serializes_different_accounts(tmp_path, monkeypatch, postgres_url):
    client, admin, other, _, sessions = setup(tmp_path,monkeypatch,database_url=postgres_url)
    response = client.post('/api/v1/admin/promos',headers=admin,json={'code':'LAST','scans':{'chatgpt':2},'max_redemptions':1})
    assert response.status_code == 201
    barrier = Barrier(2)
    def activate(headers):
        barrier.wait(timeout=10)
        return redeem(client,headers,'LAST').status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(activate,[admin,other])) == [200,422]
    with sessions() as db:
        assert len(db.scalars(select(PromoRedemption)).all()) == 1
        assert sum(db.scalars(select(FreeScanBalance.remaining)).all()) == 2


def test_postgres_password_setup_cannot_overwrite_another_setup(tmp_path,monkeypatch,postgres_url):
    client,_,other,_,sessions = setup(tmp_path,monkeypatch,database_url=postgres_url)
    user_id = client.get('/api/v1/me',headers=other).json()['id']
    with sessions() as db:
        db.get(User,user_id).password_hash = 'external:yandex'
        db.commit()
    barrier = Barrier(2)
    def save(index):
        barrier.wait(timeout=10)
        return client.put('/api/v1/auth/password',headers=other,json={'password':f'new-password-123-{index}'}).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(save,range(2))) == [200,401]


def test_account_promo_migration_preserves_old_accounts_codes_and_grants(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine,text
    from server.migrate import ROOT,upgrade_database
    url = f"sqlite:///{tmp_path / 'old-promos.db'}"
    config = Config(str(ROOT/'alembic.ini')); config.attributes['database_url'] = url
    command.upgrade(config,'20261014_promo_codes')
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO users(id,email,password_hash,is_admin,created_at) VALUES('old','old@test.example','external:yandex',1,'2026-10-01')"))
        db.execute(text("INSERT INTO wallets(user_id,balance_kopeks) VALUES('old',12345)"))
        db.execute(text("INSERT INTO promo_codes(code,scans_json,created_by,created_at) VALUES('OLD','{}','old','2026-10-01')"))
        db.execute(text("INSERT INTO promo_redemptions(user_id,code,created_at) VALUES('old','OLD','2026-10-01')"))
        db.execute(text("INSERT INTO free_scan_balances(user_id,service,remaining) VALUES('old','chatgpt',123)"))
    upgrade_database(url)
    with engine.connect() as db:
        assert db.execute(text('SELECT password_hash,is_admin FROM users')).one() == ('external:yandex',1)
        assert db.execute(text('SELECT balance_kopeks FROM wallets')).scalar() == 12345
        assert db.execute(text('SELECT remaining FROM free_scan_balances')).scalar() == 123
        assert db.execute(text('SELECT is_active,max_redemptions,expires_at,revision FROM promo_codes')).one() == (1,None,None,0)
        assert db.execute(text('SELECT COUNT(*) FROM promo_redemptions')).scalar() == 1
    engine.dispose()
