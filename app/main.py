"""Точка входа: поднимает FastAPI в фоновом потоке и показывает интерфейс.

Один процесс, один пользователь, локальный сервер только на 127.0.0.1 —
разделение на «сервер» и «клиент» здесь чисто внутреннее. Интерфейс
показывается одним из двух способов:

* по умолчанию — окном десктопного приложения (pywebview + WebView2);
* с ключом ``--browser`` — вкладкой в обычном браузере. Так запускает
  start.bat. Программа живёт, пока открыто окно консоли.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
import webbrowser

import uvicorn

from app import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("aiparser.main")


def _run_server() -> None:
    from app.api import create_app

    app = create_app()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")


def _wait_for_server(url: str, timeout: float = 15.0) -> bool:
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main() -> None:
    log.info("Каталог данных: %s (portable=%s)", config.DATA_DIR, config.PORTABLE)

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    url = f"http://{config.HOST}:{config.PORT}/"
    if not _wait_for_server(url):
        log.error("Сервер не поднялся за отведённое время")
        return

    if "--browser" in sys.argv[1:]:
        log.info("Интерфейс: %s", url)
        webbrowser.open(url)
        try:
            while server_thread.is_alive():
                server_thread.join(1)
        except KeyboardInterrupt:
            pass
        return

    import webview

    webview.create_window(
        "AI Mentions Tracker",
        url,
        width=1440,
        height=900,
        min_size=(1100, 700),
    )
    webview.start()


if __name__ == "__main__":
    main()
