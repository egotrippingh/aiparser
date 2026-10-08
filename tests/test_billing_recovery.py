"""Billing recovery must not release a check while a scan is starting."""

import asyncio

import pytest

from app import agent, billing, config
from app.db import repo


def test_released_saved_result_is_reserved_and_settled(monkeypatch):
    calls = []
    responses = iter([{"status": "released"}, {"status": "settled"}])

    async def complete(check_id, status):
        calls.append(("complete", check_id, status))
        return next(responses)

    async def reserve(check_ids):
        calls.append(("reserve", check_ids))

    monkeypatch.setattr(billing.repo, "pending_billing", lambda: [{"check_id": "saved", "status": "found"}])
    monkeypatch.setattr(billing.repo, "billing_sent", lambda ids: calls.append(("sent", ids)))
    monkeypatch.setattr(billing, "complete", complete)
    monkeypatch.setattr(billing, "reserve", reserve)

    asyncio.run(billing.flush_outbox())
    assert calls == [
        ("complete", "saved", "found"),
        ("reserve", ["saved"]),
        ("complete", "saved", "found"),
        ("sent", ["saved"]),
    ]


def test_idle_agent_rechecks_for_scan_after_waiting_for_start_lock(monkeypatch):
    async def scenario():
        lock = asyncio.Lock()
        await lock.acquire()
        heartbeat_done = asyncio.Event()
        active = False
        recovered = []

        async def heartbeat(*_args):
            heartbeat_done.set()
            return {"preferences": {"speed_profile": "balanced"}}

        async def recover():
            recovered.append(True)

        async def sync(*_args):
            raise asyncio.CancelledError

        monkeypatch.setattr(agent, "device_id", lambda: "desktop")
        monkeypatch.setattr(agent.billing, "enabled", lambda: True)
        monkeypatch.setattr(agent.billing, "token", lambda: "connected")
        monkeypatch.setattr(agent.billing, "heartbeat", heartbeat)
        monkeypatch.setattr(agent.billing, "identity", lambda: asyncio.sleep(0, result={"id": "owner"}))
        monkeypatch.setattr(agent.billing, "recover_interrupted_scans", recover)
        monkeypatch.setattr(agent.orchestrator, "scan_start_lock", lambda: lock)
        monkeypatch.setattr(agent.orchestrator, "active_controller", lambda: object() if active else None)
        monkeypatch.setattr(agent.repo, "get_setting", lambda *_args: "balanced")
        monkeypatch.setattr(agent, "_sync_results", sync)

        task = asyncio.create_task(agent.run_agent())
        await heartbeat_done.wait()
        await asyncio.sleep(0)
        assert recovered == []
        active = True
        lock.release()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert recovered == []

    asyncio.run(scenario())


def test_recovery_reconciles_results_before_releasing(tmp_path, monkeypatch):
    old_conn = getattr(repo._local, "conn", None)
    if old_conn is not None:
        old_conn.close()
        del repo._local.conn
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "recovery.db")
    repo.init_db()
    try:
        project_id = repo.create_project("Recovery", "Brand")
        repo.add_queries(project_id, ["one", "two"])
        first, second = [q["id"] for q in repo.list_queries(project_id)]
        keys = [billing.check_id("run", query_id, "chatgpt") for query_id in (first, second)]
        scan_id = repo.create_scan(project_id, ["chatgpt"], {
            "billing_run_id": "run", "billing_reserved_ids": keys,
        })
        repo.save_result(scan_id, first, "chatgpt", "not_found")
        for key in keys:
            repo.queue_billing(key, "release")

        calls = []

        async def complete(check_key, status):
            calls.append(("complete", check_key, status))
            return {"status": "settled"}

        async def release(check_ids):
            calls.append(("release", list(check_ids)))
            return {"released": len(check_ids)}

        monkeypatch.setattr(billing, "complete", complete)
        monkeypatch.setattr(billing, "release", release)
        asyncio.run(billing.recover_interrupted_scans())

        assert calls == [("complete", keys[0], "not_found"), ("release", [keys[1]])]
        assert repo.pending_billing() == []
        assert repo.get_scan(scan_id)["status"] == "stopped"
    finally:
        repo._local.conn.close()
        del repo._local.conn


@pytest.fixture
def managed(tmp_path, monkeypatch):
    import json
    import threading
    monkeypatch.setattr(repo, "_local", threading.local())
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "managed.db")
    repo.init_db()
    project = repo.create_project("Recovery", "Brand")
    repo.add_queries(project, ["query"])
    qid = repo.list_queries(project)[0]["id"]
    snapshot = {"billing_run_id": "run", "billing_user_id": "owner", "cloud_job_id": "run",
                "cloud_query_map": {str(qid): "remote"}, "billing_reserved_ids": ["run:remote:chatgpt"]}
    scan = repo.create_scan(project, ["chatgpt"], snapshot)
    repo.save_result(scan, qid, "chatgpt", "found", screenshot_path="old.webp")
    repo.finish_scan(scan, status="failed")
    yield {"project": project, "qid": qid, "scan": scan, "snapshot": snapshot,
           "old": f"run:{qid}:chatgpt", "new": "run:remote:chatgpt"}
    repo.conn().close()


def test_managed_repair_is_idempotent_and_handles_screenshot_only(managed, monkeypatch):
    old, new = managed["old"], managed["new"]
    repo.queue_billing(old, "release")
    repo.queue_screenshot(old, "old.webp")
    assert repo.repair_managed_outbox("owner") == 1
    assert repo.pending_billing() == [{"check_id": new, "status": "found"}]
    assert repo.pending_screenshots() == [{"check_id": new, "local_path": "old.webp"}]
    calls = []
    async def complete(key, status):
        calls.append((key, status))
        return {"status": "settled"}
    monkeypatch.setattr(billing, "complete", complete)
    asyncio.run(billing.flush_outbox("owner"))
    asyncio.run(billing.flush_outbox("owner"))
    assert calls == [(new, "found")]
    repo.screenshot_sent(new)
    repo.queue_screenshot(old, "old.webp")
    assert repo.repair_managed_outbox("owner") == 1
    assert repo.pending_screenshots() == [{"check_id": new, "local_path": "old.webp"}]


@pytest.mark.parametrize("conflict", ["source", "canonical", "screenshot"])
def test_conflicts_survive_repair_and_recovery(managed, monkeypatch, conflict):
    old, new = managed["old"], managed["new"]
    repo.set_scan_status(managed["scan"], "running")
    repo.queue_billing(old, "not_found" if conflict == "source" else "found")
    repo.queue_screenshot(old, "old.webp")
    if conflict == "canonical":
        repo.queue_billing(new, "not_found")
    if conflict == "screenshot":
        repo.queue_screenshot(new, "different.webp")
    before = (repo.pending_billing(), repo.pending_screenshots())
    async def unexpected(*args):
        raise AssertionError("Ambiguous work must remain queued")
    monkeypatch.setattr(billing, "complete", unexpected)
    monkeypatch.setattr(billing, "release", unexpected)
    asyncio.run(billing.recover_interrupted_scans("owner"))
    assert (repo.pending_billing(), repo.pending_screenshots()) == before


def test_atomic_repair_rolls_both_queues_back(managed):
    import sqlite3
    old, new = managed["old"], managed["new"]
    repo.queue_billing(old, "found")
    repo.queue_screenshot(old, "old.webp")
    before = (repo.pending_billing(), repo.pending_screenshots())
    repo.conn().execute("CREATE TRIGGER interrupt BEFORE DELETE ON screenshot_outbox BEGIN SELECT RAISE(ABORT, 'interrupted'); END")
    with pytest.raises(sqlite3.IntegrityError, match="interrupted"):
        repo.repair_managed_outbox("owner")
    assert (repo.pending_billing(), repo.pending_screenshots()) == before
    repo.conn().execute("DROP TRIGGER interrupt")
    assert repo.repair_managed_outbox("owner") == 1


@pytest.mark.parametrize("foreign", [True, False])
def test_foreign_or_missing_mapping_is_retained_without_flush(managed, monkeypatch, foreign):
    import json
    snapshot = dict(managed["snapshot"])
    if foreign:
        snapshot["billing_user_id"] = "other"
    else:
        snapshot["cloud_query_map"] = {}
    repo._exec("UPDATE scans SET settings_snapshot_json=?, status='running' WHERE id=?",
               (json.dumps(snapshot), managed["scan"]))
    repo.queue_billing(managed["old"], "found")
    repo.queue_screenshot(managed["old"], "old.webp")
    before = (repo.pending_billing(), repo.pending_screenshots())
    async def unexpected(*args):
        raise AssertionError("Unproven work cannot be sent")
    monkeypatch.setattr(billing, "complete", unexpected)
    monkeypatch.setattr(billing, "release", unexpected)
    asyncio.run(billing.recover_interrupted_scans("owner"))
    assert (repo.pending_billing(), repo.pending_screenshots()) == before
    assert repo.get_scan(managed["scan"])["status"] == "running"
    assert repo.pending_screenshots("owner") == []


def test_actual_runtime_uses_same_cloud_id_for_model_arbiter_and_saved_result(managed, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from app.scanner import orchestrator as mod
    from app.detect.llm import LLMVerdict
    calls = []
    async def ask(*args, **kwargs):
        pass
    async def capture(*args):
        return SimpleNamespace(shown=True, screenshot_bytes=b"fixture", answer_text="Generic answer", sources=[], extra={})
    async def evaluate(**kwargs):
        calls.append(("analyze", kwargs["managed_check_id"]))
        return LLMVerdict(found=True, confidence=0.99, mention_types=["indirect"], quote="Generic answer", model="test")
    async def arbitrate(**kwargs):
        calls.append(("arbiter", kwargs["managed_check_id"]))
        return LLMVerdict(found=True, confidence=0.99, mention_types=["indirect"], quote="Generic answer", model="test")
    async def no_flush(*args):
        pass
    monkeypatch.setattr(mod.imaging, "to_webp", lambda _: b"fixture")
    monkeypatch.setattr(config, "screenshot_dir", lambda *args: tmp_path)
    monkeypatch.setattr(mod.llm_mod, "evaluate", evaluate)
    monkeypatch.setattr(mod.llm_mod, "arbitrate", arbitrate)
    monkeypatch.setattr(billing, "flush_outbox", no_flush)
    monkeypatch.setattr(billing, "flush_screenshot_outbox", no_flush)
    settings = {**managed["snapshot"], "managed_llm": True, "arbiter": True,
                "llm_confidence_threshold": 0.7, "arbiter_model": "test"}
    ctl = mod.ScanController(managed["scan"], managed["project"], 1, "2026-09-29", billing_run_id="run")
    status = asyncio.run(mod._run_one(repo.get_project(managed["project"]), {"id": managed["qid"], "text": "query"},
                                    "chatgpt", SimpleNamespace(ask=ask, capture=capture), None, settings, 1, "", "test", "always", ctl))
    assert status == "found"
    assert calls == [("analyze", managed["new"]), ("arbiter", managed["new"])]
    assert repo.pending_billing() == [{"check_id": managed["new"], "status": "found"}]
    assert repo.pending_screenshots()[0]["check_id"] == managed["new"]


def test_real_server_settlement_after_old_local_id_repair_is_charged_once(tmp_path, monkeypatch):
    import threading
    import uuid
    from sqlalchemy import select
    from server.test_control import setup
    from server.models import Wallet, LedgerEntry, make_session_factory
    from app import control_agent
    client, owner, _, devices, url = setup(tmp_path)
    user_id = client.get("/api/v1/me", headers=owner).json()["id"]
    engine, sessions = make_session_factory(url)
    with sessions() as db:
        db.scalar(select(Wallet).where(Wallet.user_id == user_id)).balance_kopeks = 1000
        db.commit()
    project = client.post("/api/v1/control/projects", headers=owner, json={
        "name": "Recovery", "brand_name": "Brand", "device_id": "a"*32,
        "queries": [{"text": "query"}], "config": {"services": ["chatgpt"]}}).json()
    def launch():
        response = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=owner,
                               json={"request_id": uuid.uuid4().hex})
        assert response.status_code == 201, response.text
        return client.post("/api/v1/control/agent/poll", headers=devices[0], json={}).json()["run"]
    job = launch()
    monkeypatch.setattr(repo, "_local", threading.local())
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "desktop.db")
    repo.init_db()
    try:
        local_id, managed_job = control_agent.materialize(job, user_id)
        qid = repo.list_queries(local_id, only_active=True)[0]["id"]
        snapshot = {"billing_run_id": job["id"], "billing_user_id": user_id, "cloud_job_id": job["id"],
                    "cloud_query_map": managed_job["query_map"]}
        canonical = billing.canonical_check_id(snapshot, qid, "chatgpt")
        old = billing.check_id(job["id"], qid, "chatgpt")
        reserved = client.post("/api/v1/checks/reserve", headers=devices[0], json={"check_ids": [canonical]})
        assert reserved.status_code == 200, reserved.text
        snapshot["billing_reserved_ids"] = [canonical]
        scan = repo.create_scan(local_id, ["chatgpt"], snapshot)
        repo.save_result(scan, qid, "chatgpt", "found")
        repo.finish_scan(scan, status="failed")
        repo.queue_billing(old, "found")
        assert client.post(f"/api/v1/checks/{old}/complete", headers=devices[0], json={"status": "found"}).status_code == 403
        client.post(f"/api/v1/control/agent/runs/{job['id']}", headers=devices[0],
                    json={"lease_token": job["lease_token"], "state": "failed", "error": "old client"})
        async def request(method, path, *, body=None, **kwargs):
            response = client.request(method, "/api/v1"+path, headers=devices[0], json=body)
            if response.is_error:
                raise billing.BillingError(response.json().get("detail"), response.status_code)
            return response.json()
        monkeypatch.setattr(billing, "_request", request)
        asyncio.run(billing.recover_interrupted_scans(user_id))
        asyncio.run(billing.recover_interrupted_scans(user_id))
        assert repo.pending_billing() == []
        wallet = client.get("/api/v1/wallet", headers=owner).json()
        assert wallet["balance_kopeks"] == 1000-reserved.json()["price_kopeks"]
        with sessions() as db:
            assert len(list(db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id)))) == 1
        new_job = launch()
        new_id = billing.check_id(new_job["id"], new_job["snapshot"]["queries"][0]["id"], "chatgpt")
        asyncio.run(billing.recover_interrupted_scans(user_id))
        assert client.post("/api/v1/checks/reserve", headers=devices[0], json={"check_ids": [new_id]}).status_code == 200
        assert client.post("/api/v1/checks/reserve", headers=devices[1], json={"check_ids": [new_id]}).status_code == 403
    finally:
        repo.conn().close()
        engine.dispose()
