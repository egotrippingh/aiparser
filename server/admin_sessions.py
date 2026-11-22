"""Separate browser sessions for the operator console."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from server.admin_ip_allowlist import NOT_FOUND, entry_allowed, require_admin_entry_ip
from server.models import SessionToken, User, Wallet, utcnow
from server.security import new_token, token_hash

ADMIN_COOKIE = "__Host-airate_admin"
ADMIN_SESSION_SECONDS = 8 * 60 * 60
ADMIN_LOGIN = "admin"
OPERATOR_USER_ID = "adminconsole0000000000000001"
OPERATOR_EMAIL = "admin@localhost"
_PRIVATE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
            "Referrer-Policy": "no-referrer"}
_WEB = Path(__file__).resolve().parent.parent / "web"
_NOT_FOUND_PAGE = _WEB / "404" / "index.html"


class AdminLoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


def admin_token_hash(token: str) -> str:
    # Standard session hashes always contain 64 hex characters.
    return "a:" + token_hash(token)[:62]


def console_password_ok(password: str) -> bool:
    expected = os.environ.get("ADMIN_CONSOLE_PASSWORD", "")
    if not expected or not password or len(password) > 200:
        return False
    left = hashlib.sha256(password.encode("utf-8")).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)


def ensure_operator_user(db: Session) -> User:
    user = db.get(User, OPERATOR_USER_ID)
    if user is None:
        user = User(id=OPERATOR_USER_ID, email=OPERATOR_EMAIL,
                    password_hash="external:console", is_admin=True, wallet=Wallet(balance_kopeks=0))
        db.add(user)
        db.flush()
        return user
    user.is_admin = True
    user.password_hash = "external:console"
    if user.wallet is None:
        user.wallet = Wallet(balance_kopeks=0)
    return user


def _stealth_not_found(request: Request) -> Response:
    wants_html = request.method in {"GET", "HEAD"} and "text/html" in request.headers.get("accept", "")
    if wants_html and _NOT_FOUND_PAGE.is_file():
        return FileResponse(
            _NOT_FOUND_PAGE, status_code=404,
            headers={"Cache-Control": "no-cache", "X-Robots-Tag": "noindex, follow", **{
                k: v for k, v in _PRIVATE.items() if k != "Cache-Control"
            }},
        )
    return JSONResponse({"detail": NOT_FOUND}, 404, headers=_PRIVATE)


def register_admin_sessions(app, db_session, current_user, public_base, admin_base, SessionLocal):
    admin_host = urlsplit(admin_base).netloc

    @app.middleware("http")
    async def admin_boundary(request: Request, call_next):
        path = request.url.path
        private_api = path == "/api/v1/admin" or path.startswith("/api/v1/admin/")
        on_admin_host = request.url.netloc == admin_host
        if private_api and not on_admin_host:
            return JSONResponse({"detail": NOT_FOUND}, 404, headers=_PRIVATE)
        if on_admin_host:
            with SessionLocal() as db:
                allowed = entry_allowed(request, db)
            if not allowed:
                return _stealth_not_found(request)
            if not (private_api or path in {"/", "/robots.txt"} or path.startswith("/assets/")):
                return JSONResponse({"detail": NOT_FOUND}, 404, headers=_PRIVATE)
            if request.method not in ("GET", "HEAD", "OPTIONS") and (
                request.headers.get("origin") != admin_base or request.headers.get("x-ai-client") != "browser"
            ):
                return JSONResponse({"detail": "Недопустимый источник запроса"}, 403, headers=_PRIVATE)
        response = await call_next(request)
        if on_admin_host and not path.startswith("/assets/"):
            response.headers.update(_PRIVATE)
        return response

    @app.get("/admin/", include_in_schema=False)
    @app.get("/admin", include_in_schema=False)
    def admin_location():
        return RedirectResponse(f"{admin_base}/", headers=_PRIVATE)

    @app.post("/api/v1/admin/session", include_in_schema=False)
    def admin_login(body: AdminLoginIn, request: Request, response: Response, db=Depends(db_session)):
        require_admin_entry_ip(request, db)
        if not os.environ.get("ADMIN_CONSOLE_PASSWORD"):
            raise HTTPException(503, "Вход в админку не настроен")
        if body.login != ADMIN_LOGIN or not console_password_ok(body.password):
            raise HTTPException(401, "Неверный логин или пароль")
        user = ensure_operator_user(db)
        old_cookie = request.cookies.get(ADMIN_COOKIE, "")
        if old_cookie and len(old_cookie) <= 200 and old_cookie.isascii():
            db.execute(delete(SessionToken).where(SessionToken.token_hash == admin_token_hash(old_cookie)))
        token = new_token()
        db.add(SessionToken(token_hash=admin_token_hash(token), user_id=user.id,
                            expires_at=utcnow() + timedelta(seconds=ADMIN_SESSION_SECONDS)))
        db.commit()
        response.set_cookie(ADMIN_COOKIE, token, max_age=ADMIN_SESSION_SECONDS,
                            httponly=True, secure=True, samesite="strict", path="/")
        response.headers.update(_PRIVATE)
        return {"id": user.id, "email": ADMIN_LOGIN}

    @app.get("/api/v1/admin/session", include_in_schema=False)
    def admin_identity(user: User = Depends(current_user)):
        if not user or not user.is_admin:
            raise HTTPException(401, "Войдите в аккаунт")
        return {"id": user.id, "email": ADMIN_LOGIN if user.id == OPERATOR_USER_ID else user.email}

    @app.delete("/api/v1/admin/session", status_code=204, include_in_schema=False)
    def admin_logout(request: Request, db=Depends(db_session)):
        token = request.cookies.get(ADMIN_COOKIE, "")
        if token and len(token) <= 200 and token.isascii():
            db.execute(delete(SessionToken).where(SessionToken.token_hash == admin_token_hash(token)))
            db.commit()
        response = Response(status_code=204)
        response.delete_cookie(ADMIN_COOKIE, secure=True, httponly=True, samesite="strict")
        return response
