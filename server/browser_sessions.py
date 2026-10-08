"""Persistent web sessions and one-use desktop-to-browser handoff."""
from datetime import timedelta, timezone
from typing import Literal

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from server.models import AgentDevice, BrowserLoginTicket, DeviceGrant, SessionToken, User, utcnow
from server.security import new_token, token_hash

COOKIE_NAME = "aimt_session"
SESSION_SECONDS = 30 * 24 * 60 * 60


def request_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization:
        return authorization[7:] if authorization.startswith("Bearer ") else ""
    return request.cookies.get(COOKIE_NAME, "")


def web_session_response(request, response, payload, *, secure):
    if request is not None and request.headers.get("x-ai-client") == "browser":
        response.set_cookie(COOKIE_NAME, payload["token"], max_age=SESSION_SECONDS,
                            httponly=True, secure=secure or request.url.scheme == "https",
                            samesite="lax", path="/")
        response.headers["Cache-Control"] = "no-store"
        return {"user": payload["user"]}
    return payload


class BrowserLinkIn(BaseModel):
    destination: Literal["cabinet", "topup"] = "cabinet"


class BrowserExchangeIn(BaseModel):
    ticket: str = Field(min_length=20, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


def register_browser_login(app, db_session, current_user, issue_session):
    @app.post("/api/v1/auth/browser-link")
    def create_link(body: BrowserLinkIn, request: Request, response: Response,
                    user=Depends(current_user), db=Depends(db_session)):
        parent_hash = token_hash(request_token(request))
        db.execute(delete(BrowserLoginTicket).where(
            (BrowserLoginTicket.expires_at <= utcnow()) | (BrowserLoginTicket.parent_hash == parent_hash)))
        ticket = new_token()
        db.add(BrowserLoginTicket(ticket_hash=token_hash(ticket), user_id=user.id,
                                 parent_hash=parent_hash, destination=body.destination,
                                 expires_at=utcnow() + timedelta(seconds=60)))
        db.commit()
        response.headers["Cache-Control"] = "no-store"
        # The fragment is never sent in HTTP requests or Referer headers.
        return {"path": f"/cabinet/#browser_ticket={ticket}", "expires_in": 60}

    @app.post("/api/v1/auth/browser/exchange")
    def exchange(body: BrowserExchangeIn, request: Request, response: Response,
                 db=Depends(db_session)):
        if request.headers.get("x-ai-client") != "browser":
            raise HTTPException(403, "Откройте ссылку в браузере")
        # Atomic consume works on both PostgreSQL and SQLite; replay cannot issue a session.
        ticket = db.execute(delete(BrowserLoginTicket).where(
            BrowserLoginTicket.ticket_hash == token_hash(body.ticket),
            BrowserLoginTicket.expires_at > utcnow()).returning(BrowserLoginTicket)).scalar_one_or_none()
        if not ticket:
            raise HTTPException(401, "Ссылка истекла. Откройте кабинет из агента ещё раз.")
        parent = db.get(SessionToken, ticket.parent_hash)
        if not parent or parent.user_id != ticket.user_id or parent.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
            raise HTTPException(401, "Подключение агента истекло. Войдите в агент заново.")
        grant = db.get(DeviceGrant, parent.token_hash)
        if grant:
            device = db.scalar(select(AgentDevice).where(
                AgentDevice.user_id == grant.user_id, AgentDevice.device_id == grant.device_id))
            if not device or device.revoked:
                raise HTTPException(401, "Доступ компьютера отозван")
        result = issue_session(db, db.get(User, ticket.user_id), request, response)
        return {**result, "destination": ticket.destination}
