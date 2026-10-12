import asyncio
import json

import httpx
from sqlalchemy import select

from server.admin import provider_balances
from server.models import Check, Wallet
from server.test_cloud_scans import setup


def test_all_users_wallets_and_admin_only(tmp_path, monkeypatch):
    client, admin, other, user_id, sessions = setup(tmp_path, monkeypatch)
    assert client.get('/api/v1/admin/users').status_code == 401
    assert client.get('/api/v1/admin/users', headers=other).status_code == 403
    assert client.get('/api/v1/admin/provider-balances', headers=other).status_code == 403
    device = client.post('/api/v1/control/agent/enroll', headers=admin,
        json={'device_id': 'a' * 32, 'name': 'PC'}).json()
    headers = {'Authorization': 'Bearer ' + device['token']}
    assert client.get('/api/v1/admin/users', headers=headers).status_code == 403
    assert client.get('/api/v1/admin/provider-balances', headers=headers).status_code == 403
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 12345
        db.add(Check(user_id=user_id, client_check_id='held-check', price_kopeks=120))
        db.add(Check(user_id=user_id, client_check_id='done-check', price_kopeks=120, status='settled'))
        db.commit()
    response = client.get('/api/v1/admin/users?limit=1', headers=admin)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['total'] == 2 and len(response.json()['users']) == 1
    page2 = client.get('/api/v1/admin/users?limit=1&offset=1', headers=admin).json()
    assert page2['users'][0]['id'] != response.json()['users'][0]['id']
    owner = client.get('/api/v1/admin/users?search=owner', headers=admin).json()['users'][0]
    assert owner['wallet'] == {'balance_kopeks': 12345, 'reserved_kopeks': 120, 'available_kopeks': 12225}
    assert client.get('/api/v1/admin/users?search=%25', headers=admin).json()['total'] == 0
    assert client.get('/api/v1/admin/users?limit=101', headers=admin).status_code == 422
    assert not {'password_hash', 'token', 'sessions'} & set(owner)


def balances(monkeypatch, handler):
    monkeypatch.setenv('SCRAPELESS_API_KEY', 'SECRET_SCRAPELESS')
    monkeypatch.setenv('OPENROUTER_MANAGEMENT_KEY', 'SECRET_ROUTER')
    monkeypatch.setenv('AIPARSER_XMLRIVER_USER', 'SECRET_USER')
    monkeypatch.setenv('AIPARSER_XMLRIVER_KEY', 'SECRET_XML')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await provider_balances(client)
    return asyncio.run(scenario())


def test_real_balance_contracts_and_separate_subscription(monkeypatch, caplog):
    def handler(request):
        if request.url.host == 'openrouter.ai':
            assert request.headers['Authorization'] == 'Bearer SECRET_ROUTER'
            return httpx.Response(200, json={'data': {'total_credits': 15, 'total_usage': 2.005}})
        if request.url.host == 'api.scrapeless.com':
            assert request.headers['x-api-token'] == 'SECRET_SCRAPELESS'
            return httpx.Response(200, json={'credits': '10', 'excessCredits': '0',
                'plan': {'credits': '3.705', 'usage': 7410, 'endAt': '2026-10-19T03:31:12Z'}})
        assert request.url.params['key'] == 'SECRET_XML'
        return httpx.Response(200, text='256.724')
    rows = balances(monkeypatch, handler)
    assert [r['balance'] for r in rows] == ['12.995', '10', '256.724']
    assert rows[1]['details'][1]['amount'] == '3.705'
    assert rows[1]['currency'] == 'CREDITS'
    assert all(r['status'] == 'ok' for r in rows)
    assert 'SECRET_' not in json.dumps(rows) and 'SECRET_' not in caplog.text


def test_failure_does_not_become_zero_or_hide_siblings(monkeypatch):
    def handler(request):
        if request.url.host == 'openrouter.ai':
            return httpx.Response(403, text='SECRET_ROUTER')
        if request.url.host == 'api.scrapeless.com':
            raise httpx.ReadTimeout('SECRET_SCRAPELESS', request=request)
        return httpx.Response(200, text='0')
    rows = balances(monkeypatch, handler)
    assert [r['balance'] for r in rows] == [None, None, '0']
    assert 'management key' in rows[0]['message']
    assert 'SECRET_' not in json.dumps(rows)


def test_unconfigured_and_malformed_balances(monkeypatch):
    for key in ('OPENROUTER_MANAGEMENT_KEY', 'OPENROUTER_API_KEY', 'SCRAPELESS_API_KEY',
                'AIPARSER_XMLRIVER_USER', 'AIPARSER_XMLRIVER_KEY'):
        monkeypatch.delenv(key, raising=False)
    async def missing():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError()))) as client:
            return await provider_balances(client)
    rows = asyncio.run(missing())
    assert all(r['status'] == 'not_configured' and r['balance'] is None for r in rows)
    rows = balances(monkeypatch, lambda r: httpx.Response(200, text='NaN'))
    assert all(r['status'] == 'unavailable' and r['balance'] is None for r in rows)
