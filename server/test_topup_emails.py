import hashlib
import hmac
import json
import smtplib
import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from server.app import create_app
from server.mailer import MailDeliveryError, PasswordMailer, topup_message
from server.models import LedgerEntry, PaymentOrder, TopupEmail, Wallet, utcnow
from server.test_app import FakeCoinso
from server.test_cloud_scans import postgres_url
from server.topup_emails import TopupEmailWorker


class Mailer:
    def __init__(self, error=None):
        self.messages = []
        self.error = error

    def send_topup(self, *message):
        if self.error:
            raise self.error
        self.messages.append(message)


def setup_payment(tmp_path, monkeypatch, *, url=None, amount=30001):
    monkeypatch.setenv("COINSO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://airate.tech")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    coinso = FakeCoinso()
    app = create_app(database_url=url or f"sqlite:///{tmp_path / 'mail.db'}", coinso_client=coinso)
    client = TestClient(app)
    account = client.post("/api/v1/auth/register", json={
        "email": "owner@example.test", "password": "a-long-test-password"}).json()
    headers = {"Authorization": "Bearer " + account["token"]}
    response = client.post("/api/v1/payments", headers=headers,
                           json={"amount_kopeks": amount, "method": "sbp"})
    assert response.status_code == 201, response.text
    order_id = response.json()["id"]
    invoice_id = next(iter(coinso.orders))
    return app, client, headers, coinso, order_id, invoice_id


def test_credit_queues_once_without_smtp_and_survives_worker_restart(tmp_path, monkeypatch):
    app, client, headers, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch)
    coinso.paid.add(invoice)
    raw = json.dumps({"event": "payment.success", "custom": order_id, "invoice_id": invoice}).encode()
    assert client.post("/api/v1/webhooks/coinso", content=raw).status_code == 401
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    for _ in range(2):
        assert client.post("/api/v1/webhooks/coinso", content=raw,
                           headers={"X-Signature": signature}).status_code == 200
    assert client.get(f"/api/v1/payments/{order_id}", headers=headers).json()["status"] == "paid"
    sessions = app.state.payment_sessions
    with sessions() as db:
        row = db.get(TopupEmail, order_id)
        assert (row.email, row.amount_kopeks, row.balance_kopeks, row.status, row.attempts) == (
            "owner@example.test", 30001, 30001, "pending", 0)
        assert db.scalar(select(func.count()).select_from(TopupEmail)) == 1
        assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 1
    mailer = Mailer()
    assert TopupEmailWorker(sessions, mailer).send_once()
    assert not TopupEmailWorker(sessions, mailer).send_once()
    assert mailer.messages == [("owner@example.test", order_id, 30001, 30001)]
    with sessions() as db:
        assert db.get(TopupEmail, order_id).sent_at is not None


@pytest.mark.parametrize("outcome", ["pending", "failed", "test", "wrong_amount"])
def test_uncredited_orders_never_queue_mail(tmp_path, monkeypatch, outcome):
    app, client, headers, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch)
    if outcome != "pending":
        coinso.paid.add(invoice)
    original = coinso.invoice_status

    def status(invoice_id):
        result = original(invoice_id)
        if outcome == "test":
            result["test_mode"] = True
        elif outcome == "wrong_amount":
            result["amount"] = "900.00"
        elif outcome == "failed":
            result["status"] = "failed"
        return result

    coinso.invoice_status = status
    assert client.get(f"/api/v1/payments/{order_id}", headers=headers).status_code == 200
    with app.state.payment_sessions() as db:
        assert db.scalar(select(Wallet)).balance_kopeks == 0
        assert db.scalar(select(func.count()).select_from(TopupEmail)) == 0


def test_failed_credit_transaction_also_rolls_back_notification(tmp_path, monkeypatch):
    app, _, _, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch)
    coinso.paid.add(invoice)
    with app.state.payment_sessions() as db:
        def fail_commit(session):
            session.flush()
            raise RuntimeError("simulated commit failure")
        event.listen(db, "before_commit", fail_commit)
        with pytest.raises(RuntimeError):
            app.state.reconcile_payment(db, db.get(PaymentOrder, order_id), invoice)
        db.rollback()
    with app.state.payment_sessions() as db:
        assert db.get(TopupEmail, order_id) is None
        assert db.get(PaymentOrder, order_id).status == "pending"
        assert db.scalar(select(Wallet)).balance_kopeks == 0
        assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 0


@pytest.mark.parametrize("uncertain", [False, True])
def test_delivery_failure_never_reverses_credit_and_only_known_rejection_retries(tmp_path, monkeypatch, uncertain):
    app, client, headers, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch)
    coinso.paid.add(invoice)
    client.get(f"/api/v1/payments/{order_id}", headers=headers)
    mailer = Mailer(MailDeliveryError(uncertain=uncertain))
    worker = TopupEmailWorker(app.state.payment_sessions, mailer)
    assert worker.send_once()
    with app.state.payment_sessions() as db:
        row = db.get(TopupEmail, order_id)
        assert row.status == ("uncertain" if uncertain else "pending")
        assert row.attempts == 1
        assert row.sent_at is None
        assert db.scalar(select(Wallet)).balance_kopeks == 30001
        row.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()
    mailer.error = None
    assert TopupEmailWorker(app.state.payment_sessions, mailer).send_once() is not uncertain
    assert len(mailer.messages) == (0 if uncertain else 1)


def test_claim_commits_before_network_and_another_worker_cannot_send_it(tmp_path, monkeypatch):
    app, client, headers, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch)
    coinso.paid.add(invoice)
    client.get(f"/api/v1/payments/{order_id}", headers=headers)
    mailer = Mailer()
    first = TopupEmailWorker(app.state.payment_sessions, mailer)

    def send(*message):
        # Separate DB connection can read while SMTP runs; claim is already durable.
        with app.state.payment_sessions() as db:
            assert db.get(TopupEmail, order_id).status == "sending"
        assert not TopupEmailWorker(app.state.payment_sessions, Mailer()).send_once()
        raise RuntimeError("unknown transport outcome")

    mailer.send_topup = send
    assert first.send_once()
    assert not TopupEmailWorker(app.state.payment_sessions, Mailer()).send_once()


def test_enabling_mailer_starts_delivery_of_queued_topup_and_stops_worker(tmp_path, monkeypatch):
    app, client, headers, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch)
    coinso.paid.add(invoice)
    client.get(f"/api/v1/payments/{order_id}", headers=headers)
    started = threading.Event()
    workers = []

    def run(self):
        workers.append(self)
        self.send_once()
        started.set()
        self.stop.wait(10)

    monkeypatch.setattr(TopupEmailWorker, "run", run)
    mailer = Mailer()
    restarted = create_app(database_url=f"sqlite:///{tmp_path / 'mail.db'}", password_mailer=mailer)
    with TestClient(restarted):
        assert started.wait(5)
        assert mailer.messages == [("owner@example.test", order_id, 30001, 30001)]
    assert not workers[0].thread.is_alive()


def test_stale_claim_cannot_bypass_another_workers_retry_deadline(tmp_path, monkeypatch):
    app, client, headers, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch)
    coinso.paid.add(invoice)
    client.get(f"/api/v1/payments/{order_id}", headers=headers)
    sessions = app.state.payment_sessions
    engine = sessions.kw["bind"]
    armed = [True]
    late_mailer = Mailer()

    def retry_before_stale_claim(connection, cursor, statement, parameters, context, executemany):
        if armed[0] and statement.startswith("UPDATE topup_emails"):
            armed[0] = False
            refusing = Mailer(MailDeliveryError(uncertain=False))
            assert TopupEmailWorker(sessions, refusing).send_once()

    event.listen(engine, "before_cursor_execute", retry_before_stale_claim)
    try:
        assert not TopupEmailWorker(sessions, late_mailer).send_once()
    finally:
        event.remove(engine, "before_cursor_execute", retry_before_stale_claim)
    assert not late_mailer.messages
    with sessions() as db:
        row = db.get(TopupEmail, order_id)
        assert row.status == "pending" and row.attempts == 1
        assert row.next_attempt_at > utcnow().replace(tzinfo=None)


def test_postgres_confirmation_race_creates_one_credit_and_one_mail(tmp_path, monkeypatch, postgres_url):
    app, _, _, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch, url=postgres_url)
    coinso.paid.add(invoice)
    barrier = threading.Barrier(2, timeout=10)
    errors = []

    def confirm():
        try:
            with app.state.payment_sessions() as db:
                order = db.get(PaymentOrder, order_id)
                barrier.wait()
                app.state.reconcile_payment(db, order, invoice)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=confirm) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()
    assert not errors
    with app.state.payment_sessions() as db:
        assert db.scalar(select(Wallet)).balance_kopeks == 30001
        assert db.scalar(select(func.count()).select_from(TopupEmail)) == 1
        assert db.scalar(select(func.count()).select_from(LedgerEntry)) == 1
    mailer = Mailer()
    barrier = threading.Barrier(2, timeout=10)
    engine = app.state.payment_sessions.kw["bind"]

    def synchronize_claim(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT") and "FROM topup_emails" in statement:
            barrier.wait()

    def send():
        try:
            TopupEmailWorker(app.state.payment_sessions, mailer).send_once()
        except Exception as exc:
            errors.append(exc)

    event.listen(engine, "after_cursor_execute", synchronize_claim)
    threads = [threading.Thread(target=send) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
            assert not thread.is_alive()
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_claim)
    assert not errors
    assert len(mailer.messages) == 1


def test_successful_smtp_then_failed_commit_is_not_resent_after_restart(tmp_path, monkeypatch):
    app, client, headers, coinso, order_id, invoice = setup_payment(tmp_path, monkeypatch)
    coinso.paid.add(invoice)
    client.get(f"/api/v1/payments/{order_id}", headers=headers)
    sessions = app.state.payment_sessions
    mailer = Mailer()
    worker = TopupEmailWorker(sessions, mailer)

    def reject_sent_commit(session):
        row = session.get(TopupEmail, order_id)
        if row.status == "sent":
            raise RuntimeError("database unavailable after SMTP acceptance")

    event.listen(sessions.class_, "before_commit", reject_sent_commit)
    try:
        with pytest.raises(RuntimeError):
            worker.send_once()
    finally:
        event.remove(sessions.class_, "before_commit", reject_sent_commit)
    with sessions() as db:
        assert db.get(TopupEmail, order_id).status == "sending"
    assert not TopupEmailWorker(sessions, mailer).send_once()
    assert len(mailer.messages) == 1


def test_multipart_message_uses_exact_kopeks_escaped_urls_and_embedded_current_logo():
    message = topup_message("noreply@airate.tech", 'https://airate.tech/"&',
                            "owner@example.test", "a" * 32, 123456, 654321)
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "1 234,56 ₽" in plain and "6 543,21 ₽" in html
    assert 'href="https://airate.tech/&quot;&amp;/cabinet/#/topup"' in html
    assert "Спасибо, что пользуетесь AIRate!" in html
    assert "Письмо сгенерировано автоматически" in plain
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["Message-ID"] == f"<topup.{'a' * 32}@airate.tech>"
    image = next(part for part in message.walk() if part.get_content_type() == "image/png")
    assert image["Content-ID"] == "<airate-logo>"
    assert image.get_payload(decode=True).startswith(b"\x89PNG")
    assert "<script" not in html and "https://airate.tech/assets" not in html


def test_upgrade_preserves_existing_credit_without_backfilling_old_receipts(tmp_path):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from server.migrate import upgrade_database
    from server.models import User, make_session_factory

    url = f"sqlite:///{tmp_path / 'previous-release.db'}"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "20261014_account_promos")
    engine, sessions = make_session_factory(url)
    try:
        with sessions() as db:
            db.add(User(id="b" * 32, email="existing@example.test", password_hash="existing-hash"))
            db.flush()
            db.add(Wallet(user_id="b" * 32, balance_kopeks=98765))
            db.add(PaymentOrder(id="c" * 32, user_id="b" * 32, amount_kopeks=98765,
                                method="sbp", status="paid", invoice_id="old-invoice"))
            db.add(LedgerEntry(user_id="b" * 32, amount_kopeks=98765, kind="topup",
                               reference=f"payment:{'c' * 32}"))
            db.commit()
        upgrade_database(url)
        with sessions() as db:
            assert db.get(Wallet, "b" * 32).balance_kopeks == 98765
            assert db.get(User, "b" * 32).password_hash == "existing-hash"
            assert db.get(PaymentOrder, "c" * 32).invoice_id == "old-invoice"
            assert db.scalar(select(LedgerEntry)).amount_kopeks == 98765
            assert db.scalar(select(func.count()).select_from(TopupEmail)) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize("failure,uncertain", [("connect", False), ("reject", False), ("data_timeout", True), ("quit", None)])
def test_smtp_acceptance_is_distinguished_from_quit_and_explicit_refusal(monkeypatch, failure, uncertain):
    class SMTP:
        def __init__(self, *args, **kwargs):
            if failure == "connect":
                raise TimeoutError("connect")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            if failure == "quit":
                raise smtplib.SMTPServerDisconnected("quit")
        def starttls(self, **kwargs):
            pass
        def send_message(self, message):
            if failure == "reject":
                raise smtplib.SMTPDataError(550, b"domain not verified")
            if failure == "data_timeout":
                raise TimeoutError("DATA response")

    monkeypatch.setattr("server.mailer.smtplib.SMTP", SMTP)
    mailer = PasswordMailer("smtp.example.test", 2525, "noreply@airate.tech", "", "", "starttls", "https://airate.tech")
    if uncertain is None:
        mailer.send_topup("owner@example.test", "a" * 32, 30001, 30001)
    else:
        with pytest.raises(MailDeliveryError) as result:
            mailer.send_topup("owner@example.test", "a" * 32, 30001, 30001)
        assert result.value.uncertain is uncertain
