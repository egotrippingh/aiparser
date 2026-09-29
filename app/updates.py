"""Release notice polling; it is deliberately independent of account sync."""
from __future__ import annotations

import asyncio
import json
import re

import httpx

from app import __version__, config
from app.db import repo

RELEASE_URL = "https://airate.tech/api/v1/agent-download"
INSTALLER_URL = "https://airate.tech/downloads/AIRate-Setup.exe"
PORTABLE_URL = "https://airate.tech/downloads/AI-Mentions-Windows.zip"
MAX_BODY = 64 * 1024
VERSION_RE = re.compile(r"[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}\Z")
_release: dict | None = None
_error = ""
_checking = False


def version_parts(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        return None
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def valid_release(value: object) -> dict | None:
    if not isinstance(value, dict) or version_parts(value.get("version")) is None:
        return None
    artifacts = []
    for name in ("installer", "portable"):
        artifact = value.get(name)
        if not isinstance(artifact, dict) or type(artifact.get("size_bytes")) is not int or artifact["size_bytes"] <= 0:
            return None
        if not isinstance(artifact.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
            return None
        artifacts.append(artifact)
    return {"version": value["version"], "installer": artifacts[0], "portable": artifacts[1]}


def snapshot() -> dict:
    dismissed = repo.get_setting("dismissed_update_version")
    available = bool(_release and dismissed != _release["version"])
    return {"current": __version__, "portable": config.PORTABLE, "checking": _checking,
            "error": _error, "release": _release if available else None}


def checked_snapshot(manual: bool) -> dict:
    if manual and not _checking and not _error and _release:
        if repo.get_setting("dismissed_update_version") == _release["version"]:
            repo.set_setting("dismissed_update_version", None)
    return snapshot()


async def check(*, manual: bool = False) -> dict:
    global _checking, _error, _release
    if _checking:
        if manual:
            deadline = asyncio.get_running_loop().time() + 10
            while _checking and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(.05)
        if manual and _checking:
            return {**snapshot(), "release": None, "error": "Проверка обновлений ещё выполняется"}
        return checked_snapshot(manual)
    _checking = True
    _error = ""
    try:
        async with asyncio.timeout(10), httpx.AsyncClient(timeout=httpx.Timeout(8), follow_redirects=False) as client:
            async with client.stream("GET", RELEASE_URL, headers={"Accept": "application/json"}) as response:
                if response.status_code != 200:
                    raise ValueError("Сервер обновлений недоступен")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BODY:
                        raise ValueError("Ответ сервера обновлений слишком большой")
        payload = json.loads(body)
        release = valid_release(payload.get("release") if isinstance(payload, dict) else None)
        current = version_parts(__version__)
        if not isinstance(payload, dict) or payload.get("release") is None:
            raise ValueError("Метаданные обновления недоступны")
        if release is None:
            raise ValueError("Некорректные метаданные обновления")
        if current is None or version_parts(release["version"]) <= current:
            _release = None
        else:
            _release = release
    except (httpx.HTTPError, TimeoutError, ValueError, TypeError, json.JSONDecodeError):
        _release = None
        _error = "Не удалось проверить обновления"
    finally:
        _checking = False
    return checked_snapshot(manual)


async def run() -> None:
    while True:
        await check()
        await asyncio.sleep(3600)


def dismiss(version: str) -> None:
    if _release and version == _release["version"]:
        repo.set_setting("dismissed_update_version", version)
