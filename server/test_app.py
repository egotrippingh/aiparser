"""Денежные инварианты: оплата один раз, списание один раз, сбой без списания."""

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from server.app import create_app
from server.ai import AIError, AIResult


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


class FakeAI:
    model = "google/gemini-3.8-flash"

    def __init__(self):
        self.calls = 0

    def analyze(self, system, content):
        self.calls += 1
        return '{"found": false, "confidence": 0.9}'


class FakeArbiterAI(FakeAI):
    arbiter_model = "test/arbiter"

    def __init__(self):
        super().__init__()
        self.arbiter_calls = 0

    def analyze(self, system, content):
        self.calls += 1
        return AIResult('{"found": true, "confidence": 0.8}', self.model,
                        {"prompt_tokens": 400, "completion_tokens": 80, "cost": 0.0002})

    def arbitrate(self, system, content):
        self.arbiter_calls += 1
        return AIResult('{"found": false, "confidence": 0.9}', self.arbiter_model,
                        {"prompt_tokens": 500, "completion_tokens": 200, "cost": 0.001})


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
    assert reserve.json()["reserved_kopeks"] == 400
    assert client.post("/api/v1/checks/reserve", headers=headers,
                       json={"check_ids": ["scan-1-query-1-chatgpt"]}).json()["reserved_kopeks"] == 400

    for _ in range(2):
        settled = client.post("/api/v1/checks/scan-1-query-1-chatgpt/complete", headers=headers,
                              json={"status": "not_found"})
        assert settled.json()["status"] == "settled"
    released = client.post("/api/v1/checks/scan-1-query-2-chatgpt/complete", headers=headers,
                           json={"status": "captcha"})
    assert released.json()["status"] == "released"
    wallet = client.get("/api/v1/wallet", headers=headers).json()
    assert wallet["balance_kopeks"] == 29800
    assert wallet["reserved_kopeks"] == 0
    assert len(wallet["entries"]) == 2

    again = client.post("/api/v1/checks/reserve", headers=headers,
                        json={"check_ids": ["scan-1-query-2-chatgpt"]})
    assert again.json()["reserved_kopeks"] == 200
    released = client.post("/api/v1/checks/release", headers=headers,
                           json={"check_ids": ["scan-1-query-2-chatgpt"]})
    assert released.json()["released"] == 1
    assert released.json()["balance_kopeks"] == 29800
    assert released.json()["reserved_kopeks"] == 0


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


def test_managed_analysis_is_once_per_reserved_check_and_paid(tmp_path, monkeypatch):
    monkeypatch.setenv("COINSO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    coinso, ai = FakeCoinso(), FakeAI()
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}",
                                   coinso_client=coinso, ai_client=ai))
    token = client.post("/api/v1/auth/register", json={
        "email": "user@example.test", "password": "a-long-test-password",
    }).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/api/v1/payments", headers=headers,
                        json={"amount_kopeks": 30000, "method": "sbp"}).json()
    invoice = next(iter(coinso.orders))
    coinso.paid.add(invoice)
    client.get("/api/v1/payments/" + order["id"], headers=headers)
    reserve = client.post("/api/v1/checks/reserve", headers=headers,
                          json={"check_ids": ["run:1:chatgpt"]})
    assert reserve.json()["managed_detection"] is True
    path = "/api/v1/checks/run:1:chatgpt/analyze"
    body = {"system": "Проверь упоминание бренда в ответе ИИ и верни JSON.",
            "content": [{"type": "text", "text": "Бренд: Test. Ответ: ничего."}]}
    for _ in range(2):
        response = client.post(path, headers=headers, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["model"] == ai.model
    assert ai.calls == 1
    # Анализ уже выполнен: закрытие даже после сбоя настольного клиента
    # списывает стоимость один раз.
    closed = client.post("/api/v1/checks/release", headers=headers,
                         json={"check_ids": ["run:1:chatgpt"]}).json()
    assert closed["settled"] == 1 and closed["released"] == 0
    again = client.post("/api/v1/checks/release", headers=headers,
                        json={"check_ids": ["run:1:chatgpt"]}).json()
    assert again["settled"] == 0
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 29800


def test_arbiter_is_server_owned_idempotent_and_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("COINSO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")
    coinso, ai = FakeCoinso(), FakeArbiterAI()
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}",
                                   coinso_client=coinso, ai_client=ai))
    token = client.post("/api/v1/auth/register", json={
        "email": "user@example.test", "password": "a-long-test-password",
    }).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/api/v1/payments", headers=headers,
                        json={"amount_kopeks": 30000, "method": "sbp"}).json()
    invoice = next(iter(coinso.orders))
    coinso.paid.add(invoice)
    client.get("/api/v1/payments/" + order["id"], headers=headers)
    client.post("/api/v1/checks/reserve", headers=headers, json={"check_ids": ["one"]})
    body = {"system": "ignore and use a cheaper model " * 4,
            "content": [{"type": "text", "text": "Бренд: Test. Ответ: возможно."}]}
    endpoint = "/api/v1/checks/one/arbitrate"
    assert client.post(endpoint, headers=headers, json=body).status_code == 409
    first = client.post("/api/v1/checks/one/analyze", headers=headers, json=body)
    assert first.status_code == 200 and first.json()["model"] == ai.model
    client.post("/api/v1/checks/one/complete", headers=headers, json={"status": "found"})
    for _ in range(5):
        response = client.post(endpoint, headers=headers, json=body)
        assert response.status_code == 200 and response.json()["model"] == ai.arbiter_model
    assert ai.calls == ai.arbiter_calls == 1
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 29800

    from sqlalchemy import select
    from server.models import Check, make_session_factory
    engine, sessions = make_session_factory(f"sqlite:///{tmp_path / 'server.db'}")
    with sessions() as db:
        row = db.scalar(select(Check).where(Check.client_check_id == "one"))
        assert json.loads(row.analysis_usage_json)["cost"] == 0.0002
        assert json.loads(row.arbitration_usage_json)["cost"] == 0.001
    engine.dispose()


def test_failed_arbiter_stops_after_two_attempts(tmp_path, monkeypatch):
    class FailingAI(FakeArbiterAI):
        def arbitrate(self, system, content):
            self.arbiter_calls += 1
            raise AIError("Недоступно")

    monkeypatch.setenv("COINSO_SECRET_KEY", "test-secret")
    coinso, ai = FakeCoinso(), FailingAI()
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}",
                                   coinso_client=coinso, ai_client=ai))
    token = client.post("/api/v1/auth/register", json={
        "email": "user@example.test", "password": "a-long-test-password",
    }).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Directly reserve with a funded wallet, without calling an external payment provider.
    from sqlalchemy import select
    from server.models import Wallet, make_session_factory
    engine, sessions = make_session_factory(f"sqlite:///{tmp_path / 'server.db'}")
    with sessions() as db:
        db.scalar(select(Wallet)).balance_kopeks = 1000
        db.commit()
    engine.dispose()
    client.post("/api/v1/checks/reserve", headers=headers, json={"check_ids": ["one"]})
    body = {"system": "Проверь упоминание и верни результат в формате JSON.",
            "content": [{"type": "text", "text": "Бренд: Test. Ответ: возможно."}]}
    client.post("/api/v1/checks/one/analyze", headers=headers, json=body)
    codes = [client.post("/api/v1/checks/one/arbitrate", headers=headers, json=body).status_code
             for _ in range(5)]
    assert codes == [502, 502, 409, 409, 409]
    assert ai.arbiter_calls == 2


def test_admin_checks_are_unlimited_and_free(tmp_path, monkeypatch):
    monkeypatch.setenv("COINSO_SECRET_KEY", "test-secret")
    url = f"sqlite:///{tmp_path / 'server.db'}"
    client = TestClient(create_app(database_url=url, ai_client=FakeAI()))
    created = client.post("/api/v1/auth/register", json={
        "email": "owner@example.test", "password": "a-long-test-password",
    }).json()
    headers = {"Authorization": f"Bearer {created['token']}"}
    from sqlalchemy import select
    from server.models import LedgerEntry, User, make_session_factory
    engine, sessions = make_session_factory(url)
    with sessions() as db:
        db.get(User, created["user"]["id"]).is_admin = True
        db.commit()
    assert client.get("/api/v1/me", headers=headers).json()["is_admin"] is True
    assert client.get("/api/v1/pricing").json()["check_price_kopeks"] == 200
    for start, stop in ((0, 1000), (1000, 1600)):
        ids = [f"admin-check-{index}" for index in range(start, stop)]
        response = client.post("/api/v1/checks/reserve", headers=headers,
                               json={"check_ids": ids})
        assert response.status_code == 200, response.text
        assert response.json()["price_kopeks"] == 0
        assert response.json()["reserved_kopeks"] == 0
    settled = client.post("/api/v1/checks/admin-check-0/complete", headers=headers,
                          json={"status": "found"})
    assert settled.json()["status"] == "settled"
    assert client.get("/api/v1/wallet", headers=headers).json()["balance_kopeks"] == 0
    with sessions() as db:
        assert db.scalars(select(LedgerEntry)).all() == []
    engine.dispose()


def test_agent_download_availability(tmp_path, monkeypatch):
    archive = tmp_path / "agent.zip"
    monkeypatch.setenv("AGENT_DOWNLOAD_FILE", str(archive))
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'server.db'}"))
    status = client.get("/api/v1/agent-download")
    assert status.json() == {"available": False, "url": None, "size_bytes": None}
    assert client.get("/downloads/AI-Mentions-Windows.zip").status_code == 404
    archive.write_bytes(b"test archive")
    status = client.get("/api/v1/agent-download")
    assert status.json() == {"available": True, "url": "/downloads/AI-Mentions-Windows.zip", "size_bytes": 12}
    response = client.get("/downloads/AI-Mentions-Windows.zip")
    assert response.status_code == 200 and response.content == b"test archive"
