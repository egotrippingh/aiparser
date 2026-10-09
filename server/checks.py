"""Shared server-owned reservation, model budget and settlement operations."""

import json
import os

from fastapi import HTTPException
from sqlalchemy import func, select

from server.ai import AIError, AIResult
from server.models import Check, LedgerEntry, Wallet
from server.scan_feedback import analysis_content


def _held(db, user_id):
    return db.scalar(select(func.coalesce(func.sum(Check.price_kopeks), 0)).where(
        Check.user_id == user_id, Check.status == "reserved")) or 0


def reserve_checks(db, user, ids, price, ai_client=None):
    if os.environ.get("APP_ENV") == "production" and not ai_client:
        raise HTTPException(503, "Серверный анализ не настроен; новые проверки временно недоступны")
    if len(ids) != len(set(ids)) or any(not 1 <= len(i) <= 100 for i in ids):
        raise HTTPException(422, "Идентификаторы проверок должны быть уникальными")
    effective_price = 0 if user.is_admin else price
    wallet = db.execute(select(Wallet).where(Wallet.user_id == user.id).with_for_update()).scalar_one()
    existing = {check.client_check_id: check for check in db.scalars(select(Check).where(
        Check.user_id == user.id, Check.client_check_id.in_(ids)))}
    if any(check.status == "released" and (check.analysis_attempts or check.arbitration_attempts
           or check.analysis_json or check.arbitration_json) for check in existing.values()):
        raise HTTPException(409, "Проверка с начатым анализом не может быть зарезервирована повторно")
    pending = [key for key in ids if key not in existing or existing[key].status == "released"]
    if len(pending) * effective_price > wallet.balance_kopeks - _held(db, user.id):
        raise HTTPException(402, "Недостаточно средств для выбранных проверок")
    for key in pending:
        if key in existing:
            check = existing[key]
            check.status, check.result_status, check.price_kopeks = "reserved", None, effective_price
            check.analysis_json = check.analysis_model = check.analysis_usage_json = None
            check.analysis_attempts = 0
            check.arbitration_json = check.arbitration_model = check.arbitration_usage_json = None
            check.arbitration_attempts = 0
        else:
            db.add(Check(user_id=user.id, client_check_id=key, price_kopeks=effective_price))
    db.commit()
    return effective_price


def _ai_payload(result: AIResult | str, fallback_model: str):
    if isinstance(result, AIResult):
        return result.raw, result.model, json.dumps(result.usage)
    return result, fallback_model, "{}"


def _usage_with_previous(previous, current):
    if not previous:
        return current
    old, new = json.loads(previous), json.loads(current)
    if not isinstance(old, dict) or not isinstance(new, dict):
        return current
    merged = {**old, **new}
    for key in ("cost", "prompt_tokens", "completion_tokens", "total_tokens"):
        before, after = old.get(key), new.get(key)
        if (isinstance(before, (int, float)) and not isinstance(before, bool)
                and isinstance(after, (int, float)) and not isinstance(after, bool)):
            merged[key] = before + after
    return json.dumps(merged)


def analyze_check(db, user, check_id, system, content, ai_client, *, retry_saved=False,
                  accumulate_usage=False):
    if not ai_client:
        raise HTTPException(503, "Серверный анализ пока не настроен")
    check = db.execute(select(Check).where(Check.user_id == user.id,
        Check.client_check_id == check_id).with_for_update()).scalar_one_or_none()
    if not check:
        raise HTTPException(404, "Проверка не зарезервирована")
    if check.analysis_json:
        return {"raw": check.analysis_json, "model": check.analysis_model or ai_client.model}
    if check.status != "reserved":
        raise HTTPException(409, "Проверка уже закрыта")
    if check.analysis_attempts >= (4 if retry_saved else 2):
        raise HTTPException(409, "Лимит попыток анализа исчерпан")
    check.analysis_attempts += 1
    try:
        raw, model, usage = _ai_payload(ai_client.analyze(system, analysis_content(db, check, content)), ai_client.model)
    except AIError as exc:
        import telemetry
        telemetry.capture(exc, component="server", operation="ai_analyze", user_id=user.id, run_id=check_id.split(":", 1)[0])
        db.commit()
        raise HTTPException(502, str(exc)) from exc
    if accumulate_usage:
        usage = _usage_with_previous(check.analysis_usage_json, usage)
    check.analysis_json, check.analysis_model, check.analysis_usage_json = raw, model, usage
    db.commit()
    return {"raw": raw, "model": model}


def arbitrate_check(db, user, check_id, system, content, ai_client, *, retry_saved=False,
                    accumulate_usage=False):
    if not ai_client:
        raise HTTPException(503, "Серверный арбитр пока не настроен")
    check = db.execute(select(Check).where(Check.user_id == user.id,
        Check.client_check_id == check_id).with_for_update()).scalar_one_or_none()
    if not check:
        raise HTTPException(404, "Проверка не зарезервирована")
    fallback = getattr(ai_client, "arbiter_model", ai_client.model)
    if check.arbitration_json:
        return {"raw": check.arbitration_json, "model": check.arbitration_model or fallback}
    if not check.analysis_json or not json.loads(check.analysis_json).get("found"):
        raise HTTPException(409, "Арбитр доступен только после положительного первого анализа")
    if check.status not in ("reserved", "settled"):
        raise HTTPException(409, "Проверка закрыта без оплаты")
    if check.arbitration_attempts >= (4 if retry_saved else 2):
        raise HTTPException(409, "Лимит попыток арбитра исчерпан")
    check.arbitration_attempts += 1
    try:
        raw, model, usage = _ai_payload(ai_client.arbitrate(system, analysis_content(db, check, content)), fallback)
    except AIError as exc:
        import telemetry
        telemetry.capture(exc, component="server", operation="ai_arbitrate", user_id=user.id, run_id=check_id.split(":", 1)[0])
        db.commit()
        raise HTTPException(502, str(exc)) from exc
    if accumulate_usage:
        usage = _usage_with_previous(check.arbitration_usage_json, usage)
    check.arbitration_json, check.arbitration_model, check.arbitration_usage_json = raw, model, usage
    db.commit()
    return {"raw": raw, "model": model}


def settle_check(db, wallet, check, status):
    check.status, check.result_status = "settled", status
    if check.price_kopeks:
        wallet.balance_kopeks -= check.price_kopeks
        db.add(LedgerEntry(user_id=check.user_id, amount_kopeks=-check.price_kopeks,
            kind="check", reference=f"check:{check.user_id}:{check.client_check_id}"))


def complete_check(db, user, check_id, status, *, commit=True):
    wallet = db.execute(select(Wallet).where(Wallet.user_id == user.id).with_for_update()).scalar_one()
    check = db.execute(select(Check).where(Check.user_id == user.id,
        Check.client_check_id == check_id).with_for_update()).scalar_one_or_none()
    if not check:
        raise HTTPException(404, "Проверка не зарезервирована")
    if check.status == "reserved":
        if status in ("found", "not_found") or check.analysis_json:
            settle_check(db, wallet, check, status)
        else:
            check.status, check.result_status = "released", status
        if commit:
            db.commit()
    return check.status
