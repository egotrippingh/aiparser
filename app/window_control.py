"""In-process bridge for bringing the desktop window to the front."""

from __future__ import annotations

from collections.abc import Callable

_focus: Callable[[], None] | None = None


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
