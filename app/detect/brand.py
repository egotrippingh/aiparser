"""Формы бренда: из имени и алиасов проекта строит словарь для поиска.

Один и тот же бренд в ответах ИИ встречается как угодно: с большой буквы, в
транслите, с опечаткой, в косвенном падеже, слитно с доменной зоной. Здесь
собран генератор форм, а не сам поиск — поиск в rules.py.
"""

from __future__ import annotations

import re

_translit_ru_en = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})

_translit_en_ru = {
    "shch": "щ", "yo": "ё", "zh": "ж", "kh": "х", "ts": "ц", "ch": "ч",
    "sh": "ш", "yu": "ю", "ya": "я",
    "a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "e": "е", "z": "з",
    "i": "и", "y": "й", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о",
    "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "f": "ф", "h": "х",
    "c": "к",
}


def _translit_to_ru(latin: str) -> str:
    s = latin.lower()
    out, i = [], 0
    keys = sorted(_translit_en_ru, key=len, reverse=True)
    while i < len(s):
        for k in keys:
            if s.startswith(k, i):
                out.append(_translit_en_ru[k])
                i += len(k)
                break
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def normalize(text: str) -> str:
    """Нижний регистр, ё→е, схлопывание пробелов и пунктуации вокруг слов."""
    t = text.lower().replace("ё", "е")
    t = re.sub(r"[‐-―]", "-", t)          # разные виды тире → дефис
    t = re.sub(r"[^\w\s-]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _morph_forms(word: str) -> set[str]:
    """Падежные формы русского слова через pymorphy3, если словарь доступен."""
    try:
        import pymorphy3

        morph = pymorphy3.MorphAnalyzer(lang="ru")
    except Exception:
        return set()

    forms: set[str] = set()
    try:
        parsed = morph.parse(word)[0]
        for case in ("nomn", "gent", "datv", "accs", "ablt", "loct"):
            infl = parsed.inflect({case})
            if infl:
                forms.add(infl.word)
    except Exception:
        pass
    return forms


def build_forms(brand_name: str, aliases: list[str] | None = None) -> set[str]:
    """Полный набор нормализованных форм бренда для точного и нечёткого поиска."""
    names = [brand_name, *(aliases or [])]
    forms: set[str] = set()

    for name in names:
        name = name.strip()
        if not name:
            continue
        n = normalize(name)
        forms.add(n)
        forms.add(n.replace(" ", ""))
        forms.add(n.replace(" ", "-"))
        forms.add(n.replace("-", " "))
        forms.add(n.replace("-", ""))

        is_latin = bool(re.fullmatch(r"[a-z0-9\s-]+", n))
        if is_latin:
            forms.add(_translit_to_ru(n))
        else:
            forms.add(n.translate(_translit_ru_en))
            # Падежные формы строим только для однословного имени. Для
            # многословного (например, «Опт Торг 24») инфлекция каждого
            # слова по отдельности плодит общесловарные формы — "опт",
            # "торга", "торгом" — которые как самостоятельные подстроки
            # ловят случайный текст ("оптторг сервис", "закупка оптом").
            # Такую цену за расширенный охват платить не стоит: он того
            # не покрывает, а ложные срабатывания подрывают доверие к
            # автоматической метке found.
            words = n.split()
            if len(words) == 1 and len(words[0]) > 3:
                forms |= {normalize(f) for f in _morph_forms(words[0])}

    return {f for f in forms if f}


# Домены второго уровня, где регистрируемая часть — три метки, а не две
# (site.co.uk, shop.com.br). Список короткий намеренно: инструмент про
# российский рынок, а тащить ради полноты весь Public Suffix List и его
# обновления в portable-сборку не стоит.
_MULTI_TLD = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.br", "com.au", "co.jp",
    "com.tr", "com.ua", "co.il", "com.cn", "com.mx",
})


def normalize_host(value: str) -> str:
    """Приводит что угодно похожее на адрес к голому хосту.

    Пользователи вводят домен как придётся: `https://neighbors-expert.ru/`,
    `www.site.ru`, `site.ru/catalog`. Именно так и случилось в реальном
    проекте 09.09.2026 — в настройках лежал полный URL со схемой и слэшем, а
    сравнение шло как со строкой, из-за чего ссылки на сайт клиента вообще
    не засчитывались. Разбираем терпимо, а не требуем идеального ввода.
    """
    d = value.strip().lower()
    if "://" in d:
        d = d.split("://", 1)[1]
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if "@" in d:                      # user@host из почты
        d = d.rsplit("@", 1)[1]
    d = d.split(":")[0]               # порт
    return d.removeprefix("www.").strip(".")


def registrable_domain(value: str) -> str:
    """Регистрируемая часть: shop.opttorg24.ru → opttorg24.ru."""
    host = normalize_host(value)
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if ".".join(parts[-2:]) in _MULTI_TLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_site(host: str, brand_domain: str) -> bool:
    """Совпадают ли сайты с точностью до поддомена.

    `shop.opttorg24.ru` — это тот же сайт, что и `opttorg24.ru`: карточка
    товара на поддомене магазина клиента должна засчитываться как упоминание.
    """
    a, b = registrable_domain(host), registrable_domain(brand_domain)
    return bool(a) and a == b


def domain_root(domain: str) -> str:
    """Первая метка домена. Оставлено для мест, где нужен именно короткий ключ."""
    return normalize_host(domain).split(".")[0]
