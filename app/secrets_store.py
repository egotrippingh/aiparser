"""Хранение API-ключа OpenRouter.

Ключ шифруется через Windows DPAPI и привязывается к учётной записи Windows.
Это осознанное ограничение: portable-папку можно унести на флешке, но ключ на
другом компьютере не расшифруется и его попросят ввести заново. Секрет не
должен путешествовать вместе с данными.

Если pywin32 недоступен (например, при запуске под другой ОС во время
разработки), откатываемся на обратимое кодирование и честно сообщаем об этом
через ``is_encrypted``.
"""

from __future__ import annotations

import base64
import os

try:
    import win32crypt  # type: ignore

    _HAS_DPAPI = True
except ImportError:  # pragma: no cover — только не-Windows окружение
    _HAS_DPAPI = False

_ENTROPY = b"AIParser.OpenRouterKey.v1"

ENV_KEY = "OPENROUTER_API_KEY"


def key_from_env() -> str:
    """Ключ из переменной окружения — для Docker.

    В контейнере нет DPAPI: ключ, сохранённый под Windows, не расшифруется, а
    введённый заново ляжет в базу почти открытым текстом. Переменная из .env
    избавляет от обоих вариантов. Ключ из базы, если он есть, главнее.
    """
    return os.environ.get(ENV_KEY, "").strip()


def is_encrypted() -> bool:
    return _HAS_DPAPI


def protect(plain: str) -> str:
    if not plain:
        return ""
    if _HAS_DPAPI:
        blob = win32crypt.CryptProtectData(plain.encode("utf-8"), "AIParser", _ENTROPY, None, None, 0)
        return "dpapi:" + base64.b64encode(blob).decode("ascii")
    return "plain:" + base64.b64encode(plain.encode("utf-8")).decode("ascii")


def unprotect(stored: str | None) -> str:
    if not stored:
        return ""
    scheme, _, payload = stored.partition(":")
    raw = base64.b64decode(payload)
    if scheme == "dpapi":
        if not _HAS_DPAPI:
            return ""
        try:
            _desc, data = win32crypt.CryptUnprotectData(raw, _ENTROPY, None, None, 0)
        except Exception:
            # Ключ шифровали под другой учёткой Windows — расшифровать нечем.
            return ""
        return data.decode("utf-8")
    return raw.decode("utf-8")


def mask(plain: str) -> str:
    """Показываем в интерфейсе хвост ключа, чтобы было видно, какой именно введён."""
    if not plain:
        return ""
    return "•" * 8 + plain[-4:] if len(plain) > 4 else "•" * len(plain)
