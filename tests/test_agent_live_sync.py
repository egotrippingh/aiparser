"""Completed results reach the cabinet while a long scan is still running."""

import asyncio
import json

import pytest

from app import agent


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
