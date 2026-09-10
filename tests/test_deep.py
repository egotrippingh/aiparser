"""Тесты глубокой проверки источников (без сети — только чистая логика).

Сетевую часть тестировать здесь нечем и незачем: она проверяется живым
прогоном на реальных страницах. Здесь — отбор источников и извлечение текста,
то есть места, где легко тихо ошибиться и получить ложное «найдено».
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detect.deep import html_to_text, pick_sources  # noqa: E402
from app.detect.merge import MergedVerdict, with_deep  # noqa: E402

BRAND_DOMAINS = ["opttorg24.ru"]


# --------------------------------------------------------------------------
# извлечение текста
# --------------------------------------------------------------------------

def test_tags_stripped():
    assert html_to_text("<p>Метизы <b>оптом</b></p>") == "Метизы оптом"


def test_scripts_and_styles_dropped():
    """Строки внутри JS не должны попадать в «видимый текст».

    Иначе имя бренда, случайно оказавшееся в аналитике или конфиге на
    странице, дало бы ложное «найдено».
    """
    html = "<div>Каталог</div><script>var brand='Оптторг24';</script><style>.a{content:'Оптторг24'}</style>"
    text = html_to_text(html)
    assert "Каталог" in text
    assert "Оптторг24" not in text


def test_whitespace_collapsed():
    assert html_to_text("<p>а</p>\n\n   <p>б</p>") == "а б"


# --------------------------------------------------------------------------
# отбор источников
# --------------------------------------------------------------------------

def test_own_domain_skipped():
    """Ссылка на сайт клиента уже поймана правилами — открывать её незачем."""
    got = pick_sources(["https://opttorg24.ru/catalog", "https://shop.ru/a"], BRAND_DOMAINS, depth=3)
    assert got == ["https://shop.ru/a"]


def test_depth_limits_count():
    urls = [f"https://shop{i}.ru/a" for i in range(10)]
    assert len(pick_sources(urls, BRAND_DOMAINS, depth=3)) == 3


def test_one_page_per_domain():
    """Две страницы одного магазина дадут один и тот же ответ — хватит одной."""
    got = pick_sources(
        ["https://shop.ru/a", "https://shop.ru/b", "https://other.ru/c"], BRAND_DOMAINS, depth=5
    )
    assert got == ["https://shop.ru/a", "https://other.ru/c"]


def test_www_and_bare_domain_are_same_site():
    got = pick_sources(["https://www.shop.ru/a", "https://shop.ru/b"], BRAND_DOMAINS, depth=5)
    assert len(got) == 1


def test_garbage_urls_skipped_without_crash():
    got = pick_sources(["не ссылка", "", "https://shop.ru/a"], BRAND_DOMAINS, depth=3)
    assert got == ["https://shop.ru/a"]


def test_zero_depth_returns_nothing():
    assert pick_sources(["https://shop.ru/a"], BRAND_DOMAINS, depth=0) == []


# --------------------------------------------------------------------------
# применение вердикта
# --------------------------------------------------------------------------

def test_with_deep_upgrades_to_found():
    before = MergedVerdict(status="not_found", detected_by="none")
    after = with_deep(before, "https://shop.ru/postavshiki", "…поставщик Оптторг24…")
    assert after.status == "found"
    assert "indirect" in after.mention_types
    assert after.detected_by == "deep"
    # Адрес страницы обязан быть в цитате: иначе «найдено» непроверяемо.
    assert "shop.ru/postavshiki" in (after.evidence_quote or "")


def test_with_deep_keeps_existing_mention_types():
    before = MergedVerdict(status="not_found", mention_types=["link"], detected_by="rules")
    after = with_deep(before, "https://shop.ru/a", None)
    assert set(after.mention_types) == {"link", "indirect"}


def test_with_deep_confidence_below_direct_match():
    after = with_deep(MergedVerdict(status="not_found"), "https://shop.ru/a", "цитата")
    assert 0.5 < after.confidence < 0.95, "косвенное упоминание не должно весить как прямое"


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
