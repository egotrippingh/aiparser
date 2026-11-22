"""Admin entry is IP-gated; established admin sessions are not re-checked."""
from server.admin_ip_allowlist import ENTRY_DENIED
from server.models import AdminAllowedIp
from server.test_admin_sessions import (
    ADMIN_HEADERS, ALLOWED_IP, DENIED_IP, SITE_HEADERS, exchange, login, operator_clients, ticket_for,
)


def test_admin_entry_denied_without_allowlist(tmp_path, monkeypatch):
    site, admin, _ = operator_clients(tmp_path, monkeypatch, allow_ips="")
    login(site, "owner")
    denied = site.post("/api/v1/auth/admin-link", headers=SITE_HEADERS, json={})
    assert denied.status_code == 403 and denied.json()["detail"] == ENTRY_DENIED


def test_admin_entry_allowed_from_env_and_blocked_from_other_ip(tmp_path, monkeypatch):
    site, admin, _ = operator_clients(tmp_path, monkeypatch, allow_ips=f"{ALLOWED_IP}, 10.0.0.0/8")
    login(site, "owner")
    ticket = ticket_for(site)
    assert exchange(admin, ticket).status_code == 200
    pending = ticket_for(site)

    monkeypatch.setattr("server.admin_ip_allowlist.client_ip", lambda _request: DENIED_IP)
    blocked = site.post("/api/v1/auth/admin-link", headers=SITE_HEADERS, json={})
    assert blocked.status_code == 403 and blocked.json()["detail"] == ENTRY_DENIED
    denied_exchange = exchange(admin, pending)
    assert denied_exchange.status_code == 403 and denied_exchange.json()["detail"] == ENTRY_DENIED


def test_established_admin_session_survives_ip_change(tmp_path, monkeypatch):
    site, admin, _ = operator_clients(tmp_path, monkeypatch)
    login(site, "owner")
    assert exchange(admin, ticket_for(site)).status_code == 200
    assert admin.get("/api/v1/admin/users").status_code == 200

    monkeypatch.setattr("server.admin_ip_allowlist.client_ip", lambda _request: DENIED_IP)
    monkeypatch.setenv("ADMIN_ALLOWED_IPS", "10.255.255.255")
    assert admin.get("/api/v1/admin/users").status_code == 200
    assert admin.get("/api/v1/admin/session").status_code == 200
    assert admin.get("/api/v1/admin/allowed-ips").status_code == 200
    assert site.post("/api/v1/auth/admin-link", headers=SITE_HEADERS, json={}).status_code == 403


def test_db_allowlist_bootstrap_and_crud(tmp_path, monkeypatch):
    site, admin, sessions = operator_clients(tmp_path, monkeypatch, allow_ips="")
    login(site, "owner")
    with sessions() as db:
        db.add(AdminAllowedIp(cidr=ALLOWED_IP, label="bootstrap", created_by="owner"))
        db.commit()

    ticket = ticket_for(site)
    assert exchange(admin, ticket).status_code == 200

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
