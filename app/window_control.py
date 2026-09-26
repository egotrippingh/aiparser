"""In-process bridge for bringing the desktop window to the front."""

from __future__ import annotations

from collections.abc import Callable

_focus: Callable[[], None] | None = None
_hide: Callable[[], None] | None = None
_device_name: Callable[[str], None] | None = None


def set_device_name_callback(callback: Callable[[str], None] | None) -> None:
    global _device_name
    _device_name = callback


def update_device_name(name: str) -> None:
    if _device_name:
        try:
            _device_name(name)
        except Exception:
            pass


def set_hide(callback: Callable[[], None] | None) -> None:
    global _hide
    _hide = callback


def hide() -> bool:
    if _hide is None:
        return False
    try:
        _hide()
        return True
    except Exception:
        return False


def set_focus(callback: Callable[[], None] | None) -> None:
    global _focus
    _focus = callback


def focus() -> bool:
    if _focus is None:
        return False
    try:
        _focus()
    except Exception:
        return False
    return True
