"""Денежные инварианты: оплата один раз, списание один раз, сбой без списания."""

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from server.app import create_app


class FakeCoinso:
    def __init__(self):
        self.orders = {}
        self.paid = set()

    def create_invoice(self, *, order_id, amount_kopeks, method, email, return_url):
        invoice_id = f"invoice-{len(self.orders) + 1}"
        self.orders[invoice_id] = (order_id, amount_kopeks, method)
        return {"success": True, "invoice_id": invoice_id,
                "payment_url": f"https://coinso.io/pay/{invoice_id}"}

    def invoice_status(self, invoice_id):
        order_id, amount, method = self.orders[invoice_id]
        return {"success": True, "invoice_id": invoice_id,
                "status": "paid" if invoice_id in self.paid else "pending",
                "custom": order_id, "amount": f"{amount / 100:.2f}",
                "currency": "RUB", "payment_method": method}


def test_payment_and_checks_are_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("COINSO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    coinso = FakeCoinso()
    app = create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}", coinso_client=coinso)
    client = TestClient(app)

    created = client.post("/api/v1/auth/register", json={
        "email": "USER@example.test", "password": "a-long-test-password",
    })
    assert created.status_code == 201, created.text
    token = created.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/wallet").status_code == 401
    assert client.get("/api/v1/me", headers=headers).json()["email"] == "user@example.test"

    created = client.post("/api/v1/payments", headers=headers,
                          json={"amount_kopeks": 30000, "method": "sbp"})
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    invoice_id = next(iter(coinso.orders))
    assert client.get("/api/v1/payments/" + order_id, headers=headers).json()["status"] == "pending"

    # Подписи нет — даже если тело сообщает об оплате, баланс остаётся нулём.
    payload = {"event": "payment.success", "custom": order_id, "invoice_id": invoice_id}
    raw = json.dumps(payload).encode()
    assert client.post("/api/v1/webhooks/coinso", content=raw).status_code == 401
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 0

    coinso.paid.add(invoice_id)
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    for _ in range(2):
        response = client.post("/api/v1/webhooks/coinso", content=raw,
                               headers={"X-Signature": signature})
        assert response.status_code == 200, response.text
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 30000
    assert client.get("/api/v1/payments/" + order_id, headers=headers).json()["status"] == "paid"

    reserve = client.post("/api/v1/checks/reserve", headers=headers,
                          json={"check_ids": ["scan-1-query-1-chatgpt", "scan-1-query-2-chatgpt"]})
    assert reserve.status_code == 200, reserve.text
    assert reserve.json()["reserved_kopeks"] == 300
    assert client.post("/api/v1/checks/reserve", headers=headers,
                       json={"check_ids": ["scan-1-query-1-chatgpt"]}).json()["reserved_kopeks"] == 300

    for _ in range(2):
        settled = client.post("/api/v1/checks/scan-1-query-1-chatgpt/complete", headers=headers,
                              json={"status": "not_found"})
        assert settled.json()["status"] == "settled"
    released = client.post("/api/v1/checks/scan-1-query-2-chatgpt/complete", headers=headers,
                           json={"status": "captcha"})
    assert released.json()["status"] == "released"
    wallet = client.get("/api/v1/wallet", headers=headers).json()
    assert wallet["balance_kopeks"] == 29850
    assert wallet["reserved_kopeks"] == 0
    assert len(wallet["entries"]) == 2


def test_payment_status_must_match_order(tmp_path, monkeypatch):
    monkeypatch.setenv("COINSO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    coinso = FakeCoinso()
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}", coinso_client=coinso))
    token = client.post("/api/v1/auth/register", json={
        "email": "user@example.test", "password": "a-long-test-password",
    }).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/api/v1/payments", headers=headers,
                        json={"amount_kopeks": 30000, "method": "sbp"}).json()
    invoice_id = next(iter(coinso.orders))
    coinso.paid.add(invoice_id)
    coinso.orders[invoice_id] = (order["id"], 29900, "sbp")
    assert client.get("/api/v1/payments/" + order["id"], headers=headers).json()["status"] == "pending"
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 0
