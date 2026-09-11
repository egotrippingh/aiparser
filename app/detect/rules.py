"""Детерминированный слой детекции: работает всегда, бесплатно, без сети.

Три независимых признака: точное вхождение формы бренда, нечёткое совпадение
(опечатки/разное написание) и домен бренда в ссылках. Любой сработавший
признак — это `found` без обращения к LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from rapidfuzz import fuzz

from app.detect.brand import build_forms, normalize, normalize_host, same_site

# Совпадение короче этого — почти наверняка случайное (например, форма "мс"
# внутри "москва"). Отсекаем на уровне генератора признаков, а не постфактум.
_MIN_FORM_LEN = 3

MARKETPLACE_DOMAINS = ("market.yandex.ru", "ozon.ru", "wildberries.ru", "avito.ru")


@dataclass
class RuleVerdict:
    found: bool
    mention_types: list[str] = field(default_factory=list)
    evidence_quote: str | None = None
    matched_forms: list[str] = field(default_factory=list)


def _find_quote(original_text: str, normalized_text: str, form: str, radius: int = 60, idx: int | None = None) -> str:
    if idx is None:
        idx = normalized_text.find(form)
    if idx < 0:
        return ""
    # normalize() не меняет длину построчно 1:1 из-за схлопывания пробелов,
    # поэтому цитату берём щадяще — по пропорциональной позиции в оригинале,
    # этого достаточно для контекста в UI (это не юридическая выписка).
    ratio = len(original_text) / max(len(normalized_text), 1)
    start = max(0, int((idx - radius) * ratio))
    end = min(len(original_text), int((idx + len(form) + radius) * ratio))
    quote = original_text[start:end].strip()
    return ("…" if start > 0 else "") + quote + ("…" if end < len(original_text) else "")


def check_text(
    text: str,
    brand_name: str,
    aliases: list[str],
    *,
    fuzzy_threshold: int = 90,
    fuzzy: bool = True,
    whole_word: bool = False,
) -> RuleVerdict:
    """Ищет форму бренда в тексте.

    Для ответа ИИ — как раньше: вхождение подстроки плюс нечёткий проход
    (ловит опечатки и склейки). Для чужих веб-страниц — whole_word=True,
    fuzzy=False: живой прогон 11.09.2026 на бренде «Neighbors» нашёл его на
    страницах про «nearest neighbors» и приложение «Neighborbrite» — на целой
    странице нечёткое сравнение и подстрока цепляют похожие слова.
    """
    if not text:
        return RuleVerdict(found=False)

    forms = {f for f in build_forms(brand_name, aliases) if len(f) >= _MIN_FORM_LEN}
    norm_text = normalize(text)

    for form in sorted(forms, key=len, reverse=True):
        if whole_word:
            m = re.search(rf"(?<!\w){re.escape(form)}(?!\w)", norm_text)
            idx = m.start() if m else -1
        else:
            idx = norm_text.find(form)
        if idx >= 0:
            return RuleVerdict(
                found=True,
                mention_types=["text"],
                evidence_quote=_find_quote(text, norm_text, form, idx=idx),
                matched_forms=[form],
            )

    if not fuzzy:
        return RuleVerdict(found=False)

    # Нечёткий проход — только по достаточно длинным формам, иначе рапидфаз
    # находит совпадения там, где их нет (короткие строки почти всегда похожи
    # друг на друга процентов на 90).
    words = norm_text.split()
    windows = [" ".join(words[i : i + 3]) for i in range(len(words))]
    for form in sorted(forms, key=len, reverse=True):
        if len(form) < 5:
            continue
        for w in windows:
            if fuzz.partial_ratio(form, w) >= fuzzy_threshold:
                return RuleVerdict(
                    found=True,
                    mention_types=["text"],
                    evidence_quote=_find_quote(text, norm_text, w),
                    matched_forms=[form],
                )

    return RuleVerdict(found=False)


def check_links(sources: list[str], brand_domains: list[str]) -> RuleVerdict:
    if not sources or not brand_domains:
        return RuleVerdict(found=False)

    for url in sources:
        try:
            host = urlparse(url if "://" in url else f"//{url}").hostname or ""
        except ValueError:
            continue
        host = normalize_host(host)

        if any(same_site(host, d) for d in brand_domains):
            mtype = "marketplace" if any(m in host for m in MARKETPLACE_DOMAINS) else "link"
            return RuleVerdict(found=True, mention_types=[mtype], evidence_quote=url, matched_forms=[host])

    return RuleVerdict(found=False)


def check_marketplace_mention(sources: list[str], brand_name: str, aliases: list[str]) -> RuleVerdict:
    """Ссылка на маркетплейс, в анкоре/URL которой встречается форма бренда.

    Отдельный признак от check_links: тут домен НЕ бренда (это Маркет или
    Озон), а бренд ищется в самом URL — так ловятся карточки товаров вида
    market.yandex.ru/.../opttorg24-...
    """
    forms = {f for f in build_forms(brand_name, aliases) if len(f) >= _MIN_FORM_LEN}
    for url in sources:
        host = (urlparse(url if "://" in url else f"//{url}").hostname or "").lower()
        if not any(m in host for m in MARKETPLACE_DOMAINS):
            continue
        norm_url = normalize(url)
        for form in forms:
            if form in norm_url:
                return RuleVerdict(found=True, mention_types=["marketplace"], evidence_quote=url, matched_forms=[form])
    return RuleVerdict(found=False)


def check_cards(card_text: str, brand_name: str, aliases: list[str]) -> RuleVerdict:
    """Бренд в нетекстовых блоках ответа: карточки источников, товаров, организаций.

    Это тоже упоминание — ИИ показал бренд пользователю, — но не в словах
    ответа, поэтому тип свой: «card». Иначе бренд, который есть только в
    заголовке процитированной страницы, выглядел бы в статистике так же,
    как прямая рекомендация.
    """
    # Строго, как на чужих страницах: целым словом, без нечёткого сравнения.
    # Карточки — это сниппеты чужих сайтов; живая проверка 11.09.2026 дала
    # ложное «в карточке» на небрендовом запросе (цитата «VC.ru Лучшие
    # премиальные студии…», бренда там нет) — нечёткий проход зацепил
    # похожее слово.
    v = check_text(card_text, brand_name, aliases, fuzzy=False, whole_word=True)
    if not v.found:
        return v
    return RuleVerdict(found=True, mention_types=["card"], evidence_quote=v.evidence_quote,
                       matched_forms=v.matched_forms)


def evaluate(
    answer_text: str,
    sources: list[str],
    brand_name: str,
    aliases: list[str],
    brand_domains: list[str],
    *,
    card_text: str = "",
) -> RuleVerdict:
    """Сводит признаки: любой найденный — результат found, типы объединяются.

    `answer_text` — сам текст ответа, `card_text` — текст нетекстовых блоков
    (карточки), если адаптер умеет их отделять. Цитатой становится первое
    найденное по порядку: текст, ссылка, маркетплейс, карточка.
    """
    results = [
        check_text(answer_text, brand_name, aliases),
        check_links(sources, brand_domains),
        check_marketplace_mention(sources, brand_name, aliases),
        check_cards(card_text, brand_name, aliases),
    ]
    hits = [r for r in results if r.found]
    if not hits:
        return RuleVerdict(found=False)

    types: list[str] = []
    forms: list[str] = []
    quote = None
    for h in hits:
        types.extend(h.mention_types)
        forms.extend(h.matched_forms)
        quote = quote or h.evidence_quote

    seen = []
    for t in types:
        if t not in seen:
            seen.append(t)

    return RuleVerdict(found=True, mention_types=seen, evidence_quote=quote, matched_forms=forms)
