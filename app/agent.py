"""Background account sync and scans on selected days of each month."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from urllib.parse import urlparse

from app import billing
from app.db import repo
from app.scanner import orchestrator

log = logging.getLogger("aiparser.agent")
DEVICE_KEY = "agent_device_id"
POLL_SECONDS = 30


def device_id() -> str:
    value = repo.get_setting(DEVICE_KEY)
    if not value:
        value = uuid.uuid4().hex
        repo.set_setting(DEVICE_KEY, value)
    return value


def schedule_due(preferences: dict, now: datetime) -> bool:
    if not preferences.get("enabled") or now.day not in preferences.get("month_days", []):
        return False
    return now.strftime("%H:%M") >= preferences.get("local_time", "09:00")


def _payload(row: dict) -> dict:
    snapshot = json.loads(row["settings_snapshot_json"] or "{}")
    run_id = snapshot.get("billing_run_id")
    query_id = snapshot.get("cloud_query_map", {}).get(str(row["query_id"]), row["query_id"])
    query = next((q for q in snapshot.get("cloud_queries", []) if q["id"] == query_id), {})
    check_id = (billing.check_id(run_id, query_id, row["service"])
                if run_id and row["status"] in ("found", "not_found") else None)
    sources = [url for url in json.loads(row["sources_json"] or "[]")
               if isinstance(url, str) and len(url) <= 2000
               and urlparse(url).scheme in ("http", "https")][:50]
    return {
        "project_id": snapshot.get("cloud_project_id"),
        "query_id": query_id if isinstance(query_id, str) else None,
        "run_id": snapshot.get("cloud_job_id"),
        "local_result_id": row["id"], "local_project_id": row["project_id"],
        "project_name": row["project_name"], "brand_name": row["brand_name"],
        "query_text": query.get("text", row["query_text"]), "group_tag": query.get("group_tag", row["group_tag"]),
        "service": row["service"], "scan_date": row["scan_date"],
        "status": row["status"], "mention_types": json.loads(row["mention_types_json"] or "[]"),
        "evidence_quote": row["evidence_quote"][:12000] if row["evidence_quote"] else None,
        "answer_text": row["answer_text"][:60000] if row["answer_text"] else None,
        "sources": sources, "check_id": check_id,
    }


async def _sync_results(user_id: str, current_device_id: str) -> None:
    cursor_key = f"cloud_result_cursor:{user_id}"
    for _ in range(10):  # bounded work per heartbeat; remaining rows follow next time
        cursor = int(repo.get_setting(cursor_key, "0") or "0")
        rows = repo.cloud_results_after(cursor)
        if not rows:
            return
        owned = [row for row in rows if json.loads(row["settings_snapshot_json"] or "{}")
                 .get("billing_user_id") == user_id]
        if owned:
            await billing.upload_cloud_results(current_device_id, [_payload(row) for row in owned])
        repo.set_setting(cursor_key, str(rows[-1]["id"]))
        if len(rows) < 100:
            return


async def _scheduled_scan(preferences: dict, retry_after: dict[int, float]) -> None:
    now = datetime.now().astimezone()
    if not schedule_due(preferences, now) or orchestrator.active_controller():
        return
    scan_date = now.date().isoformat()
    for project in repo.list_projects():
        project_id = project["id"]
        if repo.scheduled_scan_exists(project_id, scan_date) or retry_after.get(project_id, 0) > asyncio.get_running_loop().time():
            continue
        if not repo.list_queries(project_id, only_active=True):
            continue
        try:
            scan_id = await orchestrator.start_scan(
                project_id, preferences["services"], resume=True,
                headless=preferences["browser_mode"] == "headless",
            )
        except ValueError as exc:
            if "всё уже проверено" in str(exc):
                repo.mark_scheduled_scan(project_id, scan_date, None)
            else:
                log.warning("Расписание проекта %s: %s", project_id, exc)
                retry_after[project_id] = asyncio.get_running_loop().time() + 900
            continue
        except (billing.BillingError, orchestrator.ScanAlreadyRunning) as exc:
            log.warning("Не удалось запустить скан проекта %s: %s", project_id, exc)
            retry_after[project_id] = asyncio.get_running_loop().time() + 900
            return
        repo.mark_scheduled_scan(project_id, scan_date, scan_id)
        log.info("Плановый скан проекта %s запущен: %s", project_id, scan_id)
        return


async def run_agent() -> None:
    current_device_id = device_id()
    retry_after: dict[int, float] = {}
    while True:
        try:
            if billing.enabled() and billing.token():
                active = orchestrator.active_controller() is not None
                zone = datetime.now().astimezone().tzname() or ""
                response = await billing.heartbeat(current_device_id,
                                                   f"Windows агент {current_device_id[-4:]}", zone, active)
                preferences = response["preferences"]
                if repo.get_setting("speed_profile") != preferences["speed_profile"]:
                    repo.set_setting("speed_profile", preferences["speed_profile"])
                # A scan can begin while heartbeat is in flight. Hold the same
                # lock as start_scan and recheck before touching provisional
                # release entries in the billing outbox.
                async with orchestrator.scan_start_lock():
                    if orchestrator.active_controller() is None:
                        await billing.recover_interrupted_scans()
                        await billing.flush_outbox()
                        try:
                            await billing.flush_screenshot_outbox()
                        except billing.ScreenshotError as exc:
                            log.warning("Отложенная отправка снимков: %s", exc)
                user = await billing.identity()
                try:
                    await _sync_results(user["id"], current_device_id)
                except billing.BillingError as exc:
                    log.warning("Отложенная синхронизация отчётов: %s", exc)
                if not active:
                    await _scheduled_scan(preferences, retry_after)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Фоновая синхронизация агента не удалась; повтор через %s с", POLL_SECONDS)
        await asyncio.sleep(POLL_SECONDS)
