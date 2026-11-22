from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from server.admin_sessions import ADMIN_COOKIE
from server.app import create_app
from server.browser_sessions import COOKIE_NAME
from server.models import BrowserLoginTicket, SessionToken, User, Wallet, make_session_factory, utcnow
from server.security import hash_password, token_hash
from server.test_cloud_scans import postgres_url

SITE = "https://airate.test"
ADMIN = "https://admin.airate.test"
SITE_HEADERS = {"Origin": SITE, "X-AI-Client": "browser"}
ADMIN_HEADERS = {**SITE_HEADERS, "Origin": ADMIN}
PASSWORD = "long-test-password-123"
ALLOWED_IP = "203.0.113.10"
DENIED_IP = "198.51.100.20"


def operator_clients(tmp_path, monkeypatch, database_url=None, *, client_ip=ALLOWED_IP, allow_ips=ALLOWED_IP):
    monkeypatch.setenv("PUBLIC_BASE_URL", SITE)
    monkeypatch.setenv("ADMIN_BASE_URL", ADMIN)
    monkeypatch.setenv("ADMIN_ALLOWED_IPS", allow_ips)
    monkeypatch.setattr("server.admin_ip_allowlist.client_ip", lambda _request: client_ip)
    url = database_url or f"sqlite:///{tmp_path / 'operator.db'}"
    app = create_app(database_url=url)
    _, sessions = make_session_factory(url)
    with sessions() as db:
        for user_id, admin in [("owner", True), ("customer", False)]:
            db.add(User(id=user_id, email=f"{user_id}@example.test", is_admin=admin,
                        password_hash=hash_password(PASSWORD), wallet=Wallet(balance_kopeks=0)))
        db.commit()
    return TestClient(app, base_url=SITE), TestClient(app, base_url=ADMIN), sessions


def login(client, username):
    response = client.post("/api/v1/auth/login", headers=SITE_HEADERS,
                           json={"email": f"{username}@example.test", "password": PASSWORD})
    assert response.status_code == 200


def ticket_for(site):
    response = site.post("/api/v1/auth/admin-link", headers=SITE_HEADERS, json={})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    url = urlsplit(response.json()["url"])
    assert f"{url.scheme}://{url.netloc}" == ADMIN
    return url.fragment.removeprefix("ticket=")


def exchange(admin, ticket, headers=ADMIN_HEADERS):
    return admin.post("/api/v1/admin/session", headers=headers, json={"ticket": ticket})


def test_admin_origin_session_and_logout_are_isolated(tmp_path, monkeypatch):
    site, admin, _ = operator_clients(tmp_path, monkeypatch)
    login(site, "owner")
    assert admin.get("/sign-in", follow_redirects=False).headers["location"] == f"{SITE}/cabinet/?admin=1"
    assert site.get("/admin/", follow_redirects=False).headers["location"] == f"{ADMIN}/"
    assert site.get("/api/v1/admin/users").status_code == 404
    assert site.get("/api/v1/admin/scan-results").status_code == 404
    assert admin.get("/api/v1/me").status_code == 404
    assert admin.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {site.cookies[COOKIE_NAME]}"}).status_code == 401
    assert admin.get("/api/v1/admin/users", headers={"Cookie": f"{COOKIE_NAME}={site.cookies[COOKIE_NAME]}"}).status_code == 401

    ticket = ticket_for(site)
    rejected = site.post("/api/v1/auth/browser/exchange", headers=SITE_HEADERS, json={"ticket": ticket})
    assert rejected.status_code == 401
    assert exchange(admin, ticket, SITE_HEADERS).status_code == 403
    assert exchange(admin, ticket, {"X-AI-Client": "browser"}).status_code == 403
    response = exchange(admin, ticket)
    assert response.status_code == 200 and response.json() == {"id": "owner", "email": "owner@example.test"}
    cookie = response.headers["set-cookie"]
    assert all(attribute in cookie for attribute in ("HttpOnly", "Secure", "Path=/", "SameSite=strict", "Max-Age=28800"))
    assert "Domain=" not in cookie
    assert exchange(admin, ticket).status_code == 401
    assert admin.get("/api/v1/admin/users").status_code == 200
    assert admin.get("/api/v1/admin/scan-results").status_code == 200
    assert admin.get("/api/v1/admin/users").headers["x-robots-tag"] == "noindex, nofollow"

    token = admin.cookies[ADMIN_COOKIE]
    isolated = TestClient(site.app, base_url=SITE)
    assert isolated.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert admin.post("/api/v1/admin/users/topup", headers=SITE_HEADERS, json={}).status_code == 403
    assert admin.delete("/api/v1/admin/session", headers=SITE_HEADERS).status_code == 403
    assert admin.delete("/api/v1/admin/session", headers=ADMIN_HEADERS).status_code == 204
    assert admin.get("/api/v1/admin/users", headers={"Cookie": f"{ADMIN_COOKIE}={token}"}).status_code == 401
    assert site.get("/api/v1/me").status_code == 200


def test_admin_handoff_requires_active_privileged_browser_session(tmp_path, monkeypatch):
    site, admin, sessions = operator_clients(tmp_path, monkeypatch)
    login(site, "customer")
    assert site.post("/api/v1/auth/admin-link", headers=SITE_HEADERS, json={}).status_code == 403

    login(site, "owner")
    bearer = {**SITE_HEADERS, "Authorization": f"Bearer {site.cookies[COOKIE_NAME]}"}
    assert site.post("/api/v1/auth/admin-link", headers=bearer, json={}).status_code == 403
    assert site.post("/api/v1/auth/admin-link", headers=ADMIN_HEADERS, json={}).status_code == 403
    expired = ticket_for(site)
    with sessions() as db:
        db.get(BrowserLoginTicket, token_hash(expired)).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert exchange(admin, expired).status_code == 401

    active = ticket_for(site)
    assert exchange(admin, active).status_code == 200
    revoked = ticket_for(site)
    with sessions() as db:
        db.get(User, "owner").is_admin = False
        db.commit()
    assert exchange(admin, revoked).status_code == 403
    assert admin.get("/api/v1/admin/session").status_code == 403
    assert admin.get("/api/v1/admin/users").status_code == 403

    with sessions() as db:
        db.get(User, "owner").is_admin = True
        db.commit()
    invalid_parent = ticket_for(site)
    with sessions() as db:
        db.get(SessionToken, token_hash(site.cookies[COOKIE_NAME])).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert exchange(admin, invalid_parent).status_code == 401


def test_admin_ticket_is_consumed_once_on_postgres(tmp_path, monkeypatch, postgres_url):
    site, admin, _ = operator_clients(tmp_path, monkeypatch, postgres_url)
    login(site, "owner")
    ticket = ticket_for(site)
    start = Barrier(2, timeout=5)

    def open_console():
        # Fresh cookie jar per racer. Do not use `with TestClient`: entering lifespan
        # in parallel threads starts/stops the shared control scheduler on different
        # event loops (CI flake: RuntimeError at control.py stop_scheduler).
        client = TestClient(admin.app, base_url=ADMIN)
        start.wait()
        return exchange(client, ticket).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: open_console(), range(2))) == [200, 401]
