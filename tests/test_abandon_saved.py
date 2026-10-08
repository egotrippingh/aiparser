"""The desktop-only abandonment route must not bypass payer or activity checks."""
import asyncio
import json
import threading

from fastapi.testclient import TestClient

from app import agent, billing, config, secrets_store
from app.api import create_app, desktop
from app import control_agent
from app.db import repo
from app.scanner import orchestrator


def _saved(tmp_path, monkeypatch, name="Project"):
    monkeypatch.setattr(repo, "_local", threading.local())
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "abandon.db")
    monkeypatch.setattr(config, "ACCOUNT_URL", "https://account.example")
    monkeypatch.setattr(orchestrator, "_active", {})
    repo.init_db()
    project = repo.create_project(name, "Brand")
    repo.add_queries(project, ["question"])
    query = repo.list_queries(project)[0]
    snapshot = {"billing_user_id": "owner", "billing_reserved_ids": ["run:1:chatgpt"]}
    scan_id = repo.create_scan(project, ["chatgpt"], snapshot)
    repo.save_capture(scan_id, query["id"], "chatgpt", project=repo.get_project(project), query=query,
                      settings=snapshot, check_id="run:1:chatgpt", payer_id="owner", shown=True,
                      answer_text="raw", sources=[], extra={}, screenshot_bytes=b"image", screenshot_path=None)
    repo.capture_state(scan_id, query["id"], "chatgpt", "error")
    return scan_id


def test_configured_desktop_abandonment_checks_owner_and_activity(tmp_path, monkeypatch):
    scan_id = _saved(tmp_path, monkeypatch)
    async def identity(): return {"id": "other"}
    async def flush(_owner): raise AssertionError("must not flush")
    monkeypatch.setattr(desktop.billing, "identity", identity)
    monkeypatch.setattr(desktop.billing, "flush_outbox", flush)
    monkeypatch.setattr(desktop, "work_in_progress", lambda: False, raising=False)
    client = TestClient(create_app())
    response = client.post(f"/api/desktop/scans/{scan_id}/abandon-saved")
    assert response.status_code == 403
    assert repo.capture(scan_id, 1, "chatgpt")["state"] == "error"

    async def owner(): return {"id": "owner"}
    async def sent(_owner): return None
    monkeypatch.setattr(desktop.billing, "identity", owner)
    monkeypatch.setattr(desktop.billing, "flush_outbox", sent)
    monkeypatch.setattr(billing, "token", lambda: "pinned")
    monkeypatch.setattr(orchestrator, "active_controller", lambda: object())
    assert client.post(f"/api/desktop/scans/{scan_id}/abandon-saved").status_code == 409
    assert repo.capture(scan_id, 1, "chatgpt")["state"] == "error"
    monkeypatch.setattr(orchestrator, "active_controller", lambda: None)
    response = client.post(f"/api/desktop/scans/{scan_id}/abandon-saved")
    assert response.status_code == 200, response.text
    assert repo.get_scan(scan_id)["status"] == "abandoned"
    assert repo.capture(scan_id, 1, "chatgpt")["answer_text"] == "raw"
    assert repo.pending_billing() == [{"check_id": "run:1:chatgpt", "status": "release"}]


def test_abandonment_rejects_wrong_origin_and_mixed_payers_without_writes(tmp_path, monkeypatch):
    scan_id = _saved(tmp_path, monkeypatch)
    async def owner(): return {"id": "owner"}
    monkeypatch.setattr(desktop.billing, "identity", owner)
    client = TestClient(create_app())
    monkeypatch.setitem(desktop.STATE, "user", {"id": "owner"})
    assert client.get("/api/desktop/state").json()["saved_scan"] == {"scan_id": scan_id, "saved_answers": 1}
    monkeypatch.setitem(desktop.STATE, "user", {"id": "other"})
    assert client.get("/api/desktop/state").json()["saved_scan"] is None
    monkeypatch.setitem(desktop.STATE, "user", {"id": "owner"})
    assert client.post(f"/api/desktop/scans/{scan_id}/abandon-saved",
                       headers={"Origin": "https://evil.example"}).status_code == 403
    repo._exec("UPDATE captures SET payer_id='other' WHERE scan_id=?", (scan_id,))
    assert client.post(f"/api/desktop/scans/{scan_id}/abandon-saved").status_code == 403
    assert repo.get_scan(scan_id)["status"] == "running"
    assert repo.capture(scan_id, 1, "chatgpt")["state"] == "error"


def test_terminal_marker_replays_after_lost_response(tmp_path, monkeypatch):
    _saved(tmp_path, monkeypatch)
    key = "abandoned_terminal:owner:device:1"
    repo.set_setting(key, secrets_store.protect(json.dumps({
        "run_id": "run", "lease_token": "x" * 30, "owner": "owner", "device_id": "device",
        "scan_id": 1, "total": 1,
    })), is_secret=True)
    async def recovered(_owner): return None
    async def synced(_owner, _device): return None
    calls = []
    async def request(method, path, **_kwargs):
        calls.append((method, path))
        if method == "POST":
            raise billing.BillingError("lost reply", 409)
        return {"state": "failed"}
    monkeypatch.setattr(control_agent.billing, "recover_interrupted_scans", recovered)
    monkeypatch.setattr(control_agent, "_sync_results", synced)
    monkeypatch.setattr(control_agent.billing, "_request", request)
    monkeypatch.setattr(control_agent, "device_id", lambda: "device")
    monkeypatch.setattr(orchestrator, "active_controller", lambda: None)
    asyncio.run(control_agent.maintenance("owner"))
    assert calls == [("POST", "/control/agent/runs/run"), ("GET", "/control/agent/runs/run/status")]
    assert repo.secret_settings("abandoned_terminal:") == []


def test_cloud_abandonment_falls_back_for_stale_state_and_marks_only_trusted_lease(tmp_path, monkeypatch):
    scan_id = _saved(tmp_path, monkeypatch)
    snapshot = json.loads(repo.get_scan(scan_id)["settings_snapshot_json"])
    snapshot["cloud_job_id"] = "cloud-run"
    repo._exec("UPDATE scans SET settings_snapshot_json=? WHERE id=?", (json.dumps(snapshot), scan_id))
    async def owner(): return {"id": "owner"}
    async def sent(_owner): return None
    calls = []
    async def terminal(method, path, **_kwargs):
        calls.append((method, path))
        return {"state": "done"}
    monkeypatch.setattr(desktop.billing, "identity", owner)
    monkeypatch.setattr(desktop.billing, "flush_outbox", sent)
    monkeypatch.setattr(desktop.billing, "_request", terminal)
    monkeypatch.setattr(orchestrator, "active_controller", lambda: None)
    monkeypatch.setattr(control_agent, "work_in_progress", lambda: False)
    monkeypatch.setitem(control_agent.STATE, "job", {"id": "cloud-run", "lease_token": "lease"})
    monkeypatch.setitem(control_agent.STATE, "user", None)
    response = TestClient(create_app()).post(f"/api/desktop/scans/{scan_id}/abandon-saved")
    assert response.status_code == 200 and calls == [("GET", "/control/agent/runs/cloud-run/status")]
    assert repo.secret_settings("abandoned_terminal:") == []

    trusted_id = _saved(tmp_path, monkeypatch, "Trusted")
    snapshot = json.loads(repo.get_scan(trusted_id)["settings_snapshot_json"])
    snapshot["cloud_job_id"] = "cloud-run"
    repo._exec("UPDATE scans SET settings_snapshot_json=? WHERE id=?", (json.dumps(snapshot), trusted_id))
    monkeypatch.setitem(control_agent.STATE, "user", {"id": "owner"})
    response = TestClient(create_app()).post(f"/api/desktop/scans/{trusted_id}/abandon-saved")
    assert response.status_code == 200 and len(repo.secret_settings("abandoned_terminal:")) == 1


def test_cloud_abandonment_rejects_nonterminal_or_missing_lease_without_writes(tmp_path, monkeypatch):
    scan_id = _saved(tmp_path, monkeypatch)
    snapshot = json.loads(repo.get_scan(scan_id)["settings_snapshot_json"])
    snapshot["cloud_job_id"] = "cloud-run"
    repo._exec("UPDATE scans SET settings_snapshot_json=? WHERE id=?", (json.dumps(snapshot), scan_id))
    async def owner(): return {"id": "owner"}
    async def running(*_args, **_kwargs): return {"state": "running"}
    monkeypatch.setattr(desktop.billing, "identity", owner)
    monkeypatch.setattr(desktop.billing, "_request", running)
    monkeypatch.setattr(orchestrator, "active_controller", lambda: None)
    monkeypatch.setattr(control_agent, "work_in_progress", lambda: False)
    monkeypatch.setitem(control_agent.STATE, "job", None)
    assert TestClient(create_app()).post(f"/api/desktop/scans/{scan_id}/abandon-saved").status_code == 409
    assert repo.capture(scan_id, 1, "chatgpt")["state"] == "error" and repo.pending_billing() == []
    async def absent(*_args, **_kwargs): raise billing.BillingError("gone", 404)
    monkeypatch.setattr(desktop.billing, "_request", absent)
    assert TestClient(create_app()).post(f"/api/desktop/scans/{scan_id}/abandon-saved").status_code == 404
    assert repo.capture(scan_id, 1, "chatgpt")["state"] == "error" and repo.pending_billing() == []


def test_abandonment_replaces_error_result_with_fresh_uploadable_evidence(tmp_path, monkeypatch):
    scan_id = _saved(tmp_path, monkeypatch)
    repo._exec("UPDATE captures SET sources_json=? WHERE scan_id=?", (json.dumps(["https://example.test"]), scan_id))
    repo.finalize_capture(scan_id, 1, "chatgpt", "captcha", {
        "mention_types": ["brand"], "confidence": 0.7, "evidence_quote": "quote",
            "answer_text": None, "sources": [],
        "screenshot_path": "shot.webp", "detected_by": "model", "needs_review": True,
        "llm_model": "fixture", "duration_ms": 9, "error_message": "old reason",
    })
    old_id = repo.results_for_scan(scan_id)[0]["id"]
    repo.set_setting("cloud_result_cursor:owner", str(old_id))
    repo.abandon_saved_scan(scan_id, "operator reason")
    result = repo.results_for_scan(scan_id)[0]
    assert result["id"] > old_id and result["error_message"] == "operator reason"
    assert result["answer_text"] == "raw" and result["screenshot_path"] == "shot.webp"
    assert result["sources_json"] == json.dumps(["https://example.test"])
    assert repo.capture(scan_id, 1, "chatgpt")["answer_text"] == "raw"
    repo.set_setting("cloud_diagnostic_cursor:v1:owner:desktop", str(result["id"]))
    uploaded = []
    async def upload(_device, rows):
        uploaded.append([row["local_result_id"] for row in rows])
        return {"diagnostics_version": 1}
    monkeypatch.setattr(agent.billing, "upload_cloud_results", upload)
    asyncio.run(agent._sync_results("owner", "desktop"))
    asyncio.run(agent._sync_results("owner", "desktop"))
    assert uploaded == [[result["id"]]]
    empty_scan = _saved(tmp_path, monkeypatch, "No result")
    repo.abandon_saved_scan(empty_scan, "operator reason")
    empty = repo.results_for_scan(empty_scan)[0]
    assert empty["answer_text"] == "raw" and empty["sources_json"] == "[]"
