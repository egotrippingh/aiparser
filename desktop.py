"""Точка входа Windows-сборки с видимой ошибкой при сбое запуска."""

from __future__ import annotations

import ctypes
import os
import sys
import traceback
from pathlib import Path


if __name__ == "__main__":
    log_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AIParser"
    log_dir.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None or sys.stderr is None:
        stream = (log_dir / "desktop.log").open("a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
    try:
        from app.main import main

        main()
    except Exception:
        log_path = log_dir / "startup-error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        if "--self-test" not in sys.argv[1:]:
            ctypes.windll.user32.MessageBoxW(
                None,
                f"Не удалось запустить AI Mentions. Подробности: {log_path}",
                "AI Mentions",
                0x10,
            )
        sys.exit(1)
