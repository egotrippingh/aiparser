"""Promotions grant scans, never spendable money or answer recomputations."""
import json
import hashlib
import re
from datetime import timezone

from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import func, select

from server.models import Check, FreeScanBalance, PromoCode, PromoRedemption, Wallet, utcnow

SERVICES = ("chatgpt", "perplexity", "gemini", "google_aio", "yandex_neuro")


def normalize_code(value):
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{3,64}", value):
        raise ValueError("Промокод: 3–64 латинские буквы, цифры, дефис или подчёркивание")
    return value


class RedeemIn(BaseModel):
    code: str = Field(max_length=128)
    _normalize = field_validator("code")(normalize_code)


class ScanCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chatgpt: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    perplexity: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    gemini: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    google_aio: int = Field(default=0, ge=0, le=1_000_000, strict=True)
    yandex_neuro: int = Field(default=0, ge=0, le=1_000_000, strict=True)


class PromoConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: StrictBool = True
    max_redemptions: int | None = Field(default=None, ge=1, le=1_000_000, strict=True)
    expires_at: AwareDatetime | None = None

    @field_validator("expires_at")
    @classmethod
    def utc_expiry(cls, value):
        return value.astimezone(timezone.utc) if value else None


class PromoIn(RedeemIn, PromoConditions):
    scans: ScanCounts


class PromoUpdate(PromoConditions):
    revision: int = Field(ge=0, strict=True)


def promo_payload(row, uses):
    expiry = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at else None
    status = ("inactive" if not row.is_active else "expired" if expiry and expiry <= utcnow()
              else "exhausted" if row.max_redemptions is not None and uses >= row.max_redemptions else "active")
    return {"code": row.code, "scans": json.loads(row.scans_json), "created_at": row.created_at.isoformat(),
            "redemptions": uses, "is_active": row.is_active, "max_redemptions": row.max_redemptions,
            "expires_at": expiry.isoformat() if expiry else None, "revision": row.revision, "status": status}


def redeem_promo(db, user_id, code):
    db.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update()).scalar_one()
    promo = db.scalar(select(PromoCode).where(PromoCode.code == code).with_for_update())
    if not promo:
        raise HTTPException(404, "Промокод не найден. Проверьте написание.")
    if db.get(PromoRedemption, (user_id, code)):
        return {"code": code, "already_redeemed": True, "scans": json.loads(promo.scans_json)}
    if not promo.is_active:
        raise HTTPException(422, "Промокод отключён.")
    if promo.expires_at and promo.expires_at.replace(tzinfo=timezone.utc) <= utcnow():
        raise HTTPException(422, "Срок действия промокода истёк.")
    if promo.max_redemptions is not None:
        uses = db.scalar(select(func.count()).select_from(PromoRedemption).where(PromoRedemption.code == code))
        if uses >= promo.max_redemptions:
            raise HTTPException(422, "Лимит активаций промокода исчерпан.")
    scans = json.loads(promo.scans_json)
    for service, count in scans.items():
        if not count:
            continue
        balance = db.get(FreeScanBalance, (user_id, service))
        if balance is None:
            db.add(FreeScanBalance(user_id=user_id, service=service, remaining=count))
        else:
            balance.remaining += count
    db.add(PromoRedemption(user_id=user_id, code=code))
    return {"code": code, "already_redeemed": False, "scans": scans}


def free_scans_payload(db, user_id):
    balances = {row.service: row.remaining for row in db.scalars(select(FreeScanBalance).where(
        FreeScanBalance.user_id == user_id))}
    held = dict(db.execute(select(Check.free_scan_service, func.count()).where(
        Check.user_id == user_id, Check.status == "reserved", Check.free_scan_service.is_not(None))
        .group_by(Check.free_scan_service)).all())
    return {service: {"available": balances.get(service, 0), "reserved": held.get(service, 0)}
            for service in SERVICES}


def free_scans_state(balances):
    return hashlib.sha256(json.dumps({s: row["available"] for s, row in balances.items()},
                                    sort_keys=True).encode()).hexdigest()


def reserve_run_credits(db, user, run_id, snapshot):
    if user.is_admin:
        return
    db.execute(select(Wallet).where(Wallet.user_id == user.id).with_for_update()).scalar_one()
    for service in snapshot["cloud_services"]:
        balance = db.get(FreeScanBalance, (user.id, service))
        count = min(balance.remaining, len(snapshot["queries"])) if balance else 0
        # Freeze the free portion at launch so another run cannot increase its quoted cost.
        for query in snapshot["queries"][:count]:
            db.add(Check(user_id=user.id, client_check_id=f"{run_id}:{query['id']}:{service}",
                         price_kopeks=0, free_scan_service=service))
        if count:
            balance.remaining -= count
