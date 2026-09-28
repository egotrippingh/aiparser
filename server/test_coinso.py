import hashlib
import hmac
import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.coinso import CoinsoClient, CoinsoError
from server.models import PaymentOrder, User, utcnow
from server.payment_reconcile import PaymentReconciler
from server.test_app import FakeCoinso


def test_provider_contract():
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("methods"):
            assert request.headers["Authorization"] == "Bearer private-secret"
            assert request.url.params["project_id"] == "135269696"
            return httpx.Response(200, json={"success": True, "currency": "RUB", "methods": []})
        payload = json.loads(request.content)
        assert payload["amount"] == 300.01 and payload["method"] == "crypto"
        assert payload["integration_type"] == "standard"
        assert "payment=success" in payload["success_url"] and payload["success_url"].endswith("#/topup")
        return httpx.Response(200, json={"success": True, "invoice_id": "invoice-1", "payment_url": "https://coinso.io/pay/invoice-1"})
    provider = CoinsoClient("https://coinso.io/api", 135269696, "private-secret", httpx.MockTransport(handler))
    provider.payment_methods(); provider.payment_methods()
    provider.create_invoice(order_id="a" * 32, amount_kopeks=30001, method="crypto", email="test@example.test", return_url="https://airate.tech/cabinet/?order=abc#/topup")
    assert len(calls) == 2


@pytest.mark.parametrize("link", ["https://coinso.io:bad/pay/a", "https://evil.test/a", "http://coinso.io/pay/a", "https://coinso.io@evil.test/a"])
def test_provider_rejects_unsafe_payment_urls(link):
    provider = CoinsoClient("https://coinso.io/api", 1, "secret", httpx.MockTransport(lambda r: httpx.Response(200, json={"success": True, "invoice_id": "a", "payment_url": link})))
    with pytest.raises(CoinsoError):
        provider.create_invoice(order_id="a", amount_kopeks=30000, method="sbp", email="a@b.test", return_url="https://airate.tech/cabinet/")


def setup(tmp_path, monkeypatch, provider=None, admin=False, testing=False):
    monkeypatch.setenv("COINSO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv("COINSO_ALLOW_TEST_PAYMENTS", str(testing).lower())
    provider = provider or FakeCoinso()
    app = create_app(database_url=f"sqlite:///{tmp_path / 'payments.db'}", coinso_client=provider)
    client = TestClient(app)
    auth = client.post("/api/v1/auth/register", json={"email": "test@example.test", "password": "long-test-password"}).json()
    if admin:
        with app.state.payment_sessions() as db:
            db.get(User, auth["user"]["id"]).is_admin = True
            db.commit()
    return app, client, {"Authorization": "Bearer " + auth["token"]}, provider


def test_crypto_amount_is_rubles_and_checkout_can_switch_method(tmp_path, monkeypatch):
    app, client, headers, provider = setup(tmp_path, monkeypatch)
    original = provider.invoice_status
    provider.invoice_status = lambda invoice: {**original(invoice), "currency": "usdt_trc20", "payment_method": "crypto"}
    order = client.post("/api/v1/payments", headers=headers, json={"amount_kopeks": 30001, "method": "sbp"}).json()
    invoice = next(iter(provider.orders)); provider.paid.add(invoice)
    for _ in range(2):
        result = client.get("/api/v1/payments/" + order["id"], headers=headers).json()
        assert result["status"] == "paid" and result["method"] == "crypto"
    wallet = client.get("/api/v1/wallet", headers=headers).json()
    assert wallet["balance_kopeks"] == 30001 and len(wallet["entries"]) == 1


def test_test_payment_never_creates_spendable_money(tmp_path, monkeypatch):
    app, client, headers, provider = setup(tmp_path, monkeypatch, admin=True, testing=True)
    order = client.post("/api/v1/payments", headers=headers, json={"amount_kopeks": 30000, "method": "sbp"}).json()
    provider.paid.update(provider.orders)
    assert client.get("/api/v1/payments/" + order["id"], headers=headers).json()["status"] == "test_paid"
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 0


def test_provider_limits_and_non_admin_test_rejected(tmp_path, monkeypatch):
    _, client, headers, provider = setup(tmp_path, monkeypatch, testing=True)
    provider.payment_methods = lambda: {"currency": "RUB", "methods": [{"method": "sbp", "min_amount": 500, "max_amount": 2000, "available": True}]}
    assert client.post("/api/v1/payments", headers=headers, json={"amount_kopeks": 30000, "method": "sbp"}).status_code == 422
    assert not provider.orders
    assert client.post("/api/v1/payments", headers=headers, json={"amount_kopeks": 50000, "method": "sbp"}).status_code == 503


def test_missed_webhook_recovered_without_browser(tmp_path, monkeypatch):
    app, client, headers, provider = setup(tmp_path, monkeypatch)
    order = client.post("/api/v1/payments", headers=headers, json={"amount_kopeks": 30000, "method": "sbp"}).json()
    with app.state.payment_sessions() as db:
        db.get(PaymentOrder, order["id"]).created_at = utcnow() - timedelta(minutes=1)
        db.commit()
    provider.paid.update(provider.orders)
    recovery = PaymentReconciler(app.state.payment_sessions, app.state.reconcile_payment)
    recovery.reconcile_once(); recovery.reconcile_once()
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 30000


@pytest.mark.parametrize("change", [{"custom": "wrong"}, {"invoice_id": "wrong"}, {"currency": "USD"}, {"amount": "299.99"}])
def test_verified_status_must_match_every_invoice_field(tmp_path, monkeypatch, change):
    _, client, headers, provider = setup(tmp_path, monkeypatch)
    order = client.post("/api/v1/payments", headers=headers, json={"amount_kopeks": 30000, "method": "sbp"}).json()
    provider.paid.update(provider.orders)
    original = provider.invoice_status
    provider.invoice_status = lambda invoice: {**original(invoice), **change}
    assert client.get("/api/v1/payments/" + order["id"], headers=headers).json()["status"] == "pending"
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 0


def test_creation_callback_waits_for_test_flag_and_reuses_pending_invoice(tmp_path, monkeypatch):
    app, client, headers, provider = setup(tmp_path, monkeypatch)
    order = client.post("/api/v1/payments", headers=headers, json={"amount_kopeks": 30000, "method": "sbp"}).json()
    second = client.post("/api/v1/payments", headers=headers, json={"amount_kopeks": 30000, "method": "sbp"}).json()
    assert second["id"] == order["id"] and len(provider.orders) == 1
    invoice = next(iter(provider.orders)); provider.paid.add(invoice)
    with app.state.payment_sessions() as db:
        row = db.get(PaymentOrder, order["id"])
        row.invoice_id = None
        db.commit()
        app.state.reconcile_payment(db, row, invoice)
        assert row.status == "pending"
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 0


@pytest.mark.parametrize("payload", [[], {"event": "payment.success", "custom": 123, "invoice_id": "invoice-1"}])
def test_signed_malformed_webhook_does_not_credit(tmp_path, monkeypatch, payload):
    _, client, headers, _ = setup(tmp_path, monkeypatch)
    raw = json.dumps(payload).encode()
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    assert client.post("/api/v1/webhooks/coinso", content=raw, headers={"X-Signature": signature}).status_code == 400
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 0
