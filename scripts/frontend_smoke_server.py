"""Loopback-only, disposable frontend audit; never uses the production database."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Fixture processes must never inherit production database or provider access.
for key in ('DATABASE_URL', 'COINSO_SECRET_KEY', 'COINSO_PROJECT_ID', 'OPENROUTER_API_KEY',
            'S3_SCREENSHOTS_BUCKET', 'S3_ACCESS_KEY_ID', 'S3_SECRET_ACCESS_KEY',
            'YANDEX_CLIENT_ID', 'YANDEX_CLIENT_SECRET', 'SMTP_HOST'):
    os.environ.pop(key, None)
os.environ['APP_ENV'] = 'test'
import uvicorn
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from server.test_reporting import seed_report
from server.models import CloudResult, make_session_factory

work = Path(tempfile.mkdtemp(prefix='airate-frontend-'))
client, owner, _, _, project, ids, url = seed_report(work)
_, sessions = make_session_factory(url)
with sessions() as db:
    db.get(CloudResult, ids[1]).check_id = 'qa-a'
    db.get(CloudResult, ids[-1]).check_id = 'qa-b'
    db.commit()
state = {'save': 'pass', 'shot': 'pass', 'seen': []}
app = client.app

async def qa(request, call_next):
    path = request.url.path
    if path == '/__qa/state':
        if request.method == 'POST':
            state.update(await request.json())
        return JSONResponse(state)
    if path == '/cabinet/' and request.query_params.get('native_dialogs') != '1':
        html = (Path(__file__).resolve().parents[1] / 'web/cabinet/index.html').read_text(encoding='utf-8')
        controls = '''<aside style="position:fixed;bottom:0;left:0;z-index:9999;background:#fff;color:#111;padding:8px;font:12px sans-serif">
          <label><input id="qa-accept-leave" type="checkbox"> QA: разрешить уход</label>
          <span id="qa-confirm-count">Подтверждений: 0</span></aside>
          <script>window.confirm=function(message){const counter=document.getElementById('qa-confirm-count');
            counter.dataset.count=String(Number(counter.dataset.count||0)+1);
            counter.textContent='Подтверждений: '+counter.dataset.count+' · '+message;
            return document.getElementById('qa-accept-leave').checked;};</script>'''
        return Response(html.replace('</body>', controls+'</body>'), media_type='text/html')
    if path.startswith('/__qa/shot-'):
        label = 'B' if 'shot-b' in path else 'A'
        return Response(f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="#39483d"/><text x="20" y="100" fill="white">TEST SCREENSHOT {label}</text></svg>', media_type='image/svg+xml')
    if path.startswith('/api/v1/'):
        request.scope['headers'] = [(key, value) for key, value in request.scope['headers'] if key.lower() != b'authorization'] + [(b'authorization', owner['Authorization'].encode())]
    if path == '/api/v1/auth/logout':
        state['seen'].append('logout')
    if request.method in ('PUT', 'POST') and path.startswith('/api/v1/control/projects'):
        state['seen'].append('save')
        while state['save'] == 'hold':
            await asyncio.sleep(.05)
        if state['save'] == 'fail':
            return JSONResponse({'detail': 'QA: сохранение не удалось'}, status_code=503)
    if path == '/api/v1/screenshots/qa-a/url':
        state['seen'].append('shot-a')
        while state['shot'] == 'hold':
            await asyncio.sleep(.05)
        if state['shot'] == 'fail':
            return JSONResponse({'detail': 'QA: старый скриншот недоступен'}, status_code=503)
        return JSONResponse({'url': '/__qa/shot-a.svg'})
    if path == '/api/v1/screenshots/qa-b/url':
        return JSONResponse({'url': '/__qa/shot-b.svg'})
    return await call_next(request)

print(json.dumps({'project_id': project['id'], 'result_a': ids[1], 'result_b': ids[-1], 'url': 'http://127.0.0.1:8793/cabinet/'}), flush=True)
uvicorn.run(BaseHTTPMiddleware(app, dispatch=qa), host='127.0.0.1', port=8793, log_level='warning')
