"""Screenshots must be private, bounded, and safe to retry."""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from app import billing, config
from app.db import repo
from server.app import create_app


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def put(self, key, data):
        self.objects[key] = data

    def download_url(self, key):
        return f"https://storage.example/{key}?signed=1"


def test_private_screenshot_upload_and_retry(tmp_path):
    db_path = tmp_path / "accounts.db"
    storage = FakeStorage()
    client = TestClient(create_app(database_url=f"sqlite:///{db_path}",
                                   screenshot_storage=storage))

    def account(email):
        response = client.post("/api/v1/auth/register", json={
            "email": email, "password": "a-long-password-123",
        })
        assert response.status_code == 201
        return {"Authorization": f"Bearer {response.json()['token']}"}, response.json()["user"]["id"]

    owner, owner_id = account("owner@example.com")
    stranger, _ = account("other@example.com")
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE wallets SET balance_kopeks = 500 WHERE user_id = ?", (owner_id,))

    check_id = "run:1:chatgpt"
    path = f"/api/v1/checks/{check_id}/screenshot"
    assert client.post("/api/v1/checks/reserve", headers=owner,
                       json={"check_ids": [check_id]}).status_code == 200
    data = b"RIFF\x04\x00\x00\x00WEBPdata"
    assert client.put(path, headers=owner, content=data).status_code == 404
    assert client.post(f"/api/v1/checks/{check_id}/complete", headers=owner,
                       json={"status": "found"}).status_code == 200
    assert client.put(path, headers=stranger, content=data).status_code == 404
    assert client.put(path, headers=owner, content=b"not-webp").status_code == 422
    assert client.put(path, headers=owner, content=data).status_code == 200
    assert client.put(path, headers=owner, content=data).status_code == 200
    assert len(storage.objects) == 1
    assert list(storage.objects.values()) == [data]

    assert client.get("/api/v1/screenshots", headers=stranger).json() == {"screenshots": []}
    assert client.get(f"/api/v1/screenshots/{check_id}/url", headers=stranger).status_code == 404
    assert client.get(f"/api/v1/screenshots/{check_id}/url", headers=owner).json()["url"].startswith(
        "https://storage.example/screenshots/"
    )
    assert client.get("/api/v1/screenshots", headers=owner).json()["screenshots"][0]["check_id"] == check_id
    old_date = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE screenshots SET created_at = ?", (old_date,))
    assert client.get("/api/v1/screenshots", headers=owner).json() == {"screenshots": []}
    assert client.get(f"/api/v1/screenshots/{check_id}/url", headers=owner).status_code == 404


def test_screenshot_size_limit(tmp_path):
    # The limit is checked while streaming, before anything reaches S3.
    db_path = tmp_path / "accounts.db"
    storage = FakeStorage()
    client = TestClient(create_app(database_url=f"sqlite:///{db_path}",
                                   screenshot_storage=storage))
    response = client.post("/api/v1/auth/register", json={
        "email": "owner@example.com", "password": "a-long-password-123",
    })
    token = {"Authorization": f"Bearer {response.json()['token']}"}
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE wallets SET balance_kopeks = 500")
    client.post("/api/v1/checks/reserve", headers=token, json={"check_ids": ["oversize"]})
    client.post("/api/v1/checks/oversize/complete", headers=token, json={"status": "found"})
    data = b"RIFF\x04\x00\x00\x00WEBP" + b"x" * (8 * 1024 * 1024)
    assert client.put("/api/v1/checks/oversize/screenshot", headers=token,
                      content=data).status_code == 413
    assert storage.objects == {}


def test_desktop_upload_queue_survives_server_failure(tmp_path, monkeypatch):
    old_conn = getattr(repo._local, "conn", None)
    if old_conn is not None:
        old_conn.close()
        del repo._local.conn
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "local.db")
    monkeypatch.setattr(config, "SCREENSHOTS_DIR", tmp_path / "shots")
    monkeypatch.setattr(config, "ACCOUNT_URL", "https://account.example")
    monkeypatch.setattr(billing, "token", lambda: "desktop-session")
    repo.init_db()
    shot = config.SCREENSHOTS_DIR / "1" / "today.webp"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"RIFF\x04\x00\x00\x00WEBPdata")
    repo.queue_screenshot("run:1:chatgpt", "1/today.webp")

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.is_error = status_code >= 400

    class Client:
        status = 503

        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def put(self, url, *, content, headers):
            assert url.endswith("/checks/run:1:chatgpt/screenshot")
            assert content == shot.read_bytes()
            assert headers["Authorization"] == "Bearer desktop-session"
            return Response(self.status)

    monkeypatch.setattr(billing.httpx, "AsyncClient", Client)
    try:
        try:
            asyncio.run(billing.flush_screenshot_outbox())
        except billing.ScreenshotError:
            pass
        else:
            raise AssertionError("503 must keep the upload queued")
        assert len(repo.pending_screenshots()) == 1
        Client.status = 200
        monkeypatch.setattr(billing, "_screenshot_retry_after", 0)
        asyncio.run(billing.flush_screenshot_outbox())
        assert repo.pending_screenshots() == []
        assert shot.exists()
    finally:
        repo._local.conn.close()
        del repo._local.conn


def test_desktop_upload_stops_when_token_changes(tmp_path, monkeypatch):
    old_conn = getattr(repo._local, "conn", None)
    if old_conn is not None:
        old_conn.close()
        del repo._local.conn
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "local.db")
    monkeypatch.setattr(config, "SCREENSHOTS_DIR", tmp_path / "shots")
    monkeypatch.setattr(config, "ACCOUNT_URL", "https://account.example")
    monkeypatch.setattr(billing.secrets_store, "unprotect", lambda value: value)
    monkeypatch.setattr(billing, "_screenshot_retry_after", 0)
    repo.init_db()
    repo.set_setting(billing.TOKEN_KEY, "old")
    for name in ("one.webp", "two.webp"):
        path = config.SCREENSHOTS_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"RIFF\x04\x00\x00\x00WEBPdata")
    repo.queue_screenshot("run:1:chatgpt", "one.webp")
    repo.queue_screenshot("run:2:chatgpt", "two.webp")
    sent = []

    class Response:
        status_code = 200
        is_error = False

    class Client:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def put(self, _url, *, content, headers):
            sent.append(headers["Authorization"])
            repo.set_setting(billing.TOKEN_KEY, "new")
            return Response()

    monkeypatch.setattr(billing.httpx, "AsyncClient", Client)
    try:
        asyncio.run(billing.flush_screenshot_outbox(pinned="old"))
        assert sent == ["Bearer old"]
        assert repo.pending_screenshots() == [{"check_id": "run:2:chatgpt", "local_path": "two.webp"}]
    finally:
        repo._local.conn.close()
        del repo._local.conn


def test_screenshot_flush_cursor_reaches_later_good_row_after_persistent_404s(tmp_path, monkeypatch):
    old_conn = getattr(repo._local, "conn", None)
    if old_conn is not None:
        old_conn.close()
        del repo._local.conn
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "local.db")
    monkeypatch.setattr(config, "SCREENSHOTS_DIR", tmp_path / "shots")
    monkeypatch.setattr(config, "ACCOUNT_URL", "https://account.example")
    monkeypatch.setattr(billing, "token", lambda: "owner-token")
    monkeypatch.setattr(billing.secrets_store, "unprotect", lambda value: value)
    monkeypatch.setattr(billing, "_screenshot_retry_after", 0)
    monkeypatch.setattr(billing, "_screenshot_cursor", "")
    repo.init_db()
    repo.set_setting(billing.TOKEN_KEY, "owner-token")
    for number in range(20, -1, -1):
        name = f"bad-{number:02}.webp"
        (config.SCREENSHOTS_DIR / name).parent.mkdir(parents=True, exist_ok=True)
        (config.SCREENSHOTS_DIR / name).write_bytes(b"RIFF\x04\x00\x00\x00WEBPdata")
        repo.queue_screenshot(f"run:bad-{number:02}:chatgpt", name)
    (config.SCREENSHOTS_DIR / "good.webp").write_bytes(b"RIFF\x04\x00\x00\x00WEBPdata")
    repo.queue_screenshot("run:good:chatgpt", "good.webp")
    uploaded = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.is_error = status_code >= 400

    class Client:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def put(self, url, **_kwargs):
            uploaded.append(url)
            return Response(200 if "run:good:" in url else 404)

    monkeypatch.setattr(billing.httpx, "AsyncClient", Client)
    try:
        asyncio.run(billing.flush_screenshot_outbox(limit=20, pinned="owner-token"))
        asyncio.run(billing.flush_screenshot_outbox(limit=20, pinned="owner-token"))
        assert any("run:good:" in url for url in uploaded)
        assert len(repo.pending_screenshots()) == 21
    finally:
        repo._local.conn.close()
        del repo._local.conn


def test_locked_screenshot_stays_queued(tmp_path, monkeypatch):
    old_conn = getattr(repo._local, "conn", None)
    if old_conn is not None:
        old_conn.close()
        del repo._local.conn
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "local.db")
    monkeypatch.setattr(config, "SCREENSHOTS_DIR", tmp_path / "shots")
    monkeypatch.setattr(config, "ACCOUNT_URL", "https://account.example")
    monkeypatch.setattr(billing, "token", lambda: "desktop-session")
    monkeypatch.setattr(billing, "_screenshot_retry_after", 0)
    repo.init_db()
    shot = config.SCREENSHOTS_DIR / "locked.webp"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"RIFF\x04\x00\x00\x00WEBPdata")
    repo.queue_screenshot("run:1:chatgpt", "locked.webp")
    monkeypatch.setattr(type(shot), "read_bytes", lambda _path: (_ for _ in ()).throw(PermissionError("locked")))
    try:
        with pytest.raises(billing.ScreenshotError):
            asyncio.run(billing.flush_screenshot_outbox())
        assert repo.pending_screenshots() == [{"check_id": "run:1:chatgpt", "local_path": "locked.webp"}]
    finally:
        repo._local.conn.close()
        del repo._local.conn
