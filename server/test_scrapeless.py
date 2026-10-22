import asyncio
import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import select

from server import provider_tasks, scrapeless
from server.cloud_scans import _claim, _cloud_tick
from server.models import Check, CloudResult, ControlRun, ControlProject, ProviderAccount, ProviderTask, ServerCapture, User, Wallet, utcnow
from server.test_cloud_scans import setup, project_and_run, postgres_url  # noqa: F401


@pytest.mark.parametrize("service", ["chatgpt", "perplexity", "gemini"])
def test_exact_actor_and_no_shopping(monkeypatch, service):
    monkeypatch.setenv("SCRAPELESS_API_KEY", "private-test-key")
    def handle(request):
        assert request.headers["x-api-token"] == "private-test-key"
        assert "private-test-key" not in str(request.url)
        data = json.loads(request.content)
        assert data["actor"] == "scraper." + service
        assert data["input"]["country"] == "US"
        if service != "gemini":
            assert data["input"]["web_search"] is True
        if service != "perplexity":
            assert data["input"]["shopping"] is False
        return httpx.Response(201, json={"task_id": "task-123"})
    async def scenario():
        async with scrapeless.ScrapelessClient(transport=httpx.MockTransport(handle)) as client:
            assert await client.submit(service, "Question", "US") == "task-123"
    asyncio.run(scenario())


def test_get_transport_retry_preserves_id():
    calls = []
    def handle(request):
        calls.append((request.method, request.url.path))
        if len(calls) == 1:
            raise httpx.ReadError("private details", request=request)
        return httpx.Response(200, json={"status": "success", "task_result": {"result_text": "## Brand\n\n**Good** answer"}})
    async def scenario():
        async with scrapeless.ScrapelessClient(transport=httpx.MockTransport(handle)) as client:
            assert await client.poll("same-id") == ("pending", None)
            status, answer = await client.poll("same-id")
            assert status == "success" and answer["format"] == "markdown"
    asyncio.run(scenario())
    assert calls == [("GET", "/api/v2/scraper/result/same-id")] * 2


@pytest.mark.parametrize("status,body", [(410, {}), (400, {"message": "task expired."}), (200, {"status": "failed"})])
def test_known_terminal_statuses(status, body):
    async def scenario():
        async with scrapeless.ScrapelessClient(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body))) as client:
            result, _ = await client.poll("id")
            assert result in ("expired", "failed")
    asyncio.run(scenario())


@pytest.mark.parametrize("status,body", [(500, {}), (201, {}), (201, {"task_id": "bad/id"})])
def test_ambiguous_post_cannot_retry(status, body):
    calls = []
    async def scenario():
        def handle(request):
            calls.append(request)
            return httpx.Response(status, json=body)
        async with scrapeless.ScrapelessClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(scrapeless.SubmissionUnknown):
                await client.submit("chatgpt", "Question", "US")
    asyncio.run(scenario())
    assert len(calls) == 1


def test_markdown_and_all_citation_shapes_are_preserved():
    text = "# Brand\n\n| Name | URL |\n| --- | --- |\n| Brand | [Site](https://brand.test/item_(1)) |\n\n```html\n<script>alert(1)</script>\n```"
    result = scrapeless.evidence({"result_text": text, "links": ["https://one.test", "javascript:alert(1)"],
        "web_results": [{"name": "Web", "url": "https://two.test", "snippet": "Fact"}],
        "citations": [{"url": "https://three.test"}], "content_references": [{"url": "https://u:p@private.test"}]})
    assert result["answer_text"] == text
    assert result["main_text"] == text
    assert result["sources"] == ["https://one.test", "https://two.test", "https://three.test", "https://brand.test/item_(1)"]
    assert result["cards_text"] == ""
    assert result["source_cards"] == [{"title": "Web", "text": "Fact", "url": "https://two.test"}]
    for bad in ({}, {"result_text": " "}, {"result_text": ["answer"]}):
        with pytest.raises(scrapeless.CollectionDeferred):
            scrapeless.evidence(bad)


class Supplier:
    def __init__(self):
        self.posts, self.gets = [], []
        self.unknown = False
        self.pending = 0
        self.stop = None

    async def submit(self, service, prompt, country):
        self.posts.append((service, prompt, country))
        if self.unknown:
            raise scrapeless.SubmissionUnknown("Неизвестен исход отправки")
        if self.stop:
            self.stop()
        return "task-" + str(len(self.posts))

    async def poll(self, task_id):
        self.gets.append(task_id)
        if self.pending:
            self.pending -= 1
            return "pending", None
        return "success", scrapeless.evidence({"result_text": "# Brand\n\n**Recommended** [source](https://brand.test)"})


def create(tmp_path, monkeypatch, *, services=("chatgpt",), queries=None, admin=True, database_url=None):
    monkeypatch.setenv("SCRAPELESS_API_KEY", "fake-key")
    client, owner, other, user_id, sessions = setup(tmp_path, monkeypatch, admin=admin, database_url=database_url)
    project, run = project_and_run(client, owner, services=services, queries=queries, legacy=False)
    return client, owner, other, user_id, sessions, project, run


def tick(sessions, supplier):
    return asyncio.run(_cloud_tick(sessions, None, 120, __import__("shared.xmlriver", fromlist=["XMLRiverClient"]).XMLRiverClient,
        provider_client=supplier, prefetch_limits={"chatgpt": 100, "perplexity": 100, "gemini": 50}))


def test_three_services_without_pc_and_owner_scoped_markdown(tmp_path, monkeypatch):
    client, owner, other, _, sessions, project, run = create(tmp_path, monkeypatch,
        services=("chatgpt", "perplexity", "gemini"))
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert run["device_id"] is None
    with sessions() as db:
        assert db.get(ControlRun, run["id"]).state == "done"
        results = db.scalars(select(CloudResult)).all()
        assert len(results) == 3 and all(r.status == "found" for r in results)
        result_id = results[0].id
        assert all(t.state == "completed" and t.task_id for t in db.scalars(select(ProviderTask)))
    endpoint = f"/api/v1/control/projects/{project['id']}/mentions/results/{result_id}"
    detail = client.get(endpoint, headers=owner)
    assert detail.status_code == 200 and detail.json()["answer_evidence"]["format"] == "markdown"
    assert client.get(endpoint, headers=other).status_code == 404
    assert not tick(sessions, supplier)
    assert len(supplier.posts) == 3


def test_insufficient_funds_never_posts(tmp_path, monkeypatch):
    _, _, _, _, sessions, _, run = create(tmp_path, monkeypatch, admin=False)
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert supplier.posts == []
    with sessions() as db:
        assert db.get(ControlRun, run["id"]).desired_state == "paused"
        assert db.scalar(select(ProviderTask)) is None


def test_ambiguous_post_retains_capacity_and_has_no_error_result(tmp_path, monkeypatch):
    _, _, _, _, sessions, _, run = create(tmp_path, monkeypatch)
    supplier = Supplier()
    supplier.unknown = True
    assert tick(sessions, supplier)
    with sessions() as db:
        assert db.scalar(select(ProviderTask)).state == "uncertain"
        assert db.scalar(select(CloudResult)) is None
        db.get(ControlRun, run["id"]).retry_at = None
        db.commit()
    assert tick(sessions, supplier)
    assert len(supplier.posts) == 1


def test_restart_uses_existing_id_and_stop_drains_without_new_posts(tmp_path, monkeypatch):
    client, owner, _, _, sessions, _, run = create(tmp_path, monkeypatch)
    _, token, snapshot = _claim(sessions)
    query = snapshot["queries"][0]
    from server.checks import reserve_checks
    with sessions() as db:
        current = db.get(ControlRun, run["id"])
        reserve_checks(db, db.get(User, current.user_id), [f"{run['id']}:{query['id']}:chatgpt"], 120, None)
    task, fresh = provider_tasks.admit(sessions, run["id"], token, query["id"], "chatgpt", 100)
    assert fresh
    provider_tasks.submitted(sessions, task, "existing-id")
    with sessions() as db:
        db.get(ControlRun, run["id"]).lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert supplier.posts == [] and supplier.gets == ["existing-id"]
    assert client.get('/api/v1/control/runs', headers=owner).json()[0]['state'] == 'done'


def test_stop_after_post_saves_capture_and_does_not_submit_rest(tmp_path, monkeypatch):
    client, owner, _, _, sessions, _, run = create(tmp_path, monkeypatch,
        queries=[{"text": "q1"}, {"text": "q2"}])
    monkeypatch.setenv("SCRAPELESS_CHATGPT_CONCURRENCY", "1")
    supplier = Supplier()
    supplier.stop = lambda: client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner, json={"action": "stop"})
    assert tick(sessions, supplier)
    assert len(supplier.posts) == 1
    with sessions() as db:
        assert db.scalar(select(ServerCapture)) is not None
        assert db.scalar(select(ProviderTask)).state == "completed"
        assert db.get(ControlRun, run["id"]).state == "cancelled"


@pytest.mark.parametrize("action", ["pause", "stop"])
def test_restart_drains_previously_accepted_tasks_after_command(tmp_path, monkeypatch, action):
    client, owner, _, _, sessions, _, run = create(tmp_path, monkeypatch,
        queries=[{"text": "q1"}, {"text": "q2"}])
    _, token, snapshot = _claim(sessions)
    query = snapshot["queries"][0]
    task, _ = provider_tasks.admit(sessions, run["id"], token, query["id"], "chatgpt", 100)
    provider_tasks.submitted(sessions, task, "accepted-before-crash")
    from server.checks import reserve_checks
    with sessions() as db:
        current = db.get(ControlRun, run["id"])
        reserve_checks(db, db.get(User, current.user_id), [task.check_id], 120, None)
        current.lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
        json={"action": action}).status_code == 200
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert supplier.posts == [] and supplier.gets == ["accepted-before-crash"]
    with sessions() as db:
        assert db.get(ProviderTask, task.check_id).state == "completed"
        assert db.scalar(select(ServerCapture)) is not None
        assert db.get(ControlRun, run["id"]).state == ("paused" if action == "pause" else "cancelled")
        assert all(r.status != "error" for r in db.scalars(select(CloudResult)))


@pytest.mark.parametrize("use_postgres", [False, True])
def test_shared_admission_across_users_and_stale_submission(tmp_path, monkeypatch, request, use_postgres):
    url = request.getfixturevalue("postgres_url") if use_postgres else None
    client, owner, other, _, sessions, _, first = create(tmp_path, monkeypatch, database_url=url)
    _, second = project_and_run(client, other, services=("chatgpt",), legacy=False)
    claims = [_claim(sessions), _claim(sessions)]
    def admit(claim):
        run_id, token, snap = claim
        return provider_tasks.admit(sessions, run_id, token, snap["queries"][0]["id"], "chatgpt", 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(admit, claims))
    accepted = [t for t, fresh in results if fresh]
    assert len(accepted) == 1
    task = accepted[0]
    with sessions() as db:
        run = db.get(ControlRun, task.run_id)
        run.lease_token = "new-owner"
        db.commit()
    provider_tasks.submitted(sessions, task, "late-id")
    with sessions() as db:
        saved = db.get(ProviderTask, task.check_id)
        assert saved.task_id == "late-id" and saved.state == "submitted"
    waiting = next(c for c in claims if c[0] != task.run_id)
    assert admit(waiting) == (None, False)
    provider_tasks.save(sessions, task, scrapeless.evidence({"result_text": "Brand"}))
    assert admit(waiting)[1] is True


def test_expired_paid_task_never_posts_again_or_holds_account_capacity(tmp_path, monkeypatch):
    _, _, _, _, sessions, _, run = create(tmp_path, monkeypatch)
    class Expired(Supplier):
        async def poll(self, task_id):
            self.gets.append(task_id)
            return "expired", None
    supplier = Expired()
    assert tick(sessions, supplier)
    with sessions() as db:
        db.get(ControlRun, run['id']).retry_at = None
        db.commit()
    assert tick(sessions, supplier)
    with sessions() as db:
        task = db.scalar(select(ProviderTask))
        assert task.state == 'expired' and task.task_id == 'task-1'
        assert task.state not in provider_tasks.ACTIVE
        assert db.scalar(select(CloudResult)) is None
    assert len(supplier.posts) == 1


def test_admit_delay_waits_out_shared_cooldown_then_backs_off(tmp_path, monkeypatch):
    _, _, _, _, sessions, _, _ = create(tmp_path, monkeypatch)
    with sessions() as db:
        db.get(ProviderAccount, 'chatgpt').cooldown_until = utcnow() + timedelta(seconds=12)
        db.commit()
    delay = provider_tasks.admit_delay(sessions, 'chatgpt', attempt=0)
    assert 11.0 <= delay <= 12.0
    with sessions() as db:
        db.get(ProviderAccount, 'chatgpt').cooldown_until = None
        db.commit()
    assert provider_tasks.admit_delay(sessions, 'chatgpt', attempt=0) == 0.5
    assert provider_tasks.admit_delay(sessions, 'chatgpt', attempt=2) == pytest.approx(2.1)


def test_known_failed_task_retries_without_error_report_or_double_client_charge(tmp_path, monkeypatch):
    _, _, _, user_id, sessions, _, run = create(tmp_path, monkeypatch, admin=False)
    with sessions() as db:
        db.get(Wallet,user_id).balance_kopeks = 500
        db.commit()
    class Retry(Supplier):
        async def poll(self, task_id):
            return ('failed',None) if len(self.posts)==1 else await super().poll(task_id)
    supplier = Retry()
    assert tick(sessions,supplier)
    with sessions() as db:
        assert db.scalar(select(CloudResult)) is None
        db.get(ControlRun,run['id']).retry_at = None
        db.get(ProviderAccount,'chatgpt').cooldown_until = None
        db.commit()
    assert tick(sessions,supplier)
    with sessions() as db:
        assert db.get(ControlRun,run['id']).state == 'done'
        assert db.get(Wallet,user_id).balance_kopeks == 380
        assert db.scalar(select(Check)).status == 'settled'
        assert db.scalar(select(CloudResult)).status == 'found'
        assert db.scalar(select(ProviderTask)).attempts == 2
    assert len(supplier.posts) == 2


def test_stop_preserves_unanalysed_answer_without_error_report(tmp_path, monkeypatch):
    client, owner, _, _, sessions, _, run = create(tmp_path,monkeypatch)
    class Unanalysed(Supplier):
        async def poll(self, task_id):
            return 'success',scrapeless.evidence({'result_text':'An unrelated answer'})
    supplier=Unanalysed()
    supplier.stop=lambda:client.post(f"/api/v1/control/runs/{run['id']}/command",headers=owner,json={'action':'stop'})
    assert tick(sessions,supplier)
    with sessions() as db:
        assert db.scalar(select(ServerCapture)) is not None
        assert db.scalar(select(CloudResult)) is None
        assert db.scalar(select(Check)).status == 'released'
        assert db.get(ControlRun,run['id']).state == 'cancelled'


def test_xml_recovery_preserves_live_owner_even_for_old_intent(tmp_path,monkeypatch):
    _,_,_,_,sessions,_,run=create(tmp_path,monkeypatch,services=('google_aio',))
    _,token,snapshot=_claim(sessions)
    task,_=provider_tasks.admit(sessions,run['id'],token,snapshot['queries'][0]['id'],'google_aio',1)
    with sessions() as db:
        db.get(ProviderTask,task.check_id).updated_at=utcnow()-timedelta(hours=1)
        db.commit()
    provider_tasks.recover_xml(sessions)
    with sessions() as db:
        assert db.get(ProviderTask,task.check_id).state == 'submitting'
        assert db.get(ControlRun,run['id']).lease_token == token


def test_stopped_crashed_xml_intent_releases_slot_after_bounded_timeout(tmp_path,monkeypatch):
    client,owner,_,_,sessions,_,run=create(tmp_path,monkeypatch,services=('google_aio',))
    _,token,snapshot=_claim(sessions)
    task,_=provider_tasks.admit(sessions,run['id'],token,snapshot['queries'][0]['id'],'google_aio',1)
    from server.checks import reserve_checks
    with sessions() as db:
        current=db.get(ControlRun,run['id'])
        reserve_checks(db,db.get(User,current.user_id),[task.check_id],120,None)
        current.lease_until=utcnow()-timedelta(hours=1)
        db.get(ProviderTask,task.check_id).updated_at=utcnow()-timedelta(hours=1)
        db.commit()
    client.post(f"/api/v1/control/runs/{run['id']}/command",headers=owner,json={'action':'stop'})
    assert tick(sessions,Supplier())
    with sessions() as db:
        assert db.get(ProviderTask,task.check_id).state == 'rejected'
        assert db.get(ControlRun,run['id']).state == 'cancelled'
        assert db.get(ControlRun,run['id']).active_project_key is None
        assert db.scalar(select(Check)).status == 'released'


@pytest.mark.parametrize('use_postgres',[False,True])
def test_claim_limits_one_active_project_per_owner(tmp_path,monkeypatch,request,use_postgres):
    url=request.getfixturevalue('postgres_url') if use_postgres else None
    client,owner,other,user_id,sessions,_,_=create(tmp_path,monkeypatch,database_url=url)
    for _ in range(3):
        project_and_run(client,owner,services=('chatgpt',),legacy=False)
    _,second=project_and_run(client,other,services=('chatgpt',),legacy=False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _: _claim(sessions),range(4)))
    claimed=[c for c in claims if c]
    assert len(claimed)==2
    assert second['id'] in [c[0] for c in claimed]


def test_legacy_and_new_xml_share_global_admission(tmp_path,monkeypatch):
    from shared.xmlriver import XMLRiverClient
    from server.test_cloud_scans import Collector
    client,owner,other,_,sessions,_,_=create(tmp_path,monkeypatch,services=('google_aio',))
    other_id=client.get('/api/v1/me',headers=other).json()['id']
    with sessions() as db:
        db.get(Wallet,other_id).balance_kopeks=1000
        db.commit()
    project_and_run(client,other,services=('google_aio',),legacy=True)
    active=peak=calls=0
    async def collect(self,query,**kwargs):
        nonlocal active,peak,calls
        active+=1; calls+=1; peak=max(peak,active)
        await asyncio.sleep(.05)
        active-=1
        return dict(Collector.answer)
    monkeypatch.setattr(XMLRiverClient,'collect',collect)
    async def scenario():
        await asyncio.gather(*(_cloud_tick(sessions,None,120,XMLRiverClient,
            provider_client=Supplier(),prefetch_limits={'google_aio':1}) for _ in range(2)))
    asyncio.run(scenario())
    assert calls==2 and peak==1


def test_old_alice_only_schedule_never_silently_switches_service(tmp_path,monkeypatch):
    client,owner,_,_,sessions,project,run=create(tmp_path,monkeypatch)
    with sessions() as db:
        current=db.get(ControlRun,run['id'])
        current.state='done'; current.active_project_key=None
        row=db.get(ControlProject,project['id'])
        config=json.loads(row.config_json); config['services']=['alice']
        row.config_json=json.dumps(config)
        now=utcnow()
        row.schedule_json=json.dumps({'enabled':True,'timezone':'UTC','month_days':[now.day],
            'time':now.strftime('%H:%M'),'device_id':None})
        db.commit()
    from server.control import schedule_tick
    schedule_tick(sessions)
    with sessions() as db:
        assert len(db.scalars(select(ControlRun)).all())==1
    assert client.get(f"/api/v1/control/projects/{project['id']}",headers=owner).json()['config']['services']==[]
    response=client.post(f"/api/v1/control/projects/{project['id']}/runs",headers=owner,json={'request_id':'d'*32})
    assert response.status_code==422
