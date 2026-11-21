"""Separate browser sessions for the operator console."""
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete

from server.browser_sessions import COOKIE_NAME, BrowserExchangeIn, lock_web_session
from server.models import BrowserLoginTicket, DeviceGrant, SessionToken, User, utcnow
from server.security import new_token, token_hash

ADMIN_COOKIE = "__Host-airate_admin"
ADMIN_SESSION_SECONDS = 8 * 60 * 60


def admin_token_hash(token: str) -> str:
    # Standard session hashes always contain 64 hex characters.
    return "a:" + token_hash(token)[:62]


def register_admin_sessions(app, db_session, current_user, public_base, admin_base):
    admin_host = urlsplit(admin_base).netloc
    public_host = urlsplit(public_base).netloc
    private_headers = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
                       "Referrer-Policy": "no-referrer"}

    @app.middleware("http")
    async def admin_boundary(request: Request, call_next):
        path = request.url.path
        private_api = path == "/api/v1/admin" or path.startswith("/api/v1/admin/")
        on_admin_host = request.url.netloc == admin_host
        if private_api and not on_admin_host:
            return JSONResponse({"detail": "Страница не найдена"}, 404, headers=private_headers)
        if on_admin_host:
            if not (private_api or path in {"/", "/sign-in", "/back-to-cabinet", "/robots.txt"} or path.startswith("/assets/")):
                return JSONResponse({"detail": "Страница не найдена"}, 404, headers=private_headers)
            if request.method not in ("GET", "HEAD", "OPTIONS") and (
                request.headers.get("origin") != admin_base or request.headers.get("x-ai-client") != "browser"
            ):
                return JSONResponse({"detail": "Недопустимый источник запроса"}, 403, headers=private_headers)
        response = await call_next(request)
        if on_admin_host and not path.startswith("/assets/"):
            response.headers.update(private_headers)
        return response

    @app.get("/sign-in", include_in_schema=False)
    def admin_sign_in(request: Request):
        if request.url.netloc != admin_host:
            raise HTTPException(404, "Страница не найдена")
        return RedirectResponse(f"{public_base}/cabinet/?admin=1", headers=private_headers)

    @app.get("/back-to-cabinet", include_in_schema=False)
    def return_to_cabinet(request: Request):
        if request.url.netloc != admin_host:
            raise HTTPException(404, "Страница не найдена")
        return RedirectResponse(f"{public_base}/cabinet/", headers=private_headers)

    @app.get("/admin/", include_in_schema=False)
    @app.get("/admin", include_in_schema=False)
    def admin_location():
        return RedirectResponse(f"{admin_base}/", headers=private_headers)

    @app.post("/api/v1/auth/admin-link", include_in_schema=False)
    def create_admin_link(request: Request, response: Response, user=Depends(current_user), db=Depends(db_session)):
        if (request.url.netloc != public_host or request.headers.get("origin") != public_base
                or request.headers.get("x-ai-client") != "browser" or request.headers.get("authorization")
                or not request.cookies.get(COOKIE_NAME) or not user or not user.is_admin):
            raise HTTPException(403, "Доступно только администратору")
        parent_hash = token_hash(request.cookies[COOKIE_NAME])
        user = lock_web_session(db, user.id, parent_hash)
        if not user.is_admin or db.get(DeviceGrant, parent_hash):
            raise HTTPException(403, "Доступно только администратору")
        db.execute(delete(BrowserLoginTicket).where(
            (BrowserLoginTicket.expires_at <= utcnow()) |
            ((BrowserLoginTicket.parent_hash == parent_hash) & (BrowserLoginTicket.destination == "admin"))))
        ticket = new_token()
        db.add(BrowserLoginTicket(ticket_hash=token_hash(ticket), user_id=user.id, parent_hash=parent_hash,
            destination="admin", expires_at=utcnow() + timedelta(seconds=60)))
        db.commit()
        response.headers.update(private_headers)
        return {"url": f"{admin_base}/#ticket={ticket}"}

    @app.post("/api/v1/admin/session", include_in_schema=False)
    def exchange_admin_link(body: BrowserExchangeIn, request: Request, response: Response, db=Depends(db_session)):
        ticket_hash = token_hash(body.ticket)
        candidate = db.get(BrowserLoginTicket, ticket_hash)
        if not candidate or candidate.destination != "admin":
            raise HTTPException(401, "Ссылка истекла. Войдите снова.")
        user = lock_web_session(db, candidate.user_id, candidate.parent_hash)
        if not user.is_admin or db.get(DeviceGrant, candidate.parent_hash):
            raise HTTPException(403, "Доступно только администратору")
        used = db.execute(delete(BrowserLoginTicket).where(
            BrowserLoginTicket.ticket_hash == ticket_hash,
            BrowserLoginTicket.expires_at > utcnow()).returning(BrowserLoginTicket.ticket_hash)
            .execution_options(synchronize_session=False)).scalar_one_or_none()
        if not used:
            raise HTTPException(401, "Ссылка истекла. Войдите снова.")
        old_cookie = request.cookies.get(ADMIN_COOKIE, "")
        if old_cookie and len(old_cookie) <= 200 and old_cookie.isascii():
            db.execute(delete(SessionToken).where(SessionToken.token_hash == admin_token_hash(old_cookie)))
        token = new_token()
        db.add(SessionToken(token_hash=admin_token_hash(token), user_id=user.id,
                            expires_at=utcnow() + timedelta(seconds=ADMIN_SESSION_SECONDS)))
        db.commit()
        response.set_cookie(ADMIN_COOKIE, token, max_age=ADMIN_SESSION_SECONDS,
                            httponly=True, secure=True, samesite="strict", path="/")
        return {"id": user.id, "email": user.email}

    @app.get("/api/v1/admin/session", include_in_schema=False)
    def admin_identity(user: User = Depends(current_user)):
        if not user or not user.is_admin:
            raise HTTPException(403, "Доступно только администратору")
        return {"id": user.id, "email": user.email}

    @app.delete("/api/v1/admin/session", status_code=204, include_in_schema=False)
    def admin_logout(request: Request, db=Depends(db_session)):
        token = request.cookies.get(ADMIN_COOKIE, "")
        if token and len(token) <= 200 and token.isascii():
            db.execute(delete(SessionToken).where(SessionToken.token_hash == admin_token_hash(token)))
            db.commit()
        response = Response(status_code=204)
        response.delete_cookie(ADMIN_COOKIE, secure=True, httponly=True, samesite="strict")
        return response
