"""Точка входа: поднимает FastAPI в фоновом потоке и показывает интерфейс.

Один процесс, один пользователь, локальный сервер только на 127.0.0.1 —
разделение на «сервер» и «клиент» здесь чисто внутреннее. Интерфейс
показывается одним из двух способов:

* Windows-сборка показывает окно WebView2, а при закрытии скрывает его в трее;
* автозапуск подключённого агента идёт в трей, ручной запуск показывает окно;
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


def _check_saved_sessions() -> dict[str, str]:
    """Read local cookies only; provider verification happens in a later scan."""
    from app.scanner.profiles import AUTH_COOKIES, cookie_auth_state
    states = {service: cookie_auth_state(service)["state"] for service in AUTH_COOKIES}
    log.info("Проверка сохранённых cookies: %s", ", ".join(f"{service}:{state}" for service, state in states.items()))
    return states


def main() -> None:
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(config.DATA_DIR / "agent.log", maxBytes=2_000_000,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    log.info("Каталог данных: %s (portable=%s)", config.DATA_DIR, config.PORTABLE)

    args = sys.argv[1:]
    # Use predictable fallback ports so a second launch can find the first
    # native window even when the development server owns 8756.
    for port in (8756, *range(8758, 8776)):
        candidate = f"http://{config.HOST}:{port}/app/"
        if not _port_available(port):
            if "--self-test" not in args and _focus_existing(candidate):
                return
            continue
        config.PORT = port
        break
    else:
        config.PORT = _free_local_port()
    url = f"http://{config.HOST}:{config.PORT}/app/"
    if config.PORT != 8756:
        log.info("Порт 8756 занят; агент откроется на %s", url)

    try:
        _check_saved_sessions()
    except Exception:
        log.exception("Не удалось проверить сохранённые cookies")

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    if not _wait_for_server(url):
        raise RuntimeError("Локальный сервер не поднялся за отведённое время")

    if "--self-test" in args:
        import urllib.request
        import webview.platforms.winforms

        from PIL import Image
        with Image.open(config.RESOURCE_DIR / "assets" / "airate.ico") as app_icon:
            app_icon.load()
            if not {(16, 16), (32, 32), (256, 256)}.issubset(app_icon.ico.sizes()):
                raise RuntimeError("В сборке отсутствуют нужные размеры иконки AIRate")

        for path in ("/api/meta", "/api/browser/status", "/app/"):
            with urllib.request.urlopen(f"http://{config.HOST}:{config.PORT}{path}", timeout=5) as response:
                if response.status != 200:
                    raise RuntimeError(f"Проверка {path} завершилась с HTTP {response.status}")
        from zoneinfo import ZoneInfo
        ZoneInfo("Europe/Moscow")
        if "--self-test-browser" in args:
            import asyncio

            from camoufox.async_api import AsyncCamoufox
            from app.scanner.browser_install import launch_resources

            async def check_browser() -> None:
                async with AsyncCamoufox(headless=True, os="windows", geoip=False,
                                        **launch_resources()) as browser:
                    page = await browser.new_page()
                    await page.goto("about:blank")
                    if page.url != "about:blank":
                        raise RuntimeError("Camoufox не открыл тестовую страницу")
                # The login path uses a visible persistent profile and GeoIP;
                # the disposable headless browser alone does not cover it.
                from app.scanner.browser import service_context
                async with service_context("self-test-login", headless=False) as context:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto("about:blank")
                    log.info("Проверка видимого окна входа прошла")

            # Reproduce a partial addon installation without touching the user's
            # cache. Both frozen launch paths must work with no manifest present.
            import tempfile
            from pathlib import Path
            from camoufox import addons
            original_addons_dir = addons.ADDONS_DIR
            try:
                with tempfile.TemporaryDirectory(prefix="airate-addon-probe-") as temporary:
                    addons.ADDONS_DIR = Path(temporary)
                    (addons.ADDONS_DIR / "UBO").mkdir()
                    asyncio.run(check_browser())
            finally:
                addons.ADDONS_DIR = original_addons_dir
        log.info("Проверка настольного приложения прошла")
        return

    import pystray
    from PIL import Image

    browser_mode = "--browser" in args
    from app import billing
    # Autostart stays in the tray only after this device has an account token.
    background = "--background" in args and bool(billing.token())
    window = None
    exiting = False
    if not browser_mode:
        import webview

        window = webview.create_window(
            "AIRate — агент", url, width=540, height=760,
            min_size=(430, 600), hidden=background, background_color="#1e1f1c",
        )

        def on_closing() -> bool:
            if exiting:
                return True
            window.hide()
            return False

        window.events.closing += on_closing
        window_control.set_focus(window.show)
        window_control.set_hide(window.hide)
        def show_login_if_needed():
            if not billing.token():
                window.show()
        window.events.loaded += show_login_if_needed
    elif not background:
        webbrowser.open(url)

    with Image.open(config.RESOURCE_DIR / "assets" / "airate.ico") as source:
        image = source.convert("RGBA")

    def open_agent(icon, item) -> None:
        if window is not None:
            window.show()
        else:
            webbrowser.open(url)

    def open_account(icon, item) -> None:
        if config.ACCOUNT_URL:
            def open_in_browser():
                import asyncio
                try:
                    webbrowser.open(asyncio.run(billing.browser_url()))
                except billing.BillingError as exc:
                    from app.control_agent import STATE
                    STATE["error"] = str(exc)
                    open_agent(icon, item)
            threading.Thread(target=open_in_browser, daemon=True).start()

    def quit_agent(icon, item) -> None:
        nonlocal exiting
        exiting = True
        icon.stop()
        if window is not None:
            window.destroy()

    import platform
    from app.db import repo

    device_label = [repo.get_setting("agent_display_name") or platform.node() or "Windows агент"]
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"Компьютер: {device_label[0]}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Открыть агент", open_agent, default=True),
        pystray.MenuItem("Личный кабинет", open_account,
                         enabled=lambda _: bool(config.ACCOUNT_URL)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выйти", quit_agent),
    )
    icon = pystray.Icon("AIRate", image, f"AIRate · {device_label[0]}"[:127], menu)
    def update_label(name: str) -> None:
        device_label[0] = name
        icon.title = f"AIRate · {name}"[:127]
        icon.update_menu()
    window_control.set_device_name_callback(update_label)
    if window is not None:
        # pystray allows a non-main thread on Windows; WebView2 needs main.
        threading.Thread(target=icon.run, daemon=True, name="agent-tray").start()
        webview.start()
        icon.stop()
    else:
        icon.run()


if __name__ == "__main__":
    main()
