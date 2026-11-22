"""Admin host is stealth-gated by IP; denied clients see a plain 404."""
from server.admin_ip_allowlist import NOT_FOUND
from server.models import AdminAllowedIp
from server.test_admin_sessions import (
    ADMIN_HEADERS, ALLOWED_IP, DENIED_IP, login_console, operator_clients,
)


def test_admin_host_hidden_without_allowlist(tmp_path, monkeypatch):
    _, admin, _ = operator_clients(tmp_path, monkeypatch, allow_ips="")
    denied = admin.get("/", headers={"Accept": "text/html"})
    assert denied.status_code == 404
    session = login_console(admin)
    assert session.status_code == 404 and session.json()["detail"] == NOT_FOUND


def test_admin_host_hidden_from_other_ip(tmp_path, monkeypatch):
    _, admin, _ = operator_clients(tmp_path, monkeypatch, allow_ips=f"{ALLOWED_IP}, 10.0.0.0/8")
    assert login_console(admin).status_code == 200
    assert admin.get("/api/v1/admin/users").status_code == 200

    monkeypatch.setattr("server.admin_ip_allowlist.client_ip", lambda _request: DENIED_IP)
    hidden = admin.get("/api/v1/admin/users")
    assert hidden.status_code == 404 and hidden.json()["detail"] == NOT_FOUND
    assert login_console(admin).status_code == 404
    assert admin.get("/", headers={"Accept": "application/json"}).status_code == 404


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
