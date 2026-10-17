"""Shared verdict and prompt helpers; no desktop I/O imports."""
from dataclasses import dataclass, field
import json
import math


MENTION_TYPES = frozenset({"text", "link", "marketplace", "url", "card", "indirect", "source"})

@dataclass
class LLMVerdict:
    found: bool
    mention_types: list[str] = field(default_factory=list)
    # None means an old provider did not send an optional confidence.  It is
    # different from an explicit low-confidence 0.0.
    confidence: float | None = None
    quote: str = ""
    reasoning: str = ""
    model: str = ""
    error: str | None = None


def _build_prompt(
    brand_name: str, aliases: list[str], answer_text: str, sources: list[str], query: str | None = None,
    brand_clarification: str = "", domains: list[str] | None = None, *, text_only: bool = False,
    cards_text: str = "",
) -> str:
    forms = ", ".join([brand_name, *aliases]) if aliases else brand_name
    known_domains = ", ".join(domains or []) or "(не заданы)"
    src = "\n".join(f"- {s}" for s in sources[:50 if text_only else 10]) or "(источников нет)"
    # Вопрос передаём явно и помечаем: в брендовых запросах имя бренда стоит
    # в самом вопросе, и без пометки модель засчитывает его за упоминание.
    asked = f"Вопрос пользователя (НЕ считается упоминанием): {query}\n\n" if query else ""
    clarification = (f"Контекст идентичности бренда (используй, чтобы отличить его от тёзок и похожих компаний): "
                     f"{brand_clarification[:2000]}\n\n" if brand_clarification else "")
    return (
        asked +
        clarification +
        f"Бренд и его известные формы: {forms}\nДомены бренда: {known_domains}\n\n"
        f"Текст ответа ИИ:\n{answer_text[:60000 if text_only else 6000]}\n\n"
        f"Карточки, показанные внутри ответа:\n{cards_text[:60000]}\n\n"
        f"Ссылки-источники в ответе:\n{src}\n\n" +
        ("Карточки источников и товаров отделены от основного текста. Проверяй все сохранённые данные; скриншота нет."
         if text_only else "Проверь также приложенный скриншот на упоминания, которых нет в тексте.")
    )


def parse_verdict(raw: str | None, model: str) -> LLMVerdict | None:
    """Разбирает ответ модели. None — ответ не похож на наш JSON.

    Модели то и дело оборачивают JSON в ```json-блок или предваряют его
    словами, хотя формат задан явно: берём то, что между первой «{» и
    последней «}», вместо того чтобы терять проверку из-за обрамления.
    """
    s = (raw or "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        parsed = json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "found" not in parsed:
        return None
    if not isinstance(parsed["found"], bool):
        return None
    mention_types = parsed.get("mention_types", [])
    if not isinstance(mention_types, list) or any(not isinstance(kind, str) or kind not in MENTION_TYPES
                                                   for kind in mention_types):
        return None
    confidence = parsed.get("confidence")
    if "confidence" in parsed:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None
        if not 0 <= confidence <= 1:
            return None
        confidence = float(confidence)
        if not math.isfinite(confidence):
            return None
    quote = parsed.get("quote", "")
    reasoning = parsed.get("reasoning", "")
    if not isinstance(quote, str) or not isinstance(reasoning, str):
        return None
    return LLMVerdict(
        found=parsed["found"],
        mention_types=mention_types,
        confidence=confidence,
        quote=quote,
        reasoning=reasoning,
        model=model,
    )
