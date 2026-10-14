"""Private operator view; never expose provider credentials or response bodies."""
import asyncio
import json
import os
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, StrictBool
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from server.models import Check, PromoCode, PromoRedemption, ProviderAccount, User, Wallet, utcnow
from server.promos import PromoIn

SERVICES = ("chatgpt", "perplexity", "gemini", "google_aio", "yandex_neuro")


class ProviderPauseIn(BaseModel):
    paused: StrictBool


def amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Missing balance")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Invalid balance")
    return str(result)


async def provider_balances(client):
    async def fetch(provider):
        row = {"id": provider, "name": {"openrouter": "OpenRouter", "scrapeless": "Scrapeless", "xmlriver": "XMLRiver"}[provider],
            "currency": "RUB" if provider == "xmlriver" else "USD", "balance": None, "details": [],
            "status": "unavailable", "message": None, "checked_at": utcnow().isoformat(),
            "topup_url": {"openrouter": "https://openrouter.ai/settings/credits",
                "scrapeless": "https://app.scrapeless.com/", "xmlriver": "https://xmlriver.com/account/"}[provider]}
        key = os.environ.get({"openrouter": "OPENROUTER_MANAGEMENT_KEY", "scrapeless": "SCRAPELESS_API_KEY",
                              "xmlriver": "AIPARSER_XMLRIVER_KEY"}[provider], "")
        if provider == "openrouter":
            key = key or os.environ.get("OPENROUTER_API_KEY", "")
        user = os.environ.get("AIPARSER_XMLRIVER_USER", "")
        if not key or (provider == "xmlriver" and not user):
            row.update(status="not_configured", message="Доступ к балансу не настроен")
            return row
        try:
            if provider == "openrouter":
                response = await client.get("https://openrouter.ai/api/v1/credits", headers={"Authorization": "Bearer " + key})
            elif provider == "scrapeless":
                response = await client.get("https://api.scrapeless.com/api/v1/me", headers={"x-api-token": key})
            else:
                # The shared XMLRiver HTTP log filter redacts credential-bearing URLs.
                from shared import xmlriver  # noqa: F401
                response = await client.get("https://xmlriver.com/api/get_balance/", params={"user": user, "key": key})
            response.raise_for_status()
            if provider == "xmlriver":
                row["balance"] = amount(response.text.strip())
            elif provider == "openrouter":
                data = response.json()["data"]
                row["balance"] = amount(Decimal(amount(data["total_credits"])) - Decimal(amount(data["total_usage"])))
            else:
                data = response.json()
                # Dashboard formatCredits uses USD; /teams/current and /subscriptions/current confirm the same amounts.
                row["balance"] = amount(data["credits"])
                row["details"] = [{"label": "Credits", "amount": row["balance"]}]
                plan = data.get("plan")
                if isinstance(plan, dict) and plan.get("credits") is not None:
                    row["details"].append({"label": "Остаток подписки", "amount": amount(plan["credits"]),
                        "expires_at": plan.get("endAt")})
                if data.get("excessCredits") is not None:
                    row["details"].append({"label": "Excess Credits", "amount": amount(data["excessCredits"]), "currency": "CREDITS"})
            row["status"] = "ok"
        except httpx.HTTPStatusError as exc:
            row["message"] = ("Для баланса аккаунта нужен management key" if provider == "openrouter" and
                exc.response.status_code in (401, 403) else f"Баланс недоступен (HTTP {exc.response.status_code})")
        except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation):
            row["message"] = "Не удалось получить актуальный баланс"
        return row
    return list(await asyncio.gather(*(fetch(p) for p in ("openrouter", "scrapeless", "xmlriver"))))


def register_admin(app, db_session, current_user):
    router = APIRouter(prefix="/api/v1/admin")

    def admin(user=Depends(current_user)):
        if not user.is_admin:
            raise HTTPException(403, "Доступно только администратору")
        return user

    @router.get("/promos")
    def promos(response: Response, offset: int = Query(default=0, ge=0),
               user=Depends(admin), db=Depends(db_session)):
        response.headers["Cache-Control"] = "no-store"
        counts = select(PromoRedemption.code, func.count().label("uses")).group_by(PromoRedemption.code).subquery()
        rows = db.execute(select(PromoCode, counts.c.uses).outerjoin(counts, counts.c.code == PromoCode.code)
            .order_by(PromoCode.created_at.desc(), PromoCode.code).offset(offset).limit(50)).all()
        return {"total": db.scalar(select(func.count()).select_from(PromoCode)),
                "promos": [{"code": row.code, "scans": json.loads(row.scans_json),
                            "created_at": row.created_at.isoformat(), "redemptions": uses or 0}
                           for row, uses in rows]}

    @router.post("/promos", status_code=201)
    def create_promo(body: PromoIn, response: Response, user=Depends(admin), db=Depends(db_session)):
        row = PromoCode(code=body.code, scans_json=body.scans.model_dump_json(), created_by=user.id)
        db.add(row)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Промокод с таким названием уже существует") from exc
        response.headers["Cache-Control"] = "no-store"
        return {"code": row.code, "scans": json.loads(row.scans_json),
                "created_at": row.created_at.isoformat(), "redemptions": 0}

    @router.get("/users")
    def users(response: Response, search: str = Query(default="", max_length=200),
              offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
              user=Depends(admin), db=Depends(db_session)):
        response.headers["Cache-Control"] = "no-store"
        conditions = [User.email.contains(search, autoescape=True)] if search else []
        total = db.scalar(select(func.count()).select_from(User).where(*conditions))
        held = select(Check.user_id, func.sum(Check.price_kopeks).label("held")).where(
            Check.status == "reserved").group_by(Check.user_id).subquery()
        rows = db.execute(select(User, Wallet.balance_kopeks, held.c.held).outerjoin(Wallet,
            Wallet.user_id == User.id).outerjoin(held, held.c.user_id == User.id).where(*conditions)
            .order_by(User.created_at, User.id).offset(offset).limit(limit)).all()
        return {"total": total, "users": [{"id": u.id, "email": u.email, "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat(), "wallet": {"balance_kopeks": balance or 0,
                "reserved_kopeks": reserved or 0, "available_kopeks": (balance or 0) - (reserved or 0)}}
                for u, balance, reserved in rows]}

    @router.get("/provider-balances")
    async def balances(response: Response, user=Depends(admin)):
        response.headers["Cache-Control"] = "no-store"
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            return {"providers": await provider_balances(client)}

    @router.get("/providers")
    def providers(response: Response, user=Depends(admin), db=Depends(db_session)):
        response.headers["Cache-Control"] = "no-store"
        rows = {row.service: row for row in db.scalars(select(ProviderAccount)).all()}
        return {"providers": [{"service": service, "paused": bool(rows.get(service) and rows[service].paused)} for service in SERVICES]}

    @router.put("/providers/{service}")
    def provider_pause(service: str, body: ProviderPauseIn, response: Response, user=Depends(admin), db=Depends(db_session)):
        if service not in SERVICES:
            raise HTTPException(404, "Неизвестная ИИ-система")
        account = db.scalar(select(ProviderAccount).where(ProviderAccount.service == service).with_for_update())
        if not account:
            raise HTTPException(409, "Требуется миграция аккаунтов сервисов")
        if account.paused != body.paused:
            account.paused = body.paused
            account.revision += 1
            # This is an admission cutoff, not a provider revision: a resumed
            # service must still exclude slots that elapsed while it was paused.
            account.last_paused_at = utcnow()
            db.commit()
        response.headers["Cache-Control"] = "no-store"
        return {"service": service, "paused": account.paused}

    app.include_router(router)
