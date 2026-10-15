"""Яндекс ID: одноразовое состояние, регистрация и безопасная привязка."""

from server.test_accounts import register_account
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.yandex import YandexOAuth, challenge


class FakeYandex:
    client_id = "test-yandex-client"

    def __init__(self):
        self.verifiers = []
        self.profile_data = {"id": "yandex-123", "client_id": self.client_id,
                             "default_email": "owner@example.test"}

    def authorize_url(self, state, verifier):
        self.verifiers.append(verifier)
        return f"https://oauth.yandex.test/authorize?state={state}&code_challenge={challenge(verifier)}"

    def profile(self, code, verifier):
        assert code == "valid-code" and verifier == self.verifiers[-1]
        return self.profile_data


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:8757")
    fake = FakeYandex()
    app = create_app(database_url=f"sqlite:///{tmp_path / 'auth.db'}", yandex_client=fake)
    return TestClient(app, base_url="http://127.0.0.1:8757"), fake


def start(client):
    response = client.get("/api/v1/auth/yandex/start", follow_redirects=False)
    assert response.status_code == 303
    assert "aimt_yandex_state" in response.headers["set-cookie"]
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def callback(client, state):
    return client.get("/api/v1/auth/yandex/callback",
                      params={"state": state, "code": "valid-code"}, follow_redirects=False)


def complete_registration(client, response):
    ticket = parse_qs(urlparse(response.headers["location"]).fragment)["registration_ticket"][0]
    return client.post("/api/v1/auth/yandex/register", json={"ticket": ticket, "password": "a-long-test-password"})


def test_yandex_register_login_and_single_use_ticket(tmp_path, monkeypatch):
    client, fake = setup(tmp_path, monkeypatch)
    assert client.get("/api/v1/auth/providers").json() == {"yandex": True, "password_reset": False}
    state = start(client)
    assert callback(client, "wrong-state").status_code == 400
    response = callback(client, state)
    assert response.status_code == 303
    ticket = parse_qs(urlparse(response.headers["location"]).fragment)["registration_ticket"][0]
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/auth/yandex/exchange", json={"ticket": ticket}).status_code == 401
    assert client.post("/api/v1/auth/yandex/registration", json={"ticket": ticket}).json() == {"email": "owner@example.test"}
    issued = complete_registration(client, response)
    assert issued.status_code == 201
    user = issued.json()["user"]
    assert user["email"] == "owner@example.test"
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {issued.json()['token']}"}).json()["yandex_linked"]
    assert client.post("/api/v1/auth/yandex/exchange", json={"ticket": ticket}).status_code == 401
    assert client.post("/api/v1/auth/yandex/register", json={"ticket": ticket, "password": "another-long-password"}).status_code == 401
    assert callback(client, state).status_code == 400

    second = callback(client, start(client))
    second_ticket = parse_qs(urlparse(second.headers["location"]).fragment)["auth_ticket"][0]
    again = client.post("/api/v1/auth/yandex/exchange", json={"ticket": second_ticket}).json()
    assert again["user"]["id"] == user["id"]
    assert fake.verifiers[0] != fake.verifiers[1]
    assert client.post("/api/v1/auth/login", json={"email": user["email"], "password": "a-long-test-password"}).status_code == 200


def test_existing_email_requires_explicit_link(tmp_path, monkeypatch):
    client, fake = setup(tmp_path, monkeypatch)
    registered = register_account(client, json={
        "email": "owner@example.test", "password": "a-long-test-password",
    }).json()
    headers = {"Authorization": f"Bearer {registered['token']}"}
    collision = callback(client, start(client))
    assert "auth_error=link_required" in collision.headers["location"]
    assert client.get("/api/v1/me", headers=headers).json()["yandex_linked"] is False

    started = client.post("/api/v1/auth/yandex/link/start", headers=headers)
    assert started.status_code == 200
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]
    linked = callback(client, state)
    assert "linked=1" in linked.headers["location"]
    assert client.get("/api/v1/me", headers=headers).json()["yandex_linked"] is True
    logged_in = callback(client, start(client))
    ticket = parse_qs(urlparse(logged_in.headers["location"]).fragment)["auth_ticket"][0]
    yandex_user = client.post("/api/v1/auth/yandex/exchange", json={"ticket": ticket}).json()["user"]
    assert yandex_user["id"] == registered["user"]["id"]
    assert client.post("/api/v1/auth/login", json={
        "email": "owner@example.test", "password": "a-long-test-password",
    }).status_code == 200


def test_link_cannot_take_another_users_yandex_id(tmp_path, monkeypatch):
    client, fake = setup(tmp_path, monkeypatch)
    first = callback(client, start(client))
    owner_id = complete_registration(client, first).json()["user"]["id"]
    second = register_account(client, json={
        "email": "second@example.test", "password": "a-long-test-password",
    }).json()
    started = client.post("/api/v1/auth/yandex/link/start",
                          headers={"Authorization": f"Bearer {second['token']}"})
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]
    linked = callback(client, state)
    assert "auth_error=already_linked" in linked.headers["location"]
    owner_login = callback(client, start(client))
    owner_ticket = parse_qs(urlparse(owner_login.headers["location"]).fragment)["auth_ticket"][0]
    assert client.post("/api/v1/auth/yandex/exchange", json={"ticket": owner_ticket}).json()["user"]["id"] == owner_id


def test_missing_email_does_not_create_account(tmp_path, monkeypatch):
    client, fake = setup(tmp_path, monkeypatch)
    fake.profile_data.pop("default_email")
    response = callback(client, start(client))
    assert "auth_error=email_required" in response.headers["location"]


def test_one_time_code_connects_desktop_without_password(tmp_path, monkeypatch):
    client, fake = setup(tmp_path, monkeypatch)
    first = callback(client, start(client))
    browser = complete_registration(client, first).json()
    headers = {"Authorization": f"Bearer {browser['token']}"}
    assert client.post("/api/v1/auth/device/code").status_code == 401
    old_code = client.post("/api/v1/auth/device/code", headers=headers).json()["code"]
    code = client.post("/api/v1/auth/device/code", headers=headers).json()["code"]
    assert client.post("/api/v1/auth/device/exchange", json={"ticket": old_code}).status_code == 401
    device = client.post("/api/v1/auth/device/exchange", json={"ticket": code})
    assert device.status_code == 200
    assert device.json()["user"]["id"] == browser["user"]["id"]
    assert client.post("/api/v1/auth/device/exchange", json={"ticket": code}).status_code == 401


def test_yandex_http_flow_uses_code_pkce_and_profile_header():
    requests = []

    def responder(request):
        requests.append(request)
        if request.url.path == "/token":
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["authorization_code"]
            assert form["code_verifier"] == ["test-verifier"]
            assert form["client_secret"] == ["test-secret"]
            return httpx.Response(200, json={"access_token": "test-access-token"})
        assert request.headers["Authorization"] == "OAuth test-access-token"
        return httpx.Response(200, json={"id": "123", "client_id": "test-client",
                                          "default_email": "owner@example.test"})

    oauth = YandexOAuth("test-client", "test-secret", "https://example.test/callback",
                        transport=httpx.MockTransport(responder))
    url = urlparse(oauth.authorize_url("state", "test-verifier"))
    params = parse_qs(url.query)
    assert params["response_type"] == ["code"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"] == [challenge("test-verifier")]
    assert oauth.profile("test-code", "test-verifier")["id"] == "123"
    assert len(requests) == 2


def test_yandex_pending_registration_password_promo_expiry_and_connect_are_atomic(tmp_path, monkeypatch):
    from datetime import timedelta
    from sqlalchemy import select
    from server.models import DeviceConnect, User, YandexRegistration, make_session_factory, utcnow
    client, _ = setup(tmp_path, monkeypatch)
    _, sessions = make_session_factory(f"sqlite:///{tmp_path / 'auth.db'}")
    pending = client.post("/api/v1/control/connect/start", json={"device_id": "c" * 32, "name": "Test PC"}).json()
    response = client.get("/api/v1/auth/yandex/start", params={"connect": pending["id"]}, follow_redirects=False)
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    first = callback(client, state)
    ticket = parse_qs(urlparse(first.headers["location"]).fragment)["registration_ticket"][0]
    path = "/api/v1/auth/yandex/register"
    assert client.post(path, json={"ticket": ticket}).status_code == 422
    assert client.post(path, json={"ticket": ticket, "password": "short"}).status_code == 422
    assert client.post(path, json={"ticket": ticket, "password": "a-long-test-password", "promo_code": "UNKNOWN"}).status_code == 404
    with sessions() as db:
        assert db.scalar(select(User)) is None
        assert db.get(DeviceConnect, pending["id"]).user_id is None
        assert db.scalar(select(YandexRegistration)) is not None
    assert client.post(path, json={"ticket": ticket, "password": "a-long-test-password"}).status_code == 201
    with sessions() as db:
        assert db.get(DeviceConnect, pending["id"]).user_id == db.scalar(select(User.id))
        assert db.scalar(select(YandexRegistration)) is None
    # Expired pending registrations never create an account.
    client.cookies.clear()
    with sessions() as db:
        from server.security import token_hash
        raw = "expired-registration-ticket-12345"
        db.add(YandexRegistration(token_hash=token_hash(raw), email="new@test.example", subject="new",
                                  expires_at=utcnow()-timedelta(seconds=1)))
        db.commit()
    assert client.post(path, json={"ticket": raw, "password": "a-long-test-password"}).status_code == 401


def test_legacy_yandex_account_keeps_login_and_can_add_password(tmp_path, monkeypatch):
    from sqlalchemy import select
    from server.models import OAuthIdentity, User, Wallet, make_session_factory
    client, _ = setup(tmp_path, monkeypatch)
    _, sessions = make_session_factory(f"sqlite:///{tmp_path / 'auth.db'}")
    with sessions() as db:
        db.add_all([User(id="legacy", email="owner@example.test", password_hash="external:yandex"),
                    Wallet(user_id="legacy", balance_kopeks=100), OAuthIdentity(provider="yandex", subject="yandex-123", user_id="legacy")])
        db.commit()
    response = callback(client, start(client))
    ticket = parse_qs(urlparse(response.headers["location"]).fragment)["auth_ticket"][0]
    session = client.post("/api/v1/auth/yandex/exchange", json={"ticket": ticket}).json()
    headers = {"Authorization": f"Bearer {session['token']}"}
    assert client.get("/api/v1/me", headers=headers).json()["has_password"] is False
    result = client.put("/api/v1/auth/password", headers=headers, json={"password": "a-long-test-password"})
    assert result.status_code == 200, result.text
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    new_headers = {"Authorization": f"Bearer {result.json()['token']}"}
    assert client.get("/api/v1/me", headers=new_headers).json()["has_password"] is True
    assert client.put("/api/v1/auth/password", headers=new_headers, json={"password": "another-long-password"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "owner@example.test", "password": "a-long-test-password"}).status_code == 200
    with sessions() as db:
        assert db.scalar(select(Wallet.balance_kopeks)) == 100


@pytest.mark.parametrize("ticket", ["я" * 32, "!" * 32])
def test_registration_rejects_malformed_ticket(tmp_path, monkeypatch, ticket):
    client, _ = setup(tmp_path, monkeypatch)
    for path in ("registration", "register"):
        assert client.post(f"/api/v1/auth/yandex/{path}", json={
            "ticket": ticket, "password": "a-long-test-password"}).status_code == 422


@pytest.mark.parametrize("reset", [False, True])
def test_password_change_revokes_pending_link_and_device_approval(tmp_path, monkeypatch, reset):
    from server.test_auth_hardening import FakeMailer
    fake, mailer = FakeYandex(), FakeMailer()
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:8757")
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        yandex_client=fake, password_mailer=mailer), base_url="http://127.0.0.1:8757")
    account = register_account(client, json={
        "email": "owner@example.test", "password": "a-long-test-password"}).json()
    headers = {"Authorization": "Bearer " + account["token"]}
    link = client.post("/api/v1/auth/yandex/link/start", headers=headers).json()
    state = parse_qs(urlparse(link["authorization_url"]).query)["state"][0]
    pending = client.post("/api/v1/control/connect/start", json={"device_id": "c"*32, "name": "Test"}).json()
    assert client.post(f"/api/v1/control/connect/{pending['id']}/approve", headers=headers).status_code == 200
    if reset:
        client.post("/api/v1/auth/password/request", json={"email": "owner@example.test"})
        changed = client.post("/api/v1/auth/password/confirm", json={
            "token": mailer.messages[-1][1], "password": "another-long-password"})
    else:
        changed = client.put("/api/v1/auth/password", headers=headers, json={
            "current_password": "a-long-test-password", "password": "another-long-password"})
    assert changed.status_code == 200
    assert callback(client, state).status_code == 400
    assert client.post("/api/v1/control/connect/exchange", json={
        "id": pending["id"], "secret": pending["secret"]}).status_code == 410


def test_password_change_during_provider_call_prevents_link(tmp_path, monkeypatch):
    client, fake = setup(tmp_path, monkeypatch)
    account = register_account(client, json={
        "email": "owner@example.test", "password": "a-long-test-password"}).json()
    headers = {"Authorization": "Bearer " + account["token"]}
    link = client.post("/api/v1/auth/yandex/link/start", headers=headers).json()
    state = parse_qs(urlparse(link["authorization_url"]).query)["state"][0]
    def profile(code, verifier):
        assert client.put("/api/v1/auth/password", headers=headers, json={
            "current_password": "a-long-test-password", "password": "another-long-password"}).status_code == 200
        return fake.profile_data
    monkeypatch.setattr(fake, "profile", profile)
    response = callback(client, state)
    assert "auth_error=retry" in response.headers["location"]
    login = client.post("/api/v1/auth/login", json={
        "email": "owner@example.test", "password": "another-long-password"}).json()
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer " + login["token"]}).json()["yandex_linked"] is False
