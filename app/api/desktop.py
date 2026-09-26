"""Tray agent controls. Browser authorization keeps credentials out of the WebView."""
import asyncio
import platform
import webbrowser

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import billing, config, window_control
from app.agent import device_id
from app.control_agent import STATE, paused, store_token
from app.db import repo
from app.scanner import orchestrator

router = APIRouter(prefix="/api/desktop")
login_task = None


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


@router.post("/login")
async def login():
    global login_task
    if not billing.enabled():
        raise HTTPException(503, "Адрес сайта не настроен в этой сборке")
    if login_task and not login_task.done():
        return {"pending": True}
    response = await billing._request("POST", "/control/connect/start", auth=False,
        body={"device_id": device_id(), "name": platform.node() or "Windows агент"})
    webbrowser.open(f"{config.ACCOUNT_URL}{response['path']}")

    async def wait_login():
        try:
            for _ in range(300):
                result = await billing._request("POST", "/control/connect/exchange", auth=False,
                    body={"id": response["id"], "secret": response["secret"]})
                if not result["pending"]:
                    store_token(result["token"])
                    STATE["error"] = ""
                    window_control.hide()
                    return
                await asyncio.sleep(2)
            STATE["error"] = "Время входа истекло. Нажмите «Войти» ещё раз."
        except Exception as exc:
            STATE["error"] = str(exc)
    login_task = asyncio.create_task(wait_login())
    return {"pending": True}


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


@router.post("/cabinet")
def cabinet():
    if not billing.enabled():
        raise HTTPException(503, "Адрес сайта не настроен")
    webbrowser.open(f"{config.ACCOUNT_URL}/cabinet/")
    return {"ok": True}
