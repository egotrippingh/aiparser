"""Связь настольного парсера с аккаунтом и оплачиваемыми проверками."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from app import config, secrets_store
from app.db import repo

TOKEN_KEY = "account_token"
_screenshot_retry_after = 0.0


class BillingError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ScreenshotError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(config.ACCOUNT_URL)


def token() -> str:
    return secrets_store.unprotect(repo.get_setting(TOKEN_KEY))


def check_id(run_id: str, query_id: int | str, service: str) -> str:
    return f"{run_id}:{query_id}:{service}"


def canonical_check_id(snapshot: dict, query_id: int, service: str) -> str | None:
    """Return the server's check ID, never a local ID for a managed run."""
    run_id = snapshot.get("billing_run_id")
    if not run_id:
        return None
    managed = "cloud_job_id" in snapshot or "cloud_query_map" in snapshot
    query_map = snapshot.get("cloud_query_map", {})
    if managed:
        canonical = query_map.get(str(query_id)) if isinstance(query_map, dict) else None
        if not canonical:
            raise BillingError("В управляемой проверке отсутствует сопоставление запроса")
        return check_id(run_id, canonical, service)
    return check_id(run_id, query_id, service)


async def _request(method: str, path: str, *, body: dict | None = None,
                   auth: bool = True, timeout: float = 20, bearer: str | None = None) -> dict:
    if not enabled():
        raise BillingError("Этот выпуск приложения не подключён к личному кабинету")
    key = (bearer if bearer is not None else token()) if auth else ""
    if auth and not key:
        raise BillingError("Войдите в аккаунт перед запуском скана")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, f"{config.ACCOUNT_URL}/api/v1{path}",
                                            json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise BillingError("Не удалось связаться с сервером оплаты") from exc
    if response.is_error:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise BillingError(str(detail or f"Ошибка сервера оплаты: HTTP {response.status_code}"), response.status_code)
    return response.json()


async def browser_url(destination: str = "cabinet") -> str:
    if not token():
        return f"{config.ACCOUNT_URL}/cabinet/" + ("#/topup" if destination == "topup" else "")
    result = await _request("POST", "/auth/browser-link", body={"destination": destination})
    path = result.get("path", "")
    if not path.startswith("/cabinet/#browser_ticket="):
        raise BillingError("Сервер вернул некорректную ссылку входа")
    return f"{config.ACCOUNT_URL}{path}"


async def login(email: str, password: str) -> dict:
    response = await _request("POST", "/auth/login", body={"email": email, "password": password}, auth=False)
    repo.set_setting(TOKEN_KEY, secrets_store.protect(response["token"]), is_secret=True)
    return response["user"]


async def login_with_code(code: str) -> dict:
    response = await _request("POST", "/auth/device/exchange",
                              body={"ticket": code.strip()}, auth=False)
    repo.set_setting(TOKEN_KEY, secrets_store.protect(response["token"]), is_secret=True)
    return response["user"]


async def logout() -> None:
    if token():
        try:
            await _request("POST", "/auth/logout")
        except BillingError:
            pass
    repo.set_setting(TOKEN_KEY, None, is_secret=True)


async def status() -> dict:
    if not enabled():
        return {"enabled": False, "connected": False}
    if not token():
        return {"enabled": True, "connected": False,
                "cabinet_url": f"{config.ACCOUNT_URL}/cabinet/"}
    user = await _request("GET", "/me")
    wallet = await _request("GET", "/wallet")
    pricing = await _request("GET", "/pricing", auth=False)
    return {"enabled": True, "connected": True, "user_id": user["id"], "email": user["email"],
            "is_admin": user.get("is_admin", False),
            "wallet": wallet, "pricing": pricing,
            "cabinet_url": f"{config.ACCOUNT_URL}/cabinet/"}


async def identity() -> dict:
    return await _request("GET", "/me")


async def heartbeat(device_id: str, name: str, zone: str, active_scan: bool) -> dict:
    return await _request("POST", "/agent/heartbeat", body={
        "device_id": device_id, "name": name, "local_time_zone": zone,
        "active_scan": active_scan,
    })


async def scan_preferences() -> dict:
    return await _request("GET", "/scan-preferences")


async def save_scan_preferences(preferences: dict) -> dict:
    return await _request("PUT", "/scan-preferences", body=preferences)


async def upload_cloud_results(device_id: str, results: list[dict]) -> dict:
    return await _request("POST", "/agent/results",
                          body={"device_id": device_id, "results": results}, timeout=60)


async def reserve(check_ids: list[str]) -> dict:
    result = {}
    for offset in range(0, len(check_ids), 1000):
        result = await _request("POST", "/checks/reserve",
                                body={"check_ids": check_ids[offset:offset + 1000]})
    return result


async def analyze(check_id_value: str, system: str, content: list[dict]) -> dict:
    return await _request("POST", f"/checks/{check_id_value}/analyze",
                          body={"system": system, "content": content}, timeout=100)


async def arbitrate(check_id_value: str, system: str, content: list[dict]) -> dict:
    return await _request("POST", f"/checks/{check_id_value}/arbitrate",
                          body={"system": system, "content": content}, timeout=100)


async def complete(check_id_value: str, status: str) -> dict:
    return await _request("POST", f"/checks/{check_id_value}/complete", body={"status": status})


async def release(check_ids: list[str]) -> dict:
    if not check_ids:
        return {"released": 0}
    released = 0
    for offset in range(0, len(check_ids), 1000):
        result = await _request("POST", "/checks/release",
                                body={"check_ids": check_ids[offset:offset + 1000]})
        released += result.get("released", 0)
    return {"released": released}


async def flush_outbox(user_id: str | None = None) -> None:
    pending = repo.pending_billing(user_id) if user_id else repo.pending_billing()
    for item in pending:
        if item["status"] == "release":
            continue
        response = await complete(item["check_id"], item["status"])
        if response.get("status") == "released":
            # A saved answer can outlive an accidental release during an
            # interrupted scan. Reserve that same ID again before settling.
            await reserve([item["check_id"]])
            response = await complete(item["check_id"], item["status"])
        if response.get("status") != "settled":
            raise BillingError("Сервер не подтвердил списание за сохранённую проверку")
        repo.billing_sent([item["check_id"]])
    releases = [item["check_id"] for item in pending if item["status"] == "release"]
    for offset in range(0, len(releases), 1000):
        chunk = releases[offset:offset + 1000]
        await release(chunk)
        repo.billing_sent(chunk)


async def flush_screenshot_outbox(user_id: str | None = None) -> None:
    """Best-effort upload; billing and the local result remain independent."""
    global _screenshot_retry_after
    if not enabled() or not token():
        return
    if time.monotonic() < _screenshot_retry_after:
        return
    root = Path(config.SCREENSHOTS_DIR).resolve()
    for item in (repo.pending_screenshots(user_id) if user_id else repo.pending_screenshots()):
        path = (root / item["local_path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            repo.screenshot_sent(item["check_id"])
            continue
        if path.stat().st_size > 8 * 1024 * 1024:
            repo.screenshot_sent(item["check_id"])
            continue
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.put(
                    f"{config.ACCOUNT_URL}/api/v1/checks/{item['check_id']}/screenshot",
                    content=path.read_bytes(),
                    headers={"Authorization": f"Bearer {token()}",
                             "Content-Type": "image/webp"},
                )
        except httpx.HTTPError as exc:
            _screenshot_retry_after = time.monotonic() + 60
            raise ScreenshotError("Не удалось отправить скриншот") from exc
        if response.status_code == 404:
            # Проверка могла принадлежать другому аккаунту на этом ПК.
            # Сохраняем очередь для прежнего владельца, остальные шлём дальше.
            continue
        if response.is_error:
            _screenshot_retry_after = time.monotonic() + 60
            raise ScreenshotError(f"Сервер не принял скриншот: HTTP {response.status_code}")
        repo.screenshot_sent(item["check_id"])


async def recover_interrupted_scans(user_id: str | None = None) -> None:
    """Освободить незавершённые резервы после аварийного закрытия приложения."""
    if user_id:
        repo.repair_managed_outbox(user_id)
    scans = repo.interrupted_billing_scans()
    reconciled = []
    pending = {item["check_id"]: item["status"] for item in repo.pending_billing()}
    shots = {item["check_id"] for item in repo.pending_screenshots()}
    # До отправки очереди заменяем страховочные release на фактические
    # результаты. Иначе сбой сразу после сохранения результата освободит
    # резерв, а повторное списание сервер уже не примет.
    for scan in scans:
        snapshot = json.loads(scan["settings_snapshot_json"] or "{}")
        if user_id and snapshot.get("billing_user_id") != user_id:
            continue
        run_id = snapshot.get("billing_run_id")
        results, blocked = {}, set()
        try:
            for row in repo.results_for_scan(scan["id"]):
                key = canonical_check_id(snapshot, row["query_id"], row["service"])
                old = check_id(run_id, row["query_id"], row["service"])
                if key != old and (old in pending or old in shots):
                    blocked.add(key)
                results[key] = row["status"]
        except BillingError:
            continue
        for key in snapshot.get("billing_reserved_ids", []):
            if key in blocked or pending.get(key) in ("found", "not_found"):
                continue
            status_value = results.get(key)
            repo.queue_billing(key, status_value if status_value in ("found", "not_found") else "release")
        reconciled.append(scan)
    await flush_outbox(user_id)
    for scan in reconciled:
        repo.finish_scan(scan["id"], status="stopped")
