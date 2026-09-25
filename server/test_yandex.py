"""Яндекс ID: одноразовое состояние, регистрация и безопасная привязка."""

from urllib.parse import parse_qs, urlparse

import httpx
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


def test_yandex_register_login_and_single_use_ticket(tmp_path, monkeypatch):
    client, fake = setup(tmp_path, monkeypatch)
    assert client.get("/api/v1/auth/providers").json() == {"yandex": True, "password_reset": False}
    state = start(client)
    assert callback(client, "wrong-state").status_code == 400
    response = callback(client, state)
    assert response.status_code == 303
    ticket = parse_qs(urlparse(response.headers["location"]).fragment)["auth_ticket"][0]
    issued = client.post("/api/v1/auth/yandex/exchange", json={"ticket": ticket})
    assert issued.status_code == 200
    user = issued.json()["user"]
    assert user["email"] == "owner@example.test"
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {issued.json()['token']}"}).json()["yandex_linked"]
    assert client.post("/api/v1/auth/yandex/exchange", json={"ticket": ticket}).status_code == 401
    assert callback(client, state).status_code == 400

    second = callback(client, start(client))
    second_ticket = parse_qs(urlparse(second.headers["location"]).fragment)["auth_ticket"][0]
    again = client.post("/api/v1/auth/yandex/exchange", json={"ticket": second_ticket}).json()
    assert again["user"]["id"] == user["id"]
    assert fake.verifiers[0] != fake.verifiers[1]


def test_existing_email_requires_explicit_link(tmp_path, monkeypatch):
    client, fake = setup(tmp_path, monkeypatch)
    registered = client.post("/api/v1/auth/register", json={
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
    ticket = parse_qs(urlparse(first.headers["location"]).fragment)["auth_ticket"][0]
    owner_id = client.post("/api/v1/auth/yandex/exchange", json={"ticket": ticket}).json()["user"]["id"]
    second = client.post("/api/v1/auth/register", json={
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
    ticket = parse_qs(urlparse(first.headers["location"]).fragment)["auth_ticket"][0]
    browser = client.post("/api/v1/auth/yandex/exchange", json={"ticket": ticket}).json()
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
