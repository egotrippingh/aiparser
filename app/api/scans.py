"""Запуск скана, пауза/остановка, живой прогресс через SSE."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import services
from app.db import repo
from app.scanner import orchestrator
from app.scanner.adapters import ADAPTERS

router = APIRouter(prefix="/api", tags=["scans"])


class StartScanIn(BaseModel):
    services: list[str] | None = None  # пусто — все известные сервисы
    resume: bool = True                # продолжить незаконченный скан, если он есть


@router.post("/projects/{project_id}/scans", status_code=201)
async def start_scan(project_id: int, body: StartScanIn) -> dict:
    if not repo.get_project(project_id):
        raise HTTPException(404, "Проект не найден")

    ids = body.services or services.ALL_IDS
    unknown = [s for s in ids if s not in services.BY_ID]
    if unknown:
        raise HTTPException(400, f"Неизвестные сервисы: {unknown}")

    try:
        scan_id = await orchestrator.start_scan(project_id, ids, resume=body.resume)
    except orchestrator.ScanAlreadyRunning as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    return {"scan_id": scan_id}


@router.get("/projects/{project_id}/scans")
def list_scans(project_id: int, limit: int = 60) -> list[dict]:
    return repo.list_scans(project_id, limit=limit)


@router.get("/scans/active")
def active_scan() -> dict | None:
    """Идущий сейчас скан или null.

    Нужен интерфейсу, чтобы показать прогресс с любой вкладки и подхватить
    его после перезапуска приложения — SSE-поток для этого не годится, он
    рассказывает только о новых событиях, а не о текущем состоянии.
    """
    ctl = orchestrator.active_controller()
    return ctl.snapshot() if ctl else None


@router.get("/projects/{project_id}/resumable")
def resumable(project_id: int) -> dict | None:
    """Незаконченный скан проекта — сколько проверок осталось досканировать."""
    return repo.find_resumable_scan(project_id, scannable=set(ADAPTERS))


@router.get("/scans/{scan_id}")
def get_scan(scan_id: int) -> dict:
    s = repo.get_scan(scan_id)
    if not s:
        raise HTTPException(404, "Скан не найден")
    return s


@router.post("/scans/{scan_id}/pause")
def pause_scan(scan_id: int) -> dict:
    ctl = orchestrator.get_controller(scan_id)
    if not ctl:
        raise HTTPException(404, "Скан не выполняется")
    ctl.pause()
    return {"ok": True}


@router.post("/scans/{scan_id}/resume")
def resume_scan(scan_id: int) -> dict:
    ctl = orchestrator.get_controller(scan_id)
    if not ctl:
        raise HTTPException(404, "Скан не выполняется")
    ctl.resume()
    return {"ok": True}


@router.post("/scans/{scan_id}/stop")
def stop_scan(scan_id: int) -> dict:
    ctl = orchestrator.get_controller(scan_id)
    if not ctl:
        raise HTTPException(404, "Скан не выполняется")
    ctl.stop()
    return {"ok": True}


@router.get("/scans/{scan_id}/stream")
async def stream_scan(scan_id: int) -> StreamingResponse:
    ctl = orchestrator.get_controller(scan_id)
    if not ctl:
        raise HTTPException(404, "Скан не выполняется — возможно, уже завершился")

    queue = ctl.subscribe()

    async def gen():
        try:
            # Опоздавший подписчик сразу получает текущее состояние, а не ждёт
            # следующего события — иначе полоса прогресса пустовала бы до
            # конца текущего запроса.
            snap = {"event": "progress", **ctl.snapshot()}
            yield f"event: progress\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {item['event']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
                    if item["event"] == "scan_finished":
                        break
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # держим соединение живым сквозь прокси/антивирусы
        finally:
            ctl.unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")
