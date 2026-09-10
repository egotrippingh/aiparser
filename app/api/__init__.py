"""Сборка FastAPI-приложения.

Сервер слушает только localhost и существует ради одного клиента — окна
WebView. Поэтому ни аутентификации, ни CORS здесь нет и быть не должно.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config, services
from app.db import repo
from app.scanner.adapters import ADAPTERS


def create_app() -> FastAPI:
    # basicConfig — no-op, если root-логгер уже настроен (например, app.main
    # это уже сделал). Нужен на случай прямого запуска через
    # `uvicorn app.api:create_app --factory` — тогда без этого логи сканера
    # и адаптеров (aiparser.*) тихо проваливаются в никуда, что уже стоило
    # времени при отладке.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    repo.init_db()

    app = FastAPI(title="AI Mentions Tracker", docs_url="/api/docs", openapi_url="/api/openapi.json")

    from app.api import browser, projects, queries, results, scans, settings

    app.include_router(projects.router)
    app.include_router(queries.router)
    app.include_router(scans.router)
    app.include_router(results.router)
    app.include_router(settings.router)
    app.include_router(browser.router)

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

    # Скриншоты отдаём как статику: в WebView путь к файлу на диске напрямую
    # не подставить, а гонять их через base64 в JSON — лишний расход памяти.
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

    return app
