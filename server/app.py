"""Публичный API аккаунта и денег. Не импортирует локальный API парсера."""

from __future__ import annotations

import json
import os
import uuid
from datetime import timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.coinso import CoinsoClient, CoinsoError, kopeks, verify_webhook
from server.models import Base, Check, LedgerEntry, PaymentOrder, SessionToken, User, Wallet, make_session_factory, utcnow
from server.security import hash_password, new_token, token_hash, verify_password


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=190)
    password: str = Field(min_length=12, max_length=256)


class TopupIn(BaseModel):
    amount_kopeks: int = Field(ge=30000, le=10_000_000)
    method: str = Field(pattern="^(sbp|card)$")


class ReserveIn(BaseModel):
    check_ids: list[str] = Field(min_length=1, max_length=1000)


class CompleteIn(BaseModel):
    status: str = Field(pattern="^(found|not_found|skipped|error|captcha|auth_required|limit_reached)$")


def _email(raw: str) -> str:
    email = raw.strip().lower()
    if "@" not in email or " " in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(422, "Укажите корректный email")
    return email


def _locked_wallet(db: Session, user_id: str) -> Wallet:
    return db.execute(select(Wallet).where(Wallet.user_id == user_id).with_for_update()).scalar_one()


def _held(db: Session, user_id: str) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(Check.price_kopeks), 0)).where(
            Check.user_id == user_id, Check.status == "reserved"
        )
    ) or 0


def _wallet_payload(db: Session, user_id: str) -> dict:
    wallet = db.get(Wallet, user_id)
    held = _held(db, user_id)
    entries = db.scalars(
        select(LedgerEntry).where(LedgerEntry.user_id == user_id)
        .order_by(LedgerEntry.id.desc()).limit(50)
    ).all()
    return {
        "balance_kopeks": wallet.balance_kopeks,
        "reserved_kopeks": held,
        "available_kopeks": wallet.balance_kopeks - held,
        "entries": [
            {"amount_kopeks": entry.amount_kopeks, "kind": entry.kind,
             "reference": entry.reference, "created_at": entry.created_at.isoformat()}
            for entry in entries
        ],
    }


def _order_payload(order: PaymentOrder) -> dict:
    return {
        "id": order.id,
        "amount_kopeks": order.amount_kopeks,
        "method": order.method,
        "status": order.status,
        "payment_url": order.payment_url,
        "created_at": order.created_at.isoformat(),
    }


def create_app(*, database_url: str | None = None, coinso_client: CoinsoClient | None = None) -> FastAPI:
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL не задан")
    if os.environ.get("APP_ENV") == "production" and not database_url.startswith("postgresql+"):
        raise RuntimeError("В продакшне требуется PostgreSQL")
    engine, SessionLocal = make_session_factory(database_url)
    Base.metadata.create_all(engine)

    secret_key = os.environ.get("COINSO_SECRET_KEY", "")
    if coinso_client is None and secret_key and os.environ.get("COINSO_PROJECT_ID"):
        coinso_client = CoinsoClient(
            os.environ.get("COINSO_API_BASE_URL", "https://coinso.io/api"),
            int(os.environ["COINSO_PROJECT_ID"]), secret_key,
        )
    allow_test = os.environ.get("COINSO_ALLOW_TEST_PAYMENTS", "false").lower() == "true"
    price = int(os.environ.get("CHECK_PRICE_KOPEKS", "150"))
    min_topup = int(os.environ.get("MIN_TOPUP_KOPEKS", "30000"))
    if price <= 0 or min_topup <= 0:
        raise RuntimeError("Цена и минимальное пополнение должны быть положительными")

    app = FastAPI(title="AI Mentions Account API")

    def db_session():
        with SessionLocal() as db:
            yield db

    def current_user(authorization: Annotated[str | None, Header()] = None,
                     db: Session = Depends(db_session)) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Войдите в аккаунт")
        token = authorization[7:]
        if len(token) > 200:
            raise HTTPException(401, "Недействительная сессия")
        session = db.get(SessionToken, token_hash(token))
        if not session:
            raise HTTPException(401, "Недействительная сессия")
        expires = session.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= utcnow():
            raise HTTPException(401, "Сессия истекла")
        return db.get(User, session.user_id)

    def issue_session(db: Session, user: User) -> dict:
        token = new_token()
        db.add(SessionToken(
            token_hash=token_hash(token), user_id=user.id,
            expires_at=utcnow() + timedelta(days=30),
        ))
        db.commit()
        return {"token": token, "user": {"id": user.id, "email": user.email}}

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/v1/pricing")
    def pricing() -> dict:
        return {"check_price_kopeks": price, "min_topup_kopeks": min_topup}

    @app.post("/api/v1/auth/register", status_code=201)
    def register(body: Credentials, db: Session = Depends(db_session)) -> dict:
        email = _email(body.email)
        user = User(id=uuid.uuid4().hex, email=email, password_hash=hash_password(body.password))
        db.add(user)
        db.add(Wallet(user_id=user.id, balance_kopeks=0))
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Аккаунт с таким email уже есть") from exc
        return issue_session(db, user)

    @app.post("/api/v1/auth/login")
    def login(body: Credentials, db: Session = Depends(db_session)) -> dict:
        user = db.scalar(select(User).where(User.email == _email(body.email)))
        if not user or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Неверный email или пароль")
        return issue_session(db, user)

    @app.post("/api/v1/auth/logout")
    def logout(user: User = Depends(current_user), db: Session = Depends(db_session),
               authorization: Annotated[str, Header()] = "") -> dict:
        db.query(SessionToken).filter_by(token_hash=token_hash(authorization[7:]), user_id=user.id).delete()
        db.commit()
        return {"ok": True}

    @app.get("/api/v1/me")
    def me(user: User = Depends(current_user)) -> dict:
        return {"id": user.id, "email": user.email}

    @app.get("/api/v1/wallet")
    def wallet(user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
        return _wallet_payload(db, user.id)

    def confirm_payment(db: Session, order: PaymentOrder, invoice_id: str) -> None:
        if not coinso_client:
            raise HTTPException(503, "Оплата пока не настроена")
        if not order.invoice_id:
            return  # создание счёта ещё не завершилось; клиент позже сверит статус
        if order.invoice_id != invoice_id:
            raise HTTPException(409, "Номер счёта не совпадает")
        try:
            status = coinso_client.invoice_status(invoice_id)
            amount = kopeks(status.get("amount", ""))
        except CoinsoError as exc:
            raise HTTPException(502, str(exc)) from exc
        if (status.get("status") != "paid" or status.get("invoice_id") != invoice_id
                or status.get("custom") != order.id or amount != order.amount_kopeks
                or status.get("currency") != "RUB" or status.get("payment_method") != order.method):
            return
        if order.test_mode and not allow_test:
            return
        _locked_wallet(db, order.user_id)
        locked = db.execute(
            select(PaymentOrder).where(PaymentOrder.id == order.id).with_for_update()
        ).scalar_one()
        if locked.status == "paid":
            return
        if locked.invoice_id and locked.invoice_id != invoice_id:
            raise HTTPException(409, "Номер счёта не совпадает")
        locked.invoice_id = invoice_id
        locked.status = "paid"
        wallet_row = db.get(Wallet, order.user_id)
        wallet_row.balance_kopeks += order.amount_kopeks
        db.add(LedgerEntry(
            user_id=order.user_id, amount_kopeks=order.amount_kopeks,
            kind="topup", reference=f"payment:{order.id}",
        ))
        db.commit()

    @app.post("/api/v1/payments", status_code=201)
    def create_payment(body: TopupIn, user: User = Depends(current_user),
                       db: Session = Depends(db_session)) -> dict:
        if not coinso_client or not secret_key:
            raise HTTPException(503, "Оплата пока не настроена")
        if body.amount_kopeks < min_topup:
            raise HTTPException(422, f"Минимальное пополнение {min_topup / 100:g} ₽")
        public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        if not public_base.startswith("https://"):
            raise HTTPException(503, "PUBLIC_BASE_URL должен быть HTTPS-адресом сайта")
        order = PaymentOrder(
            id=uuid.uuid4().hex, user_id=user.id,
            amount_kopeks=body.amount_kopeks, method=body.method,
        )
        db.add(order)
        db.commit()
        try:
            invoice = coinso_client.create_invoice(
                order_id=order.id, amount_kopeks=order.amount_kopeks,
                method=order.method, email=user.email,
                return_url=f"{public_base}/cabinet/?order={order.id}",
            )
        except CoinsoError as exc:
            order.status = "failed"
            db.commit()
            raise HTTPException(502, str(exc)) from exc
        order.invoice_id = invoice["invoice_id"]
        order.payment_url = invoice["payment_url"]
        order.test_mode = bool(invoice.get("test_mode"))
        if order.test_mode and not allow_test:
            order.status = "test_rejected"
            db.commit()
            raise HTTPException(503, "Coinso работает в тестовом режиме; реальные пополнения выключены")
        db.commit()
        return _order_payload(order)

    @app.get("/api/v1/payments")
    def list_payments(user: User = Depends(current_user), db: Session = Depends(db_session)) -> list[dict]:
        orders = db.scalars(
            select(PaymentOrder).where(PaymentOrder.user_id == user.id)
            .order_by(PaymentOrder.created_at.desc()).limit(50)
        ).all()
        return [_order_payload(o) for o in orders]

    @app.get("/api/v1/payments/{order_id}")
    def get_payment(order_id: str, user: User = Depends(current_user),
                    db: Session = Depends(db_session)) -> dict:
        order = db.get(PaymentOrder, order_id)
        if not order or order.user_id != user.id:
            raise HTTPException(404, "Платёж не найден")
        if order.status == "pending" and order.invoice_id:
            confirm_payment(db, order, order.invoice_id)
        return _order_payload(order)

    @app.post("/api/v1/webhooks/coinso")
    async def coinso_webhook(request: Request, db: Session = Depends(db_session)) -> dict:
        raw = await request.body()
        signature = request.headers.get("X-Signature", "")
        if not secret_key or not verify_webhook(raw, signature, secret_key):
            raise HTTPException(401, "Неверная подпись")
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise HTTPException(400, "Неверный JSON") from exc
        if payload.get("event") != "payment.success":
            return {"ok": True}
        order = db.get(PaymentOrder, payload.get("custom"))
        if not order or not payload.get("invoice_id"):
            raise HTTPException(404, "Заказ не найден")
        confirm_payment(db, order, payload["invoice_id"])
        return {"ok": True}

    @app.post("/api/v1/checks/reserve")
    def reserve(body: ReserveIn, user: User = Depends(current_user),
                db: Session = Depends(db_session)) -> dict:
        ids = body.check_ids
        if len(ids) != len(set(ids)) or any(not 1 <= len(i) <= 100 for i in ids):
            raise HTTPException(422, "Идентификаторы проверок должны быть уникальными")
        wallet_row = _locked_wallet(db, user.id)
        existing = {
            check.client_check_id: check for check in db.scalars(
                select(Check).where(Check.user_id == user.id, Check.client_check_id.in_(ids))
            )
        }
        pending = [check_id for check_id in ids if check_id not in existing or existing[check_id].status == "released"]
        available = wallet_row.balance_kopeks - _held(db, user.id)
        if len(pending) * price > available:
            raise HTTPException(402, "Недостаточно средств для выбранных проверок")
        for check_id in pending:
            if check_id in existing:
                existing[check_id].status = "reserved"
                existing[check_id].result_status = None
                existing[check_id].price_kopeks = price
            else:
                db.add(Check(user_id=user.id, client_check_id=check_id, price_kopeks=price))
        db.commit()
        return {"price_kopeks": price, "checks": ids, **_wallet_payload(db, user.id)}

    @app.post("/api/v1/checks/{check_id}/complete")
    def complete(check_id: str, body: CompleteIn, user: User = Depends(current_user),
                 db: Session = Depends(db_session)) -> dict:
        wallet_row = _locked_wallet(db, user.id)
        check = db.execute(
            select(Check).where(Check.user_id == user.id, Check.client_check_id == check_id).with_for_update()
        ).scalar_one_or_none()
        if not check:
            raise HTTPException(404, "Проверка не зарезервирована")
        if check.status != "reserved":
            return {"status": check.status, **_wallet_payload(db, user.id)}
        if body.status in ("found", "not_found"):
            check.status = "settled"
            wallet_row.balance_kopeks -= check.price_kopeks
            db.add(LedgerEntry(
                user_id=user.id, amount_kopeks=-check.price_kopeks,
                kind="check", reference=f"check:{user.id}:{check_id}",
            ))
        else:
            check.status = "released"
        check.result_status = body.status
        db.commit()
        return {"status": check.status, **_wallet_payload(db, user.id)}

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if (web_dir / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def landing() -> FileResponse:
            return FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-cache"})

        @app.get("/favicon.svg", include_in_schema=False)
        def favicon() -> FileResponse:
            return FileResponse(web_dir / "favicon.svg")

        @app.get("/cabinet/", include_in_schema=False)
        @app.get("/cabinet", include_in_schema=False)
        def cabinet() -> FileResponse:
            return FileResponse(web_dir / "cabinet" / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app() if os.environ.get("DATABASE_URL") else None
