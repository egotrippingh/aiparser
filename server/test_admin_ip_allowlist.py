"""Admin entry requires an allowed IP or an active console session."""
from datetime import timedelta

from server.admin_ip_allowlist import NOT_FOUND
from server.admin_sessions import ADMIN_COOKIE, admin_token_hash
from server.browser_sessions import COOKIE_NAME
from server.models import AdminAllowedIp, SessionToken, utcnow
from server.test_admin_sessions import (
    ADMIN_HEADERS, ALLOWED_IP, DENIED_IP, PASSWORD, SITE_HEADERS, login_console, operator_clients,
)


def test_admin_host_hidden_without_allowlist(tmp_path, monkeypatch):
    _, admin, _ = operator_clients(tmp_path, monkeypatch, allow_ips="")
    denied = admin.get("/", headers={"Accept": "text/html"})
    assert denied.status_code == 404
    session = login_console(admin)
    assert session.status_code == 404 and session.json()["detail"] == NOT_FOUND


def test_admin_session_survives_ip_change(tmp_path, monkeypatch):
    _, admin, _ = operator_clients(tmp_path, monkeypatch, allow_ips=f"{ALLOWED_IP}, 10.0.0.0/8")
    assert login_console(admin).status_code == 200
    token = admin.cookies[ADMIN_COOKIE]

    monkeypatch.setattr("server.admin_ip_allowlist.client_ip", lambda _request: DENIED_IP)
    assert admin.get("/").status_code == 200
    assert admin.get("/api/v1/admin/session").status_code == 200
    assert admin.get("/api/v1/admin/users").status_code == 200
    assert login_console(admin).status_code == 404
    assert admin.delete("/api/v1/admin/session").status_code == 403
    assert admin.delete("/api/v1/admin/session", headers=ADMIN_HEADERS).status_code == 204
    assert admin.get("/").status_code == 404
    hidden = admin.get("/api/v1/admin/users", headers={"Cookie": f"{ADMIN_COOKIE}={token}"})
    assert hidden.status_code == 404 and hidden.json()["detail"] == NOT_FOUND


def test_expired_admin_session_does_not_bypass_ip_allowlist(tmp_path, monkeypatch):
    _, admin, sessions = operator_clients(tmp_path, monkeypatch)
    assert login_console(admin).status_code == 200
    with sessions() as db:
        row = db.get(SessionToken, admin_token_hash(admin.cookies[ADMIN_COOKIE]))
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    monkeypatch.setattr("server.admin_ip_allowlist.client_ip", lambda _request: DENIED_IP)
    assert admin.get("/").status_code == 404
    assert admin.get("/api/v1/admin/users").status_code == 404


def test_cabinet_session_does_not_bypass_ip_allowlist(tmp_path, monkeypatch):
    site, admin, _ = operator_clients(tmp_path, monkeypatch, client_ip=DENIED_IP)
    assert site.post("/api/v1/auth/login", headers=SITE_HEADERS,
                     json={"email": "owner@example.test", "password": PASSWORD}).status_code == 200
    token = site.cookies[COOKIE_NAME]
    assert admin.get("/api/v1/admin/users", headers={"Cookie": f"{ADMIN_COOKIE}={token}"}).status_code == 404


def test_db_allowlist_bootstrap_and_crud(tmp_path, monkeypatch):
    _, admin, sessions = operator_clients(tmp_path, monkeypatch, allow_ips="")
    with sessions() as db:
        db.add(AdminAllowedIp(cidr=ALLOWED_IP, label="bootstrap", created_by="owner"))
        db.commit()

    assert login_console(admin).status_code == 200

    listed = admin.get("/api/v1/admin/allowed-ips", headers=ADMIN_HEADERS)
    assert listed.status_code == 200
    body = listed.json()
    assert body["client_ip"] == ALLOWED_IP
    assert body["env"] == []
    assert body["entries"][0]["cidr"] == ALLOWED_IP

    created = admin.post("/api/v1/admin/allowed-ips", headers=ADMIN_HEADERS,
                         json={"cidr": "198.51.100.0/24", "label": " office "})
    assert created.status_code == 201
    assert created.json()["cidr"] == "198.51.100.0/24"
    assert created.json()["label"] == "office"
    entry_id = created.json()["id"]
    assert admin.post("/api/v1/admin/allowed-ips", headers=ADMIN_HEADERS,
                      json={"cidr": "198.51.100.0/24"}).status_code == 409
    assert admin.post("/api/v1/admin/allowed-ips", headers=ADMIN_HEADERS,
                      json={"cidr": "not-an-ip"}).status_code == 422
    assert admin.delete(f"/api/v1/admin/allowed-ips/{entry_id}", headers=ADMIN_HEADERS).status_code == 204
    assert admin.delete(f"/api/v1/admin/allowed-ips/{entry_id}", headers=ADMIN_HEADERS).status_code == 404
    assert all(row["id"] != entry_id for row in admin.get("/api/v1/admin/allowed-ips").json()["entries"])
