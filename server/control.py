"""Account-owned projects and a durable queue pinned to desktop devices."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from server.agent_schemas import SCHEDULABLE_IDS
from server.models import (AgentDevice, CloudResult, ControlLink, ControlProject, ControlRun,
                           DeviceConnect, DeviceGrant, SessionToken, User, utcnow)
from server.security import new_token, token_hash

log = logging.getLogger(__name__)
TERMINAL = {"done", "failed", "cancelled", "missed"}


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class QueryIn(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, pattern=r"^[a-f0-9]{32}$")
    text: str = Field(min_length=1, max_length=2000)
    group_tag: str = Field(default="", max_length=120)
    active: bool = True

    @field_validator("text")
    @classmethod
    def normalize(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("Запрос не может быть пустым")
        return value


class ScanConfig(BaseModel):
    brand_aliases: list[str] = Field(default_factory=list, max_length=100)
    brand_domains: list[str] = Field(default_factory=list, max_length=100)
    region_code: str = Field(default="213", max_length=20)
    services: list[str] = Field(default_factory=lambda: ["google_aio"], min_length=1, max_length=4)
    browser_mode: str = Field(default="headless", pattern="^(headless|headful)$")
    speed_profile: str = Field(default="balanced", pattern="^(careful|balanced|fast)$")
    parallel: bool = True

    @field_validator("services")
    @classmethod
    def supported(cls, value):
        if len(set(value)) != len(value) or not set(value) <= SCHEDULABLE_IDS:
            raise ValueError("Выберите доступные ИИ-системы без повторов")
        return value

    @field_validator("brand_aliases", "brand_domains")
    @classmethod
    def bounded(cls, value):
        if any(len(item) > 500 for item in value):
            raise ValueError("Слишком длинное название или домен")
        return [item.strip() for item in value if item.strip()]


class Schedule(BaseModel):
    enabled: bool = False
    device_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    month_days: list[int] = Field(default_factory=lambda: [1], min_length=1, max_length=31)
    time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Europe/Moscow"

    @field_validator("month_days")
    @classmethod
    def days(cls, value):
        if any(day < 1 or day > 31 for day in value) or len(value) != len(set(value)):
            raise ValueError("Выберите числа месяца от 1 до 31 без повторов")
        return sorted(value)

    @field_validator("timezone")
    @classmethod
    def zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Укажите часовой пояс, например Europe/Moscow")
        return value


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(default=0, ge=0)
    name: str = Field(min_length=1, max_length=120)
    brand_name: str = Field(min_length=1, max_length=120)
    device_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    config: ScanConfig = Field(default_factory=ScanConfig)
    schedule: Schedule = Field(default_factory=Schedule)
    queries: list[QueryIn] = Field(default_factory=list, max_length=5000)

    @field_validator("name", "brand_name")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Укажите название")
        return value.strip()

    @field_validator("queries")
    @classmethod
    def distinct(cls, value):
        if len({q.id for q in value}) != len(value) or len({q.text for q in value}) != len(value):
            raise ValueError("Запросы повторяются")
        if sum(len(q.text) for q in value) > 2_000_000:
            raise ValueError("Слишком большой список запросов")
        return value


class LaunchIn(BaseModel):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    device_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class CommandIn(BaseModel):
    action: str = Field(pattern="^(pause|resume|stop)$")


class ConnectIn(BaseModel):
    device_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=100)


class ExchangeIn(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    secret: str = Field(pattern=r"^[A-Za-z0-9_-]{30,200}$")


class PollIn(BaseModel):
    capabilities: dict = Field(default_factory=dict)


class ProgressIn(BaseModel):
    lease_token: str = Field(min_length=30, max_length=100)
    state: str = Field(pattern="^(running|paused|done|failed|cancelled)$")
    progress: dict = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=1000)


class ImportIn(BaseModel):
    local_project_id: int = Field(gt=0)
    project: ProjectIn


def project_payload(row, detail=True):
    queries = json.loads(row.queries_json)
    payload = {"id": row.id, "revision": row.revision, "name": row.name,
               "brand_name": row.brand_name, "device_id": row.device_id,
               "config": json.loads(row.config_json), "schedule": json.loads(row.schedule_json),
               "query_count": len(queries), "active_queries": sum(q["active"] for q in queries),
               "updated_at": aware(row.updated_at).isoformat()}
    if detail:
        payload["queries"] = queries
    return payload


def run_payload(row, device=None):
    state = row.state
    if state == "queued" and (not device or device.revoked or
                              utcnow() - aware(device.last_seen_at) > timedelta(seconds=90)):
        state = "waiting_device"
    elif state in ("running", "paused") and row.lease_until and aware(row.lease_until) < utcnow():
        state = "connection_lost"
    snap = json.loads(row.snapshot_json)
    return {"id": row.id, "project_id": row.project_id, "project_name": snap["name"],
            "device_id": row.device_id, "device_name": device.name if device else row.device_id[-6:],
            "state": state, "desired_state": row.desired_state, "progress": json.loads(row.progress_json),
            "error": row.error, "total": len(snap["queries"]) * len(snap["config"]["services"]),
            "created_at": aware(row.created_at).isoformat(),
            "scheduled_for": aware(row.scheduled_for).isoformat() if row.scheduled_for else None}


def device_for(db, user_id, device_id):
    row = db.scalar(select(AgentDevice).where(AgentDevice.user_id == user_id, AgentDevice.device_id == device_id))
    if not row or row.revoked:
        raise HTTPException(422, "Выберите подключённый компьютер")
    return row


def create_run(db, project, device_id, key, scheduled_for=None):
    existing = db.scalar(select(ControlRun).where(ControlRun.request_key == key))
    if existing:
        return existing
    device_for(db, project.user_id, device_id)
    snap = project_payload(project)
    snap["queries"] = [q for q in snap["queries"] if q["active"]]
    if not snap["queries"]:
        raise HTTPException(422, "Добавьте активные запросы в проект")
    row = ControlRun(id=uuid.uuid4().hex, user_id=project.user_id, project_id=project.id,
                     device_id=device_id, active_project_key=project.id, request_key=key,
                     snapshot_json=json.dumps(snap, ensure_ascii=False), scheduled_for=scheduled_for)
    db.add(row)
    db.flush()
    return row


def schedule_tick(sessions, now=None):
    now = now or utcnow()
    with sessions() as db:
        # Expired queued scheduled work must never create a backlog on an offline PC.
        for run in db.scalars(select(ControlRun).where(ControlRun.state == "queued",
                                                      ControlRun.scheduled_for.is_not(None))):
            if now - aware(run.scheduled_for) > timedelta(hours=24):
                run.state, run.active_project_key = "missed", None
        db.commit()
        projects = db.scalars(select(ControlProject).where(ControlProject.archived.is_(False))).all()
        for project in projects:
            schedule = Schedule.model_validate(json.loads(project.schedule_json))
            if not schedule.enabled or not schedule.device_id:
                continue
            local = now.astimezone(ZoneInfo(schedule.timezone))
            for day_offset in (1, 0):
                day = (local - timedelta(days=day_offset)).date()
                if day.day not in schedule.month_days:
                    continue
                slot = datetime.combine(day, datetime.strptime(schedule.time, "%H:%M").time(),
                                        ZoneInfo(schedule.timezone)).astimezone(timezone.utc)
                if not timedelta(0) <= now - slot < timedelta(hours=24):
                    continue
                # Saving/enabling a schedule never retroactively executes a slot.
                enabled_at = json.loads(project.schedule_json).get("effective_from")
                if enabled_at and slot < datetime.fromisoformat(enabled_at):
                    continue
                key = f"schedule:{project.id}:{slot.isoformat()}"
                try:
                    with db.begin_nested():
                        create_run(db, project, schedule.device_id, key, slot)
                    db.commit()
                except (IntegrityError, HTTPException):
                    # Active project or unready device; another tick can retry within the slot window.
                    db.rollback()


def register_control(app, db_session, current_user, sessions):
    router = APIRouter(prefix="/api/v1/control")

    def grant_for(request, db):
        raw = request.headers.get("authorization", "")[7:]
        return db.get(DeviceGrant, token_hash(raw)) if raw else None

    def web_user(request: Request, user=Depends(current_user), db=Depends(db_session)):
        if grant_for(request, db):
            raise HTTPException(403, "Управление проектами доступно через сайт")
        return user

    def device_user(request: Request, user=Depends(current_user), db=Depends(db_session)):
        grant = grant_for(request, db)
        if not grant or grant.user_id != user.id:
            raise HTTPException(403, "Подключите агент заново")
        device_for(db, user.id, grant.device_id)
        return grant

    def owned_project(db, user_id, project_id):
        row = db.get(ControlProject, project_id)
        if not row or row.user_id != user_id or row.archived:
            raise HTTPException(404, "Проект не найден")
        return row

    def validate_assignment(db, user_id, body):
        if body.device_id:
            device_for(db, user_id, body.device_id)
        if body.schedule.device_id:
            device_for(db, user_id, body.schedule.device_id)
        if body.schedule.enabled and not body.schedule.device_id:
            raise HTTPException(422, "Выберите компьютер для расписания")

    def project_values(body, old_schedule=None):
        schedule = body.schedule.model_dump()
        old = json.loads(old_schedule or "{}")
        if schedule == {k: v for k, v in old.items() if k != "effective_from"}:
            schedule["effective_from"] = old.get("effective_from", utcnow().isoformat())
        else:
            schedule["effective_from"] = utcnow().isoformat()
        return dict(name=body.name, brand_name=body.brand_name, device_id=body.device_id,
                    config_json=body.config.model_dump_json(), queries_json=json.dumps([q.model_dump() for q in body.queries], ensure_ascii=False),
                    schedule_json=json.dumps(schedule), updated_at=utcnow())

    @router.get("/projects")
    def projects(user=Depends(web_user), db=Depends(db_session)):
        return [project_payload(p, False) for p in db.scalars(select(ControlProject).where(
            ControlProject.user_id == user.id, ControlProject.archived.is_(False)).order_by(ControlProject.created_at))]

    @router.post("/projects", status_code=201)
    def add_project(body: ProjectIn, user=Depends(web_user), db=Depends(db_session)):
        validate_assignment(db, user.id, body)
        row = ControlProject(id=uuid.uuid4().hex, user_id=user.id, **project_values(body))
        db.add(row); db.commit()
        return project_payload(row)

    @router.get("/projects/{project_id}")
    def get_project(project_id: str, user=Depends(web_user), db=Depends(db_session)):
        return project_payload(owned_project(db, user.id, project_id))

    @router.put("/projects/{project_id}")
    def save_project(project_id: str, body: ProjectIn, user=Depends(web_user), db=Depends(db_session)):
        row = owned_project(db, user.id, project_id)
        validate_assignment(db, user.id, body)
        result = db.execute(update(ControlProject).where(ControlProject.id == row.id,
            ControlProject.revision == body.revision).values(**project_values(body, row.schedule_json), revision=body.revision + 1))
        if result.rowcount != 1:
            raise HTTPException(409, "Проект изменён на другом устройстве. Обновите страницу перед сохранением.")
        db.commit(); db.refresh(row)
        return project_payload(row)

    @router.delete("/projects/{project_id}")
    def archive_project(project_id: str, user=Depends(web_user), db=Depends(db_session)):
        row = owned_project(db, user.id, project_id)
        if db.scalar(select(ControlRun.id).where(ControlRun.active_project_key == row.id)):
            raise HTTPException(409, "Сначала остановите проверку проекта")
        row.archived = True; db.commit()
        return {"ok": True}

    @router.post("/projects/{project_id}/runs", status_code=201)
    def launch(project_id: str, body: LaunchIn, user=Depends(web_user), db=Depends(db_session)):
        row = owned_project(db, user.id, project_id)
        device_id = body.device_id or row.device_id
        try:
            run = create_run(db, row, device_id, f"manual:{row.id}:{body.request_id}")
            db.commit()
        except IntegrityError:
            db.rollback()
            run = db.scalar(select(ControlRun).where(ControlRun.request_key == f"manual:{row.id}:{body.request_id}"))
            if run is None:
                raise HTTPException(409, "У проекта уже есть проверка в очереди или в работе")
        return run_payload(run, device_for(db, user.id, run.device_id))

    @router.get("/runs")
    def runs(user=Depends(web_user), db=Depends(db_session)):
        devices = {d.device_id: d for d in db.scalars(select(AgentDevice).where(AgentDevice.user_id == user.id))}
        return [run_payload(r, devices.get(r.device_id)) for r in db.scalars(select(ControlRun).where(
            ControlRun.user_id == user.id).order_by(ControlRun.created_at.desc()).limit(100))]

    @router.post("/runs/{run_id}/command")
    def command(run_id: str, body: CommandIn, user=Depends(web_user), db=Depends(db_session)):
        row = db.get(ControlRun, run_id)
        if not row or row.user_id != user.id:
            raise HTTPException(404, "Проверка не найдена")
        if row.state in TERMINAL:
            raise HTTPException(409, "Проверка уже завершена")
        row.desired_state = {"pause": "paused", "resume": "running", "stop": "cancelled"}[body.action]
        if body.action == "stop" and (row.state == "queued" or
                (row.lease_until and aware(row.lease_until) < utcnow())):
            row.state = "cancelled"
            row.active_project_key = row.active_device_key = None
            row.lease_token = None
        row.updated_at = utcnow(); db.commit()
        return {"ok": True}

    @router.get("/devices")
    def devices(user=Depends(web_user), db=Depends(db_session)):
        return [{"device_id": d.device_id, "name": d.name, "revoked": d.revoked,
                 "online": not d.revoked and utcnow() - aware(d.last_seen_at) < timedelta(seconds=90),
                 "last_seen_at": aware(d.last_seen_at).isoformat(), "capabilities": json.loads(d.capabilities_json)}
                for d in db.scalars(select(AgentDevice).where(AgentDevice.user_id == user.id).order_by(AgentDevice.name))]

    @router.patch("/devices/{device_id}")
    def rename(device_id: str, body: ConnectIn, user=Depends(web_user), db=Depends(db_session)):
        row = device_for(db, user.id, device_id); row.name = body.name; db.commit()
        return {"ok": True}

    @router.delete("/devices/{device_id}")
    def revoke(device_id: str, user=Depends(web_user), db=Depends(db_session)):
        row = device_for(db, user.id, device_id); row.revoked = True
        invalidate_device_tokens(db, user.id, device_id)
        for run in db.scalars(select(ControlRun).where(ControlRun.user_id == user.id,
                ControlRun.device_id == device_id, ControlRun.active_project_key.is_not(None))):
            run.desired_state = "cancelled"
            run.state = "cancelled"
            run.active_project_key = run.active_device_key = run.lease_token = None
        db.commit(); return {"ok": True}

    def invalidate_device_tokens(db, user_id, device_id):
        hashes = list(db.scalars(select(DeviceGrant.token_hash).where(
            DeviceGrant.user_id == user_id, DeviceGrant.device_id == device_id)))
        if hashes:
            db.execute(delete(DeviceGrant).where(DeviceGrant.token_hash.in_(hashes)))
            db.execute(delete(SessionToken).where(SessionToken.token_hash.in_(hashes)))

    def issue_device(db, user_id, device_id, name):
        invalidate_device_tokens(db, user_id, device_id)
        row = db.scalar(select(AgentDevice).where(AgentDevice.user_id == user_id, AgentDevice.device_id == device_id))
        if row is None:
            row = AgentDevice(user_id=user_id, device_id=device_id, name=name)
            db.add(row)
        row.revoked = False; row.last_seen_at = utcnow()
        token = new_token()
        db.add(SessionToken(token_hash=token_hash(token), user_id=user_id, expires_at=utcnow()+timedelta(days=90)))
        db.flush()
        db.add(DeviceGrant(token_hash=token_hash(token), user_id=user_id, device_id=device_id))
        return token

    @router.post("/connect/start")
    def connect_start(body: ConnectIn, request: Request, db=Depends(db_session)):
        from server.auth_limit import guard, record, source_key
        key = source_key(request)
        guard(db, "device-start", [(key, 20)]); record(db, "device-start", [key])
        secret = new_token(); identifier = uuid.uuid4().hex
        db.add(DeviceConnect(id=identifier, secret_hash=token_hash(secret), device_id=body.device_id,
                             name=body.name, expires_at=utcnow()+timedelta(minutes=10)))
        db.commit()
        return {"id": identifier, "secret": secret, "path": f"/cabinet/?connect={identifier}"}

    @router.get("/connect/{identifier}")
    def connect_info(identifier: str, user=Depends(web_user), db=Depends(db_session)):
        row = db.get(DeviceConnect, identifier)
        if not row or aware(row.expires_at) < utcnow():
            raise HTTPException(410, "Запрос подключения истёк. Начните вход из агента заново.")
        return {"name": row.name, "id": row.id}

    @router.post("/connect/{identifier}/approve")
    def connect_approve(identifier: str, user=Depends(web_user), db=Depends(db_session)):
        changed = db.execute(update(DeviceConnect).where(DeviceConnect.id == identifier,
            DeviceConnect.expires_at > utcnow(), DeviceConnect.user_id.is_(None)).values(user_id=user.id))
        if changed.rowcount != 1:
            raise HTTPException(409, "Запрос уже использован или истёк")
        db.commit(); return {"ok": True}

    @router.post("/connect/exchange")
    def connect_exchange(body: ExchangeIn, db=Depends(db_session)):
        row = db.get(DeviceConnect, body.id)
        if not row or row.secret_hash != token_hash(body.secret) or aware(row.expires_at) < utcnow():
            raise HTTPException(410, "Запрос входа истёк")
        if not row.user_id:
            return {"pending": True}
        # DELETE returning makes concurrent polls consume the request only once.
        consumed = db.execute(delete(DeviceConnect).where(DeviceConnect.id == row.id,
            DeviceConnect.secret_hash == row.secret_hash)).rowcount
        if consumed != 1:
            raise HTTPException(409, "Запрос уже использован")
        token = issue_device(db, row.user_id, row.device_id, row.name)
        db.commit(); return {"pending": False, "token": token}

    @router.post("/agent/enroll")
    def enroll(body: ConnectIn, user=Depends(web_user), db=Depends(db_session)):
        token = issue_device(db, user.id, body.device_id, body.name)
        db.commit(); return {"token": token}

    @router.post("/agent/import")
    def import_project(body: ImportIn, grant=Depends(device_user), db=Depends(db_session)):
        link = db.scalar(select(ControlLink).where(ControlLink.user_id == grant.user_id,
            ControlLink.device_id == grant.device_id, ControlLink.local_project_id == body.local_project_id))
        if link:
            return project_payload(db.get(ControlProject, link.project_id))
        body.project.device_id = grant.device_id
        body.project.schedule.enabled = False
        body.project.schedule.device_id = grant.device_id
        row = ControlProject(id=uuid.uuid4().hex, user_id=grant.user_id, **project_values(body.project))
        db.add(row); db.flush()
        db.add(ControlLink(user_id=grant.user_id, device_id=grant.device_id,
                           local_project_id=body.local_project_id, project_id=row.id))
        db.execute(update(CloudResult).where(CloudResult.user_id == grant.user_id,
            CloudResult.device_id == grant.device_id, CloudResult.local_project_id == body.local_project_id).values(project_id=row.id))
        db.commit(); return project_payload(row)

    @router.post("/agent/poll")
    def poll(body: PollIn, grant=Depends(device_user), db=Depends(db_session)):
        if len(json.dumps(body.capabilities)) > 20000:
            raise HTTPException(422, "Слишком большой статус устройства")
        # Serialize claims on this device, including concurrent heartbeat requests.
        device = db.scalar(select(AgentDevice).where(AgentDevice.user_id == grant.user_id,
            AgentDevice.device_id == grant.device_id).with_for_update())
        device.last_seen_at = utcnow(); device.capabilities_json = json.dumps(body.capabilities)
        key = f"{grant.user_id}:{grant.device_id}"
        run = db.scalar(select(ControlRun).where(ControlRun.active_device_key == key))
        if (not run and not body.capabilities.get("paused") and not body.capabilities.get("active_scan")
                and body.capabilities.get("installed") is not False):
            run = db.scalar(select(ControlRun).where(ControlRun.user_id == grant.user_id,
                ControlRun.device_id == grant.device_id, ControlRun.state == "queued",
                ControlRun.desired_state == "running").order_by(ControlRun.created_at))
            if run:
                run.active_device_key = key; run.lease_token = new_token(); run.state = "running"
        if run:
            run.lease_until = utcnow()+timedelta(seconds=120)
            run.updated_at = utcnow()
        device.active_scan = bool(run)
        try:
            db.commit()
        except IntegrityError:
            db.rollback(); return {"run": None}
        return {"run": None if not run else {**run_payload(run, device),
                "snapshot": json.loads(run.snapshot_json), "lease_token": run.lease_token}, "name": device.name}

    @router.post("/agent/runs/{run_id}")
    def progress(run_id: str, body: ProgressIn, grant=Depends(device_user), db=Depends(db_session)):
        row = db.get(ControlRun, run_id)
        if not row or row.user_id != grant.user_id or row.device_id != grant.device_id:
            raise HTTPException(404, "Задание не найдено")
        if row.state == body.state and row.state in TERMINAL and row.lease_token == body.lease_token:
            return {"desired_state": row.desired_state}
        if row.state in TERMINAL or row.lease_token != body.lease_token:
            raise HTTPException(409, "Задание больше не принадлежит этому агенту")
        if len(json.dumps(body.progress)) > 20000:
            raise HTTPException(422, "Слишком большой прогресс")
        row.state = body.state; row.progress_json = json.dumps(body.progress); row.error = body.error
        row.updated_at = utcnow(); row.lease_until = utcnow()+timedelta(seconds=120)
        if row.state in TERMINAL:
            row.active_project_key = row.active_device_key = None
        db.commit(); return {"desired_state": row.desired_state}

    app.include_router(router)
    scheduler = None

    @app.on_event("startup")
    async def start_scheduler():
        nonlocal scheduler
        async def loop():
            while True:
                try:
                    await run_in_threadpool(schedule_tick, sessions)
                except Exception:
                    log.exception("Schedule tick failed")
                await asyncio.sleep(15)
        scheduler = asyncio.create_task(loop())

    @app.on_event("shutdown")
    async def stop_scheduler():
        if scheduler:
            scheduler.cancel()
            try:
                await scheduler
            except asyncio.CancelledError:
                pass
