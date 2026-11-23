"""Credentials for the integration API, kept separate from session tokens."""
import hmac
import os
import re
from base64 import urlsafe_b64encode
from collections.abc import Callable
from datetime import datetime, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.browser_sessions import lock_web_session, request_token
from server.models import AccountApiKey, User, utcnow
from server.security import token_hash

KEY_PATH = "/api/v1/api-key"
PUBLIC_PREFIX = "/api/v1/public"
KEY_FORMAT = re.compile(r"airate_[A-Za-z0-9_-]{43}")
bearer = HTTPBearer(auto_error=False, scheme_name="AIRateApiKey")


class KeyVersion(BaseModel):
    created_at: str | None = Field(max_length=40)


def key_version(created_at: datetime) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc).isoformat()


def derive_key(secret: bytes, user_id: str, version: str, suffix: str) -> str:
    # The server secret and per-issue metadata recover the key while the DB stores only its hash.
    payload = f"airate-api-key:v1:{user_id}:{version}:{suffix}".encode("ascii")
    tag = urlsafe_b64encode(hmac.digest(secret, payload, "sha256")).decode("ascii")
    return "airate_" + tag[:39] + suffix


def key_metadata(row: AccountApiKey | None) -> dict:
    if not row:
        return {"suffix": None, "created_at": None}
    return {"suffix": row.suffix, "created_at": key_version(row.created_at)}


def verify_key_version(row: AccountApiKey | None, expected: KeyVersion) -> None:
    if key_metadata(row)["created_at"] != expected.created_at:
        raise HTTPException(409, "API-ключ изменился. Проверьте текущий ключ и повторите действие.")


def register_api_keys(app: FastAPI, db_session: Callable, current_user: Callable) -> Callable:
    router = APIRouter(prefix=KEY_PATH, include_in_schema=False)
    configured = os.environ.get("AIRATE_API_KEY_SECRET", "")
    if configured and not re.fullmatch(r"[0-9a-fA-F]{64}", configured):
        raise RuntimeError("AIRATE_API_KEY_SECRET must contain 64 hex characters")
    secret = bytes.fromhex(configured)

    def recover(row: AccountApiKey | None) -> str | None:
        if row is not None and secret:
            raw = derive_key(secret, row.user_id, key_version(row.created_at), row.suffix)
            if hmac.compare_digest(token_hash(raw), row.token_hash):
                return raw
        return None

    def api_user(request: Request, credential: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(db_session)) -> User:
        if credential and KEY_FORMAT.fullmatch(credential.credentials):
            user = db.scalar(select(User).join(AccountApiKey).where(
                AccountApiKey.token_hash == token_hash(credential.credentials)))
            if user is not None:
                request.state.telemetry_user_id = user.id
                return user
        raise HTTPException(401, "Недействительный API-ключ", headers={"WWW-Authenticate": "Bearer"})

    @router.get("")
    def status(user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
        row = db.get(AccountApiKey, user.id)
        return {**key_metadata(row), "revealable": recover(row) is not None}

    @router.post("/reveal")
    def reveal(expected: KeyVersion, request: Request, user: User = Depends(current_user),
               db: Session = Depends(db_session)) -> dict:
        lock_web_session(db, user.id, token_hash(request_token(request)))
        row = db.get(AccountApiKey, user.id)
        if row is None:
            raise HTTPException(404, "API-ключ ещё не создан")
        verify_key_version(row, expected)
        raw = recover(row)
        if raw is None:
            raise HTTPException(404, "Полный текст этого ключа недоступен")
        return {"key": raw}

    @router.put("")
    def issue(expected: KeyVersion, request: Request, user: User = Depends(current_user),
              db: Session = Depends(db_session)) -> dict:
        lock_web_session(db, user.id, token_hash(request_token(request)))
        row = db.get(AccountApiKey, user.id)
        verify_key_version(row, expected)
        if not secret:
            raise HTTPException(503, "Выпуск API-ключей временно недоступен")
        created_at, suffix = utcnow(), token_urlsafe(3)
        raw = derive_key(secret, user.id, key_version(created_at), suffix)
        if row is None:
            row = AccountApiKey(user_id=user.id)
            db.add(row)
        row.token_hash, row.suffix, row.created_at = token_hash(raw), suffix, created_at
        db.commit()
        return {**key_metadata(row), "key": raw, "revealable": True}

    @router.delete("")
    def revoke(expected: KeyVersion, request: Request, user: User = Depends(current_user),
               db: Session = Depends(db_session)) -> dict:
        lock_web_session(db, user.id, token_hash(request_token(request)))
        row = db.get(AccountApiKey, user.id)
        if row is not None:
            verify_key_version(row, expected)
            db.delete(row)
        db.commit()
        return {**key_metadata(None), "revealable": False}

    app.include_router(router)
    return api_user
