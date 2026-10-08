"""Disposable Windows Edge check for the two cost confirmation cards.

Run from repo root: .venv/Scripts/python.exe scripts/cost_popover_probe.py
"""
import asyncio
import json
import os
import sys
import tempfile
import threading
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from fastapi.testclient import TestClient
from playwright.async_api import async_playwright

from server.app import create_app
from server.models import CloudResult, User, Wallet, make_session_factory

for key in ('DATABASE_URL', 'OPENROUTER_API_KEY', 'COINSO_SECRET_KEY', 'S3_SECRET_ACCESS_KEY'):
    os.environ.pop(key, None)
os.environ['APP_ENV'] = 'test'
Path('build/qa').mkdir(parents=True, exist_ok=True)

class FakeAI:
    model = 'fixture'
    def recompute(self, clarification, content):
        return type('Reply', (), {'raw': '{"found": false, "mention_types": [], "quote": ""}'})()

with tempfile.TemporaryDirectory(prefix='airate-cost-card-', ignore_cleanup_errors=True) as directory:
    url = 'sqlite:///' + str(Path(directory) / 'db.sqlite')
    first = TestClient(create_app(database_url=url, ai_client=FakeAI()))
    auth = first.post('/api/v1/auth/register', json={'email': 'cost-card@example.test', 'password': 'fixture-password-123'}).json()
    token = auth['token']
    user_id = first.get('/api/v1/me', headers={'Authorization': 'Bearer ' + token}).json()['id']
    os.environ['BRAND_CLARIFICATIONS_USER_ID'] = user_id
    app = create_app(database_url=url, ai_client=FakeAI())
    client = TestClient(app)
    headers = {'Authorization': 'Bearer ' + token}
    _, sessions = make_session_factory(url)
    with sessions() as db:
        db.get(User, user_id).is_admin = True
        db.get(Wallet, user_id).balance_kopeks = 10000
        db.commit()
    device = client.post('/api/v1/control/agent/enroll', headers=headers,
                         json={'device_id': 'a' * 32, 'name': 'QA PC'}).json()['token']
    client.post('/api/v1/control/agent/poll', headers={'Authorization': 'Bearer ' + device},
                json={'capabilities': {'installed': True, 'brand_clarification': True}})
    project = client.post('/api/v1/control/projects', headers=headers, json={
        'name': 'QA project', 'brand_name': 'Refprom', 'device_id': 'a' * 32,
        'queries': [{'text': 'Refprom review'}],
        'config': {'services': ['chatgpt'], 'brand_clarification': 'Reflo is another brand'},
    }).json()
    assert project['id']
    with sessions() as db:
        db.add(CloudResult(user_id=user_id, device_id='a' * 32, local_result_id=1,
            local_project_id=1, project_id=project['id'], query_id=project['queries'][0]['id'],
            project_name='QA project', brand_name='Refprom', query_text='Refprom review',
            group_tag='', service='chatgpt', scan_date=date.today().isoformat(),
            status='not_found', answer_text='Saved answer about Reflo', sources_json='[]'))
        db.commit()

    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8796, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        threading.Event().wait(.1)
    assert server.started
    assert urllib.request.urlopen('http://127.0.0.1:8796/cabinet/', timeout=5).status == 200

    async def check():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True,
                executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                args=['--no-proxy-server'])
            page = await browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            paid_posts = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: paid_posts.append(request.url) if request.method == 'POST' and
                ('/recompute/' in request.url or request.url.endswith('/runs')) else None)
            await page.add_init_script(f'sessionStorage.setItem("aimt.account.token", {json.dumps(token)})')
            await page.goto(f'http://127.0.0.1:8796/cabinet/#/project/{project["id"]}/settings', wait_until='commit', timeout=60000)
            start = page.get_by_role('button', name='Запустить проверку', exact=True)
            try:
                await start.wait_for(state='visible', timeout=20000)
            except Exception:
                print('browser diagnostics:', page.url, (await page.locator('body').inner_text())[:800])
                await page.screenshot(path='build/qa/cost-popover-load-error.png', full_page=True)
                raise
            await start.click()
            card = page.get_by_role('dialog', name='Подтверждение: Запустить')
            await card.wait_for(state='visible')
            assert 'К списанию: до' in await card.inner_text()
            assert client.get('/api/v1/control/runs', headers=headers).json() == []
            await page.keyboard.press('Escape')
            await card.wait_for(state='hidden')
            assert client.get('/api/v1/control/runs', headers=headers).json() == []
            assert not paid_posts

            for width in (300, 320, 360, 390):
                await page.set_viewport_size({'width': width, 'height': 740})
                await start.click()
                card = page.get_by_role('dialog', name='Подтверждение: Запустить')
                await card.wait_for(state='visible')
                scan_box = await card.bounding_box()
                assert scan_box and scan_box['x'] >= -1 and scan_box['x'] + scan_box['width'] <= width + 1, scan_box
                await page.screenshot(path=f'build/qa/cost-popover-scan-{width}.png', full_page=True)
                await card.get_by_role('button', name='Отменить').click()
            await page.set_viewport_size({'width': 1280, 'height': 900})

            date_input = page.get_by_label('Начиная с даты включительно')
            await date_input.fill(date.today().isoformat())
            replay = page.get_by_role('button', name='Пересчитать ответы с этой даты')
            await replay.click()
            card = page.get_by_role('dialog', name='Подтверждение: Пересчитать')
            await card.wait_for(state='visible')
            assert '0,80' in await card.inner_text()
            await page.screenshot(path='build/qa/cost-popover-desktop.png', full_page=True)
            await card.get_by_role('button', name='Отменить').click()
            await card.wait_for(state='hidden')
            with sessions() as db:
                assert db.get(Wallet, user_id).balance_kopeks == 10000
            assert not paid_posts

            for width in (300, 320, 360, 390):
                await page.set_viewport_size({'width': width, 'height': 740})
                await replay.click()
                card = page.get_by_role('dialog', name='Подтверждение: Пересчитать')
                await card.wait_for(state='visible')
                box = await card.bounding_box()
                assert box and box['x'] >= -1 and box['x'] + box['width'] <= width + 1, box
                await page.screenshot(path=f'build/qa/cost-popover-recompute-{width}.png', full_page=True)
                await card.get_by_role('button', name='Отменить').click()
            assert not paid_posts

            await page.set_viewport_size({'width': 1280, 'height': 900})
            await replay.click()
            card = page.get_by_role('dialog', name='Подтверждение: Пересчитать')
            await card.get_by_role('button', name='Пересчитать', exact=True).click()
            for _ in range(30):
                with sessions() as db:
                    if db.get(Wallet, user_id).balance_kopeks == 9920:
                        break
                await asyncio.sleep(.1)
            with sessions() as db:
                assert db.get(Wallet, user_id).balance_kopeks == 9920
                db.get(User, user_id).is_admin = False
                db.commit()
            assert len(paid_posts) == 1
            paid_posts.clear()

            # The same disposable account now pays for ordinary scans. Reload
            # to fetch its current entitlement before checking the quote UI.
            await page.reload(wait_until='commit')
            await start.wait_for(state='visible')
            quote = client.get(f'/api/v1/control/projects/{project["id"]}/quote', headers=headers).json()
            assert quote['unit_kopeks'] == quote['total_kopeks'] == 120
            await start.click()
            card = page.get_by_role('dialog', name='Подтверждение: Запустить')
            await card.wait_for(state='visible')
            assert '1,20' in await card.inner_text()
            assert not paid_posts
            await card.get_by_role('button', name='Запустить', exact=True).click()
            for _ in range(30):
                if client.get('/api/v1/control/runs', headers=headers).json():
                    break
                await asyncio.sleep(.1)
            assert len(client.get('/api/v1/control/runs', headers=headers).json()) == 1
            assert len(paid_posts) == 1
            assert not errors, errors
            print('cost popovers OK: real 1.20/0.80 quotes, no POST before confirm, one each after, Esc/cancel, desktop/mobile bounds')
            await browser.close()

    try:
        asyncio.run(check())
    finally:
        server.should_exit = True
        thread.join(timeout=5)
