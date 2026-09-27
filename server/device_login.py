"""Bind a pending desktop request only after an explicit account login."""
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select

from server.models import DeviceConnect, utcnow


def pending_connect(db, identifier):
    row = db.scalar(select(DeviceConnect).where(DeviceConnect.id == identifier).with_for_update())
    if not row or row.expires_at.replace(tzinfo=timezone.utc) <= utcnow() or row.user_id:
        raise HTTPException(410, "Запрос подключения истёк. Начните вход из агента заново.")
    return row


def approve_login_connect(db, identifier, user_id):
    if identifier:
        pending_connect(db, identifier).user_id = user_id
