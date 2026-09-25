"""Recovery, throttling and legacy data migration checks."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from server.app import create_app
from server.migrate import upgrade_database
from server.models import AuthFailure, Base, User, Wallet, utcnow
from server.security import hash_password


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


def test_legacy_database_upgrade_preserves_account(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.tables.values()
                                          if table.name not in {"auth_failures", "password_resets",
                                                                "scan_preferences", "agent_devices", "cloud_results"}])
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE checks DROP COLUMN analysis_json"))
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
