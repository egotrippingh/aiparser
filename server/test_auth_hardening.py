"""Recovery, throttling and legacy data migration checks."""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import event

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from server.app import create_app
from server.migrate import upgrade_database
from server.models import AuthFailure, Base, User, Wallet, utcnow
from server.security import hash_password
from server.test_cloud_scans import postgres_url


@pytest.mark.parametrize("method", ["password", "device", "yandex"])
def test_postgres_reset_during_login_cannot_leave_a_valid_session(tmp_path, monkeypatch, postgres_url, method):
    from server.test_yandex import FakeYandex
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://testserver")
    mailer = FakeMailer()
    client = TestClient(create_app(database_url=postgres_url, yandex_client=FakeYandex(), password_mailer=mailer))
    creds = {"email": "owner@example.test", "password": "old-password-123"}
    account = client.post("/api/v1/auth/register", json=creds).json()
    headers = {"Authorization": "Bearer " + account["token"]}
    if method == "device":
        path = "/api/v1/auth/device/exchange"
        body = {"ticket": client.post("/api/v1/auth/device/code", headers=headers).json()["code"]}
    elif method == "yandex":
        from server.models import OAuthIdentity
        with Session(create_engine(postgres_url)) as db:
            db.add(OAuthIdentity(provider="yandex", subject="yandex-123", user_id=account["user"]["id"]))
            db.commit()
        started = client.get("/api/v1/auth/yandex/start", follow_redirects=False)
        state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
        result = client.get("/api/v1/auth/yandex/callback", params={"state":state,"code":"valid-code"}, follow_redirects=False)
        path, body = "/api/v1/auth/yandex/exchange", {"ticket": parse_qs(urlparse(result.headers["location"]).fragment)["auth_ticket"][0]}
    else:
        path, body = "/api/v1/auth/login", creds
    client.post("/api/v1/auth/password/request", json={"email":creds["email"]})
    reset_token = mailer.messages[-1][1]
    armed = [True]
    def reset_after_first_commit(session):
        if armed[0]:
            armed[0] = False
            assert client.post("/api/v1/auth/password/confirm", json={
                "token":reset_token,"password":"new-password-123"}).status_code == 200
    event.listen(Session, "after_commit", reset_after_first_commit)
    try:
        result = client.post(path, json=body)
    finally:
        event.remove(Session, "after_commit", reset_after_first_commit)
    assert result.status_code == 200, result.text
    assert client.get("/api/v1/me", headers={"Authorization":"Bearer "+result.json()["token"]}).status_code == 401


class FakeMailer:
    def __init__(self):
        self.messages = []

    def send_reset(self, email, token):
        self.messages.append((email, token))


def test_password_reset_is_one_use_and_revokes_sessions(tmp_path, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    mailer = FakeMailer()
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'auth.db'}",
                                   password_mailer=mailer))
    created = client.post("/api/v1/auth/register", json={
        "email": "user@example.test", "password": "old-password-123",
    })
    assert created.status_code == 201
    old_token = created.json()["token"]
    unknown = client.post("/api/v1/auth/password/request", json={"email": "other@example.test"})
    known = client.post("/api/v1/auth/password/request", json={"email": "user@example.test"})
    assert unknown.json() == known.json()
    assert len(mailer.messages) == 1
    token = mailer.messages[0][1]
    assert token not in known.text
    assert client.post("/api/v1/auth/password/confirm", json={
        "token": token, "password": "new-password-123",
    }).status_code == 200
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert client.post("/api/v1/auth/password/confirm", json={
        "token": token, "password": "another-password-123",
    }).status_code == 400
    assert client.post("/api/v1/auth/login", json={
        "email": "user@example.test", "password": "old-password-123",
    }).status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "email": "user@example.test", "password": "new-password-123",
    }).status_code == 200


def test_login_limit_persists_in_database(tmp_path, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    path = tmp_path / "auth.db"
    client = TestClient(create_app(database_url=f"sqlite:///{path}"))
    client.post("/api/v1/auth/register", json={
        "email": "user@example.test", "password": "correct-password-123",
    })
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={
            "email": "user@example.test", "password": "incorrect-password",
        }).status_code == 401
    blocked = client.post("/api/v1/auth/login", json={
        "email": "user@example.test", "password": "correct-password-123",
    })
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "900"
    with Session(create_engine(f"sqlite:///{path}")) as db:
        for row in db.scalars(select(AuthFailure)):
            row.created_at = utcnow() - timedelta(minutes=16)
        db.commit()
    assert client.post("/api/v1/auth/login", json={
        "email": "user@example.test", "password": "correct-password-123",
    }).status_code == 200


def test_password_settings_require_owner_session_current_password_and_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'settings.db'}"), base_url="https://example.test")
    created = client.post("/api/v1/auth/register", json={"email": "owner@test.example", "password": "old-password-123"}).json()
    headers = {"Authorization": "Bearer " + created["token"]}
    body = {"password": "new-password-123", "current_password": "old-password-123"}
    assert client.put("/api/v1/auth/password", json=body).status_code == 401
    assert client.put("/api/v1/auth/password", headers={**headers, "X-AI-Client": "browser", "Origin": "https://other.test"}, json=body).status_code == 403
    device = client.post("/api/v1/control/agent/enroll", headers=headers, json={"device_id": "d"*32, "name": "Test"}).json()
    assert client.put("/api/v1/auth/password", headers={"Authorization":"Bearer "+device["token"]}, json=body).status_code == 403
    assert client.put("/api/v1/auth/password", headers=headers, json={"password":"new-password-123", "current_password":"wrong-password-123"}).status_code == 401
    updated = client.put("/api/v1/auth/password", headers=headers, json=body)
    assert updated.status_code == 200, updated.text
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    assert client.get("/api/v1/me", headers={"Authorization":"Bearer "+device["token"]}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email":"owner@test.example", "password":"new-password-123"}).status_code == 200


def test_yandex_email_recovery_expiry_and_failed_delivery(tmp_path, monkeypatch, caplog):
    from server.models import OAuthIdentity, PasswordReset, make_session_factory
    monkeypatch.delenv("SMTP_HOST", raising=False)
    url = f"sqlite:///{tmp_path / 'recovery.db'}"
    mailer = FakeMailer()
    client = TestClient(create_app(database_url=url, password_mailer=mailer))
    _, sessions = make_session_factory(url)
    with sessions() as db:
        db.add_all([User(id="yandex",email="owner@yandex.test",password_hash="external:yandex"),
                    Wallet(user_id="yandex",balance_kopeks=100),OAuthIdentity(provider="yandex",subject="provider-id",user_id="yandex")])
        db.commit()
    assert client.post("/api/v1/auth/password/request", json={"email":"owner@yandex.test"}).status_code == 200
    email, token = mailer.messages[-1]
    assert email == "owner@yandex.test"
    with sessions() as db:
        db.scalar(select(PasswordReset)).expires_at = utcnow()-timedelta(seconds=1)
        db.commit()
    assert client.post("/api/v1/auth/password/confirm",json={"token":token,"password":"new-password-123"}).status_code == 400
    client.post("/api/v1/auth/password/request",json={"email":email})
    token = mailer.messages[-1][1]
    assert client.post("/api/v1/auth/password/confirm",json={"token":token,"password":"new-password-123"}).status_code == 200
    assert client.post("/api/v1/auth/login",json={"email":email,"password":"new-password-123"}).status_code == 200
    def fail_send(*args):
        raise RuntimeError("private-token-and-recipient-must-not-be-logged")
    monkeypatch.setattr(mailer,"send_reset",fail_send)
    assert client.post("/api/v1/auth/password/request",json={"email":email}).status_code == 200
    assert "private-token-and-recipient" not in caplog.text
    with sessions() as db:
        assert db.scalar(select(PasswordReset)) is None
        assert db.get(Wallet,"yandex").balance_kopeks == 100
        assert db.scalar(select(OAuthIdentity)).user_id == "yandex"


def test_legacy_database_upgrade_preserves_account(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(url)
    from server.migrate import NEW_TABLES
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.tables.values()
                                          if table.name not in NEW_TABLES])
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE checks DROP COLUMN analysis_json"))
        connection.execute(text("ALTER TABLE checks DROP COLUMN free_scan_service"))
        connection.execute(text("ALTER TABLE oauth_attempts DROP COLUMN connect_id"))
        connection.execute(text("ALTER TABLE oauth_attempts DROP COLUMN parent_hash"))
    with Session(engine) as db:
        db.add(User(id="legacy", email="legacy@example.test",
                    password_hash=hash_password("old-password-123")))
        db.add(Wallet(user_id="legacy", balance_kopeks=12345))
        db.commit()
    upgrade_database(url)
    upgrade_database(url)
    with Session(engine) as db:
        assert db.get(User, "legacy").email == "legacy@example.test"
        assert db.get(Wallet, "legacy").balance_kopeks == 12345
    assert "analysis_json" in {column["name"] for column in inspect(engine).get_columns("checks")}
    engine.dispose()
