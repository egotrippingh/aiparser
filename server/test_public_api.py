import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from server import control
from server.app import create_app
from server.browser_sessions import COOKIE_NAME
from server.models import AccountApiKey, ControlProject, Wallet
from server.security import new_token, token_hash
from server.test_accounts import register_account
from server.test_cloud_scans import postgres_url
from server.test_control import setup
from server.test_reporting import seed_report

KEY = "/api/v1/api-key"
PROJECTS = "/api/v1/public/projects"
CONTROL = "/api/v1/control/projects"


@pytest.fixture(autouse=True)
def api_key_secret(monkeypatch):
    monkeypatch.setenv("AIRATE_API_KEY_SECRET", "a7" * 32)


def issue_key(client: TestClient, headers: dict) -> dict:
    return client.put(KEY, headers=headers, json={"created_at": None}).json()


def test_key_lifecycle_separates_integration_and_cabinet_sessions(tmp_path):
    client, owner, other, devices, _ = setup(tmp_path)
    assert client.get(KEY, headers=owner).json() == {"suffix": None, "created_at": None, "revealable": False}
    expected = {"created_at": None}
    assert client.put(KEY, headers=devices[0], json=expected).status_code == 403
    assert client.get(PROJECTS, headers=owner).status_code == 401

    client.cookies.set(COOKIE_NAME, owner["Authorization"].removeprefix("Bearer "))
    assert client.put(KEY, json=expected).status_code == 403
    browser = {"X-AI-Client": "browser", "Origin": "http://testserver"}
    assert client.put(KEY, headers={**browser, "Origin": "https://outside.example"}, json=expected).status_code == 403
    issued = client.put(KEY, headers=browser, json=expected)
    assert issued.status_code == 200 and issued.headers["Cache-Control"] == "no-store"
    client.cookies.clear()
    raw = issued.json()["key"]
    api = {"Authorization": "Bearer " + raw}
    metadata = client.get(KEY, headers=owner)
    assert metadata.json() == {"suffix": raw[-4:], "created_at": issued.json()["created_at"], "revealable": True}
    assert metadata.headers["Cache-Control"] == "no-store"
    assert client.get(KEY, headers=other).json()["suffix"] is None
    with client.app.state.payment_sessions() as db:
        row = db.get(AccountApiKey, client.get("/api/v1/me", headers=owner).json()["id"])
        assert row.token_hash == token_hash(raw)
    assert client.get(PROJECTS, headers=api).json() == []
    for path in (KEY, CONTROL, "/api/v1/me", "/api/v1/wallet", "/api/v1/admin/users"):
        assert client.get(path, headers=api).status_code == 401
    assert client.put(KEY, headers=api, json=expected).status_code == 401
    assert client.request("DELETE", KEY, headers=api, json=expected).status_code == 401
    assert client.put(KEY, headers=owner, json=expected).status_code == 409

    old_state = {"created_at": issued.json()["created_at"]}
    rotated = client.put(KEY, headers=owner, json=old_state).json()
    api2 = {"Authorization": "Bearer " + rotated["key"]}
    rejected = client.get(PROJECTS, headers=api)
    assert rejected.status_code == 401 and rejected.headers["WWW-Authenticate"] == "Bearer"
    assert rejected.headers["Cache-Control"] == "no-store"
    assert client.get(PROJECTS, headers=api2).status_code == 200
    assert client.request("DELETE", KEY, headers=owner, json=old_state).status_code == 409
    current_state = {"created_at": rotated["created_at"]}
    assert client.request("DELETE", KEY, headers=owner, json=current_state).status_code == 200
    assert client.request("DELETE", KEY, headers=owner, json=current_state).json() == {"suffix": None, "created_at": None, "revealable": False}
    assert client.get(PROJECTS, headers=api2).status_code == 401

    raw3 = issue_key(client, owner)["key"]
    password = client.put("/api/v1/auth/password", headers=owner, json={
        "current_password": "long-test-password-123", "password": "another-long-test-password",
    })
    assert password.status_code == 200
    assert client.get(PROJECTS, headers={"Authorization": "Bearer " + raw3}).status_code == 401


def test_key_reveal_is_owner_only_and_preserves_legacy_key(tmp_path):
    client, owner, other, devices, url = setup(tmp_path)
    issued = issue_key(client, owner)
    version = {"created_at": issued["created_at"]}
    path = KEY + "/reveal"
    assert client.get(KEY, headers=owner).json()["revealable"] is True
    assert client.post(path, json=version).status_code == 401
    assert client.post(path, headers=devices[0], json=version).status_code == 403
    other_key = issue_key(client, other)
    assert client.post(path, headers=other, json=version).status_code == 409
    assert client.post(path, headers=other, json={"created_at": other_key["created_at"]}).json() == {
        "key": other_key["key"],
    }
    api = {"Authorization": "Bearer " + issued["key"]}
    assert client.post(path, headers=api, json=version).status_code == 401
    client.cookies.set(COOKIE_NAME, owner["Authorization"].removeprefix("Bearer "))
    browser = {"X-AI-Client": "browser", "Origin": "http://testserver"}
    assert client.post(path, json=version).status_code == 403
    assert client.post(path, headers={**browser, "Origin": "https://outside.example"}, json=version).status_code == 403
    revealed = client.post(path, headers=browser, json=version)
    assert revealed.json() == {"key": issued["key"]}
    assert revealed.headers["Cache-Control"] == "no-store"
    client.cookies.clear()
    restarted = TestClient(create_app(database_url=url))
    assert restarted.post(path, headers=owner, json=version).json() == {"key": issued["key"]}

    legacy = "airate_" + new_token()
    with client.app.state.payment_sessions() as db:
        owner_id = client.get("/api/v1/me", headers=owner).json()["id"]
        row = db.get(AccountApiKey, owner_id)
        row.token_hash, row.suffix = token_hash(legacy), legacy[-4:]
        db.commit()
    assert client.get(KEY, headers=owner).json()["revealable"] is False
    assert client.post(path, headers=owner, json=version).status_code == 404
    assert client.get(PROJECTS, headers={"Authorization": "Bearer " + legacy}).status_code == 200

    rotated = client.put(KEY, headers=owner, json=version).json()
    assert client.post(path, headers=owner, json=version).status_code == 409
    current = {"created_at": rotated["created_at"]}
    assert client.post(path, headers=owner, json=current).json() == {"key": rotated["key"]}
    assert client.request("DELETE", KEY, headers=owner, json=current).status_code == 200
    assert client.post(path, headers=owner, json=current).status_code == 404


def test_public_scan_quote_retry_commands_and_project_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPELESS_API_KEY", "fake-key")
    client, owner, other, _, _ = setup(tmp_path)
    api = {"Authorization": "Bearer " + issue_key(client, owner)["key"]}
    other_api = {"Authorization": "Bearer " + issue_key(client, other)["key"]}
    created = client.post(PROJECTS, headers=api, json={
        "name": "Project", "brand_name": "Brand", "config": {"services": ["chatgpt"]},
    })
    assert created.status_code == 201
    project = created.json()
    path, cabinet = f"{PROJECTS}/{project['id']}", f"{CONTROL}/{project['id']}"
    assert client.put(cabinet + "/members", headers=owner, json={"email": "other@test.example", "role": "editor"}).status_code == 200
    assert client.get(PROJECTS, headers=other_api).json() == []
    for suffix in ("", "/queries", "/quote", "/runs"):
        assert client.get(path + suffix, headers=other_api).status_code == 404
    assert client.post(path + "/queries", headers=other_api, json={"text": "Foreign"}).status_code == 404
    assert client.delete(cabinet, headers=other).status_code == 403

    quote_fields = ("revision", "provider_state", "free_scans_state")
    quote = client.get(path + "/quote", headers=api).json()
    old_launch = {"request_id": uuid4().hex, **{key: quote[key] for key in quote_fields}}
    added = client.post(path + "/queries", headers=api, json={"text": "  Where   is Brand? ", "group_tag": "Brand"})
    assert added.status_code == 201
    query = added.json()
    assert client.get(path + "/queries", headers=api).json() == [query]
    assert query["text"] == "Where is Brand?"
    assert client.post(path + "/queries", headers=api, json={"text": query["text"]}).status_code == 422
    assert client.post(path + "/runs", headers=api, json=old_launch).status_code == 409

    fields = ("revision", "name", "brand_name", "device_id", "config", "schedule", "queries")
    old_project = {key: project[key] for key in fields}
    assert client.put(cabinet, headers=owner, json=old_project).status_code == 409
    assert client.put(path, headers=api, json={"name": "Incomplete"}).status_code == 422
    fresh = client.get(path, headers=api).json()
    updated = client.put(path, headers=api, json={**{key: fresh[key] for key in fields}, "name": "Renamed"})
    assert updated.status_code == 200 and updated.json()["name"] == "Renamed"
    quote = client.get(path + "/quote", headers=api).json()
    launch = {**old_launch, **{key: quote[key] for key in quote_fields}}
    assert client.post(path + "/runs", headers=api, json={"request_id": uuid4().hex}).status_code == 422
    assert client.post(path + "/runs", headers=api, json=launch).status_code == 402
    assert client.get(path + "/runs", headers=api).json() == []

    with client.app.state.payment_sessions() as db:
        db.get(Wallet, db.get(ControlProject, project["id"]).user_id).balance_kopeks = quote["total_kopeks"]
        db.commit()
    launched = client.post(path + "/runs", headers=api, json=launch)
    assert launched.status_code == 201
    run = launched.json()
    run_path = path + "/runs/" + run["id"]
    assert client.get(run_path, headers=api).json()["state"] == "queued"
    assert client.get(run_path, headers=other_api).status_code == 404
    assert client.post(run_path + "/command", headers=other_api, json={"action": "stop"}).status_code == 404
    assert client.delete(cabinet, headers=owner).status_code == 409
    assert client.delete(f"{path}/queries/{query['id']}", headers=api).status_code == 204
    assert client.post(path + "/runs", headers=api, json=launch).json()["id"] == run["id"]
    assert client.get(path + "/runs", headers=api).json() == [run]
    for _ in range(2):
        assert client.post(run_path + "/command", headers=api, json={"action": "stop"}).status_code == 200
    assert client.get(run_path, headers=api).json()["state"] == "cancelled"
    assert client.delete(cabinet, headers=owner).status_code == 200
    assert client.get(path, headers=api).status_code == 404
    assert client.get(PROJECTS, headers=api).json() == []


def test_answer_date_filter_and_pagination_keep_removed_query_history(tmp_path):
    client, owner, other, _, project, ids, _ = seed_report(tmp_path)
    api = {"Authorization": "Bearer " + issue_key(client, owner)["key"]}
    other_api = {"Authorization": "Bearer " + issue_key(client, other)["key"]}
    path = f"{PROJECTS}/{project['id']}"
    query_id = project["queries"][0]["id"]
    assert client.delete(f"{path}/queries/{query_id}", headers=api).status_code == 204
    assert client.delete(f"{path}/queries/{query_id}", headers=api).status_code == 404
    params = {"date_from": "2026-09-01", "date_to": "2026-09-03", "service": "chatgpt", "limit": 1}
    first = client.get(path + "/answers", params=params, headers=api)
    assert first.status_code == 200 and first.headers["Cache-Control"] == "no-store"
    data = first.json()
    assert data["next_after_id"] == data["items"][0]["id"] == ids[3]
    assert data["items"][0]["query_id"] == query_id
    assert data["items"][0]["answer_text"] == "Original answer"
    assert data["items"][0]["scan_date"] == params["date_from"]
    page = client.get(path + "/answers", params={**params, "after_id": data["next_after_id"]}, headers=api).json()
    assert page["items"][0]["id"] == ids[-1] and page["items"][0]["scan_date"] == params["date_to"]
    assert page["next_after_id"] is None
    assert client.get(path + "/answers", params=params, headers=other_api).status_code == 404
    for invalid in ({"date_from": "2026-09-04"}, {"date_from": "2026-02-30"}, {"limit": 101}, {"after_id": 10**20}):
        assert client.get(path + "/answers", params={**params, **invalid}, headers=api).status_code == 422


def test_archived_project_is_hidden_from_legacy_reports(tmp_path, monkeypatch):
    client, owner, _, _, project, _, _ = seed_report(tmp_path)
    monkeypatch.setattr("server.app.utcnow", lambda: datetime(2026, 9, 3, tzinfo=timezone.utc))
    reports = "/api/v1/reports"
    entries = client.get(reports + "/projects", headers=owner).json()
    selectors = [project["id"], entries[0]["key"]]
    for selector in selectors:
        assert client.get(reports, headers=owner, params={"project": selector}).json()["total"] > 0
    assert client.delete(f"{CONTROL}/{project['id']}", headers=owner).status_code == 200
    assert client.get(reports + "/projects", headers=owner).json() == []
    for selector in selectors:
        assert client.get(reports, headers=owner, params={"project": selector}).json()["total"] == 0


def test_schedule_holds_project_lock_across_adjacent_dst_slots(monkeypatch, postgres_url):
    client = TestClient(create_app(database_url=postgres_url))
    account = register_account(client, json={"email": "schedule@test.example", "password": "long-test-password-123"})
    owner = {"Authorization": "Bearer " + account.json()["token"]}
    project = client.post(CONTROL, headers=owner, json={
        "name": "Project", "brand_name": "Brand",
        "schedule": {"enabled": True, "month_days": [28, 29], "time": "09:00", "timezone": "Europe/Berlin"},
    }).json()
    sessions = client.app.state.payment_sessions
    with sessions.begin() as db:
        row = db.get(ControlProject, project["id"])
        schedule = json.loads(row.schedule_json)
        row.schedule_json = json.dumps({**schedule, "effective_from": "2026-03-01T00:00:00+00:00"})

    attempts = []

    def check_lock(db, row, device_id, key, slot, **kwargs):
        # A separate transaction must be unable to take the same lock as DELETE.
        with sessions() as competing, pytest.raises(DBAPIError) as locked:
            competing.scalar(select(ControlProject.id).where(ControlProject.id == row.id).with_for_update(nowait=True))
        assert locked.value.orig.sqlstate == "55P03"
        attempts.append(slot.day)

    monkeypatch.setattr(control, "create_run", check_lock)
    tick = datetime(2026, 3, 29, 7, 1, tzinfo=timezone.utc)
    control.schedule_tick(sessions, now=tick)
    assert attempts == [28, 29]
    assert client.delete(f"{CONTROL}/{project['id']}", headers=owner).status_code == 200
    control.schedule_tick(sessions, now=tick)
    assert attempts == [28, 29]
