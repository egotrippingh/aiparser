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
from datetime import datetime

from app.scanner.browser_install import install_browser

from fastapi import APIRouter, HTTPException

from app import services
from app.db import repo
from app.scanner.browser import camoufox_installed, open_login_window
from app.scanner.profiles import cookie_auth_state
from app.scanner.adapters import xmlriver

router = APIRouter(prefix="/api/browser", tags=["browser"])
log = logging.getLogger("aiparser.api.browser")

_install_state = {"running": False, "done": False, "error": None, "log": [], "progress": None}
_login_running: set[str] = set()
_login_status: dict[str, dict] = {}
_login_tasks: set[asyncio.Task] = set()
_install_task: asyncio.Task | None = None


def _service_auth(service_id: str) -> dict:
    """Две половины правды о входе.

    `cookie` — есть ли на диске живая сессионная кука (мгновенно, без запуска
    браузера). `last_scan` — что сервис ответил в последний реальный прогон.
    Кука может лежать, а сервис её уже не принимать, поэтому показываем обе:
    одна отвечает на «я вообще логинился?», вторая на «оно ещё работает?».
    """
    api_backend = service_id == "yandex_neuro" or (service_id == "google_aio" and xmlriver.configured())
    cookie = cookie_auth_state(service_id) if not api_backend else {"state": "none", "expires_at": None}

    last_state, last_at = None, None
    raw = repo.get_setting(f"{'xmlriver_state' if api_backend else 'auth_state'}:{service_id}")
    if raw:
        try:
            parsed = json.loads(raw)
            last_state, last_at = parsed.get("state"), parsed.get("at")
        except (ValueError, AttributeError):
            pass

    return {
        "cookie_state": cookie["state"],
        "api_backend": api_backend,
        "api_configured": xmlriver.configured() if api_backend else False,
        "expires_at": cookie["expires_at"],
        "last_scan_state": last_state,
        "last_scan_at": last_at,
        "login_open": service_id in _login_running,
        "login_state": _login_status.get(service_id, {}).get("state", "idle"),
        "login_error": _login_status.get(service_id, {}).get("error"),
        "last_login_at": repo.get_setting(f"login_completed:{service_id}"),
    }


@router.get("/status")
def status() -> dict:
    return {
        "installed": camoufox_installed(),
        "installing": _install_state["running"],
        "install_error": _install_state["error"],
        "install_progress": _install_state["progress"],
        "logins_in_progress": sorted(_login_running),
        "services": {s.id: _service_auth(s.id) for s in services.SERVICES},
    }


async def _install() -> None:
    _install_state.update(running=True, done=False, error=None,
                          log=["Скачиваю Camoufox в пользовательский кэш. Это большой файл; подождите..."])
    try:
        loop = asyncio.get_running_loop()

        def report(stage, downloaded, total):
            progress = {"stage": stage, "downloaded_bytes": downloaded,
                        "total_bytes": total if total > 0 else None,
                        "percent": min(100, int(downloaded * 100 / total)) if total > 0 else None}
            loop.call_soon_threadsafe(_install_state.update, {"progress": progress})

        await asyncio.to_thread(install_browser, on_progress=report)
        _install_state["log"].append("Camoufox установлен")
    except Exception as exc:
        log.exception("Не удалось скачать Camoufox")
        _install_state["error"] = str(exc)
        _install_state["progress"] = None
    finally:
        _install_state["running"] = False
        _install_state["done"] = _install_state["error"] is None


@router.post("/install", status_code=202)
async def install() -> dict:
    global _install_task
    from app import updates
    from app.scanner import orchestrator
    async with orchestrator.scan_start_lock():
        if updates.busy():
            raise HTTPException(409, "Идёт обновление приложения")
        if _install_state["running"]:
            return {"ok": True, "already_running": True}
        if camoufox_installed():
            return {"ok": True, "already_installed": True}
        # Reserve before returning, so update_apply sees an in-flight install.
        _install_state.update(running=True, done=False, error=None,
                              progress={"stage": "preparing", "downloaded_bytes": 0,
                                        "total_bytes": None, "percent": None})
        _install_task = asyncio.create_task(_install())
    return {"ok": True}


@router.get("/install/log")
def install_log() -> dict:
    return {"lines": _install_state["log"], "running": _install_state["running"],
            "error": _install_state["error"], "progress": _install_state["progress"]}


@router.post("/services/{service_id}/login", status_code=202)
async def login(service_id: str) -> dict:
    from app.scanner import orchestrator
    from app import updates
    try:
        info = services.get(service_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    async with orchestrator.scan_start_lock():
        if updates.busy():
            raise HTTPException(409, "Идёт обновление приложения")
        if orchestrator.active_controller():
            raise HTTPException(409, "Сначала остановите проверку на сайте, затем откройте вход")
        if service_id in _login_running:
            return {"ok": True, "already_open": True}
        if not camoufox_installed():
            raise HTTPException(409, "Сначала установите браузер агента")
        # Reserve before responding: double clicks and the worker see it immediately.
        _login_running.add(service_id)
        _login_status[service_id] = {"state": "starting", "error": None}

    async def _run():
        try:
            def opened():
                _login_status[service_id]["state"] = "open"
            def navigation_error(message):
                _login_status[service_id]["error"] = message
            await open_login_window(service_id, info.login_url, on_open=opened,
                                    on_navigation_error=navigation_error)
            _login_status[service_id] = {"state": "closed", "error": None}
            # Cookies prove a saved session, not that the next scan will succeed.
            if cookie_auth_state(service_id)["state"] == "ok":
                repo.set_setting(f"login_completed:{service_id}", datetime.now().isoformat(timespec="seconds"))
        except Exception as exc:
            message = str(exc).split("\n", 1)[0][:250]
            _login_status[service_id] = {"state": "error", "error":
                f"Не удалось открыть браузер. {message or type(exc).__name__}. Попробуйте ещё раз."}
            log.exception("Окно логина для %s закрылось с ошибкой", service_id)
        finally:
            _login_running.discard(service_id)

    task = asyncio.create_task(_run())
    _login_tasks.add(task)
    task.add_done_callback(_login_tasks.discard)
    return {"ok": True}
