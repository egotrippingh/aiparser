from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from server.app import create_app
from server.mailer import MailDeliveryError, PasswordMailer
from server.models import AuthFailure, EmailRegistration, SessionToken, User, Wallet, utcnow
from server.security import token_hash
from server.test_cloud_scans import postgres_url


EMAIL = "new@example.test"
CREDS = {"email": EMAIL, "password": "long-test-password-123"}


class Mailer:
    def __init__(self, error=None):
        self.messages = []
        self.error = error

    def send_verification(self, email, code):
        self.messages.append((email, code))
        if self.error:
            raise self.error


def setup(tmp_path, monkeypatch, *, url=None, error=None):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setattr("server.app.secrets.randbelow", lambda _: 7)
    mailer = Mailer(error)
    app = create_app(database_url=url or f"sqlite:///{tmp_path / 'registration.db'}", password_mailer=mailer)
    return TestClient(app), mailer, app.state.payment_sessions


def request_code(client, email=EMAIL):
    return client.post("/api/v1/auth/registration/code", json={"email": email})


def proof(client):
    response = request_code(client)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return {**CREDS, "ticket": response.json()["ticket"], "code": "000007"}


def test_email_proof_required_and_single_use(tmp_path, monkeypatch, caplog):
    client, mailer, sessions = setup(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/register", json=CREDS).status_code == 422
    body = proof(client)
    assert mailer.messages == [(EMAIL, "000007")]
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/auth/login", json=CREDS).status_code == 401
    with sessions() as db:
        row = db.scalar(select(EmailRegistration))
        assert row.code_hash == token_hash(body["ticket"] + ":000007")
        assert row.token_hash != body["ticket"]
        assert db.scalar(select(func.count(User.id))) == 0
        assert db.scalar(select(func.count(Wallet.user_id))) == 0
    registered = client.post("/api/v1/auth/register", json=body)
    assert registered.status_code == 201, registered.text
    assert registered.json()["user"]["email"] == EMAIL
    assert client.post("/api/v1/auth/register", json=body).status_code == 400
    assert client.post("/api/v1/auth/login", json=CREDS).status_code == 200
    assert body["ticket"] not in caplog.text and "000007" not in caplog.text


@pytest.mark.parametrize("change", [{"code": "123456"}, {"email": "other@example.test"},
                                  {"ticket": "z" * 43}])
def test_wrong_proof_cannot_create_account(tmp_path, monkeypatch, change):
    client, _, sessions = setup(tmp_path, monkeypatch)
    body = proof(client)
    assert client.post("/api/v1/auth/register", json={**body, **change}).status_code == 400
    with sessions() as db:
        assert db.scalar(select(func.count(User.id))) == 0
    assert client.post("/api/v1/auth/register", json=body).status_code == 201


def test_five_wrong_attempts_expiry_and_resend(tmp_path, monkeypatch):
    client, mailer, sessions = setup(tmp_path, monkeypatch)
    body = proof(client)
    assert request_code(client).status_code == 429
    for _ in range(5):
        assert client.post("/api/v1/auth/register", json={**body, "code": "999999"}).status_code == 400
    assert client.post("/api/v1/auth/register", json=body).status_code == 400
    with sessions() as db:
        row = db.scalar(select(EmailRegistration))
        assert row.attempts == 5
        row.created_at = utcnow() - timedelta(minutes=2)
        db.commit()
    newer = proof(client)
    assert newer["ticket"] != body["ticket"]
    with sessions() as db:
        db.execute(update(EmailRegistration).values(expires_at=utcnow() - timedelta(seconds=1)))
        db.commit()
    assert client.post("/api/v1/auth/register", json=newer).status_code == 400
    assert len(mailer.messages) == 2


def test_old_ticket_survives_resend_but_second_account_is_impossible(tmp_path, monkeypatch):
    client, _, sessions = setup(tmp_path, monkeypatch)
    first = proof(client)
    with sessions() as db:
        db.execute(update(EmailRegistration).values(created_at=utcnow() - timedelta(minutes=2)))
        db.commit()
    second = proof(client)
    assert client.post("/api/v1/auth/register", json=first).status_code == 201
    assert client.post("/api/v1/auth/register", json=second).status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count(User.id))) == 1


@pytest.mark.parametrize("extra,expected", [({"promo_code": "UNKNOWN"}, 404), ({"connect_id": "a" * 32}, 410)])
def test_failure_keeps_proof_and_does_not_create_partial_account(tmp_path, monkeypatch, extra, expected):
    client, _, sessions = setup(tmp_path, monkeypatch)
    body = proof(client)
    result = client.post("/api/v1/auth/register", json={**body, **extra})
    assert result.status_code == expected, result.text
    with sessions() as db:
        assert db.scalar(select(func.count(User.id))) == 0
        assert db.scalar(select(func.count(Wallet.user_id))) == 0
        assert db.scalar(select(func.count(SessionToken.token_hash))) == 0
        assert db.get(EmailRegistration, token_hash(body["ticket"])) is not None
    assert client.post("/api/v1/auth/register", json=body).status_code == 201


@pytest.mark.parametrize("uncertain", [False, True])
def test_smtp_failure_is_not_success_and_preserves_limits(tmp_path, monkeypatch, caplog, uncertain):
    client, _, sessions = setup(tmp_path, monkeypatch, error=MailDeliveryError(uncertain=uncertain))
    response = request_code(client)
    assert response.status_code == 503 and "ticket" not in response.json()
    assert request_code(client).status_code == 429
    assert "000007" not in caplog.text
    with sessions() as db:
        assert db.scalar(select(func.count(User.id))) == 0


@pytest.mark.parametrize("email", ["one,two@example.test", "one@example.test,two@example.test", "Name <one@example.test>"])
def test_rejects_multiple_mailboxes(tmp_path, monkeypatch, email):
    client, mailer, _ = setup(tmp_path, monkeypatch)
    assert request_code(client, email).status_code == 422
    assert mailer.messages == []


def test_smtp_unconfigured_has_no_registration_bypass(tmp_path, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'no-mail.db'}"))
    assert request_code(client).status_code == 503
    assert client.post("/api/v1/auth/register", json=CREDS).status_code == 422
    assert client.post("/api/v1/auth/register", json={**CREDS, "ticket": "a" * 43, "code": "000007"}).status_code == 400


def test_existing_account_lookup_spends_rate_budget(tmp_path, monkeypatch):
    client, _, sessions = setup(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/register", json=proof(client)).status_code == 201
    assert request_code(client).status_code == 409
    assert request_code(client).status_code == 409
    assert request_code(client).status_code == 429


def test_verification_email_uses_approved_html_and_embedded_logo(monkeypatch):
    mailer = PasswordMailer("smtp.example.test", 2525, "noreply@airate.tech", "u", "p", "starttls", "https://airate.tech")
    messages = []
    monkeypatch.setattr(mailer, "_send", messages.append)
    mailer.send_verification(EMAIL, "000007")
    message = messages[0]
    assert "000007" in message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "000007" in html and 'align="center"' in html
    assert "10 минут" in html and "Письмо сгенерировано автоматически" in html
    assert 'src="cid:airate-logo"' in html
    assert any(part.get("Content-ID") == "<airate-logo>" for part in message.walk())
    assert message["Auto-Submitted"] == "auto-generated"


def test_postgres_send_and_redeem_races(tmp_path, monkeypatch, postgres_url):
    client, mailer, sessions = setup(tmp_path, monkeypatch, url=postgres_url)
    barrier = Barrier(2)

    def send():
        barrier.wait(timeout=10)
        return request_code(client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send(), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 429]
    assert len(mailer.messages) == 1
    body = {**CREDS, "ticket": next(r for r in responses if r.status_code == 200).json()["ticket"], "code": "000007"}
    barrier = Barrier(2)

    def confirm():
        barrier.wait(timeout=10)
        return client.post("/api/v1/auth/register", json=body).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: confirm(), range(2))) == [201, 400]
    with sessions() as db:
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.scalar(select(func.count(Wallet.user_id))) == 1


def test_postgres_source_budget_serializes_different_emails(tmp_path, monkeypatch, postgres_url):
    from server.auth_limit import record
    client, mailer, sessions = setup(tmp_path, monkeypatch, url=postgres_url)
    with sessions() as db:
        record(db, "registration_code", ["ip:testclient"] * 19)
    barrier = Barrier(2)

    def send(email):
        barrier.wait(timeout=10)
        return request_code(client, email).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(send, ["one@example.test", "two@example.test"])) == [200, 429]
    assert len(mailer.messages) == 1
    with sessions() as db:
        assert db.scalar(select(func.count(AuthFailure.id))) == 21  # 20 source + 1 recipient.


def test_migration_preserves_existing_accounts_sessions_and_balances(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text
    from server.import_sqlite import fingerprint
    from server.migrate import ROOT, upgrade_database

    url = f"sqlite:///{tmp_path / 'old-head.db'}"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "20261015_topup_emails")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("INSERT INTO users(id,email,password_hash,is_admin,created_at) VALUES('old','old@example.test','existing-hash',0,'2026-10-14')"))
        db.execute(text("INSERT INTO wallets(user_id,balance_kopeks) VALUES('old',12345)"))
        db.execute(text("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES('existing-session','old','2026-11-01')"))
    with engine.connect() as db:
        previous = {table: fingerprint([dict(row) for row in db.execute(text(f'SELECT * FROM "{table}"')).mappings()])
                    for table in inspect(db).get_table_names() if table != "alembic_version"}
    upgrade_database(url)
    with engine.connect() as db:
        assert set(inspect(db).get_table_names()) == set(previous) | {"alembic_version", "email_registrations", "project_members"}
        for table, digest in previous.items():
            assert fingerprint([dict(row) for row in db.execute(text(f'SELECT * FROM "{table}"')).mappings()]) == digest
        assert db.scalar(text("SELECT count(*) FROM email_registrations")) == 0
        assert db.scalar(text("SELECT count(*) FROM project_members")) == 0
    engine.dispose()
