"""Completed results reach the cabinet while a long scan is still running."""

import asyncio
import hashlib
import json

import pytest

from app import agent, billing, control_agent
from app.scanner import orchestrator


def test_active_scan_uploads_results_without_releasing_reservations(monkeypatch):
    calls = []

    async def heartbeat(*_args):
        return {"preferences": {"speed_profile": "balanced"}}

    async def identity():
        return {"id": "owner"}

    async def sync(user_id, device_id):
        calls.append((user_id, device_id))
        raise asyncio.CancelledError

    async def unexpected():
        raise AssertionError("Активный скан не должен освобождать резерв")

    monkeypatch.setattr(agent, "device_id", lambda: "desktop")
    monkeypatch.setattr(agent.billing, "enabled", lambda: True)
    monkeypatch.setattr(agent.billing, "token", lambda: "connected")
    monkeypatch.setattr(agent.billing, "heartbeat", heartbeat)
    monkeypatch.setattr(agent.billing, "identity", identity)
    monkeypatch.setattr(agent.billing, "recover_interrupted_scans", unexpected)
    monkeypatch.setattr(agent.orchestrator, "active_controller", lambda: object())
    monkeypatch.setattr(agent.repo, "get_setting", lambda key, *args: "balanced")
    monkeypatch.setattr(agent, "_sync_results", sync)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(agent.run_agent())
    assert calls == [("owner", "desktop")]


def test_enroll_skips_same_token_and_rejects_changed_token_during_scan(monkeypatch):
    token = "connected"
    marker = hashlib.sha256(token.encode()).hexdigest()
    calls = []
    async def send(*args, **kwargs):
        calls.append((args, kwargs))
        return {"token": "device"}
    monkeypatch.setattr(control_agent.billing, "token", lambda: token)
    monkeypatch.setattr(control_agent.repo, "get_setting", lambda _key: marker)
    monkeypatch.setattr(control_agent.billing, "_request", send)
    asyncio.run(control_agent.enroll())
    assert calls == []

    monkeypatch.setattr(control_agent.repo, "get_setting", lambda _key: "old-marker")
    monkeypatch.setattr(control_agent.orchestrator, "active_controller", lambda: object())
    with pytest.raises(billing.BillingError) as error:
        asyncio.run(control_agent.enroll())
    assert error.value.status_code == 409 and calls == []


def test_tracked_result_sync_blocks_account_change_until_old_owner_finishes(monkeypatch):
    async def scenario():
        lock, entered, release = asyncio.Lock(), asyncio.Event(), asyncio.Event()
        settings, bearer, sent, remote = {}, {"token": "alice"}, [], []
        rows = [{"id": i, "status": "found", "error_message": None,
                 "settings_snapshot_json": json.dumps({"billing_user_id": "alice"})}
                for i in range(1, 102)]
        monkeypatch.setattr(control_agent, "_work_tasks", set())
        monkeypatch.setattr(orchestrator, "scan_start_lock", lambda: lock)
        monkeypatch.setattr(orchestrator, "active_controller", lambda: None)
        monkeypatch.setattr(agent.repo, "get_setting", lambda key, default="": settings.get(key, default))
        monkeypatch.setattr(agent.repo, "set_setting", lambda key, value: settings.__setitem__(key, value))
        monkeypatch.setattr(agent.repo, "cloud_results_after", lambda cursor: [r for r in rows if r["id"] > cursor][:100])
        monkeypatch.setattr(agent, "_payload", lambda row: {"local_result_id": row["id"]})
        monkeypatch.setattr(billing, "token", lambda: bearer["token"])
        async def upload(_device, payload):
            sent.append((bearer["token"], [item["local_result_id"] for item in payload]))
            if len(sent) == 1:
                entered.set()
                await release.wait()
            return {"diagnostics_version": 1}
        monkeypatch.setattr(agent.billing, "upload_cloud_results", upload)
        task = control_agent._track_work(asyncio.create_task(agent._sync_results("alice", "desktop")))
        await entered.wait()
        with pytest.raises(billing.BillingError) as error:
            async with billing.account_change():
                bearer["token"] = "bob"
                remote.append("exchange")
        assert error.value.status_code == 409 and remote == []
        release.set()
        await task
        assert [owner for owner, _ids in sent] == ["alice", "alice"]
        async with billing.account_change():
            bearer["token"] = "bob"
            remote.append("exchange")
        assert remote == ["exchange"]
    asyncio.run(scenario())


def test_cloud_payload_keeps_local_answer_but_limits_upload_fields():
    row = {
        "settings_snapshot_json": "{}", "query_id": 1, "service": "google_aio",
        "status": "found", "id": 1, "project_id": 2, "project_name": "Project",
        "brand_name": "Brand", "query_text": "Query", "group_tag": None,
        "scan_date": "2026-09-26", "mention_types_json": "[]",
        "evidence_quote": "q" * 12001, "answer_text": "a" * 60001,
        "sources_json": json.dumps(["https://example.org"] * 71 + ["invalid"]),
    }
    payload = agent._payload(row)
    assert len(payload["sources"]) == 50
    assert len(payload["answer_text"]) == 60000
    assert len(payload["evidence_quote"]) == 12000
    assert payload["error_message"] is None
    assert agent._payload({**row, "error_message": None})["error_message"] is None
    assert agent._payload({**row, "error_message": "x" * 1200})["error_message"] == "x" * 1000


def test_historical_diagnostics_are_bounded_acknowledged_and_account_scoped(monkeypatch):
    settings = {"cloud_result_cursor:owner": "105"}
    def row(i, owner="owner", error="reason"):
        return {"id": i, "status": "error", "error_message": error,
                "settings_snapshot_json": json.dumps({"billing_user_id": owner})}
    rows = [row(i, "other" if i == 2 else "owner", None if i == 3 else "reason") for i in range(1, 107)]
    sent = []
    response = {}
    async def upload(device, payload):
        sent.append((device, payload))
        if response.get("fail"):
            raise agent.billing.BillingError("offline")
        return response
    monkeypatch.setattr(agent.repo, "get_setting", lambda key, default="": settings.get(key, default))
    monkeypatch.setattr(agent.repo, "set_setting", lambda key, value: settings.__setitem__(key, value))
    monkeypatch.setattr(agent.repo, "cloud_results_after", lambda cursor: [r for r in rows if r["id"] > cursor][:100])
    monkeypatch.setattr(agent, "_payload", lambda row: {"local_result_id": row["id"]})
    monkeypatch.setattr(agent.billing, "upload_cloud_results", upload)
    key = "cloud_diagnostic_cursor:v1:owner:desktop"
    # Normal new rows sync first, but an old server cannot acknowledge backfill.
    asyncio.run(agent._sync_results("owner", "desktop"))
    assert settings["cloud_result_cursor:owner"] == "106" and key not in settings
    assert sent[-1][1][0] == {"local_result_id": 1}
    assert len(sent[-1][1]) == 98
    response["fail"] = True
    with pytest.raises(agent.billing.BillingError):
        asyncio.run(agent._sync_results("owner", "desktop"))
    assert key not in settings
    response.clear(); response["diagnostics_version"] = 1
    asyncio.run(agent._sync_results("owner", "desktop"))
    assert settings[key] == "100"
    asyncio.run(agent._sync_results("owner", "desktop"))
    assert settings[key] == "106" and settings["cloud_result_cursor:owner"] == "106"
    count = len(sent)
    asyncio.run(agent._sync_results("owner", "desktop"))
    assert len(sent) == count
