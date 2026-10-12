"""Private operator view; never expose provider credentials or response bodies."""
import asyncio
import os
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from server.models import Check, User, Wallet, utcnow


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
            "currency": "RUB" if provider == "xmlriver" else "CREDITS" if provider == "scrapeless" else "USD", "balance": None, "details": [],
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
                row["balance"] = amount(data["credits"])
                row["details"] = [{"label": "Credits", "amount": row["balance"]}]
                plan = data.get("plan")
                if isinstance(plan, dict) and plan.get("credits") is not None:
                    row["details"].append({"label": "Остаток подписки", "amount": amount(plan["credits"]),
                        "expires_at": plan.get("endAt")})
                if data.get("excessCredits") is not None:
                    row["details"].append({"label": "Excess Credits", "amount": amount(data["excessCredits"])})
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

    app.include_router(router)
