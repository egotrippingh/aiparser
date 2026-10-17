import asyncio
import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import select, update

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


@pytest.mark.parametrize("result", [None, {}, {"result_text": " "}, {"result_text": []}])
def test_empty_terminal_answer_is_retryable_failure(result):
    async def scenario():
        transport = httpx.MockTransport(lambda request: httpx.Response(200,
            json={"status": "success", "task_result": result}))
        async with scrapeless.ScrapelessClient(transport=transport) as client:
            assert await client.poll("completed-empty") == ("failed", None)
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
    # Supplier's normal completed answer cites this verified brand source. These
    # transport/recovery tests intentionally keep the rules-only fast path.
    project, run = project_and_run(client, owner, services=services, queries=queries,
                                   legacy=False, domains=["brand.test"])
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


def test_run_created_while_paused_never_admits_after_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPELESS_API_KEY", "fake-key")
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    created = client.post('/api/v1/control/projects', headers=owner, json={
        'name': 'Mixed pause', 'brand_name': 'Brand', 'queries': [{'text': 'question'}],
        'config': {'services': ['chatgpt', 'perplexity']},
    })
    assert created.status_code == 201, created.text
    project = created.json()
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 120
        account = db.get(ProviderAccount, 'chatgpt')
        account.paused, account.last_paused_at = True, utcnow()
        db.commit()
    quote = client.get(f"/api/v1/control/projects/{project['id']}/quote", headers=owner).json()
    launched = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owner,
        json={'request_id': 'a' * 32, 'revision': quote['revision'], 'provider_state': quote['provider_state']})
    assert launched.status_code == 201, launched.text
    run = launched.json()
    with sessions() as db:
        account = db.get(ProviderAccount, 'chatgpt')
        account.paused, account.last_paused_at = False, utcnow()
        db.commit()
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert [service for service, _, _ in supplier.posts] == ['perplexity']
    with sessions() as db:
        frozen = json.loads(db.get(ControlRun, run['id']).snapshot_json)
        assert frozen['cloud_services'] == ['perplexity']
        assert db.scalar(select(Check).where(Check.client_check_id.like(f"{run['id']}:%:chatgpt"))) is None
        assert db.get(Wallet, user_id).balance_kopeks == 0
        assert db.scalar(select(Check)).status == 'settled'


def test_pause_releases_rejected_reservation_before_skipping(tmp_path, monkeypatch):
    _, _, _, user_id, sessions, _, run = create(tmp_path, monkeypatch, admin=False)
    run_id, token, snapshot = _claim(sessions)
    query_id = snapshot['queries'][0]['id']
    check_id = f'{run_id}:{query_id}:chatgpt'
    from server.checks import reserve_checks
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 120
        reserve_checks(db, db.get(User, user_id), [check_id], 120)
        db.add(ProviderTask(check_id=check_id, run_id=run_id, query_id=query_id,
            service='chatgpt', submission_token='rejected-token', state='rejected'))
        account = db.get(ProviderAccount, 'chatgpt')
        account.paused, account.last_paused_at = True, utcnow()
        db.get(ControlRun, run_id).lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert tick(sessions, Supplier())
    with sessions() as db:
        assert db.get(ProviderTask, check_id).state == 'skipped'
        assert db.scalar(select(Check).where(Check.client_check_id == check_id)).status == 'released'
        assert db.get(Wallet, user_id).balance_kopeks == 120
        assert db.get(ControlRun, run_id).state == 'done'


def test_paused_admission_releases_hold_before_worker_restart(tmp_path, monkeypatch):
    _, _, _, user_id, sessions, _, run = create(tmp_path, monkeypatch, admin=False)
    run_id, token, snapshot = _claim(sessions)
    query_id = snapshot['queries'][0]['id']
    check_id = f'{run_id}:{query_id}:chatgpt'
    from server.checks import reserve_checks
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 120
        reserve_checks(db, db.get(User, user_id), [check_id], 120)
        account = db.get(ProviderAccount, 'chatgpt')
        account.paused, account.last_paused_at = True, utcnow()
        db.commit()
    task, fresh = provider_tasks.admit(sessions, run_id, token, query_id, 'chatgpt', 100)
    assert task.state == 'skipped' and fresh is False
    # This is the crash boundary: release happens before the worker can refresh progress.
    with sessions() as db:
        assert db.scalar(select(Check).where(Check.client_check_id == check_id)).status == 'released'
        assert db.get(Wallet, user_id).balance_kopeks == 120
        db.get(ControlRun, run_id).lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert tick(sessions, Supplier())
    with sessions() as db:
        assert db.get(ControlRun, run_id).state == 'done'


def test_late_pause_waits_for_release_before_retrying_next_service(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPELESS_API_KEY", "fake-key")
    client, owner, _, user_id, sessions = setup(tmp_path, monkeypatch, admin=False)
    project, run = project_and_run(client, owner, services=('chatgpt', 'perplexity'), legacy=False)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 120
        db.commit()
    original = provider_tasks.skip_if_paused
    paused = False

    def pause_after_preflight(*args):
        nonlocal paused
        result = original(*args)
        if not paused and args[-1] == 'chatgpt':
            paused = True
            with sessions() as db:
                account = db.get(ProviderAccount, 'chatgpt')
                account.paused, account.last_paused_at = True, utcnow()
                db.commit()
        return result

    monkeypatch.setattr(provider_tasks, 'skip_if_paused', pause_after_preflight)
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert [service for service, _, _ in supplier.posts] == ['perplexity']
    with sessions() as db:
        checks = {check.client_check_id.rsplit(':', 1)[1]: check for check in db.scalars(select(Check))}
        assert checks['chatgpt'].status == 'released'
        assert checks['perplexity'].status == 'settled'
        assert db.get(Wallet, user_id).balance_kopeks == 0
        assert db.get(ControlRun, run['id']).state == 'done'


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


def test_postgres_pause_and_admission_are_serialized(tmp_path, monkeypatch, postgres_url):
    _, owner, _, _, sessions, _, run = create(tmp_path, monkeypatch, database_url=postgres_url)
    run_id, token, snapshot = _claim(sessions)
    query_id = snapshot['queries'][0]['id']
    def pause():
        with sessions() as db:
            db.execute(update(ProviderAccount).where(ProviderAccount.service == 'chatgpt').values(
                paused=True, last_paused_at=utcnow(), revision=ProviderAccount.revision + 1))
            db.commit()
    def admit():
        return provider_tasks.admit(sessions, run_id, token, query_id, 'chatgpt', 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        paused = pool.submit(pause)
        task, fresh = pool.submit(admit).result()
        paused.result()
    with sessions() as db:
        account = db.get(ProviderAccount, 'chatgpt')
        saved = db.get(ProviderTask, task.check_id)
        # If the pause acquired the account lock first, admission must be skipped;
        # otherwise the accepted intent predates the pause and is safe to drain.
        assert saved.state == ('skipped' if account.last_paused_at <= saved.created_at else 'submitting')
        assert fresh is (saved.state == 'submitting')


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


def test_expired_task_recovers_new_checks_after_cooldown(tmp_path, monkeypatch):
    _, _, _, user_id, sessions, _, run = create(tmp_path, monkeypatch, admin=False)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()

    class Expired(Supplier):
        async def poll(self, task_id):
            return ('expired', None) if len(self.posts) == 1 else await super().poll(task_id)
    supplier = Expired()
    assert tick(sessions, supplier)
    with sessions() as db:
        db.get(ControlRun, run['id']).retry_at = None
        db.scalar(select(ProviderTask)).updated_at = utcnow() - timedelta(minutes=16)
        db.get(ProviderAccount, 'chatgpt').cooldown_until = None
        db.commit()
    assert tick(sessions, supplier)
    assert len(supplier.posts) == 2
    with sessions() as db:
        task = db.scalar(select(ProviderTask))
        assert task.state == 'completed'
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(Check)).all()) == 1
        assert db.get(ControlRun, run['id']).state == 'done'
        assert json.loads(task.history_json) == [{'task_id': 'task-1', 'state': 'expired'}]


def test_expired_query_does_not_block_other_queries_or_services(tmp_path, monkeypatch):
    monkeypatch.setenv('SCRAPELESS_CHATGPT_CONCURRENCY', '1')
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch,
        services=('chatgpt', 'perplexity'), queries=[{'text': 'first'}, {'text': 'second'}])
    with sessions() as db:
        query_id = project['queries'][0]['id']
        db.add(ProviderTask(check_id=f"{run['id']}:{query_id}:chatgpt", run_id=run['id'],
            query_id=query_id, service='chatgpt', submission_token='old', state='expired',
            task_id='expired-id', updated_at=utcnow()))
        db.commit()
    supplier = Supplier()
    assert tick(sessions, supplier)
    assert len(supplier.posts) == 3
    with sessions() as db:
        results = db.scalars(select(CloudResult)).all()
        assert len(results) == 3 and all(row.status == 'found' for row in results)
        assert json.loads(db.get(ControlRun, run['id']).progress_json)['cloud_done'] == 3


@pytest.mark.parametrize('status', ['success', 'pending'])
def test_expired_handle_is_rechecked_before_another_paid_submission(tmp_path, monkeypatch, status):
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch)
    with sessions() as db:
        query_id = project['queries'][0]['id']
        db.add(ProviderTask(check_id=f"{run['id']}:{query_id}:chatgpt", run_id=run['id'],
            query_id=query_id, service='chatgpt', submission_token='old', state='expired',
            task_id='expired-id', updated_at=utcnow() - timedelta(minutes=16)))
        db.commit()
    class Rechecked(Supplier):
        async def poll(self, task_id):
            assert task_id == 'expired-id'
            return (status, scrapeless.evidence({'result_text': '[Brand](https://brand.test)'}) if status == 'success' else None)
    supplier = Rechecked()
    assert tick(sessions, supplier)
    assert supplier.posts == []
    with sessions() as db:
        assert db.scalar(select(ProviderTask)).state == ('completed' if status == 'success' else 'expired')
        assert len(db.scalars(select(CloudResult)).all()) == (1 if status == 'success' else 0)


@pytest.mark.parametrize('state', ['submitted', 'uncertain', 'quota'])
@pytest.mark.parametrize('use_postgres', [False, True])
def test_occupied_or_quota_service_yields_without_blocking_healthy_service(
        tmp_path, monkeypatch, request, state, use_postgres):
    url = request.getfixturevalue('postgres_url') if use_postgres else None
    monkeypatch.setenv('SCRAPELESS_CHATGPT_CONCURRENCY', '1')
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch,
        services=('chatgpt', 'perplexity'), queries=[{'text': 'first'}, {'text': 'second'}], database_url=url)
    if state != 'quota':
        with sessions() as db:
            query_id = project['queries'][0]['id']
            db.add(ProviderTask(check_id=f"{run['id']}:{query_id}:chatgpt", run_id=run['id'],
                query_id=query_id, service='chatgpt', submission_token='old', state=state,
                task_id='old-id' if state == 'submitted' else None))
            db.commit()
    class Delayed(Supplier):
        async def submit(self, service, prompt, country):
            if service == 'chatgpt':
                self.posts.append((service, prompt, country))
                raise scrapeless.Rejected(402)
            return await super().submit(service, prompt, country)

        async def poll(self, task_id):
            if task_id == 'old-id':
                raise scrapeless.CollectionDeferred('Temporary GET failure')
            return await super().poll(task_id)
    supplier = Delayed()
    async def bounded_tick():
        return await asyncio.wait_for(_cloud_tick(sessions, None, 120,
            __import__('shared.xmlriver', fromlist=['XMLRiverClient']).XMLRiverClient,
            provider_client=supplier), timeout=10)
    assert asyncio.run(bounded_tick())
    assert sum(service == 'chatgpt' for service, _, _ in supplier.posts) == (1 if state == 'quota' else 0)
    with sessions() as db:
        results = db.scalars(select(CloudResult)).all()
        assert len(results) == 2 and all(row.service == 'perplexity' for row in results)
        assert db.get(ControlRun, run['id']).lease_token is None


def test_postgres_late_expired_answer_cannot_overwrite_new_owner(tmp_path, monkeypatch, postgres_url):
    _, _, _, user_id, sessions, project, run = create(tmp_path, monkeypatch,
        admin=False, database_url=postgres_url)
    query_id = project['queries'][0]['id']
    check_id = f"{run['id']}:{query_id}:chatgpt"
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.add(ProviderTask(check_id=check_id, run_id=run['id'], query_id=query_id,
            service='chatgpt', submission_token='old', state='expired', task_id='old-id',
            updated_at=utcnow() - timedelta(minutes=16)))
        db.commit()
    class Late(Supplier):
        async def poll(self, task_id):
            if task_id == 'old-id':
                with sessions() as db:
                    db.get(ControlRun, run['id']).lease_until = utcnow() - timedelta(seconds=1)
                    db.commit()
                claimed = _claim(sessions)
                assert claimed[0] == run['id']
                replacement, fresh = provider_tasks.admit(sessions, run['id'], claimed[1], query_id, 'chatgpt', 1)
                assert fresh
                provider_tasks.submitted(sessions, replacement, 'new-id')
                return 'success', scrapeless.evidence({'result_text': 'Stale unrelated answer'})
            assert task_id == 'new-id'
            return await super().poll(task_id)
    supplier = Late()
    assert not tick(sessions, supplier)
    with sessions() as db:
        assert db.get(ProviderTask, check_id).task_id == 'new-id'
        assert db.scalar(select(ServerCapture)) is None and db.scalar(select(CloudResult)) is None
        db.get(ControlRun, run['id']).lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert tick(sessions, supplier)
    with sessions() as db:
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(Check)).all()) == 1
        assert db.scalar(select(CloudResult)).status == 'found'


@pytest.mark.parametrize('state', ['submitted', 'submitting', 'uncertain'])
@pytest.mark.parametrize('use_postgres', [False, True])
def test_submitted_query_does_not_block_free_provider_capacity(tmp_path, monkeypatch, request, state, use_postgres):
    url = request.getfixturevalue('postgres_url') if use_postgres else None
    monkeypatch.setenv('SCRAPELESS_CHATGPT_CONCURRENCY', '2')
    _, _, _, _, sessions, project, run = create(tmp_path, monkeypatch,
        queries=[{'text': 'first'}, {'text': 'second'}, {'text': 'third'}], database_url=url)
    with sessions() as db:
        query_id = project['queries'][0]['id']
        db.add(ProviderTask(check_id=f"{run['id']}:{query_id}:chatgpt", run_id=run['id'],
            query_id=query_id, service='chatgpt', submission_token='old', state=state,
            task_id='old-id' if state == 'submitted' else None))
        db.commit()
    class Delayed(Supplier):
        async def poll(self, task_id):
            if task_id == 'old-id':
                raise scrapeless.CollectionDeferred('Temporary GET failure')
            return await super().poll(task_id)
    supplier = Delayed()
    assert tick(sessions, supplier)
    assert supplier.posts == [('chatgpt', 'second', 'US'), ('chatgpt', 'third', 'US')]
    with sessions() as db:
        assert {row.query_text for row in db.scalars(select(CloudResult))} == {'second', 'third'}
        saved = db.get(ProviderTask, f"{run['id']}:{query_id}:chatgpt")
        assert saved.state == state and saved.attempts == 1
        assert db.get(ControlRun, run['id']).lease_token is None


@pytest.mark.parametrize('use_postgres', [False, True])
def test_full_provider_capacity_is_reused_after_unknown_post(tmp_path, monkeypatch, request, use_postgres):
    from shared.xmlriver import XMLRiverClient
    url = request.getfixturevalue('postgres_url') if use_postgres else None
    monkeypatch.setenv('SCRAPELESS_CHATGPT_CONCURRENCY', '2')
    _, _, _, _, sessions, _, _ = create(tmp_path, monkeypatch,
        queries=[{'text': 'first'}, {'text': 'second'}, {'text': 'third'}], database_url=url)

    class Full(Supplier):
        async def submit(self, service, prompt, country):
            if prompt == 'first':
                self.posts.append((service, prompt, country))
                await self.second_started.wait()
                self.unknown_raised.set()
                raise scrapeless.SubmissionUnknown('Unknown submission')
            task_id = await super().submit(service, prompt, country)
            if prompt == 'second':
                self.second_started.set()
            return task_id

        async def poll(self, task_id):
            await self.unknown_raised.wait()
            await asyncio.sleep(0.01)
            return await super().poll(task_id)

    async def run():
        supplier = Full()
        supplier.second_started = asyncio.Event()
        supplier.unknown_raised = asyncio.Event()
        assert await _cloud_tick(sessions, None, 120, XMLRiverClient, provider_client=supplier,
            prefetch_limits={'chatgpt': 2})
        return supplier

    supplier = asyncio.run(run())
    assert [prompt for _, prompt, _ in supplier.posts] == ['first', 'second', 'third']
    with sessions() as db:
        assert {row.query_text for row in db.scalars(select(CloudResult))} == {'second', 'third'}
        assert db.scalar(select(ProviderTask).where(ProviderTask.state == 'uncertain')).attempts == 1


def test_ambiguous_new_post_does_not_cool_down_other_queries(tmp_path, monkeypatch):
    monkeypatch.setenv('SCRAPELESS_CHATGPT_CONCURRENCY', '2')
    _, _, _, _, sessions, _, run = create(tmp_path, monkeypatch,
        queries=[{'text': 'first'}, {'text': 'second'}, {'text': 'third'}])

    class AmbiguousFirst(Supplier):
        async def submit(self, service, prompt, country):
            if prompt == 'first':
                self.posts.append((service, prompt, country))
                raise scrapeless.SubmissionUnknown('Unknown submission')
            return await super().submit(service, prompt, country)

    supplier = AmbiguousFirst()
    assert tick(sessions, supplier)
    with sessions() as db:
        assert {row.query_text for row in db.scalars(select(CloudResult))} == {'second', 'third'}
        assert db.get(ProviderAccount, 'chatgpt').cooldown_until is None
        db.get(ControlRun, run['id']).retry_at = None
        db.commit()
    assert tick(sessions, supplier)
    assert [prompt for _, prompt, _ in supplier.posts].count('first') == 1


@pytest.mark.parametrize('use_postgres', [False, True])
def test_xml_transient_query_does_not_cool_down_other_queries(tmp_path, monkeypatch, request, use_postgres):
    from shared.xmlriver import XMLRiverClient, XMLRiverResponseError
    url = request.getfixturevalue('postgres_url') if use_postgres else None
    _, _, _, _, sessions, _, run = create(tmp_path, monkeypatch,
        services=('yandex_neuro',), queries=[{'text': 'first'}, {'text': 'second'}], database_url=url)
    calls = []

    async def collect(self, prompt, *, should_continue=None):
        calls.append(prompt)
        if prompt == 'first':
            raise XMLRiverResponseError('XMLRiver: empty answer')
        return scrapeless.evidence({'result_text': '[Brand](https://brand.test) is recommended'})

    monkeypatch.setattr(XMLRiverClient, 'collect', collect)
    assert asyncio.run(_cloud_tick(sessions, None, 120, XMLRiverClient,
        provider_client=Supplier(), prefetch_limits={'yandex_neuro': 1}))
    assert calls == ['first', 'second']
    with sessions() as db:
        assert db.get(ProviderAccount, 'yandex_neuro').cooldown_until is None
        assert [row.query_text for row in db.scalars(select(CloudResult))] == ['second']
        assert db.get(ControlRun, run['id']).desired_state == 'running'


def test_bad_request_does_not_cool_down_other_queries(tmp_path, monkeypatch):
    monkeypatch.setenv('SCRAPELESS_CHATGPT_CONCURRENCY', '1')
    _, _, _, _, sessions, _, _ = create(tmp_path, monkeypatch,
        queries=[{'text': 'first'}, {'text': 'second'}])

    class BadFirst(Supplier):
        async def submit(self, service, prompt, country):
            if prompt == 'first':
                self.posts.append((service, prompt, country))
                raise scrapeless.Rejected(400)
            return await super().submit(service, prompt, country)

    assert tick(sessions, BadFirst())
    with sessions() as db:
        assert db.get(ProviderAccount, 'chatgpt').cooldown_until is None
        assert [row.query_text for row in db.scalars(select(CloudResult))] == ['second']


@pytest.mark.parametrize('error_kind', ['auth', 'quota', 'throttle'])
def test_xml_global_failure_preserves_account_cooldown(tmp_path, monkeypatch, error_kind):
    from shared.xmlriver import AdapterError, ProviderQuotaError, ProviderThrottleError
    _, _, _, _, sessions, _, _ = create(tmp_path, monkeypatch, services=('yandex_neuro',))
    run_id, token, snapshot = _claim(sessions)
    error = {'auth': AdapterError, 'quota': ProviderQuotaError, 'throttle': ProviderThrottleError}[error_kind]

    class Unavailable:
        async def collect(self, prompt, *, should_continue=None):
            raise error('Service unavailable')

    query = snapshot['queries'][0]
    with pytest.raises(error):
        asyncio.run(provider_tasks.collect_xml(sessions, Unavailable(), run_id, token, query,
            'yandex_neuro', 1, lambda: True, lambda payload: payload))
    with sessions() as db:
        assert provider_tasks._aware(db.get(ProviderAccount, 'yandex_neuro').cooldown_until) > utcnow()
        assert db.scalar(select(ProviderTask)).state == 'rejected'
    assert provider_tasks.admit(sessions, run_id, token, query['id'], 'yandex_neuro', 1) == (None, False)


@pytest.mark.parametrize('cooldown', [0, 10])
@pytest.mark.parametrize('use_postgres', [False, True])
def test_terminal_task_does_not_shorten_account_cooldown(tmp_path, monkeypatch, request, cooldown, use_postgres):
    url = request.getfixturevalue('postgres_url') if use_postgres else None
    _, _, _, _, sessions, _, _ = create(tmp_path, monkeypatch, database_url=url)
    run_id, token, snapshot = _claim(sessions)
    task, fresh = provider_tasks.admit(sessions, run_id, token, snapshot['queries'][0]['id'], 'chatgpt', 2)
    assert fresh
    deadline = utcnow() + timedelta(minutes=1)
    with sessions() as db:
        db.get(ProviderAccount, 'chatgpt').cooldown_until = deadline
        db.commit()
    provider_tasks.failed(sessions, task, expired=True, cooldown=cooldown)
    with sessions() as db:
        assert provider_tasks._aware(db.get(ProviderAccount, 'chatgpt').cooldown_until) == deadline
        assert db.get(ProviderTask, task.check_id).state == 'expired'


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


@pytest.mark.parametrize("use_postgres", [False, True])
def test_failed_tasks_recover_after_three_attempts_with_cooldown_and_one_charge(
        tmp_path, monkeypatch, request, use_postgres):
    url = request.getfixturevalue("postgres_url") if use_postgres else None
    _, _, _, user_id, sessions, _, run = create(tmp_path, monkeypatch,
        admin=False, database_url=url)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 500
        db.commit()

    class Retry(Supplier):
        async def poll(self, task_id):
            return ("failed", None) if len(self.posts) <= 3 else await super().poll(task_id)
    supplier = Retry()

    def allow_tick(*, cooled=False):
        with sessions() as db:
            db.get(ControlRun, run["id"]).retry_at = None
            db.get(ProviderAccount, "chatgpt").cooldown_until = None
            if cooled:
                db.scalar(select(ProviderTask)).updated_at = utcnow() - timedelta(minutes=16)
            db.commit()

    for _ in range(3):
        assert tick(sessions, supplier)
        allow_tick()
    assert tick(sessions, supplier)
    assert len(supplier.posts) == 3  # No immediate fourth paid request.
    with sessions() as db:
        assert db.scalar(select(CloudResult)) is None
        assert db.get(Wallet, user_id).balance_kopeks == 500
        assert db.scalar(select(Check)).status == "reserved"
    allow_tick(cooled=True)
    assert tick(sessions, supplier)
    assert len(supplier.posts) == 4
    assert not tick(sessions, supplier)
    with sessions() as db:
        assert db.get(ControlRun, run["id"]).state == "done"
        assert db.get(Wallet, user_id).balance_kopeks == 380
        assert len(db.scalars(select(Check)).all()) == 1
        assert db.scalar(select(Check)).status == "settled"
        assert db.scalar(select(ProviderTask)).attempts == 4
        assert len(json.loads(db.scalar(select(ProviderTask)).history_json)) == 3
        assert db.scalar(select(CloudResult)).status == "found"


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
