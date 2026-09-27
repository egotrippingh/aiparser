"""Validate browser files before treating a cached download as installed."""

import json
import logging
from pathlib import Path
from threading import RLock

from camoufox import multiversion, pkgman

log = logging.getLogger("aiparser.browser.install")
_lock = RLock()


def complete_install(path: Path) -> bool:
    try:
        if not pkgman.Version.from_path(path).is_supported():
            return False
        resources = path / "Camoufox.app/Contents/Resources" if pkgman.OS_NAME == "mac" else path
        executable = resources / pkgman.LAUNCH_FILE[pkgman.OS_NAME]
        if not executable.is_file() or executable.stat().st_size == 0:
            return False
        properties = json.loads((resources / "properties.json").read_text(encoding="utf-8"))
        return bool(properties) and isinstance(properties, list) and all(
            isinstance(prop, dict) and "property" in prop and "type" in prop for prop in properties
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def available_browser() -> Path | None:
    """Prefer the selected version; incomplete newer downloads are never usable."""
    with _lock:
        active = multiversion.get_active_path()
        if active is not None and complete_install(active):
            return active
        for installed in multiversion.list_installed():
            if complete_install(installed.path):
                return installed.path
        return None


def browser_executable() -> str:
    with _lock:
        path = available_browser()
        if path is None:
            raise RuntimeError("Браузер не установлен или повреждён. Нажмите «Установить браузер» в агенте.")
        if multiversion.get_active_path() != path:
            multiversion.set_active(path.relative_to(pkgman.INSTALL_DIR).as_posix())
            log.warning("Switched incomplete browser installation to %s", path)
        executable = pkgman.launch_path(path)
        log.info("Validated browser executable: %s", executable)
        return executable


def install_browser() -> None:
    if available_browser() is None:
        # A version.json alone makes upstream fetch skip a broken installation.
        pkgman.CamoufoxFetcher().install(replace=True)
    browser_executable()
