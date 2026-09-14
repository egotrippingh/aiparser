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


def for_llm(webp_bytes: bytes, *, max_width: int = 1000, chunk: int = 2500, max_parts: int = 3,
            quality: int = 70) -> list[bytes]:
    """Режет высокий снимок на куски для отправки модели.

    С 14.09.2026 снимок — это весь ответ целиком, а не один экран: у
    Perplexity это бывает 9000 пикселей в высоту. Одной картинкой такое
    отправлять бессмысленно — модель ужмёт её до нечитаемого текста. Режем на
    куски по высоте и шлём несколько картинок. Куски берём с начала, из
    середины и с конца: голова ответа, тело и блок источников — там, где чаще
    всего и видно бренд, которого нет в тексте.
    """
    img = Image.open(io.BytesIO(webp_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, int(img.height * max_width / img.width)), Image.LANCZOS)

    if img.height <= chunk:
        return [_webp(img, quality)]

    bounds = [(y, min(y + chunk, img.height)) for y in range(0, img.height, chunk)]
    if len(bounds) > max_parts:
        # Начало, середина, конец — вместо первых N подряд: иначе хвост с
        # источниками никогда бы не попадал модели на глаза.
        bounds = [bounds[0], bounds[len(bounds) // 2], bounds[-1]][:max_parts]
    return [_webp(img.crop((0, top, img.width, bottom)), quality) for top, bottom in bounds]


def _webp(img: "Image.Image", quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality)
    return buf.getvalue()


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
