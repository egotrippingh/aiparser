"""Promotions grant scans, never spendable money or answer recomputations."""
import json
import hashlib
import re

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from server.models import Check, FreeScanBalance, PromoCode, PromoRedemption, Wallet

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


class PromoIn(RedeemIn):
    scans: ScanCounts


def redeem_promo(db, user_id, code):
    db.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update()).scalar_one()
    promo = db.get(PromoCode, code)
    if not promo:
        raise HTTPException(404, "Промокод не найден. Проверьте написание.")
    if db.get(PromoRedemption, (user_id, code)):
        return {"code": code, "already_redeemed": True, "scans": json.loads(promo.scans_json)}
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
