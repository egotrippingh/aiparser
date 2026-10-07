"""Сборка FastAPI-приложения.

Сервер слушает только localhost и существует ради одного клиента — окна
WebView. Поэтому ни аутентификации, ни CORS здесь нет и быть не должно.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, services, window_control
from app.db import repo
from app.scanner.adapters import ADAPTERS


def create_app() -> FastAPI:
    # basicConfig — no-op, если root-логгер уже настроен (например, app.main
    # это уже сделал). Нужен на случай прямого запуска через
    # `uvicorn app.api:create_app --factory` — тогда без этого логи сканера
    # и адаптеров (aiparser.*) тихо проваливаются в никуда, что уже стоило
    # времени при отладке.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    import telemetry
    from app import __version__
    telemetry.init(component="agent", dsn=config.SENTRY_DSN, release=__version__)

    repo.init_db()
    from app import updates
    updates.consume_previous_result()

    app = FastAPI(title="AI Mentions Tracker", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.middleware("http")
    async def desktop_boundaries(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
                return JSONResponse({"detail": "Недопустимый источник запроса"}, status_code=403)
            if config.ACCOUNT_URL and not request.url.path.startswith((
                    "/api/desktop/", "/api/browser/", "/api/account/", "/api/agent/focus", "/api/agent/autostart")):
                return JSONResponse({"detail": "Управляйте проектами и проверками на сайте"}, status_code=403)
        try:
            return await call_next(request)
        except Exception as exc:
            telemetry.capture(exc, component="agent", operation="local_api")
            raise

    from app.api import (
        account, agent, browser, desktop, external, mentions, projects, queries, recheck, results, scans, settings,
    )
    app.include_router(desktop.router)

    app.include_router(projects.router)
    app.include_router(queries.router)
    app.include_router(scans.router)
    app.include_router(results.router)
    app.include_router(settings.router)
    app.include_router(account.router)
    app.include_router(agent.router)
    app.include_router(browser.router)
    app.include_router(external.router)
    app.include_router(recheck.router)
    app.include_router(mentions.router)

    import asyncio
    from app.control_agent import run_agent
    from app.scanner import orchestrator
    from app import updates

    agent_task: asyncio.Task | None = None
    update_task: asyncio.Task | None = None

    @app.on_event("startup")
    async def start_agent() -> None:
        from app import billing
        await billing.start_client()
        await billing.start_screenshot_consumer()
        nonlocal agent_task, update_task
        telemetry.watch_loop("agent")
        agent_task = asyncio.create_task(run_agent())
        update_task = asyncio.create_task(updates.run())

    @app.on_event("shutdown")
    async def stop_agent() -> None:
        from app import billing
        if agent_task:
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass
        if update_task:
            update_task.cancel()
            await asyncio.gather(update_task, return_exceptions=True)
        await orchestrator.stop_active_scans()
        await billing.stop_screenshot_consumer()
        await billing.close_client()

    @app.get("/api/meta")
    def meta() -> dict:
        from app import __version__

        return {
            "version": __version__,
            "portable": config.PORTABLE,
            "data_dir": str(config.DATA_DIR),
            "services": [
                {
                    "id": s.id,
                    "name": s.name,
                    "short": s.short,
                    "requires_auth": s.requires_auth,
                    "color": s.color,
                    "note": s.note,
                    # Сервис без адаптера нельзя сканировать — интерфейс должен
                    # показать его неактивным, а не давать выбрать и молча
                    # пропустить, как было раньше.
                    "has_adapter": s.id in ADAPTERS,
                }
                for s in services.SERVICES
            ],
        }

    @app.get("/api/v1/telemetry", include_in_schema=False)
    def telemetry_config(response: Response) -> dict:
        from app import __version__
        response.headers["Cache-Control"] = "no-store"
        return {"dsn": config.SENTRY_DSN, "release": __version__, "environment": telemetry.environment()}

    @app.post("/api/agent/focus", include_in_schema=False)
    def focus_agent() -> dict:
        return {"focused": window_control.focus()}

    @app.get("/cabinet/", include_in_schema=False)
    @app.get("/cabinet", include_in_schema=False)
    def open_cabinet() -> RedirectResponse:
        if not config.ACCOUNT_URL:
            raise HTTPException(404, "Адрес личного кабинета не настроен")
        return RedirectResponse(f"{config.ACCOUNT_URL}/cabinet/", status_code=307)

    # Скриншоты отдаём как статику: в WebView путь к файлу на диске напрямую
    # не подставить, а гонять их через base64 в JSON — лишний расход памяти.
    config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/shots", StaticFiles(directory=config.SCREENSHOTS_DIR), name="shots")

    # Интерфейс — собранный React (исходники в frontend/, `npm run build`
    # кладёт результат в web/). Vite ссылается на ресурсы как /assets/...
    if (config.WEB_DIR / "index.html").exists():
        assets = config.WEB_DIR / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/favicon.svg", include_in_schema=False)
        def favicon() -> FileResponse:
            return FileResponse(config.WEB_DIR / "favicon.svg")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            # no-cache: после пересборки окно не должно показывать старый
            # index.html со ссылками на уже удалённые файлы.
            return FileResponse(config.WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

        @app.get("/app/", include_in_schema=False)
        @app.get("/app", include_in_schema=False)
        def workspace() -> FileResponse:
            return FileResponse(config.WEB_DIR / "app" / "index.html", headers={"Cache-Control": "no-cache"})

    return app
