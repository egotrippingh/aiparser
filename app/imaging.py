"""Единая точка конвертации скриншотов.

Playwright умеет снимать скриншот только в PNG или JPEG — WebP среди
поддерживаемых типов нет. А WebP нужен и для компактного хранения на диске
(проект копится месяцами), и для отправки в LLM (там даже небольшая экономия
на размере запроса складывается за сотни вызовов). Конвертация делается один
раз здесь, сразу после снимка адаптером, — дальше по коду везде просто webp.
"""

from __future__ import annotations

import io

from PIL import Image


def to_webp(raw_bytes: bytes, *, quality: int = 78, max_width: int = 1600) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality)
    return buf.getvalue()
