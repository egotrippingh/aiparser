"""Тесты определения статуса входа по cookies и профилей скорости.

Единица `moz_cookies.expiry` — главный риск этого модуля: документация Firefox
говорит «секунды», а реальные профили 31.08.2026 отдали значения порядка 1.8e12
(миллисекунды). Ошибка в единице молча превратила бы живую сессию в «истекла»,
поэтому нормализация покрыта тестами по всем правдоподобным вариантам.
"""

import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.scanner import humanize  # noqa: E402
from app.scanner.profiles import cookie_auth_state, normalize_expiry  # noqa: E402

NOW = int(time.time())


# --------------------------------------------------------------------------
# нормализация времени истечения
# --------------------------------------------------------------------------

def test_expiry_seconds_unchanged():
    assert normalize_expiry(NOW) == NOW


def test_expiry_milliseconds_converted():
    got = normalize_expiry(NOW * 1_000)
    assert got is not None and abs(got - NOW) <= 1


def test_expiry_microseconds_converted():
    got = normalize_expiry(NOW * 1_000_000)
    assert got is not None and abs(got - NOW) <= 1


def test_expiry_nanoseconds_converted():
    got = normalize_expiry(NOW * 1_000_000_000)
    assert got is not None and abs(got - NOW) <= 1


def test_expiry_zero_and_none_are_sessionwide():
    # Кука без срока — сессионная; для персистентного профиля это не «истекла».
    assert normalize_expiry(0) is None
    assert normalize_expiry(None) is None


def test_real_profile_value_reads_as_future():
    """Значение из живого профиля должно распознаться как будущее, а не 59000-й год."""
    raw = 1_795_933_070_000          # снято с реального профиля chatgpt
    got = normalize_expiry(raw)
    assert got is not None
    assert got > NOW, "живая кука не должна выглядеть истёкшей"
    assert got < NOW + 400 * 86400, "и не должна улетать на столетия вперёд"


# --------------------------------------------------------------------------
# состояние сессии по cookies
# --------------------------------------------------------------------------

def _make_profile(service: str, cookies: list[tuple[str, str, int]]) -> Path:
    """Создаёт временный профиль с cookies.sqlite в формате Firefox."""
    root = Path(tempfile.mkdtemp(prefix="aiparser_test_profiles_"))
    prof = root / service
    prof.mkdir(parents=True)
    con = sqlite3.connect(prof / "cookies.sqlite")
    con.execute("CREATE TABLE moz_cookies (host TEXT, name TEXT, expiry INTEGER)")
    con.executemany("INSERT INTO moz_cookies VALUES (?,?,?)", cookies)
    con.commit()
    con.close()
    return root


def _with_profiles_dir(root: Path):
    config.PROFILES_DIR = root


def test_state_ok_for_live_session():
    root = _make_profile("chatgpt", [(".chatgpt.com", "__Secure-next-auth.session-token", (NOW + 86400) * 1000)])
    _with_profiles_dir(root)
    assert cookie_auth_state("chatgpt")["state"] == "ok"


def test_state_expired_when_cookie_is_old():
    root = _make_profile("chatgpt", [(".chatgpt.com", "__Secure-next-auth.session-token", (NOW - 86400) * 1000)])
    _with_profiles_dir(root)
    assert cookie_auth_state("chatgpt")["state"] == "expired"


def test_state_none_without_signal_cookie():
    # Куки есть, но не те — сессии нет.
    root = _make_profile("chatgpt", [(".chatgpt.com", "_ga", (NOW + 86400) * 1000)])
    _with_profiles_dir(root)
    assert cookie_auth_state("chatgpt")["state"] == "none"


def test_state_none_for_missing_profile():
    root = _make_profile("chatgpt", [])
    _with_profiles_dir(root)
    assert cookie_auth_state("alice")["state"] == "none"


def test_yandex_domain_matched_by_substring():
    """Firefox пишет host с ведущей точкой — сверка должна это переживать."""
    root = _make_profile("alice", [(".yandex.ru", "Session_id", (NOW + 86400) * 1000)])
    _with_profiles_dir(root)
    assert cookie_auth_state("alice")["state"] == "ok"


def test_chunked_nextauth_cookie_counts_as_logged_in():
    """Платный ChatGPT дробит сессионный JWT на .0/.1 — это всё ещё вход.

    Регрессия 09.09.2026: проверка на точное имя куки показывала «вход не
    выполнен» у реально залогиненного платного аккаунта, потому что токен
    перестал влезать в 4 КБ и NextAuth разрезал его на части.
    """
    root = _make_profile("chatgpt", [
        (".chatgpt.com", "__Secure-next-auth.session-token.0", (NOW + 86400) * 1000),
        (".chatgpt.com", "__Secure-next-auth.session-token.1", (NOW + 86400) * 1000),
    ])
    _with_profiles_dir(root)
    assert cookie_auth_state("chatgpt")["state"] == "ok"


def test_chunked_cookie_does_not_match_foreign_name():
    """Префиксное совпадение не должно ловить чужую куку с похожим началом."""
    root = _make_profile("chatgpt", [
        (".chatgpt.com", "__Secure-next-auth.session-token-decoy", (NOW + 86400) * 1000),
    ])
    _with_profiles_dir(root)
    assert cookie_auth_state("chatgpt")["state"] == "none"


def test_unknown_service_is_unknown_not_crash():
    root = _make_profile("chatgpt", [])
    _with_profiles_dir(root)
    assert cookie_auth_state("нет такого сервиса")["state"] == "unknown"


# --------------------------------------------------------------------------
# профили скорости
# --------------------------------------------------------------------------

def test_speed_profiles_are_ordered_from_slow_to_fast():
    careful, balanced, fast = (humanize.PROFILES[k] for k in ("careful", "balanced", "fast"))
    assert careful["delay_max_sec"] > balanced["delay_max_sec"] > fast["delay_max_sec"]
    assert careful["typing"] > balanced["typing"] > fast["typing"]


def test_fast_profile_disables_long_breaks():
    # break_every_n == 0 выключает длинные перерывы в between_queries.
    assert humanize.PROFILES["fast"]["break_every_n"] == 0


def test_unknown_profile_falls_back_to_default():
    assert humanize.profile("чепуха") == humanize.PROFILES[humanize.DEFAULT_PROFILE]
    assert humanize.profile(None) == humanize.PROFILES[humanize.DEFAULT_PROFILE]


if __name__ == "__main__":
    import traceback

    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
            passed += 1
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
