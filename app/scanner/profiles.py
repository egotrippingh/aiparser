"""Статус входа в сервис — по cookies профиля, без запуска браузера.

Запускать Camoufox только чтобы узнать «залогинен ли я» слишком дорого: это
секунды ожидания, окно поверх экрана и конфликт за `parent.lock` с идущим
сканом. Вместо этого читаем `cookies.sqlite` профиля напрямую — мгновенно и
безопасно параллельно скану.

Сигнальные куки подобраны и проверены вживую 31.08.2026 на всех пяти реальных
профилях: у залогиненных они присутствуют, у чистого профиля их нет.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from app import config

log = logging.getLogger("aiparser.profiles")

# (домен, имя куки). Домен сверяется вхождением подстроки, потому что Firefox
# хранит host с ведущей точкой для *.domain (".yandex.ru") и без неё для
# конкретного хоста ("www.perplexity.ai").
AUTH_COOKIES: dict[str, list[tuple[str, str]]] = {
    "chatgpt": [("chatgpt.com", "__Secure-next-auth.session-token")],
    "perplexity": [("perplexity.ai", "__Secure-next-auth.session-token")],
    "alice": [("yandex.ru", "Session_id"), ("ya.ru", "Session_id")],
    "yandex_neuro": [("yandex.ru", "Session_id"), ("ya.ru", "Session_id")],
    "google_aio": [("google.com", "SID"), ("google.com", "__Secure-1PSID")],
}


def normalize_expiry(raw: int | float | None) -> int | None:
    """Приводит `moz_cookies.expiry` к unix-секундам.

    Документация Firefox говорит «секунды», но замер на реальных профилях
    31.08.2026 дал значения порядка 1.8e12 при текущем времени 1.79e9 — то
    есть миллисекунды. Полагаться на одну догадку про единицу нельзя (ошибка
    молча превратит живую сессию в «истекла»), поэтому определяем по порядку
    величины: всё, что на годы больше правдоподобного unix-времени, — это
    более мелкая единица.
    """
    if not raw:
        return None
    v = float(raw)
    if v > 1e17:      # наносекунды
        return int(v / 1e9)
    if v > 1e14:      # микросекунды
        return int(v / 1e6)
    if v > 1e11:      # миллисекунды
        return int(v / 1e3)
    return int(v)     # секунды


def _name_matches(actual: str, wanted: str) -> bool:
    """Совпадение имени куки с учётом дробления на части.

    NextAuth (на нём сделаны и ChatGPT, и Perplexity) режет сессионный JWT на
    куски `.0`, `.1`, когда тот перестаёт влезать в лимит cookie около 4 КБ.
    Живой случай 09.09.2026: у платного аккаунта ChatGPT токен раздулся и
    приехал именно кусками, а проверка на точное имя сочла это «вход не
    выполнен» — при том что пользователь был залогинен.
    """
    return actual == wanted or actual.startswith(wanted + ".")


def _read_cookies(profile: Path) -> list[tuple[str, str, int | None]]:
    """(host, name, expiry_sec) из cookies.sqlite. Пусто, если профиля/файла нет."""
    db = profile / "cookies.sqlite"
    if not db.exists():
        return []

    # Копируем во временный файл: при идущем скане браузер держит БД
    # заблокированной, и прямое чтение упало бы.
    tmp = Path(tempfile.gettempdir()) / f"aiparser_cookies_{profile.name}.sqlite"
    try:
        shutil.copy2(db, tmp)
        con = sqlite3.connect(tmp)
        try:
            rows = con.execute("SELECT host, name, expiry FROM moz_cookies").fetchall()
        finally:
            con.close()
        return [(h, n, normalize_expiry(e)) for h, n, e in rows]
    except Exception:
        log.info("Не удалось прочитать cookies профиля %s", profile.name, exc_info=True)
        return []
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def cookie_auth_state(service_id: str) -> dict:
    """Состояние сессии по cookies: ok | expired | none.

    `expires_at` — ближайшее истечение среди найденных сигнальных кук: именно
    оно определяет, когда сессия перестанет работать.
    """
    wanted = AUTH_COOKIES.get(service_id)
    if not wanted:
        return {"state": "unknown", "expires_at": None}

    profile = config.PROFILES_DIR / service_id
    if not profile.exists():
        return {"state": "none", "expires_at": None}

    cookies = _read_cookies(profile)
    if not cookies:
        return {"state": "none", "expires_at": None}

    now = int(time.time())
    live: list[int | None] = []
    seen_any = False

    for host, name, expiry in cookies:
        for want_host, want_name in wanted:
            if _name_matches(name, want_name) and want_host in host:
                seen_any = True
                # Сессионная кука (expiry пустой) живёт до закрытия браузера —
                # для персистентного профиля считаем её действующей.
                if expiry is None or expiry > now:
                    live.append(expiry)

    if not seen_any:
        return {"state": "none", "expires_at": None}
    if not live:
        return {"state": "expired", "expires_at": None}

    dated = [e for e in live if e]
    return {"state": "ok", "expires_at": min(dated) if dated else None}
