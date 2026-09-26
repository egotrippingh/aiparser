"""Small desktop executor: import once, poll the server, run assigned work."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import platform
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from app import billing, secrets_store, window_control
from app.db import repo
from app.scanner import orchestrator
from app.agent import device_id, _sync_results

log = logging.getLogger(__name__)
STATE = {"connected": False, "error": "", "name": platform.node(), "last_sync": None}


def store_token(token):
    repo.set_setting(billing.TOKEN_KEY, secrets_store.protect(token), is_secret=True)
    repo.set_setting("control_token", hashlib.sha256(token.encode()).hexdigest())


async def enroll():
    token = billing.token()
    marker = hashlib.sha256(token.encode()).hexdigest()
    if repo.get_setting("control_token") != marker:
        response = await billing._request("POST", "/control/agent/enroll", body={
            "device_id": device_id(), "name": platform.node() or "Windows агент"})
        store_token(response["token"])


async def import_projects(user_id):
    for project in repo.list_projects():
        key = f"control_import:{user_id}:{project['id']}"
        if repo.get_setting(key):
            continue
        scans = repo.list_scans(project["id"], limit=1)
        owner = json.loads(scans[0]["settings_snapshot_json"] or "{}").get("billing_user_id") if scans else None
        if owner and owner != user_id:
            continue
        queries = repo.list_queries(project["id"])
        mapping = {str(q["id"]): uuid.uuid5(uuid.NAMESPACE_URL,
                   f"{user_id}:{device_id()}:{project['id']}:{q['id']}").hex for q in queries}
        response = await billing._request("POST", "/control/agent/import", body={
            "local_project_id": project["id"], "project": {
                "name": project["name"], "brand_name": project["brand_name"],
                "config": {"brand_aliases": project["brand_aliases"], "brand_domains": project["brand_domains"],
                           "region_code": project.get("region_code") or "213", "parallel": True},
                "queries": [{"id": mapping[str(q["id"])], "text": q["text"],
                             "group_tag": q.get("group_tag") or "", "active": bool(q["is_active"])} for q in queries],
            }})
        repo.set_setting(key, response["id"])
        repo.set_setting(f"control_project:{user_id}:{response['id']}", str(project["id"]))


def materialize(job, user_id):
    snap = job["snapshot"]
    key = f"control_project:{user_id}:{snap['id']}"
    local_id = int(repo.get_setting(key, "0") or 0)
    fields = {"name": snap["name"], "brand_name": snap["brand_name"],
              "brand_aliases": snap["config"]["brand_aliases"], "brand_domains": snap["config"]["brand_domains"],
              "region_code": snap["config"]["region_code"], "parallel_scan": snap["config"]["parallel"],
              "deep_check_depth": 0}
    if not local_id or not repo.get_project(local_id):
        local_id = repo.create_project(**fields)
        repo.set_setting(key, str(local_id))
        repo.set_setting(f"control_import:{user_id}:{local_id}", snap["id"])
    else:
        repo.update_project(local_id, **fields)
    # Keep historical local rows; the active list is the immutable server run snapshot.
    for q in repo.list_queries(local_id):
        repo.set_query_active(q["id"], False)
    by_text = {q["text"]: q for q in repo.list_queries(local_id)}
    query_map = {}
    for query in snap["queries"]:
        if query["text"] not in by_text:
            repo.add_queries(local_id, [query["text"]], query["group_tag"])
            by_text = {q["text"]: q for q in repo.list_queries(local_id)}
        qid = by_text[query["text"]]["id"]
        repo.set_query_active(qid, True)
        query_map[str(qid)] = query["id"]
    repo.set_setting("speed_profile", snap["config"]["speed_profile"])
    job_date = datetime.fromisoformat(job.get("scheduled_for") or job["created_at"]).astimezone(
        ZoneInfo(snap.get("schedule", {}).get("timezone", "Europe/Moscow"))).date().isoformat()
    return local_id, {"id": job["id"], "date": job_date, "project_id": snap["id"],
                      "query_map": query_map, "queries": snap["queries"]}


async def maintenance(user_id):
    async with orchestrator.scan_start_lock():
        if orchestrator.active_controller() is None:
            await billing.recover_interrupted_scans()
            await billing.flush_outbox()
    # Images and results are retried while other service tasks continue.
    await _sync_results(user_id, device_id())
    try:
        await billing.flush_screenshot_outbox()
    except billing.ScreenshotError as exc:
        log.warning("Screenshot upload pending: %s", exc)


async def update_job(job, state, progress=None, error=None):
    return await billing._request("POST", f"/control/agent/runs/{job['id']}", body={
        "lease_token": job["lease_token"], "state": state, "progress": progress or {},
        "error": str(error)[:1000] if error else None})


async def start_job(job, user_id):
    try:
        local_id, managed = materialize(job, user_id)
        await orchestrator.start_scan(local_id, job["snapshot"]["config"]["services"],
            headless=job["snapshot"]["config"]["browser_mode"] == "headless", managed_job=managed)
    except Exception as exc:
        STATE["error"] = str(exc)
        await update_job(job, "failed", error=exc)


def paused():
    return repo.get_setting("agent_paused", "0") == "1"


async def run_agent():
    from app.api.browser import status as browser_status
    starting = syncing = finishing = None
    last_ok = time.monotonic()
    known_user = None
    wallet_at = 0.0
    try:
        while True:
            try:
                if not billing.enabled() or not billing.token():
                    STATE["connected"] = False
                    ctl = orchestrator.active_controller()
                    if ctl:
                        ctl.stop()
                    await asyncio.sleep(3)
                    continue
                await enroll()
                user = await billing.identity()
                if known_user != user["id"]:
                    ctl = orchestrator.active_controller()
                    if ctl:
                        ctl.stop()
                        await asyncio.sleep(3)
                        continue
                    await import_projects(user["id"])
                    known_user = user["id"]
                ctl = orchestrator.active_controller()
                browser = browser_status()
                capabilities = {"services": browser["services"], "installed": browser["installed"],
                                "paused": paused(), "active_scan": bool(ctl or starting and not starting.done()
                                                                         or browser["logins_in_progress"])}
                reply = await billing._request("POST", "/control/agent/poll", body={"capabilities": capabilities})
                last_ok = time.monotonic()
                STATE.update(connected=True, user=user, name=reply.get("name", platform.node()),
                             last_sync=datetime.now().astimezone().isoformat(), error="")
                if repo.get_setting("agent_display_name") != STATE["name"]:
                    repo.set_setting("agent_display_name", STATE["name"])
                    window_control.update_device_name(STATE["name"])
                if time.monotonic() - wallet_at > 60:
                    STATE["wallet"] = await billing._request("GET", "/wallet")
                    wallet_at = time.monotonic()
                if (finishing is None or finishing.done()) and (syncing is None or syncing.done()):
                    if syncing and not syncing.cancelled():
                        error = syncing.exception()
                        if error:
                            log.warning("Sync pending: %s", error)
                            STATE["sync_error"] = str(error)
                        else:
                            STATE["sync_error"] = ""
                    syncing = asyncio.create_task(maintenance(user["id"]))
                job = reply["run"]
                STATE["job"] = job
                if job:
                    ctl = orchestrator.active_controller()
                    scan_id = int(repo.get_setting(f"managed_scan:{job['id']}", "0") or 0)
                    if ctl and ctl.scan_id == scan_id:
                        desired = job["desired_state"]
                        if desired == "cancelled":
                            ctl.stop()
                        elif desired == "paused" or paused():
                            if ctl.state == "running": ctl.pause()
                        elif ctl.state == "paused":
                            ctl.resume()
                        progress = ctl.snapshot()
                        baseline = job["total"] - progress["total"]
                        progress["done"] += max(0, baseline)
                        progress["total"] = job["total"]
                        await update_job(job, "paused" if ctl.state == "paused" else "running", progress)
                    elif ctl:
                        ctl.stop()
                    elif starting is None or starting.done():
                        if starting and not starting.cancelled() and starting.exception():
                            raise starting.exception()
                        scan = repo.get_scan(scan_id) if scan_id else None
                        if scan and scan["status"] in ("done", "failed") or job["desired_state"] == "cancelled":
                            if finishing is None or finishing.done():
                                if finishing and not finishing.cancelled() and finishing.exception():
                                    STATE["sync_error"] = str(finishing.exception())
                                # Keep heartbeats alive throughout potentially large uploads.
                                async def finish(current, local_scan, terminal_state, owner, pending_sync):
                                    if pending_sync:
                                        await pending_sync
                                    await maintenance(owner)
                                    count = len(repo.results_for_scan(local_scan)) if local_scan else 0
                                    await update_job(current, terminal_state, {"done": count, "total": current["total"]})
                                state = "cancelled" if job["desired_state"] == "cancelled" else scan["status"]
                                finishing = asyncio.create_task(finish(job, scan_id, state, user["id"], syncing))
                        elif job["desired_state"] == "running" and not paused():
                            starting = asyncio.create_task(start_job(job, user["id"]))
                elif ctl:
                    # Revoked/cancelled lease: stop before accepting any new work.
                    ctl.stop()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                STATE["error"] = str(exc)
                log.warning("Control sync failed: %s", exc)
                if time.monotonic() - last_ok > 90:
                    STATE["connected"] = False
                    ctl = orchestrator.active_controller()
                    if ctl: ctl.stop()
            await asyncio.sleep(15)
    finally:
        for task in (starting, syncing, finishing):
            if task and not task.done(): task.cancel()
        await asyncio.gather(*(t for t in (starting, syncing, finishing) if t), return_exceptions=True)
