"""Local facade for shared scan settings; the account token stays in Python."""

from __future__ import annotations

import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import billing
from app.autostart import autostart_enabled, set_autostart

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AutostartIn(BaseModel):
    enabled: bool


@router.get("/preferences")
async def preferences() -> dict:
    try:
        return await billing.scan_preferences()
    except billing.BillingError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.put("/preferences")
async def save_preferences(body: dict) -> dict:
    try:
        return await billing.save_scan_preferences(body)
    except billing.BillingError as exc:
        status = 409 if "другом устройстве" in str(exc) else 503
        raise HTTPException(status, str(exc)) from exc


@router.get("/autostart")
def get_autostart() -> dict:
    return {"available": bool(getattr(sys, "frozen", False)),
            "enabled": autostart_enabled()}


@router.put("/autostart")
def put_autostart(body: AutostartIn) -> dict:
    if not getattr(sys, "frozen", False):
        raise HTTPException(409, "Автозапуск доступен в установленной Windows-сборке")
    try:
        set_autostart(body.enabled)
    except OSError as exc:
        raise HTTPException(500, "Не удалось изменить автозапуск Windows") from exc
    return get_autostart()
