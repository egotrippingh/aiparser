"""Фильтр источников Алисы: служебные и рекламные ссылки не должны попадать в источники.

11.09.2026 первым «источником» каждого ответа записывался рекламный баннер
самой Алисы (360.yandex.ru/business/alice-business/?utm_source=alisa_ai…).
Настоящие источники на яндексовых доменах (например, Яндекс Карты) при этом
должны проходить — живой прогон 28.08.2026 показал их среди реальных ссылок.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scanner.adapters.alice import _is_chrome_link  # noqa: E402


def test_alice_promo_banner_is_not_a_source():
    assert _is_chrome_link(
        "https://360.yandex.ru/business/alice-business/?utm_source=alisa_ai&utm_medium=banner&utm_campaign=start070926"
    )
    assert _is_chrome_link("https://yandex.ru/promo/something?utm_source=alisa_ai")


def test_alice_own_pages_and_legal_are_not_sources():
    assert _is_chrome_link("https://alice.yandex.ru/prompthub")
    assert _is_chrome_link("https://yandex.ru/legal/rules/")


def test_real_sources_pass():
    for url in (
        "https://neighbors-expert.ru/partner/",
        "https://hh.ru/employer/4515579",
        "https://t.me/s/neighbors_expert_ru",
        "https://yandex.ru/maps/org/neighbors/91160696514/",
    ):
        assert not _is_chrome_link(url), url


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
