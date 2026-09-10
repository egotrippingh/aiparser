"""Юнит-тесты детерминированного слоя детекции — без браузера, секунды на прогон.

Покрывает ровно то, что перечислено в разделе «Проверка результата» плана:
прямое совпадение, транслит, косвенные совпадения через маркетплейс и
ложные срабатывания на похожем, но чужом бренде.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detect.brand import registrable_domain, same_site  # noqa: E402
from app.detect.rules import check_links, check_marketplace_mention, check_text, evaluate

BRAND = "Оптторг24"
ALIASES = ["opttorg24", "Опт Торг 24"]
DOMAINS = ["opttorg24.ru"]


def test_direct_mention_found():
    r = check_text("Рекомендуем Оптторг24 — крупный оптовый поставщик метизов.", BRAND, ALIASES)
    assert r.found
    assert "text" in r.mention_types
    assert "Оптторг24" in r.evidence_quote


def test_case_and_yo_insensitive():
    r = check_text("поставщик ОПТТОРГ24 работает по всей россии", BRAND, ALIASES)
    assert r.found


def test_translit_alias_found():
    r = check_text("see opttorg24.ru for wholesale fasteners", BRAND, ALIASES)
    assert r.found


def test_no_false_positive_on_unrelated_text():
    r = check_text("лучшие поставщики метизов — ТД Крепёж и Стройбаза", BRAND, ALIASES)
    assert not r.found


def test_similar_but_different_brand_not_matched():
    # "Оптторг" без "24" — намеренно другой бренд, не должен ложно сработать
    # на коротких формах ("опт", "торг" были бы отфильтрованы по длине).
    r = check_text("Оптторг Сервис предлагает доставку по Москве", BRAND, ALIASES)
    assert not r.found


def test_domain_link_found():
    r = check_links(["https://opttorg24.ru/catalog/metizy", "https://vc.ru/trade"], DOMAINS)
    assert r.found
    assert "link" in r.mention_types


def test_domain_link_absent():
    r = check_links(["https://krepezh-info.ru/postavshiki"], DOMAINS)
    assert not r.found


def test_domain_written_as_full_url_still_matches():
    """Реальный случай 09.09.2026: в настройках проекта лежал полный URL.

    Сравнение шло со строкой целиком, и ссылки на сайт клиента не
    засчитывались вообще — видимость занижалась молча.
    """
    r = check_links(["https://opttorg24.ru/catalog"], ["https://opttorg24.ru/"])
    assert r.found


def test_subdomain_counts_as_same_site():
    r = check_links(["https://shop.opttorg24.ru/item/1"], ["opttorg24.ru"])
    assert r.found


def test_lookalike_domain_does_not_match():
    """opttorg24.ru.evil.com — чужой сайт, как бы похоже он ни начинался."""
    r = check_links(["https://opttorg24.ru.evil.com/"], ["opttorg24.ru"])
    assert not r.found


def test_registrable_domain_handles_multi_part_tld():
    assert registrable_domain("shop.example.co.uk") == "example.co.uk"
    assert registrable_domain("example.ru") == "example.ru"
    assert same_site("www.example.co.uk", "example.co.uk")


def test_marketplace_indirect_mention():
    r = check_marketplace_mention(
        ["https://market.yandex.ru/product--krepezh-opttorg24/123456"], BRAND, ALIASES
    )
    assert r.found
    assert r.mention_types == ["marketplace"]


def test_marketplace_without_brand_in_url_not_matched():
    r = check_marketplace_mention(["https://market.yandex.ru/product--krepezh/999"], BRAND, ALIASES)
    assert not r.found


def test_evaluate_combines_text_and_links():
    v = evaluate(
        "Оптторг24 предлагает крепёж оптом.",
        ["https://opttorg24.ru/catalog"],
        BRAND, ALIASES, DOMAINS,
    )
    assert v.found
    assert set(v.mention_types) == {"text", "link"}


def test_evaluate_not_found():
    v = evaluate("Общий обзор рынка метизов без конкретных поставщиков.", [], BRAND, ALIASES, DOMAINS)
    assert not v.found


if __name__ == "__main__":
    import traceback

    tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
            passed += 1
        except AssertionError:
            print(f"FAIL {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
