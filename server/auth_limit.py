"""Shared database-backed limits for public authentication endpoints."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from server.models import AuthFailure, utcnow

WINDOW = timedelta(minutes=15)


def source_key(request: Request) -> str:
    # Uvicorn uses forwarded headers only for explicitly trusted proxies.
    host = request.client.host if request.client else "unknown"
    return "ip:" + host


def email_key(email: str) -> str:
    return "email:" + email


def _digest(scope: str, key: str) -> str:
    return hashlib.sha256(f"{scope}:{key}".encode()).hexdigest()


def guard(db: Session, scope: str, limits: list[tuple[str, int]]) -> None:
    since = utcnow() - WINDOW
    for key, maximum in limits:
        count = db.scalar(select(func.count(AuthFailure.id)).where(
            AuthFailure.key_hash == _digest(scope, key), AuthFailure.created_at > since,
        )) or 0
        if count >= maximum:
            raise HTTPException(429, "Слишком много попыток. Попробуйте через 15 минут",
                                headers={"Retry-After": "900"})


def record(db: Session, scope: str, keys: list[str]) -> None:
    now = utcnow()
    db.add_all(AuthFailure(key_hash=_digest(scope, key), created_at=now) for key in keys)
    db.commit()


def clear(db: Session, scope: str, key: str) -> None:
    db.execute(delete(AuthFailure).where(AuthFailure.key_hash == _digest(scope, key)))
    db.commit()


def prune(db: Session) -> int:
    result = db.execute(delete(AuthFailure).where(AuthFailure.created_at < utcnow() - WINDOW))
    db.commit()
    return result.rowcount or 0
