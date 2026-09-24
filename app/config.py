"""Пути приложения и определение portable-режима.

Программа рассчитана на запуск из любой папки, в том числе с флешки. Данные
кладём рядом с исполняемым файлом, но только если туда действительно можно
писать: если архив распаковали, например, в Program Files, прав на запись не
будет и мы уходим в %LOCALAPPDATA%.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "AIParser"


def _base_dir() -> Path:
    """Папка, рядом с которой лежит приложение.

    В сборке PyInstaller sys.frozen выставлен, и точкой отсчёта служит папка с
    exe, а не временный каталог распаковки. В режиме разработки — корень репы.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".wtest", delete=True):
            return True
    except OSError:
        return False


BASE_DIR = _base_dir()
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))

_portable_data = BASE_DIR / "data"
PORTABLE = _is_writable(_portable_data)

if PORTABLE:
    DATA_DIR = _portable_data
else:
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
    DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "aiparser.db"
PROFILES_DIR = DATA_DIR / "profiles"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
DEBUG_DIR = DATA_DIR / "debug"
EXPORTS_DIR = DATA_DIR / "exports"

# Camoufox скачивается при первом запуске в пользовательский кэш Windows.
# Профили и скриншоты остаются в DATA_DIR, отдельно от файлов сборки.
WEB_DIR = RESOURCE_DIR / "web"

# Сервер поднимается только на localhost и только для окна WebView.
HOST = "127.0.0.1"
PORT = 8756

# Адрес только для выпуска, подключённого к платному серверу. Локальный API
# остаётся на 127.0.0.1; наружу идут лишь запросы авторизации и биллинга.
_account_url_file = BASE_DIR / "account-url.txt"
ACCOUNT_URL = (os.environ.get("AIPARSER_ACCOUNT_URL") or
               (_account_url_file.read_text(encoding="utf-8-sig").strip()
                if _account_url_file.exists() else "")).rstrip("/")
if ACCOUNT_URL and not (ACCOUNT_URL.startswith("https://") or
                        ACCOUNT_URL.startswith("http://127.0.0.1:") or
                        ACCOUNT_URL.startswith("http://localhost:")):
    raise RuntimeError("AIPARSER_ACCOUNT_URL должен использовать HTTPS")

for _d in (PROFILES_DIR, SCREENSHOTS_DIR, DEBUG_DIR, EXPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def profile_dir(service_id: str) -> Path:
    """Профиль браузера на сервис, а не на проект: аккаунт ChatGPT один на всех."""
    p = PROFILES_DIR / service_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def screenshot_dir(project_id: int, scan_date: str) -> Path:
    p = SCREENSHOTS_DIR / str(project_id) / scan_date
    p.mkdir(parents=True, exist_ok=True)
    return p
