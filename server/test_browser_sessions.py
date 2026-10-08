from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from server.app import create_app
from server.browser_sessions import COOKIE_NAME, SESSION_SECONDS
from server.models import BrowserLoginTicket, make_session_factory, utcnow
from server.test_yandex import FakeYandex

WEB = {"X-AI-Client": "browser", "Origin": "http://testserver"}
CREDS = {"email": "owner@example.test", "password": "long-test-password-123"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    url = f"sqlite:///{tmp_path / 'browser.db'}"
    app = create_app(database_url=url, yandex_client=FakeYandex())
    client = TestClient(app)
    owner = client.post("/api/v1/auth/register", json=CREDS).json()
    headers = {"Authorization": "Bearer " + owner["token"]}
    agent = client.post("/api/v1/control/agent/enroll", headers=headers,
        json={"device_id": "a" * 32, "name": "Office PC"}).json()["token"]
    return client, headers, {"Authorization": "Bearer " + agent}, url


def link(client, agent, destination="topup"):
    result = client.post("/api/v1/auth/browser-link", headers=agent, json={"destination": destination})
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["expires_in"] == 60
    return parse_qs(urlparse(result.json()["path"]).fragment)["browser_ticket"][0]


def test_agent_link_cookie_persistence_replay_csrf_and_logout(setup):
    client, owner, agent, _ = setup
    ticket = link(client, agent)
    res = client.post("/api/v1/auth/browser/exchange", headers=WEB, json={"ticket": ticket})
    assert res.status_code == 200, res.text
    assert res.json()["destination"] == "topup"
    assert "token" not in res.json()
    cookie = res.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and f"Max-Age={SESSION_SECONDS}" in cookie
    assert client.get("/api/v1/me").json()["email"] == CREDS["email"]
    assert client.get("/api/v1/control/projects").status_code == 200
    assert client.post("/api/v1/auth/browser/exchange", headers=WEB, json={"ticket": ticket}).status_code == 401
    # A new tab/browser process can reuse the persistent cookie without JS storage.
    reopened = TestClient(client.app)
    reopened.cookies.update(client.cookies)
    assert reopened.get("/api/v1/me").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post("/api/v1/auth/logout", headers={**WEB, "Origin": "https://foreign.test"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=WEB).status_code == 200
    assert not client.cookies.get(COOKIE_NAME)
    assert reopened.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers=agent).status_code == 200


@pytest.mark.parametrize("invalidate", ["expired", "revoked"])
def test_link_rejects_expiry_or_revoked_parent(setup, invalidate):
    client, owner, agent, url = setup
    ticket = link(client, agent)
    if invalidate == "expired":
        _, sessions = make_session_factory(url)
        with sessions() as db:
            db.scalar(select(BrowserLoginTicket)).expires_at = utcnow() - timedelta(seconds=1)
            db.commit()
    else:
        assert client.delete("/api/v1/control/devices/" + "a" * 32, headers=owner).status_code == 200
    assert client.post("/api/v1/auth/browser/exchange", headers=WEB, json={"ticket": ticket}).status_code == 401


def test_link_destination_and_authorization_are_restricted(setup):
    client, _, agent, _ = setup
    assert client.post("/api/v1/auth/browser-link", json={}).status_code == 401
    assert client.post("/api/v1/auth/browser-link", headers=agent, json={"destination": "https://foreign.test"}).status_code == 422
    first = link(client, agent)
    second = link(client, agent, "cabinet")
    assert client.post("/api/v1/auth/browser/exchange", headers=WEB, json={"ticket": first}).status_code == 401
    assert client.post("/api/v1/auth/browser/exchange", json={"ticket": second}).status_code == 403
    assert client.post("/api/v1/auth/browser/exchange", headers=WEB, json={"ticket": second}).json()["destination"] == "cabinet"


def test_password_login_connects_pc_automatically_and_cookie_login_persists(setup):
    client, _, _, _ = setup
    pending = client.post("/api/v1/control/connect/start", json={"device_id": "b" * 32, "name": "New PC"}).json()
    assert client.get("/api/v1/auth/connect/" + pending["id"]).json()["name"] == "New PC"
    body = {**CREDS, "connect_id": pending["id"]}
    assert client.post("/api/v1/auth/login", headers=WEB, json={**body, "password": "wrong-password-123"}).status_code == 401
    poll = {key: pending[key] for key in ("id", "secret")}
    assert client.post("/api/v1/control/connect/exchange", json=poll).json()["pending"]
    res = client.post("/api/v1/auth/login", headers=WEB, json=body)
    assert res.json()["agent_connected"] and "token" not in res.json()
    assert client.get("/api/v1/me").status_code == 200
    client.cookies.clear()  # Native agent does not use the browser's cookie jar.
    result = client.post("/api/v1/control/connect/exchange", json=poll).json()
    assert not result["pending"]
    assert client.get("/api/v1/control/projects", headers={"Authorization": "Bearer " + result["token"]}).status_code == 403


def test_yandex_login_connects_pc_without_code(setup):
    client, _, _, _ = setup
    # A fresh Yandex identity uses a different email than the password account.
    pending = client.post("/api/v1/control/connect/start", json={"device_id": "c" * 32, "name": "Yandex PC"}).json()
    # Link fake identity through its separate account to avoid implicit email merging.
    from server.models import OAuthIdentity, User
    _, sessions = make_session_factory(setup[3])
    with sessions() as db:
        user = db.scalar(select(User).where(User.email == CREDS["email"]))
        db.add(OAuthIdentity(provider="yandex", subject="yandex-123", user_id=user.id))
        db.commit()
    start = client.get("/api/v1/auth/yandex/start", params={"connect": pending["id"]}, follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    callback = client.get("/api/v1/auth/yandex/callback", params={"state": state, "code": "valid-code"}, follow_redirects=False)
    assert "agent_connected=1" in callback.headers["location"]
    ticket = parse_qs(urlparse(callback.headers["location"]).fragment)["auth_ticket"][0]
    result = client.post("/api/v1/auth/yandex/exchange", headers=WEB, json={"ticket": ticket})
    assert result.status_code == 200 and "token" not in result.json()
    client.cookies.clear()
    poll = {key: pending[key] for key in ("id", "secret")}
    assert not client.post("/api/v1/control/connect/exchange", json=poll).json()["pending"]
