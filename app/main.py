"""Точка входа: поднимает FastAPI в фоновом потоке и показывает интерфейс.

Один процесс, один пользователь, локальный сервер только на 127.0.0.1 —
разделение на «сервер» и «клиент» здесь чисто внутреннее. Интерфейс
показывается одним из двух способов:

* Windows-сборка показывает окно WebView2, а при закрытии скрывает его в трее;
* с ключом ``--background`` агент запускается со скрытым окном;
* с ключом ``--browser`` интерфейс открывается в обычном браузере.
"""

from __future__ import annotations

import logging
import json
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from app import config, window_control

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


def _focus_existing(url: str) -> bool:
    import urllib.request

    request = urllib.request.Request(url.replace("/app/", "/api/agent/focus"),
                                     data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return bool(json.load(response).get("focused"))
    except Exception:
        return False


def _port_available(port: int) -> bool:
    with socket.socket() as listener:
        try:
            listener.bind((config.HOST, port))
        except OSError:
            return False
        return True


def _free_local_port() -> int:
    with socket.socket() as listener:
        listener.bind((config.HOST, 0))
        return listener.getsockname()[1]


def main() -> None:
    log.info("Каталог данных: %s (portable=%s)", config.DATA_DIR, config.PORTABLE)

    # Use predictable fallback ports so a second launch can find the first
    # native window even when the development server owns 8756.
    for port in (8756, *range(8758, 8776)):
        candidate = f"http://{config.HOST}:{port}/app/"
        if not _port_available(port):
            if "--self-test" not in sys.argv[1:] and _focus_existing(candidate):
                return
            continue
        config.PORT = port
        break
    else:
        config.PORT = _free_local_port()
    url = f"http://{config.HOST}:{config.PORT}/app/"
    if config.PORT != 8756:
        log.info("Порт 8756 занят; агент откроется на %s", url)

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    if not _wait_for_server(url):
        raise RuntimeError("Локальный сервер не поднялся за отведённое время")

    if "--self-test" in sys.argv[1:]:
        import urllib.request
        import webview.platforms.winforms

        for path in ("/api/meta", "/api/browser/status", "/app/"):
            with urllib.request.urlopen(f"http://{config.HOST}:{config.PORT}{path}", timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError(f"Проверка {path} завершилась с HTTP {response.status}")
        if "--self-test-browser" in sys.argv[1:]:
            import asyncio

            from camoufox.async_api import AsyncCamoufox

            async def check_browser() -> None:
                async with AsyncCamoufox(headless=True, os="windows", geoip=False) as browser:
                    page = await browser.new_page()
                    await page.goto("about:blank")
                    if page.url != "about:blank":
                        raise RuntimeError("Camoufox не открыл тестовую страницу")

            asyncio.run(check_browser())
        log.info("Проверка настольного приложения прошла")
        return

    import pystray
    from PIL import Image, ImageDraw

    browser_mode = "--browser" in sys.argv[1:]
    background = "--background" in sys.argv[1:]
    window = None
    exiting = False
    if not browser_mode:
        import webview

        window = webview.create_window(
            "AI Mentions — агент", url, width=1320, height=860,
            min_size=(960, 650), hidden=background,
        )

        def on_closing() -> bool:
            if exiting:
                return True
            window.hide()
            return False

        window.events.closing += on_closing
        window_control.set_focus(window.show)
    elif not background:
        webbrowser.open(url)

    image = Image.new("RGBA", (64, 64), (19, 13, 30, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((7, 7, 57, 57), radius=15, fill=(135, 82, 213, 255))
    draw.ellipse((23, 23, 41, 41), fill=(247, 244, 255, 255))

    def open_agent(icon, item) -> None:
        if window is not None:
            window.show()
        else:
            webbrowser.open(url)

    def open_account(icon, item) -> None:
        if config.ACCOUNT_URL:
            webbrowser.open(f"{config.ACCOUNT_URL}/cabinet/")

    def quit_agent(icon, item) -> None:
        nonlocal exiting
        exiting = True
        icon.stop()
        if window is not None:
            window.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("Открыть агент", open_agent, default=True),
        pystray.MenuItem("Личный кабинет", open_account,
                         enabled=lambda _: bool(config.ACCOUNT_URL)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выйти", quit_agent),
    )
    icon = pystray.Icon("AI Mentions", image, "AI Mentions — агент", menu)
    if window is not None:
        # pystray allows a non-main thread on Windows; WebView2 needs main.
        threading.Thread(target=icon.run, daemon=True, name="agent-tray").start()
        webview.start()
        icon.stop()
    else:
        icon.run()


if __name__ == "__main__":
    main()
