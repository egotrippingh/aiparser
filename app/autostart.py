"""Per-user Windows logon startup for the installed one-folder agent."""

from __future__ import annotations

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "AI Mentions Agent"


def _command() -> str:
    return f'"{os.path.abspath(sys.executable)}" --background'


def autostart_enabled() -> bool:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
        return value == _command()
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        raise OSError("Автозапуск поддерживается только установленной Windows-сборкой")
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
