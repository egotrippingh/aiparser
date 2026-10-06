"""Локальный посредник: токен аккаунта не раскрывается React-интерфейсу."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import billing, updates

router = APIRouter(prefix="/api/account", tags=["account"])


class Credentials(BaseModel):
    email: str
    password: str


class DeviceCode(BaseModel):
    code: str


@router.get("/status")
async def account_status() -> dict:
    try:
        async with updates.activity():
            return await billing.status()
    except billing.BillingError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/login")
async def account_login(body: Credentials) -> dict:
    if updates.busy():
        raise HTTPException(409, "Идёт обновление приложения")
    try:
        async with updates.activity():
            await billing.login(body.email, body.password)
            return await billing.status()
    except billing.BillingError as exc:
        raise HTTPException(exc.status_code or 401, str(exc)) from exc


@router.post("/login-code")
async def account_login_code(body: DeviceCode) -> dict:
    if updates.busy():
        raise HTTPException(409, "Идёт обновление приложения")
    try:
        async with updates.activity():
            await billing.login_with_code(body.code)
            return await billing.status()
    except billing.BillingError as exc:
        raise HTTPException(exc.status_code or 401, str(exc)) from exc


@router.post("/logout")
async def account_logout() -> dict:
    if updates.busy():
        raise HTTPException(409, "Идёт обновление приложения")
    try:
        async with updates.activity():
            await billing.logout()
    except billing.BillingError as exc:
        raise HTTPException(exc.status_code or 503, str(exc)) from exc
    from app.control_agent import STATE
    STATE.update(connected=False, user=None, wallet=None, error="")
    return {"enabled": billing.enabled(), "connected": False}
