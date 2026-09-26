"""Публичный API аккаунта и денег. Не импортирует локальный API парсера."""

from __future__ import annotations

import json
import hmac
import logging
import os
import re
import uuid
from datetime import timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.agent_schemas import AgentHeartbeatIn, CloudResultsIn, ScanPreferencesIn
from server.ai import AIError, AIResult, OpenRouterAI
from server.auth_limit import clear as clear_auth_failures
from server.auth_limit import email_key, guard as guard_auth, record as record_auth, source_key
from server.coinso import CoinsoClient, CoinsoError, kopeks, verify_webhook
from server.mailer import PasswordMailer
from server.migrate import upgrade_database
from server.models import (AgentDevice, Check, CloudResult, ScanPreferences, Screenshot, DeviceCode,
                           LedgerEntry, LoginTicket, OAuthAttempt, OAuthIdentity, PasswordReset,
                           PaymentOrder, SessionToken, User, Wallet, make_session_factory, utcnow)
from server.security import hash_password, new_token, token_hash, verify_password
from server.storage import ScreenshotStorage, StorageError
from server.yandex import YandexError, YandexOAuth
from server.models import ControlProject, ControlRun, ControlLink, DeviceGrant
from server.control import register_control


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


class AnalyzeIn(BaseModel):
    system: str = Field(min_length=50, max_length=4000)
    content: list[dict] = Field(min_length=1, max_length=4)


def _validate_ai_content(content: list[dict]) -> None:
    if (len(json.dumps(content)) > 2_000_000
            or content[0].get("type") != "text"
            or not isinstance(content[0].get("text"), str)
            or len(content[0]["text"]) > 12000
            or any(part.get("type") != "image_url"
                   or not isinstance(part.get("image_url"), dict)
                   or not str(part["image_url"].get("url", "")).startswith("data:image/webp;base64,")
                   for part in content[1:])):
        raise HTTPException(422, "Неверные или слишком большие данные для анализа")


def _ai_payload(result: AIResult | str, fallback_model: str) -> tuple[str, str, str]:
    if isinstance(result, AIResult):
        return result.raw, result.model, json.dumps(result.usage)
    return result, fallback_model, "{}"


class TicketIn(BaseModel):
    ticket: str = Field(min_length=30, max_length=200)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=190)


class PasswordResetConfirm(BaseModel):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{30,200}$")
    password: str = Field(min_length=12, max_length=256)


def _email(raw: str) -> str:
    email = raw.strip().lower()
    if not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", email):
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
    user = db.get(User, user_id)
    held = _held(db, user_id)
    entries = db.scalars(
        select(LedgerEntry).where(LedgerEntry.user_id == user_id)
        .order_by(LedgerEntry.id.desc()).limit(50)
    ).all()
    return {
        "unlimited_checks": bool(user.is_admin),
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


def _scan_preferences_payload(row: ScanPreferences | None) -> dict:
    if row is None:
        return {"revision": 0, "enabled": False, "local_time": "09:00",
                "month_days": [1], "browser_mode": "headless",
                "services": ["perplexity", "chatgpt"], "speed_profile": "balanced"}
    return {"revision": row.revision, "enabled": row.enabled,
            "local_time": row.local_time, "month_days": json.loads(row.month_days_json),
            "browser_mode": row.browser_mode, "services": json.loads(row.services_json),
            "speed_profile": row.speed_profile}


def _counts_as_found(row: CloudResult, *, include_cards: bool) -> bool:
    if row.status != "found":
        return False
    kinds = set(json.loads(row.mention_types_json or "[]"))
    return include_cards or not kinds or bool(kinds - {"marketplace"})


def create_app(*, database_url: str | None = None, coinso_client: CoinsoClient | None = None,
               ai_client: OpenRouterAI | None = None,
               yandex_client: YandexOAuth | None = None,
               screenshot_storage: ScreenshotStorage | None = None,
               password_mailer: PasswordMailer | None = None) -> FastAPI:
    database_url = database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL не задан")
    if os.environ.get("APP_ENV") == "production" and not database_url.startswith("postgresql+"):
        raise RuntimeError("В продакшне требуется PostgreSQL")
    upgrade_database(database_url)
    engine, SessionLocal = make_session_factory(database_url)

    secret_key = os.environ.get("COINSO_SECRET_KEY", "")
    if coinso_client is None and secret_key and os.environ.get("COINSO_PROJECT_ID"):
        coinso_client = CoinsoClient(
            os.environ.get("COINSO_API_BASE_URL", "https://coinso.io/api"),
            int(os.environ["COINSO_PROJECT_ID"]), secret_key,
        )
    if ai_client is None and os.environ.get("OPENROUTER_API_KEY"):
        ai_client = OpenRouterAI(os.environ["OPENROUTER_API_KEY"])
    if screenshot_storage is None:
        screenshot_storage = ScreenshotStorage.from_env()
    public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if password_mailer is None and os.environ.get("SMTP_HOST"):
        password_mailer = PasswordMailer(
            os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")),
            os.environ["SMTP_FROM"], os.environ.get("SMTP_USER", ""),
            os.environ.get("SMTP_PASSWORD", ""), os.environ.get("SMTP_SECURITY", "starttls"),
            public_base,
        )
    if yandex_client is None and public_base and os.environ.get("YANDEX_CLIENT_ID") and os.environ.get("YANDEX_CLIENT_SECRET"):
        if not (public_base.startswith("https://") or public_base.startswith("http://127.0.0.1:")
                or public_base.startswith("http://localhost:")):
            raise RuntimeError("Яндекс ID требует HTTPS-адрес сайта")
        yandex_client = YandexOAuth(
            os.environ["YANDEX_CLIENT_ID"], os.environ["YANDEX_CLIENT_SECRET"],
            f"{public_base}/api/v1/auth/yandex/callback",
        )
    allow_test = os.environ.get("COINSO_ALLOW_TEST_PAYMENTS", "false").lower() == "true"
    price = int(os.environ.get("CHECK_PRICE_KOPEKS", "200"))
    min_topup = int(os.environ.get("MIN_TOPUP_KOPEKS", "30000"))
    if price <= 0 or min_topup <= 0:
        raise RuntimeError("Цена и минимальное пополнение должны быть положительными")

    app = FastAPI(title="AI Mentions Account API")
    oauth_cookie = "aimt_yandex_state"
    cookie_secure = public_base.startswith("https://")

    def cabinet_location(fragment: str = "") -> str:
        return f"{public_base}/cabinet/{fragment}" if public_base else f"/cabinet/{fragment}"

    def oauth_redirect(suffix: str) -> RedirectResponse:
        response = RedirectResponse(cabinet_location(suffix), status_code=303)
        response.delete_cookie(oauth_cookie, path="/api/v1/auth/yandex")
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def expired(value) -> bool:
        at = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return at <= utcnow()

    def db_session():
        with SessionLocal() as db:
            yield db

    def current_user(request: Request, authorization: Annotated[str | None, Header()] = None,
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
        grant = db.get(DeviceGrant, session.token_hash)
        if grant:
            device = db.scalar(select(AgentDevice).where(AgentDevice.user_id == grant.user_id,
                                                         AgentDevice.device_id == grant.device_id))
            if not device or device.revoked:
                raise HTTPException(401, "Доступ компьютера отозван")
            allowed = request.url.path.startswith(("/api/v1/control/agent/", "/api/v1/checks/")) or request.url.path in (
                "/api/v1/me", "/api/v1/wallet", "/api/v1/auth/logout", "/api/v1/agent/results")
            if not allowed:
                raise HTTPException(403, "Это действие доступно только на сайте")
            check_id = request.path_params.get("check_id")
            if check_id:
                assigned_check(db, grant, check_id,
                    live=request.url.path.endswith(("/analyze", "/arbitrate")))
        return db.get(User, session.user_id)

    def assigned_check(db, grant, check_id, *, live=False, new=False):
        parts = check_id.split(":")
        run = db.get(ControlRun, parts[0]) if len(parts) == 3 else None
        if not run:
            # Existing pre-upgrade checks may still need settlement or screenshots.
            if not new and db.scalar(select(Check.id).where(Check.user_id == grant.user_id,
                    Check.client_check_id == check_id)):
                return
            raise HTTPException(403, "Проверка не назначена этому компьютеру")
        snap = json.loads(run.snapshot_json)
        if (run.user_id != grant.user_id or run.device_id != grant.device_id
                or parts[1] not in {q["id"] for q in snap["queries"]}
                or parts[2] not in snap["config"]["services"]):
            raise HTTPException(403, "Проверка не назначена этому компьютеру")
        until = run.lease_until
        if until and until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if live and (run.state not in ("running", "paused") or run.desired_state == "cancelled"
                     or not until or until < utcnow()):
            raise HTTPException(409, "Задание остановлено или связь с агентом потеряна")

    def issue_session(db: Session, user: User) -> dict:
        token = new_token()
        db.add(SessionToken(
            token_hash=token_hash(token), user_id=user.id,
            expires_at=utcnow() + timedelta(days=30),
        ))
        db.commit()
        return {"token": token, "user": {"id": user.id, "email": user.email}}

    register_control(app, db_session, current_user, SessionLocal)

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/v1/pricing")
    def pricing() -> dict:
        return {"check_price_kopeks": price, "min_topup_kopeks": min_topup,
                "managed_detection": ai_client is not None,
                "detection_model": ai_client.model if ai_client else None,
                "arbiter_model": getattr(ai_client, "arbiter_model", ai_client.model) if ai_client else None}

    def agent_archive() -> Path:
        return Path(os.environ.get("AGENT_DOWNLOAD_FILE") or
                    Path(__file__).resolve().parent.parent / "dist" / "AI-Mentions-Windows-latest.zip")

    @app.get("/api/v1/agent-download")
    def agent_download_status() -> dict:
        archive = agent_archive()
        return {"available": archive.is_file(),
                "url": "/downloads/AI-Mentions-Windows.zip" if archive.is_file() else None,
                "size_bytes": archive.stat().st_size if archive.is_file() else None}

    @app.get("/downloads/AI-Mentions-Windows.zip", include_in_schema=False)
    def download_agent() -> FileResponse:
        archive = agent_archive()
        if not archive.is_file():
            raise HTTPException(404, "Агент пока не опубликован")
        return FileResponse(archive, media_type="application/zip",
                            filename="AI-Mentions-Windows.zip")

    @app.get("/api/v1/scan-preferences")
    def get_scan_preferences(user: User = Depends(current_user),
                             db: Session = Depends(db_session)) -> dict:
        return _scan_preferences_payload(db.get(ScanPreferences, user.id))

    @app.put("/api/v1/scan-preferences")
    def put_scan_preferences(body: ScanPreferencesIn, user: User = Depends(current_user),
                             db: Session = Depends(db_session)) -> dict:
        # Revision prevents the website and an older desktop settings tab from
        # silently overwriting one another.
        row = db.execute(select(ScanPreferences).where(ScanPreferences.user_id == user.id)
                         .with_for_update()).scalar_one_or_none()
        actual_revision = row.revision if row else 0
        if body.revision != actual_revision:
            raise HTTPException(409, "Настройки изменились на другом устройстве. Обновите их и повторите.")
        if row is None:
            row = ScanPreferences(user_id=user.id)
            db.add(row)
        row.enabled = body.enabled
        row.local_time = body.local_time
        row.month_days_json = json.dumps(body.month_days)
        row.browser_mode = body.browser_mode
        row.services_json = json.dumps(body.services)
        row.speed_profile = body.speed_profile
        row.revision = actual_revision + 1
        row.updated_at = utcnow()
        db.commit()
        return _scan_preferences_payload(row)

    @app.post("/api/v1/agent/heartbeat")
    def agent_heartbeat(body: AgentHeartbeatIn, user: User = Depends(current_user),
                        db: Session = Depends(db_session)) -> dict:
        device = db.scalar(select(AgentDevice).where(AgentDevice.user_id == user.id,
                                                     AgentDevice.device_id == body.device_id))
        if device is None:
            device = AgentDevice(user_id=user.id, device_id=body.device_id)
            db.add(device)
        device.name = body.name.strip()
        device.local_time_zone = body.local_time_zone
        device.active_scan = body.active_scan
        device.last_seen_at = utcnow()
        db.commit()
        return {"ok": True, "preferences": _scan_preferences_payload(db.get(ScanPreferences, user.id))}

    @app.get("/api/v1/agent/devices")
    def agent_devices(user: User = Depends(current_user),
                      db: Session = Depends(db_session)) -> list[dict]:
        devices = db.scalars(select(AgentDevice).where(AgentDevice.user_id == user.id)
                             .order_by(AgentDevice.last_seen_at.desc())).all()
        online_since = utcnow() - timedelta(minutes=3)
        result = []
        for device in devices:
            seen = device.last_seen_at
            if seen.tzinfo is None:  # SQLite drops timezone metadata.
                seen = seen.replace(tzinfo=timezone.utc)
            online = seen > online_since
            result.append({"device_id": device.device_id, "name": device.name,
                           "local_time_zone": device.local_time_zone,
                           "active_scan": device.active_scan and online,
                           "online": online, "last_seen_at": seen.isoformat()})
        return result

    @app.post("/api/v1/agent/results")
    def upload_agent_results(body: CloudResultsIn, request: Request, user: User = Depends(current_user),
                             db: Session = Depends(db_session)) -> dict:
        ids = [item.local_result_id for item in body.results]
        grant = db.get(DeviceGrant, token_hash(request.headers.get("authorization", "")[7:]))
        if grant and body.device_id != grant.device_id:
            raise HTTPException(403, "Результаты относятся к другому компьютеру")
        if len(ids) != len(set(ids)):
            raise HTTPException(422, "Результат повторяется в пакете")
        if any(item.status in ("found", "not_found") and not item.check_id for item in body.results):
            raise HTTPException(422, "Для результата проверки нужен оплаченный check_id")
        device = db.scalar(select(AgentDevice.id).where(AgentDevice.user_id == user.id,
                                                        AgentDevice.device_id == body.device_id))
        if device is None:
            raise HTTPException(409, "Сначала подключите агент к аккаунту")
        check_ids = {item.check_id for item in body.results if item.check_id}
        if check_ids:
            owned = set(db.scalars(select(Check.client_check_id).where(
                Check.user_id == user.id, Check.client_check_id.in_(check_ids),
                Check.status == "settled")).all())
            if owned != check_ids:
                raise HTTPException(409, "Часть результатов ещё не оплачена или относится к другому аккаунту")
        existing = set(db.scalars(select(CloudResult.local_result_id).where(
            CloudResult.user_id == user.id, CloudResult.device_id == body.device_id,
            CloudResult.local_result_id.in_([item.local_result_id for item in body.results]))).all())
        for item in body.results:
            if item.local_result_id in existing:
                continue
            project_id = item.project_id
            if item.run_id:
                run = db.get(ControlRun, item.run_id)
                if not run or run.user_id != user.id or run.device_id != body.device_id or run.project_id != project_id:
                    raise HTTPException(403, "Результат не соответствует заданию устройства")
                snap = json.loads(run.snapshot_json)
                query = next((q for q in snap["queries"] if q["id"] == item.query_id), None)
                if not query or item.service not in snap["config"]["services"] or query["text"] != item.query_text:
                    raise HTTPException(422, "Запрос отсутствует в задании")
                expected_check = f"{run.id}:{item.query_id}:{item.service}"
                if item.check_id and item.check_id != expected_check:
                    raise HTTPException(422, "Проверка не соответствует заданию")
            elif project_id:
                project_row = db.get(ControlProject, project_id)
                link = db.scalar(select(ControlLink).where(ControlLink.user_id == user.id,
                    ControlLink.device_id == body.device_id, ControlLink.local_project_id == item.local_project_id,
                    ControlLink.project_id == project_id))
                if not project_row or project_row.user_id != user.id or not link:
                    raise HTTPException(403, "Проект не принадлежит устройству")
            else:
                link = db.scalar(select(ControlLink).where(ControlLink.user_id == user.id,
                    ControlLink.device_id == body.device_id, ControlLink.local_project_id == item.local_project_id))
                project_id = link.project_id if link else None
            db.add(CloudResult(
                user_id=user.id, device_id=body.device_id,
                local_result_id=item.local_result_id, local_project_id=item.local_project_id,
                project_name=item.project_name, brand_name=item.brand_name,
                query_text=item.query_text, group_tag=item.group_tag, service=item.service,
                scan_date=item.scan_date, status=item.status,
                mention_types_json=json.dumps(item.mention_types, ensure_ascii=False),
                evidence_quote=item.evidence_quote, answer_text=item.answer_text,
                sources_json=json.dumps(item.sources, ensure_ascii=False), check_id=item.check_id,
                project_id=project_id, query_id=item.query_id, run_id=item.run_id,
            ))
        db.commit()
        return {"accepted": len(body.results)}

    @app.get("/api/v1/reports/projects")
    def report_projects(user: User = Depends(current_user),
                        db: Session = Depends(db_session)) -> list[dict]:
        rows = db.execute(select(CloudResult.device_id, CloudResult.local_project_id,
                                 CloudResult.project_name, CloudResult.brand_name,
                                 CloudResult.scan_date).where(CloudResult.user_id == user.id)
                          .order_by(CloudResult.scan_date.desc(), CloudResult.id.desc())).all()
        projects: dict[str, dict] = {}
        for row in rows:
            key = f"{row.device_id}:{row.local_project_id}"
            if key not in projects:
                projects[key] = {"key": key, "name": row.project_name,
                                 "brand_name": row.brand_name, "last_scan_date": row.scan_date,
                                 "checks": 0}
            projects[key]["checks"] += 1
        return list(projects.values())

    @app.get("/api/v1/reports")
    def report(project: str, days: int = 30, include_cards: bool = True,
               limit: int = 100, offset: int = 0,
               user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
        if not re.fullmatch(r"[a-f0-9]{32}(?::[1-9]\d*)?", project):
            raise HTTPException(422, "Неверный проект")
        if not 1 <= days <= 365 or not 1 <= limit <= 200 or offset < 0:
            raise HTTPException(422, "Неверный период или страница отчёта")
        cutoff = (utcnow().date() - timedelta(days=days - 1)).isoformat()
        if ":" in project:
            device_id, project_id_text = project.split(":")
            project_filter = (CloudResult.device_id == device_id) & (CloudResult.local_project_id == int(project_id_text))
        else:
            project_filter = CloudResult.project_id == project
        rows = db.scalars(select(CloudResult).where(
            CloudResult.user_id == user.id, project_filter, CloudResult.scan_date >= cutoff,
        ).order_by(CloudResult.scan_date.desc(), CloudResult.id.desc())).all()
        # A daily view shows the latest measurement per query and service.
        picked = {}
        for row in rows:
            picked.setdefault((row.query_id or row.query_text, row.service, row.scan_date), row)
        rows = list(picked.values())
        by_service: dict[str, dict] = {}
        by_date: dict[str, dict] = {}
        found = 0
        checked = 0
        for row in rows:
            if row.status not in ("found", "not_found"):
                continue
            counted = _counts_as_found(row, include_cards=include_cards)
            checked += 1
            found += int(counted)
            for bucket, name in ((by_service, row.service), (by_date, row.scan_date)):
                stats = bucket.setdefault(name, {"found": 0, "checked": 0})
                stats["found"] += int(counted)
                stats["checked"] += 1
        page = rows[offset:offset + limit]
        return {"summary": {"found": found, "checked": checked,
                            "visibility_pct": round(found * 100 / checked) if checked else None,
                            "by_service": by_service, "by_date": by_date},
                "total": len(rows), "results": [{
                    "id": row.id, "query_text": row.query_text, "project_name": row.project_name,
                    "brand_name": row.brand_name, "group_tag": row.group_tag,
                    "service": row.service, "scan_date": row.scan_date,
                    "status": row.status, "counts_as_found": _counts_as_found(row, include_cards=include_cards),
                    "mention_types": json.loads(row.mention_types_json or "[]"),
                    "evidence_quote": row.evidence_quote, "answer_text": row.answer_text,
                    "sources": json.loads(row.sources_json or "[]"),
                    "check_id": row.check_id,
                } for row in page]}

    @app.get("/api/v1/auth/providers")
    def auth_providers() -> dict:
        return {"yandex": yandex_client is not None,
                "password_reset": password_mailer is not None}

    def start_yandex(db: Session, *, purpose: str, user_id: str | None = None) -> tuple[str, str]:
        if not yandex_client:
            raise HTTPException(503, "Вход через Яндекс ещё не настроен")
        state, verifier = new_token(), new_token()
        db.execute(delete(OAuthAttempt).where(OAuthAttempt.expires_at < utcnow()))
        db.execute(delete(LoginTicket).where(LoginTicket.expires_at < utcnow()))
        db.add(OAuthAttempt(state_hash=token_hash(state), code_verifier=verifier,
                            purpose=purpose, user_id=user_id,
                            expires_at=utcnow() + timedelta(minutes=10)))
        db.commit()
        return yandex_client.authorize_url(state, verifier), state

    def set_yandex_cookie(response, state: str) -> None:
        response.set_cookie(oauth_cookie, state, max_age=600, httponly=True,
                            secure=cookie_secure, samesite="lax", path="/api/v1/auth/yandex")

    @app.get("/api/v1/auth/yandex/start")
    def yandex_start(request: Request, db: Session = Depends(db_session)) -> RedirectResponse:
        source = source_key(request)
        guard_auth(db, "yandex_start", [(source, 30)])
        record_auth(db, "yandex_start", [source])
        url, state = start_yandex(db, purpose="login")
        response = RedirectResponse(url, status_code=303)
        set_yandex_cookie(response, state)
        return response

    @app.post("/api/v1/auth/yandex/link/start")
    def yandex_link_start(user: User = Depends(current_user),
                          db: Session = Depends(db_session)) -> JSONResponse:
        url, state = start_yandex(db, purpose="link", user_id=user.id)
        response = JSONResponse({"authorization_url": url})
        set_yandex_cookie(response, state)
        return response

    @app.get("/api/v1/auth/yandex/callback")
    def yandex_callback(request: Request, state: str = "", code: str = "", error: str = "",
                        db: Session = Depends(db_session)) -> RedirectResponse:
        browser_state = request.cookies.get(oauth_cookie, "")
        if not state or not browser_state or not hmac.compare_digest(state, browser_state):
            raise HTTPException(400, "Неверное состояние входа через Яндекс")
        attempt = db.execute(select(OAuthAttempt).where(OAuthAttempt.state_hash == token_hash(state))
                             .with_for_update()).scalar_one_or_none()
        if not attempt or expired(attempt.expires_at):
            raise HTTPException(400, "Время входа через Яндекс истекло")
        purpose, link_user_id, verifier = attempt.purpose, attempt.user_id, attempt.code_verifier
        db.delete(attempt)
        db.commit()  # состояние одноразовое, даже если Яндекс вернёт ошибку
        if error or not code:
            return oauth_redirect("?auth_error=cancelled")
        if not yandex_client:
            return oauth_redirect("?auth_error=provider")
        try:
            profile = yandex_client.profile(code, verifier)
        except YandexError:
            return oauth_redirect("?auth_error=provider")
        if str(profile.get("client_id")) != yandex_client.client_id:
            return oauth_redirect("?auth_error=provider")
        subject = str(profile.get("id") or "")
        if not subject or len(subject) > 190:
            return oauth_redirect("?auth_error=provider")
        identity = db.scalar(select(OAuthIdentity).where(OAuthIdentity.provider == "yandex",
                                                       OAuthIdentity.subject == subject))
        if purpose == "link":
            if not link_user_id or not db.get(User, link_user_id):
                return oauth_redirect("?auth_error=retry")
            if identity and identity.user_id != link_user_id:
                return oauth_redirect("?auth_error=already_linked")
            other = db.scalar(select(OAuthIdentity).where(OAuthIdentity.provider == "yandex",
                                                         OAuthIdentity.user_id == link_user_id))
            if other and other.subject != subject:
                return oauth_redirect("?auth_error=already_linked")
            if not identity:
                db.add(OAuthIdentity(provider="yandex", subject=subject, user_id=link_user_id))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    return oauth_redirect("?auth_error=retry")
            return oauth_redirect("?linked=1")
        if identity:
            user = db.get(User, identity.user_id)
            if not user:
                return oauth_redirect("?auth_error=retry")
        else:
            email_raw = profile.get("default_email")
            if not isinstance(email_raw, str):
                return oauth_redirect("?auth_error=email_required")
            try:
                email = _email(email_raw)
            except HTTPException:
                return oauth_redirect("?auth_error=email_required")
            if db.scalar(select(User).where(User.email == email)):
                return oauth_redirect("?auth_error=link_required")
            user = User(id=uuid.uuid4().hex, email=email, password_hash="external:yandex")
            db.add_all([user, Wallet(user_id=user.id, balance_kopeks=0),
                        OAuthIdentity(provider="yandex", subject=subject, user_id=user.id)])
        ticket = new_token()
        db.add(LoginTicket(ticket_hash=token_hash(ticket), user_id=user.id,
                           expires_at=utcnow() + timedelta(minutes=1)))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return oauth_redirect("?auth_error=retry")
        return oauth_redirect(f"#auth_ticket={ticket}")

    @app.post("/api/v1/auth/yandex/exchange")
    def yandex_exchange(body: TicketIn, request: Request,
                        db: Session = Depends(db_session)) -> dict:
        source = source_key(request)
        guard_auth(db, "ticket", [(source, 20)])
        ticket = db.execute(select(LoginTicket).where(LoginTicket.ticket_hash == token_hash(body.ticket))
                            .with_for_update()).scalar_one_or_none()
        if not ticket or expired(ticket.expires_at):
            record_auth(db, "ticket", [source])
            raise HTTPException(401, "Ссылка для входа истекла")
        user = db.get(User, ticket.user_id)
        db.delete(ticket)
        db.commit()
        return issue_session(db, user)

    @app.post("/api/v1/auth/device/code")
    def device_code(user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
        code = new_token()
        db.execute(delete(DeviceCode).where(DeviceCode.user_id == user.id))
        db.add(DeviceCode(code_hash=token_hash(code), user_id=user.id,
                          expires_at=utcnow() + timedelta(minutes=5)))
        db.commit()
        return {"code": code, "expires_in": 300}

    @app.post("/api/v1/auth/device/exchange")
    def device_exchange(body: TicketIn, request: Request,
                        db: Session = Depends(db_session)) -> dict:
        source = source_key(request)
        guard_auth(db, "device", [(source, 20)])
        code = db.execute(select(DeviceCode).where(DeviceCode.code_hash == token_hash(body.ticket))
                          .with_for_update()).scalar_one_or_none()
        if not code or expired(code.expires_at):
            record_auth(db, "device", [source])
            raise HTTPException(401, "Код подключения истёк или уже использован")
        user = db.get(User, code.user_id)
        db.delete(code)
        db.commit()
        return issue_session(db, user)

    @app.post("/api/v1/auth/register", status_code=201)
    def register(body: Credentials, request: Request,
                 db: Session = Depends(db_session)) -> dict:
        source = source_key(request)
        guard_auth(db, "register", [(source, 10)])
        record_auth(db, "register", [source])
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
    def login(body: Credentials, request: Request, db: Session = Depends(db_session)) -> dict:
        email = _email(body.email)
        source, account = source_key(request), email_key(email)
        guard_auth(db, "login", [(source, 30), (account, 5)])
        user = db.scalar(select(User).where(User.email == email))
        if not user or not verify_password(body.password, user.password_hash):
            record_auth(db, "login", [source, account])
            raise HTTPException(401, "Неверный email или пароль")
        clear_auth_failures(db, "login", account)
        return issue_session(db, user)

    @app.post("/api/v1/auth/password/request")
    def request_password_reset(body: PasswordResetRequest, request: Request,
                               db: Session = Depends(db_session)) -> dict:
        if not password_mailer:
            raise HTTPException(503, "Восстановление пароля пока недоступно")
        email = _email(body.email)
        source, account = source_key(request), email_key(email)
        guard_auth(db, "password_request", [(source, 20), (account, 3)])
        record_auth(db, "password_request", [source, account])
        user = db.scalar(select(User).where(User.email == email))
        if user:
            token = new_token()
            db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
            db.add(PasswordReset(token_hash=token_hash(token), user_id=user.id,
                                 expires_at=utcnow() + timedelta(minutes=30)))
            db.commit()
            try:
                password_mailer.send_reset(email, token)
            except Exception:
                db.execute(delete(PasswordReset).where(PasswordReset.token_hash == token_hash(token)))
                db.commit()
                logging.getLogger(__name__).exception("Не удалось отправить письмо восстановления")
        return {"ok": True, "message": "Если аккаунт существует, письмо отправлено"}

    @app.post("/api/v1/auth/password/confirm")
    def confirm_password_reset(body: PasswordResetConfirm, request: Request,
                               db: Session = Depends(db_session)) -> dict:
        source = source_key(request)
        guard_auth(db, "password_confirm", [(source, 20)])
        reset = db.execute(select(PasswordReset).where(
            PasswordReset.token_hash == token_hash(body.token)).with_for_update()).scalar_one_or_none()
        if not reset or expired(reset.expires_at):
            record_auth(db, "password_confirm", [source])
            raise HTTPException(400, "Ссылка устарела или уже использована")
        user = db.get(User, reset.user_id)
        if not user:
            record_auth(db, "password_confirm", [source])
            raise HTTPException(400, "Ссылка устарела или уже использована")
        user.password_hash = hash_password(body.password)
        db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
        db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
        db.execute(delete(DeviceCode).where(DeviceCode.user_id == user.id))
        db.execute(delete(LoginTicket).where(LoginTicket.user_id == user.id))
        db.commit()
        return {"ok": True}

    @app.post("/api/v1/auth/logout")
    def logout(user: User = Depends(current_user), db: Session = Depends(db_session),
               authorization: Annotated[str, Header()] = "") -> dict:
        db.query(SessionToken).filter_by(token_hash=token_hash(authorization[7:]), user_id=user.id).delete()
        db.commit()
        return {"ok": True}

    @app.get("/api/v1/me")
    def me(user: User = Depends(current_user), db: Session = Depends(db_session)) -> dict:
        linked = db.scalar(select(OAuthIdentity.id).where(OAuthIdentity.provider == "yandex",
                                                        OAuthIdentity.user_id == user.id))
        return {"id": user.id, "email": user.email, "yandex_linked": linked is not None,
                "is_admin": user.is_admin}

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
    def reserve(body: ReserveIn, request: Request, user: User = Depends(current_user),
                db: Session = Depends(db_session)) -> dict:
        if os.environ.get("APP_ENV") == "production" and not ai_client:
            raise HTTPException(503, "Серверный анализ не настроен; новые проверки временно недоступны")
        ids = body.check_ids
        grant = db.get(DeviceGrant, token_hash(request.headers.get("authorization", "")[7:]))
        if grant:
            for check_id in ids:
                assigned_check(db, grant, check_id, live=True, new=True)
        effective_price = 0 if user.is_admin else price
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
        if len(pending) * effective_price > available:
            raise HTTPException(402, "Недостаточно средств для выбранных проверок")
        for check_id in pending:
            if check_id in existing:
                existing[check_id].status = "reserved"
                existing[check_id].result_status = None
                existing[check_id].price_kopeks = effective_price
                existing[check_id].analysis_json = None
                existing[check_id].analysis_model = None
                existing[check_id].analysis_usage_json = None
                existing[check_id].analysis_attempts = 0
                existing[check_id].arbitration_json = None
                existing[check_id].arbitration_model = None
                existing[check_id].arbitration_usage_json = None
                existing[check_id].arbitration_attempts = 0
            else:
                db.add(Check(user_id=user.id, client_check_id=check_id, price_kopeks=effective_price))
        db.commit()
        return {"price_kopeks": effective_price, "checks": ids,
                "managed_detection": ai_client is not None,
                "detection_model": ai_client.model if ai_client else None,
                "arbiter_model": getattr(ai_client, "arbiter_model", ai_client.model) if ai_client else None,
                **_wallet_payload(db, user.id)}

    @app.post("/api/v1/checks/{check_id}/analyze")
    def analyze(check_id: str, body: AnalyzeIn, user: User = Depends(current_user),
                db: Session = Depends(db_session)) -> dict:
        if not ai_client:
            raise HTTPException(503, "Серверный анализ пока не настроен")
        _validate_ai_content(body.content)
        check = db.execute(
            select(Check).where(Check.user_id == user.id, Check.client_check_id == check_id).with_for_update()
        ).scalar_one_or_none()
        if not check:
            raise HTTPException(404, "Проверка не зарезервирована")
        if check.analysis_json:
            return {"raw": check.analysis_json, "model": check.analysis_model or ai_client.model}
        if check.status != "reserved":
            raise HTTPException(409, "Проверка уже закрыта")
        if check.analysis_attempts >= 2:
            raise HTTPException(409, "Лимит попыток анализа исчерпан")
        check.analysis_attempts += 1
        try:
            raw, model, usage = _ai_payload(ai_client.analyze(body.system, body.content), ai_client.model)
        except AIError as exc:
            db.commit()
            raise HTTPException(502, str(exc)) from exc
        check.analysis_json = raw
        check.analysis_model = model
        check.analysis_usage_json = usage
        db.commit()
        return {"raw": raw, "model": model}

    @app.post("/api/v1/checks/{check_id}/arbitrate")
    def arbitrate(check_id: str, body: AnalyzeIn, user: User = Depends(current_user),
                  db: Session = Depends(db_session)) -> dict:
        if not ai_client:
            raise HTTPException(503, "Серверный арбитр пока не настроен")
        _validate_ai_content(body.content)
        check = db.execute(
            select(Check).where(Check.user_id == user.id, Check.client_check_id == check_id).with_for_update()
        ).scalar_one_or_none()
        if not check:
            raise HTTPException(404, "Проверка не зарезервирована")
        if check.arbitration_json:
            return {"raw": check.arbitration_json,
                    "model": check.arbitration_model or getattr(ai_client, "arbiter_model", ai_client.model)}
        if not check.analysis_json or not json.loads(check.analysis_json).get("found"):
            raise HTTPException(409, "Арбитр доступен только после положительного первого анализа")
        if check.status not in ("reserved", "settled"):
            raise HTTPException(409, "Проверка закрыта без оплаты")
        if check.arbitration_attempts >= 2:
            raise HTTPException(409, "Лимит попыток арбитра исчерпан")
        check.arbitration_attempts += 1
        try:
            fallback = getattr(ai_client, "arbiter_model", ai_client.model)
            raw, model, usage = _ai_payload(ai_client.arbitrate(body.system, body.content), fallback)
        except AIError as exc:
            db.commit()
            raise HTTPException(502, str(exc)) from exc
        check.arbitration_json = raw
        check.arbitration_model = model
        check.arbitration_usage_json = usage
        db.commit()
        return {"raw": raw, "model": model}

    def settle_check(db: Session, wallet_row: Wallet, check: Check, result_status: str) -> None:
        check.status = "settled"
        check.result_status = result_status
        if check.price_kopeks:
            wallet_row.balance_kopeks -= check.price_kopeks
            db.add(LedgerEntry(
                user_id=check.user_id, amount_kopeks=-check.price_kopeks,
                kind="check", reference=f"check:{check.user_id}:{check.client_check_id}",
            ))

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
        if body.status in ("found", "not_found") or check.analysis_json:
            settle_check(db, wallet_row, check, body.status)
        else:
            check.status = "released"
            check.result_status = body.status
        db.commit()
        return {"status": check.status, **_wallet_payload(db, user.id)}

    @app.put("/api/v1/checks/{check_id}/screenshot")
    async def upload_screenshot(check_id: str, request: Request,
                                user: User = Depends(current_user),
                                db: Session = Depends(db_session)) -> dict:
        if not screenshot_storage:
            raise HTTPException(503, "Хранение скриншотов ещё не настроено")
        check = db.scalar(select(Check).where(Check.user_id == user.id,
                                              Check.client_check_id == check_id))
        if not check or check.status != "settled":
            raise HTTPException(404, "Завершённая проверка не найдена")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 8 * 1024 * 1024:
                raise HTTPException(413, "Скриншот превышает 8 МБ")
            data.extend(chunk)
        if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            raise HTTPException(422, "Требуется изображение WebP")
        object_key = f"screenshots/{user.id}/{check.id}.webp"
        try:
            await run_in_threadpool(screenshot_storage.put, object_key, bytes(data))
        except StorageError as exc:
            raise HTTPException(502, str(exc)) from exc
        screenshot = db.get(Screenshot, check.id)
        if screenshot is None:
            db.add(Screenshot(check_id=check.id, object_key=object_key,
                              size_bytes=len(data)))
        else:
            screenshot.size_bytes = len(data)
        db.commit()
        return {"stored": True}

    @app.get("/api/v1/screenshots")
    def list_screenshots(user: User = Depends(current_user),
                         db: Session = Depends(db_session)) -> dict:
        visible_since = utcnow() - timedelta(days=90)
        rows = db.execute(
            select(Check.client_check_id, Screenshot.size_bytes, Screenshot.created_at)
            .join(Screenshot, Screenshot.check_id == Check.id)
            .where(Check.user_id == user.id, Screenshot.created_at > visible_since)
            .order_by(Screenshot.created_at.desc()).limit(100)
        ).all()
        return {"screenshots": [
            {"check_id": row.client_check_id, "size_bytes": row.size_bytes,
             "created_at": row.created_at.isoformat()} for row in rows
        ]}

    @app.get("/api/v1/screenshots/{check_id}/url")
    def screenshot_url(check_id: str, user: User = Depends(current_user),
                       db: Session = Depends(db_session)) -> dict:
        if not screenshot_storage:
            raise HTTPException(503, "Хранение скриншотов ещё не настроено")
        object_key = db.scalar(
            select(Screenshot.object_key).join(Check, Screenshot.check_id == Check.id)
            .where(Check.user_id == user.id, Check.client_check_id == check_id,
                   Screenshot.created_at > utcnow() - timedelta(days=90))
        )
        if not object_key:
            raise HTTPException(404, "Скриншот не найден")
        try:
            return {"url": screenshot_storage.download_url(object_key), "expires_in": 300}
        except StorageError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/v1/checks/release")
    def release_checks(body: ReserveIn, request: Request, user: User = Depends(current_user),
                       db: Session = Depends(db_session)) -> dict:
        grant = db.get(DeviceGrant, token_hash(request.headers.get("authorization", "")[7:]))
        if grant:
            for check_id in body.check_ids:
                # A failed reservation can leave an unknown ID in the durable outbox.
                if db.scalar(select(Check.id).where(Check.user_id == user.id, Check.client_check_id == check_id)):
                    assigned_check(db, grant, check_id)
        wallet_row = _locked_wallet(db, user.id)
        checks = db.scalars(
            select(Check).where(Check.user_id == user.id, Check.client_check_id.in_(body.check_ids))
            .with_for_update()
        ).all()
        released = 0
        settled = 0
        for check in checks:
            if check.status == "reserved":
                if check.analysis_json:
                    settle_check(db, wallet_row, check, "analyzed")
                    settled += 1
                else:
                    check.status = "released"
                    check.result_status = "not_started"
                    released += 1
        db.commit()
        return {"released": released, "settled": settled, **_wallet_payload(db, user.id)}

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
