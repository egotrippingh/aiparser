"""Credentials for the integration API, kept separate from session tokens."""
import re
from collections.abc import Callable
from datetime import timezone

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.browser_sessions import lock_web_session, request_token
from server.models import AccountApiKey, User, utcnow
from server.security import new_token, token_hash

KEY_PATH = "/api/v1/api-key"
PUBLIC_PREFIX = "/api/v1/public"
KEY_FORMAT = re.compile(r"airate_[A-Za-z0-9_-]{43}")
bearer = HTTPBearer(auto_error=False, scheme_name="AIRateApiKey")


class KeyVersion(BaseModel):
    created_at: str | None = Field(max_length=40)


def key_metadata(row: AccountApiKey | None) -> dict:
    if not row:
        return {"suffix": None, "created_at": None}
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {"suffix": row.suffix, "created_at": created_at.astimezone(timezone.utc).isoformat()}


def verify_key_version(row: AccountApiKey | None, expected: KeyVersion) -> None:
    if key_metadata(row)["created_at"] != expected.created_at:
        raise HTTPException(409, "API-ключ изменился. Проверьте текущий ключ и повторите действие.")


def register_api_keys(app: FastAPI, db_session: Callable, current_user: Callable) -> Callable:
    router = APIRouter(prefix=KEY_PATH, include_in_schema=False)

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
        return key_metadata(db.get(AccountApiKey, user.id))

    @router.put("")
    def issue(expected: KeyVersion, request: Request, user: User = Depends(current_user),
              db: Session = Depends(db_session)) -> dict:
        lock_web_session(db, user.id, token_hash(request_token(request)))
        row = db.get(AccountApiKey, user.id)
        verify_key_version(row, expected)
        raw = "airate_" + new_token()
        if row is None:
            row = AccountApiKey(user_id=user.id)
            db.add(row)
        row.token_hash, row.suffix, row.created_at = token_hash(raw), raw[-4:], utcnow()
        db.commit()
        return {**key_metadata(row), "key": raw}

    @router.delete("")
    def revoke(expected: KeyVersion, request: Request, user: User = Depends(current_user),
               db: Session = Depends(db_session)) -> dict:
        lock_web_session(db, user.id, token_hash(request_token(request)))
        row = db.get(AccountApiKey, user.id)
        if row is not None:
            verify_key_version(row, expected)
            db.delete(row)
        db.commit()
        return key_metadata(None)

    app.include_router(router)
    return api_user
