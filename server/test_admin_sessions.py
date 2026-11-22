from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from server.admin_sessions import ADMIN_COOKIE, ADMIN_LOGIN, OPERATOR_USER_ID
from server.app import create_app
from server.browser_sessions import COOKIE_NAME
from server.models import User, Wallet, make_session_factory
from server.security import hash_password
from server.test_cloud_scans import postgres_url

SITE = "https://airate.test"
ADMIN = "https://admin.airate.test"
SITE_HEADERS = {"Origin": SITE, "X-AI-Client": "browser"}
ADMIN_HEADERS = {**SITE_HEADERS, "Origin": ADMIN}
PASSWORD = "long-test-password-123"
CONSOLE_PASSWORD = "console-operator-password-xyz"
ALLOWED_IP = "203.0.113.10"
DENIED_IP = "198.51.100.20"


def operator_clients(tmp_path, monkeypatch, database_url=None, *, client_ip=ALLOWED_IP, allow_ips=ALLOWED_IP,
                     console_password=CONSOLE_PASSWORD):
    monkeypatch.setenv("PUBLIC_BASE_URL", SITE)
    monkeypatch.setenv("ADMIN_BASE_URL", ADMIN)
    monkeypatch.setenv("ADMIN_ALLOWED_IPS", allow_ips)
    if console_password is None:
        monkeypatch.delenv("ADMIN_CONSOLE_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("ADMIN_CONSOLE_PASSWORD", console_password)
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


def login_console(admin, *, login=ADMIN_LOGIN, password=CONSOLE_PASSWORD, headers=ADMIN_HEADERS):
    return admin.post("/api/v1/admin/session", headers=headers, json={"login": login, "password": password})


def test_admin_origin_session_and_logout_are_isolated(tmp_path, monkeypatch):
    site, admin, _ = operator_clients(tmp_path, monkeypatch)
    assert site.get("/admin/", follow_redirects=False).headers["location"] == f"{ADMIN}/"
    assert site.get("/api/v1/admin/users").status_code == 404
    assert site.get("/api/v1/admin/scan-results").status_code == 404
    assert admin.get("/api/v1/me").status_code == 404
    assert admin.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {site.cookies.get(COOKIE_NAME, 'x')}"}).status_code == 401

    assert login_console(admin, headers=SITE_HEADERS).status_code == 403
    assert login_console(admin, headers={"X-AI-Client": "browser"}).status_code == 403
    response = login_console(admin)
    assert response.status_code == 200 and response.json() == {"id": OPERATOR_USER_ID, "email": ADMIN_LOGIN}
    cookie = response.headers["set-cookie"]
    assert all(attribute in cookie for attribute in ("HttpOnly", "Secure", "Path=/", "SameSite=strict", "Max-Age=28800"))
    assert "Domain=" not in cookie
    assert admin.get("/api/v1/admin/users").status_code == 200
    assert admin.get("/api/v1/admin/scan-results").status_code == 200
    assert admin.get("/api/v1/admin/users").headers["x-robots-tag"] == "noindex, nofollow"
    assert admin.get("/api/v1/admin/session").json() == {"id": OPERATOR_USER_ID, "email": ADMIN_LOGIN}

    token = admin.cookies[ADMIN_COOKIE]
    isolated = TestClient(site.app, base_url=SITE)
    assert isolated.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert admin.post("/api/v1/admin/users/topup", headers=SITE_HEADERS, json={}).status_code == 403
    assert admin.delete("/api/v1/admin/session", headers=SITE_HEADERS).status_code == 403
    assert admin.delete("/api/v1/admin/session", headers=ADMIN_HEADERS).status_code == 204
    assert admin.get("/api/v1/admin/users", headers={"Cookie": f"{ADMIN_COOKIE}={token}"}).status_code == 401


def test_admin_password_login_rejects_bad_credentials(tmp_path, monkeypatch):
    _, admin, _ = operator_clients(tmp_path, monkeypatch)
    assert login_console(admin, login="Admin").status_code == 401
    assert login_console(admin, password="wrong-password").status_code == 401
    assert login_console(admin, password="").status_code == 422

    _, bare, _ = operator_clients(tmp_path, monkeypatch, database_url=f"sqlite:///{tmp_path / 'bare.db'}",
                                  console_password=None)
    assert login_console(bare).status_code == 503


def test_admin_login_independent_of_account_admin_flag(tmp_path, monkeypatch):
    site, admin, sessions = operator_clients(tmp_path, monkeypatch)
    with sessions() as db:
        db.get(User, "owner").is_admin = False
        db.commit()
    assert site.post("/api/v1/auth/login", headers=SITE_HEADERS,
                     json={"email": "owner@example.test", "password": PASSWORD}).status_code == 200
    assert site.post("/api/v1/auth/admin-link", headers=SITE_HEADERS, json={}).status_code == 404
    assert login_console(admin).status_code == 200
    assert admin.get("/api/v1/admin/users").status_code == 200


def test_admin_password_login_allows_parallel_sessions_on_postgres(tmp_path, monkeypatch, postgres_url):
    _, admin, _ = operator_clients(tmp_path, monkeypatch, postgres_url)
    start = Barrier(2, timeout=5)

    def open_console():
        client = TestClient(admin.app, base_url=ADMIN)
        start.wait()
        return login_console(client).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: open_console(), range(2))) == [200, 200]
