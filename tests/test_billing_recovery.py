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
