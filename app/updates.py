"""Release notice polling; it is deliberately independent of account sync."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import shutil
import threading
import time
from pathlib import Path

import httpx

from app import __version__, config
from app.db import repo

RELEASE_URL = "https://airate.tech/api/v1/agent-download"
INSTALLER_URL = "https://airate.tech/downloads/AIRate-Setup.exe"
PORTABLE_URL = "https://airate.tech/downloads/AI-Mentions-Windows.zip"
MAX_BODY = 64 * 1024
MAX_ARTIFACT = 512 * 1024 * 1024
VERSION_RE = re.compile(r"[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}\Z")
_release: dict | None = None
_error = ""
_checking = False
_applying = False
_progress: dict | None = None
_activity = 0
_handoff_error = ""
_abort_path: Path | None = None
_installer: subprocess.Popen | None = None
_watcher: threading.Thread | None = None
_abort_failed = False


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
    return {"current": __version__, "portable": config.PORTABLE, "checking": _checking, "applying": _applying,
            "progress": _progress,
            "error": _handoff_error or _error, "release": _release if available else None}


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


async def _latest() -> dict:
    await check(manual=True)
    if not _release:
        raise ValueError(_error or "Обновление больше недоступно")
    return _release


async def _download(release: dict, destination: Path) -> None:
    artifact = release["installer"]
    size = artifact["size_bytes"]
    if size > MAX_ARTIFACT:
        raise ValueError("Файл обновления слишком большой")
    digest = hashlib.sha256()
    received = 0
    async with httpx.AsyncClient(timeout=httpx.Timeout(30), follow_redirects=False) as client:
        async with client.stream("GET", INSTALLER_URL, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200 or response.headers.get("content-encoding"):
                raise ValueError("Не удалось скачать обновление")
            with destination.open("xb") as output:
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > size:
                        raise ValueError("Размер файла обновления не совпадает")
                    digest.update(chunk)
                    output.write(chunk)
                    global _progress
                    _progress = {"stage": "download", "downloaded_bytes": received, "total_bytes": size}
    if received != size or digest.hexdigest() != artifact["sha256"]:
        raise ValueError("Контрольная сумма обновления не совпадает")


def working() -> bool:
    return _activity > 0


async def admit() -> None:
    global _activity
    from app.scanner import orchestrator
    async with orchestrator.scan_start_lock():
        if _applying:
            raise ValueError("Идёт обновление приложения")
        _activity += 1


def release_activity() -> None:
    global _activity
    _activity -= 1


@asynccontextmanager
async def activity():
    """Admit a network operation atomically with update reservation."""
    await admit()
    try:
        yield
    finally:
        release_activity()


def reserve() -> bool:
    """Set the shared update gate before an endpoint releases scan_start_lock."""
    global _applying, _error, _handoff_error, _installer, _watcher, _abort_failed
    if _applying:
        return False
    if _activity:
        raise ValueError("Сначала дождитесь завершения текущей работы агента")
    if not getattr(sys, "frozen", False) or not config.BASE_DIR.exists() or not os.access(config.BASE_DIR, os.W_OK):
        raise ValueError("Автообновление доступно только для установленного приложения Windows")
    _applying = True
    _error = ""
    _handoff_error = ""
    _installer = None
    _watcher = None
    _abort_failed = False
    return True


def _release_after_exit(process: subprocess.Popen) -> None:
    """Do not permit another installer while a rejected one can still be waiting."""
    global _applying
    process.wait()
    if process is _installer:
        _applying = False


def _watch_installer() -> None:
    global _watcher
    if _installer is not None and _watcher is None:
        _watcher = threading.Thread(target=_release_after_exit, args=(_installer,), daemon=True,
                                    name="agent-update-installer-watch")
        _watcher.start()


def _abort_installer() -> None:
    global _abort_failed
    try:
        if _abort_path is not None:
            _abort_path.touch(exist_ok=True)
    except OSError:
        _abort_failed = True
        logging.getLogger(__name__).exception("Не удалось записать отмену обновления")
    finally:
        _watch_installer()


def wait_failed_cancellation() -> None:
    # Keep the parent alive until Setup's own timeout if it cannot read an abort.
    # Otherwise a tray Quit could accidentally authorize the cancelled update.
    if _abort_failed and _installer is not None:
        _installer.wait()


def _owned_stage(stage: Path) -> bool:
    return stage.parent.resolve() == Path(tempfile.gettempdir()).resolve() and stage.name.startswith("airate-update-")


async def apply(expected_version: str, shutdown, *, reserved: bool = False) -> dict:
    """Verify the official installer, wait for its acknowledgement, then exit cleanly."""
    global _applying, _progress, _error, _abort_path, _installer
    if not reserved and not reserve():
        return snapshot()
    stage: Path | None = None
    process: subprocess.Popen | None = None
    try:
        stage = Path(tempfile.mkdtemp(prefix="airate-update-"))
        abort = stage / "abort"
        _abort_path = abort
        release = await _latest()
        if release["version"] != expected_version or version_parts(release["version"]) <= version_parts(__version__):
            raise ValueError("Версия обновления изменилась; проверьте её снова")
        installer = stage / "AIRate-Setup.exe"
        await _download(release, installer)
        ack = stage / "ready"
        result = stage / "result.json"
        mode = "installed" if (config.BASE_DIR / "installed-mode.txt").is_file() else "portable"
        _progress = {"stage": "prepare", "downloaded_bytes": release["installer"]["size_bytes"], "total_bytes": release["installer"]["size_bytes"]}
        process = subprocess.Popen([str(installer), "/SP-", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NOICONS",
                          "/TASKS=", "/NOCLOSEAPPLICATIONS", "/NOFORCECLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS",
                          "/NORESTART", f"/UPDATEPID={os.getpid()}", f"/UPDATETARGET={config.BASE_DIR}",
                          f"/DIR={config.BASE_DIR}", f"/UPDATEMODE={mode}", f"/UPDATEACK={ack}", f"/UPDATEABORT={abort}", f"/UPDATEVERSION={release['version']}", f"/UPDATERESULT={result}"], shell=False)
        _installer = process
        deadline = time.monotonic() + 15
        while not ack.exists() and time.monotonic() < deadline:
            await asyncio.sleep(.05)
        if not ack.exists() or ack.read_text(encoding="ascii", errors="ignore").strip() != "READY" or process.poll() is not None:
            raise ValueError("Установщик не подтвердил подготовку")
        repo.set_setting("update_stage", str(stage))
        _progress = {"stage": "restart", "downloaded_bytes": release["installer"]["size_bytes"], "total_bytes": release["installer"]["size_bytes"]}
        if not shutdown():
            raise ValueError("Не удалось подготовить безопасное завершение приложения")
        return snapshot()
    except (Exception, asyncio.CancelledError) as exc:
        _error = str(exc)
        _progress = {"stage": "error"}
        if process is None:
            _applying = False
            if stage is not None and _owned_stage(stage):
                shutil.rmtree(stage, ignore_errors=True)
        else:
            # The setup executable may still be holding an old process handle.
            # Let it see this sentinel and keep the shared gate until it exits.
            _abort_installer()
        raise


def consume_previous_result() -> None:
    """Remove only a stage we created after the updated process actually starts."""
    global _error, _handoff_error
    raw = repo.get_setting("update_stage")
    if not raw:
        return
    stage = Path(raw)
    try:
        if not _owned_stage(stage):
            return
        verified = repo.get_setting("update_stage_ready") == raw
        if not verified:
            result = (stage / "result.json").read_text(encoding="utf-8")
            if result != "ready:" + __version__:
                if result.startswith("error:"):
                    _handoff_error = "Установщик не смог перезапустить агент"
                return
            # Remember the exact owned path before deletion: Setup may still
            # hold its executable open after it has launched this process.
            repo.set_setting("update_stage_ready", raw)
        shutil.rmtree(stage)
        repo.set_setting("update_stage", None)
        repo.set_setting("update_stage_ready", None)
    except OSError:
        # A still-running setup executable can retain its own stage briefly.
        return



async def run() -> None:
    while True:
        await check()
        await asyncio.sleep(3600)


def dismiss(version: str) -> None:
    if _release and version == _release["version"]:
        repo.set_setting("dismissed_update_version", version)


def busy() -> bool:
    return _applying


def shutdown_failed(message: str) -> None:
    global _applying, _progress, _handoff_error
    _handoff_error = message
    _progress = {"stage": "error"}
    _abort_installer()
