"""Сведение вердиктов правил и LLM в одну запись результата.

Логика ровно как в плане: правила нашли — готово, LLM не спрашиваем зря.
Правила молчат — спрашиваем LLM (если включено и есть ключ) и доверяем ей
только выше порога уверенности. Расхождение помечается needs_review, чтобы
пользователь посмотрел эти строки в первую очередь, а не рылся во всех 120.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.detect.llm import LLMVerdict
from app.detect.rules import RuleVerdict


@dataclass
class MergedVerdict:
    status: str                        # found | not_found
    mention_types: list[str] = field(default_factory=list)
    confidence: float | None = None
    evidence_quote: str | None = None
    detected_by: str = "rules"         # rules | llm | both | none
    needs_review: bool = False
    llm_model: str | None = None


def merge(rule: RuleVerdict, llm: LLMVerdict | None, *, confidence_threshold: float) -> MergedVerdict:
    if rule.found and llm and llm.found:
        return MergedVerdict(
            status="found",
            mention_types=sorted(set(rule.mention_types) | set(llm.mention_types)),
            confidence=max(llm.confidence, 0.95),
            evidence_quote=rule.evidence_quote or llm.quote,
            detected_by="both",
            llm_model=llm.model,
        )

    if rule.found:
        return MergedVerdict(
            status="found",
            mention_types=rule.mention_types,
            confidence=0.95,
            evidence_quote=rule.evidence_quote,
            detected_by="rules",
        )

    if llm and llm.found and llm.confidence >= confidence_threshold:
        return MergedVerdict(
            status="found",
            mention_types=llm.mention_types or ["indirect"],
            confidence=llm.confidence,
            evidence_quote=llm.quote,
            detected_by="llm",
            # Правила не нашли ничего, а LLM нашла — это ровно тот случай,
            # где легче всего ошибиться (галлюцинация модели), поэтому
            # такие строки всегда на ручную проверку, даже выше порога.
            needs_review=True,
            llm_model=llm.model,
        )

    if llm and llm.found and llm.confidence < confidence_threshold:
        # LLM что-то заподозрила, но неуверенно — не считаем found, но
        # оставляем след для ручной проверки, а не молча теряем сигнал.
        return MergedVerdict(
            status="not_found",
            confidence=llm.confidence,
            evidence_quote=llm.quote,
            detected_by="llm",
            needs_review=True,
            llm_model=llm.model,
        )

    return MergedVerdict(status="not_found", detected_by="none" if not llm else "llm", llm_model=llm.model if llm else None)


def with_deep(result: MergedVerdict, url: str, quote: str | None) -> MergedVerdict:
    """Повышает вердикт до «найдено» по результату глубокой проверки источников.

    Это ровно тот случай, ради которого глубокая проверка и делалась: бренда
    нет в тексте ответа, но он есть на странице, которую этот ответ цитирует
    (клиент-оптовик, упомянутый как поставщик на сайте магазина-перекупщика).
    Тип упоминания — `source` («на сайте-источнике»; до 11.09.2026 был общий
    `indirect`, которым LLM помечает косвенные описания — это разные вещи), и
    в цитату кладём адрес страницы: без него пользователь не смог бы
    проверить, откуда взялось «найдено».

    Уверенность 0.9, а не 1.0: совпадение детерминированное, но связь
    «источник процитирован ⇒ бренд виден в выдаче» всё же слабее прямого
    упоминания в самом ответе.
    """
    return MergedVerdict(
        status="found",
        mention_types=sorted(set(result.mention_types) | {"source"}),
        confidence=0.9,
        evidence_quote=f"На сайте-источнике {url}: {quote or ''}".strip(),
        detected_by="deep",
        needs_review=result.needs_review,
        llm_model=result.llm_model,
    )


def should_call_llm(rule: RuleVerdict, llm_mode: str) -> bool:
    if llm_mode == "never":
        return False
    if llm_mode == "always":
        return True
    # "smart" (по умолчанию): не тратим вызов, если правила уже нашли прямое
    # совпадение по домену/тексту — экономия там, где LLM ничего не добавит.
    return not rule.found
