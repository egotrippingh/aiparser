"""Установка Camoufox и вход в аккаунты сервисов — обе операции долгие
и блокирующие, поэтому запускаются фоновой задачей, а прогресс/готовность
опрашивается отдельным эндпоинтом. Окно логина открывается по-настоящему
поверх экрана, поэтому дожидаться его в теле HTTP-запроса нельзя — таймаут
браузера/фронта наступит раньше, чем пользователь успеет ввести пароль.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException

from app import services
from app.db import repo
from app.scanner.browser import camoufox_installed, open_login_window
from app.scanner.profiles import cookie_auth_state

router = APIRouter(prefix="/api/browser", tags=["browser"])
log = logging.getLogger("aiparser.api.browser")

_install_state = {"running": False, "done": False, "error": None, "log": []}
_login_running: set[str] = set()


def _service_auth(service_id: str) -> dict:
    """Две половины правды о входе.

    `cookie` — есть ли на диске живая сессионная кука (мгновенно, без запуска
    браузера). `last_scan` — что сервис ответил в последний реальный прогон.
    Кука может лежать, а сервис её уже не принимать, поэтому показываем обе:
    одна отвечает на «я вообще логинился?», вторая на «оно ещё работает?».
    """
    cookie = cookie_auth_state(service_id)

    last_state, last_at = None, None
    raw = repo.get_setting(f"auth_state:{service_id}")
    if raw:
        try:
            parsed = json.loads(raw)
            last_state, last_at = parsed.get("state"), parsed.get("at")
        except (ValueError, AttributeError):
            pass

    return {
        "cookie_state": cookie["state"],
        "expires_at": cookie["expires_at"],
        "last_scan_state": last_state,
        "last_scan_at": last_at,
        "login_open": service_id in _login_running,
    }


@router.get("/status")
def status() -> dict:
    return {
        "installed": camoufox_installed(),
        "installing": _install_state["running"],
        "install_error": _install_state["error"],
        "logins_in_progress": sorted(_login_running),
        "services": {s.id: _service_auth(s.id) for s in services.SERVICES},
    }


async def _install() -> None:
    _install_state.update(running=True, error=None)
    try:
        proc = await asyncio.create_subprocess_exec(
            *[__import__("sys").executable, "-m", "camoufox", "fetch"],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout
        async for line in proc.stdout:
            _install_state["log"].append(line.decode(errors="replace").rstrip())
            _install_state["log"] = _install_state["log"][-200:]
        code = await proc.wait()
        if code != 0:
            _install_state["error"] = f"camoufox fetch завершился с кодом {code}"
    except Exception as exc:
        log.exception("Не удалось скачать Camoufox")
        _install_state["error"] = str(exc)
    finally:
        _install_state["running"] = False
        _install_state["done"] = True


@router.post("/install", status_code=202)
async def install() -> dict:
    if _install_state["running"]:
        return {"ok": True, "already_running": True}
    if camoufox_installed():
        return {"ok": True, "already_installed": True}
    asyncio.create_task(_install())
    return {"ok": True}


@router.get("/install/log")
def install_log() -> dict:
    return {"lines": _install_state["log"], "running": _install_state["running"], "error": _install_state["error"]}


@router.post("/services/{service_id}/login", status_code=202)
async def login(service_id: str) -> dict:
    try:
        info = services.get(service_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    if service_id in _login_running:
        return {"ok": True, "already_open": True}

    async def _run():
        _login_running.add(service_id)
        try:
            await open_login_window(service_id, info.login_url)
        except Exception:
            log.exception("Окно логина для %s закрылось с ошибкой", service_id)
        finally:
            _login_running.discard(service_id)

    asyncio.create_task(_run())
    return {"ok": True}
