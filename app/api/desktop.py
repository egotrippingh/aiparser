"""Tray agent controls. Browser authorization keeps credentials out of the WebView."""
import asyncio
import json
import platform
import webbrowser
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import billing, config, secrets_store, window_control
from app.agent import device_id
from app.control_agent import STATE, paused, store_token
from app.db import repo
from app.scanner import orchestrator
from app import updates

router = APIRouter(prefix="/api/desktop")
login_task = None


async def connected(token: str, user: dict | None = None):
    """Store a replacement device token only while scan admission is locked."""
    async with billing.account_change():
        store_token(token, admitted=True)
        STATE.update(error="", connected=True, user=user, wallet=None)


@router.get("/state")
def state():
    from app.api.browser import status
    from app.api.agent import get_autostart
    ctl = orchestrator.active_controller()
    user = STATE.get("user") or {}
    saved_scan = repo.abandonable_saved_scan(user.get("id", "")) if user.get("id") else None
    return {**STATE, "configured": billing.enabled(), "has_token": bool(billing.token()),
            "paused": paused(), "browser": status(), "autostart": get_autostart(),
            "scan": ctl.snapshot() if ctl else None,
            "saved_scan": saved_scan,
            "update": updates.snapshot(),
            "cabinet_url": f"{config.ACCOUNT_URL}/cabinet/" if billing.enabled() else None,
            "login_pending": bool(login_task and not login_task.done())}


class LoginIn(BaseModel):
    provider: Literal["browser", "yandex"] = "browser"


@router.post("/login")
async def login(body: LoginIn = LoginIn()):
    global login_task
    if updates.busy():
        raise HTTPException(409, "Идёт обновление приложения")
    if not billing.enabled():
        raise HTTPException(503, "Адрес сайта не настроен в этой сборке")
    if login_task and not login_task.done():
        return {"pending": True}
    try:
        async with updates.activity():
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
                async with billing.account_change():
                    result = await billing._request("POST", "/control/connect/exchange", auth=False,
                        body={"id": response["id"], "secret": response["secret"]})
                    if not result["pending"]:
                        store_token(result["token"], admitted=True)
                        STATE.update(error="", connected=True, user=None, wallet=None)
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
    if updates.busy():
        raise HTTPException(409, "Идёт обновление приложения")
    if login_task and not login_task.done():
        raise HTTPException(409, "Сначала отмените ожидающий вход через браузер")
    async with updates.activity():
        temporary = None
        try:
            async with billing.account_change():
                result = await billing._request("POST", "/auth/login", auth=False,
                                                body={"email": body.email, "password": body.password})
                temporary = result["token"]
                device = await billing._request("POST", "/control/agent/enroll", bearer=temporary,
                    body={"device_id": device_id(), "name": platform.node() or "Windows агент"})
                store_token(device["token"], admitted=True)
                STATE.update(error="", connected=True, user=result["user"], wallet=None)
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


@router.post("/scans/{scan_id}/abandon-saved")
async def abandon_saved(scan_id: int) -> dict:
    try:
        async with updates.activity():
            return await _abandon_saved(scan_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


async def _abandon_saved(scan_id: int) -> dict:
    """End every retained answer in an inactive scan without losing its evidence."""
    from app.control_agent import STATE, work_in_progress
    async with orchestrator.scan_start_lock():
        if orchestrator.active_controller() or work_in_progress():
            raise HTTPException(409, "Дождитесь окончания текущей работы агента")
        scan = repo.get_scan(scan_id)
        if not scan:
            raise HTTPException(404, "Скан не найден")
        snapshot = json.loads(scan["settings_snapshot_json"] or "{}")
        owner = snapshot.get("billing_user_id")
        try:
            identity = await billing.identity()
        except billing.BillingError as exc:
            raise HTTPException(exc.status_code or 503, str(exc)) from exc
        if not owner or identity.get("id") != owner:
            raise HTTPException(403, "Сохранённые ответы принадлежат другому аккаунту")
        rows = repo.pending_captures(scan_id)
        if not rows:
            if scan["status"] == "abandoned":
                return {"ok": True, "state": "abandoned", "saved_answers": 0}
            raise HTTPException(409, "В скане нет сохранённых ответов")
        if any(row.get("payer_id") != owner for row in rows):
            raise HTTPException(403, "Сохранённые ответы принадлежат другому аккаунту")
        marker = None
        if snapshot.get("cloud_job_id"):
            job = STATE.get("job") or {}
            if (job.get("id") == snapshot["cloud_job_id"] and job.get("lease_token")
                    and (STATE.get("user") or {}).get("id") == owner):
                marker_key = f"abandoned_terminal:{owner}:{device_id()}:{scan_id}"
                marker_value = secrets_store.protect(json.dumps({
                    "run_id": job["id"], "lease_token": job["lease_token"], "owner": owner,
                    "device_id": device_id(), "scan_id": scan_id, "total": job.get("total", 0),
                }))
                marker = (marker_key, marker_value)
            else:
                try:
                    status = await billing._request("GET", f"/control/agent/runs/{snapshot['cloud_job_id']}/status")
                except billing.BillingError as exc:
                    raise HTTPException(exc.status_code or 409, "Задание больше не принадлежит этому компьютеру") from exc
                if status.get("state") not in ("done", "failed", "cancelled", "missed"):
                    raise HTTPException(409, "Задание больше не принадлежит этому компьютеру")
        abandoned = repo.abandon_saved_scan(
            scan_id, "Сохранённый ответ завершён без анализа по запросу оператора", terminal_marker=marker)
        bearer = billing.token()
        context = billing.scan_bearer.set(bearer)
        try:
            await billing.flush_outbox(owner)
        except billing.BillingError:
            pass
        finally:
            billing.scan_bearer.reset(context)
    return {"ok": True, "state": "abandoned", "saved_answers": len(abandoned["captures"])}


@router.post("/hide")
def hide():
    return {"hidden": window_control.hide()}


@router.post("/update/check")
async def check_update():
    return await updates.check(manual=True)


class UpdateIn(BaseModel):
    version: str
    portable: bool = False


@router.post("/update/dismiss")
def dismiss_update(body: UpdateIn):
    updates.dismiss(body.version)
    return updates.snapshot()


@router.post("/update/apply")
@router.post("/update/download")
async def download_update(body: UpdateIn):
    # Reserve under the same lock as all scan/browser starts, then release it
    # before the network download. The process-wide update gate rejects later starts.
    from app.api.browser import status as browser_status
    from app.control_agent import work_in_progress
    try:
        if updates.working() or (login_task and not login_task.done()):
            raise ValueError("Сначала дождитесь завершения текущей работы агента")
        async with orchestrator.scan_start_lock():
            browser = browser_status()
            if (orchestrator.active_controller() or login_task and not login_task.done()
                    or browser["installing"] or browser["logins_in_progress"] or work_in_progress()):
                raise ValueError("Сначала дождитесь завершения текущей работы агента")
            if not window_control.shutdown_ready():
                raise ValueError("Перезапуск агента пока недоступен")
            if not updates.reserve():
                return updates.snapshot()
        return await updates.apply(body.version, window_control.shutdown, reserved=True)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class CabinetIn(BaseModel):
    destination: Literal["cabinet", "topup"] = "cabinet"


@router.post("/cabinet")
async def cabinet(body: CabinetIn = CabinetIn()):
    if not billing.enabled():
        raise HTTPException(503, "Адрес сайта не настроен")
    try:
        async with updates.activity():
            url = await billing.browser_url(body.destination)
    except billing.BillingError as exc:
        raise HTTPException(exc.status_code or 503, str(exc)) from exc
    if not webbrowser.open(url):
        raise HTTPException(503, "Не удалось открыть браузер по умолчанию")
    return {"ok": True}
