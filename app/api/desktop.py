"""Tray agent controls. Browser authorization keeps credentials out of the WebView."""
import asyncio
import platform
import webbrowser
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import billing, config, window_control
from app.agent import device_id
from app.control_agent import STATE, paused, store_token
from app.db import repo
from app.scanner import orchestrator

router = APIRouter(prefix="/api/desktop")
login_task = None


def connected(token: str, user: dict | None = None):
    store_token(token)
    STATE.update(error="", connected=True, user=user, wallet=None)
    window_control.hide()


@router.get("/state")
def state():
    from app.api.browser import status
    from app.api.agent import get_autostart
    ctl = orchestrator.active_controller()
    return {**STATE, "configured": billing.enabled(), "has_token": bool(billing.token()),
            "paused": paused(), "browser": status(), "autostart": get_autostart(),
            "scan": ctl.snapshot() if ctl else None,
            "cabinet_url": f"{config.ACCOUNT_URL}/cabinet/" if billing.enabled() else None,
            "login_pending": bool(login_task and not login_task.done())}


class LoginIn(BaseModel):
    provider: Literal["browser", "yandex"] = "browser"


@router.post("/login")
async def login(body: LoginIn = LoginIn()):
    global login_task
    if not billing.enabled():
        raise HTTPException(503, "Адрес сайта не настроен в этой сборке")
    if login_task and not login_task.done():
        return {"pending": True}
    try:
        response = await billing._request("POST", "/control/connect/start", auth=False,
            body={"device_id": device_id(), "name": platform.node() or "Windows агент"})
    except billing.BillingError as exc:
        raise HTTPException(exc.status_code or 503, str(exc)) from exc
    target = f"{config.ACCOUNT_URL}{response['path']}"
    if body.provider == "yandex":
        target += "&provider=yandex"
    if not webbrowser.open(target):
        raise HTTPException(503, "Не удалось открыть браузер по умолчанию")

    async def wait_login():
        try:
            for _ in range(300):
                result = await billing._request("POST", "/control/connect/exchange", auth=False,
                    body={"id": response["id"], "secret": response["secret"]})
                if not result["pending"]:
                    connected(result["token"])
                    return
                await asyncio.sleep(2)
            STATE["error"] = "Время входа истекло. Нажмите «Войти» ещё раз."
        except Exception as exc:
            STATE["error"] = str(exc)
    login_task = asyncio.create_task(wait_login())
    return {"pending": True}


class PasswordIn(BaseModel):
    email: str
    password: str


@router.post("/login/password")
async def password_login(body: PasswordIn):
    if login_task and not login_task.done():
        raise HTTPException(409, "Сначала отмените ожидающий вход через браузер")
    temporary = None
    try:
        result = await billing._request("POST", "/auth/login", auth=False,
                                        body={"email": body.email, "password": body.password})
        temporary = result["token"]
        device = await billing._request("POST", "/control/agent/enroll", bearer=temporary,
            body={"device_id": device_id(), "name": platform.node() or "Windows агент"})
        connected(device["token"], result["user"])
        return {"ok": True}
    except billing.BillingError as exc:
        raise HTTPException(exc.status_code or 503, str(exc)) from exc
    finally:
        if temporary:
            try:
                await billing._request("POST", "/auth/logout", bearer=temporary)
            except billing.BillingError:
                pass


@router.post("/login/cancel")
async def cancel_login():
    global login_task
    if login_task and not login_task.done():
        login_task.cancel()
        try:
            await login_task
        except asyncio.CancelledError:
            pass
    login_task = None
    return {"ok": True}


class PauseIn(BaseModel):
    paused: bool


@router.post("/pause")
def pause(body: PauseIn):
    repo.set_setting("agent_paused", "1" if body.paused else "0")
    ctl = orchestrator.active_controller()
    if ctl and body.paused:
        ctl.pause()
    return {"paused": body.paused}


@router.post("/hide")
def hide():
    return {"hidden": window_control.hide()}


class CabinetIn(BaseModel):
    destination: Literal["cabinet", "topup"] = "cabinet"


@router.post("/cabinet")
async def cabinet(body: CabinetIn = CabinetIn()):
    if not billing.enabled():
        raise HTTPException(503, "Адрес сайта не настроен")
    try:
        url = await billing.browser_url(body.destination)
    except billing.BillingError as exc:
        raise HTTPException(exc.status_code or 503, str(exc)) from exc
    if not webbrowser.open(url):
        raise HTTPException(503, "Не удалось открыть браузер по умолчанию")
    return {"ok": True}
