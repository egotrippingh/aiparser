import asyncio
from unittest.mock import AsyncMock, MagicMock

from app import billing
from app.api import desktop


def test_password_login_enrolls_and_keeps_only_device_token(monkeypatch):
    monkeypatch.setattr(desktop, "login_task", None)
    calls = []
    async def request(method, path, **kwargs):
        calls.append((path, kwargs))
        if path == "/auth/login":
            return {"token": "temporary-web-token", "user": {"email": "test@example.test"}}
        if path == "/control/agent/enroll":
            return {"token": "device-token"}
        return {"ok": True}
    stored = MagicMock()
    monkeypatch.setattr(billing, "_request", request)
    monkeypatch.setattr(desktop, "store_token", stored)
    monkeypatch.setattr(desktop, "STATE", {})
    monkeypatch.setattr(desktop, "device_id", lambda: "device")
    monkeypatch.setattr(desktop.window_control, "hide", MagicMock())
    asyncio.run(desktop.password_login(desktop.PasswordIn(email="test@example.test", password="password")))
    stored.assert_called_once_with("device-token", admitted=True)
    assert calls[1][1]["bearer"] == "temporary-web-token"
    assert calls[2] == ("/auth/logout", {"bearer": "temporary-web-token"})
    assert desktop.STATE["connected"]
    desktop.window_control.hide.assert_not_called()


def test_topup_opens_one_use_browser_link(monkeypatch):
    monkeypatch.setattr(billing, "enabled", lambda: True)
    monkeypatch.setattr(billing, "token", lambda: "secret-device-token")
    monkeypatch.setattr(billing.config, "ACCOUNT_URL", "https://account.test")
    request = AsyncMock(return_value={"path": "/cabinet/#browser_ticket=one-use-ticket"})
    monkeypatch.setattr(billing, "_request", request)
    opened = MagicMock(return_value=True)
    monkeypatch.setattr(desktop.webbrowser, "open", opened)
    asyncio.run(desktop.cabinet(desktop.CabinetIn(destination="topup")))
    request.assert_awaited_once_with("POST", "/auth/browser-link", body={"destination": "topup"})
    opened.assert_called_once_with("https://account.test/cabinet/#browser_ticket=one-use-ticket")


def test_failed_enrollment_does_not_store_full_account_session(monkeypatch):
    monkeypatch.setattr(desktop, "login_task", None)
    request = AsyncMock(side_effect=[
        {"token": "temporary-web-token", "user": {}}, billing.BillingError("offline"), {"ok": True}
    ])
    monkeypatch.setattr(billing, "_request", request)
    monkeypatch.setattr(desktop, "device_id", lambda: "device")
    stored = MagicMock()
    monkeypatch.setattr(desktop, "store_token", stored)
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException):
        asyncio.run(desktop.password_login(desktop.PasswordIn(email="test@example.test", password="password")))
    stored.assert_not_called()
    assert request.await_args_list[-1].kwargs["bearer"] == "temporary-web-token"
