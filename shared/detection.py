"""Shared verdict and prompt helpers; no desktop I/O imports."""
from dataclasses import dataclass, field
import json

@dataclass
class LLMVerdict:
    found: bool
    mention_types: list[str] = field(default_factory=list)
    confidence: float = 0.0
    quote: str = ""
    reasoning: str = ""
    model: str = ""
    error: str | None = None


def _build_prompt(
    brand_name: str, aliases: list[str], answer_text: str, sources: list[str], query: str | None = None,
    brand_clarification: str = "", *, text_only: bool = False,
) -> str:
    forms = ", ".join([brand_name, *aliases]) if aliases else brand_name
    src = "\n".join(f"- {s}" for s in sources[:50 if text_only else 10]) or "(источников нет)"
    # Вопрос передаём явно и помечаем: в брендовых запросах имя бренда стоит
    # в самом вопросе, и без пометки модель засчитывает его за упоминание.
    asked = f"Вопрос пользователя (НЕ считается упоминанием): {query}\n\n" if query else ""
    clarification = (f"Контекст идентичности бренда (используй, чтобы отличить его от тёзок и похожих компаний): "
                     f"{brand_clarification[:2000]}\n\n" if brand_clarification else "")
    return (
        asked +
        clarification +
        f"Бренд и его известные формы: {forms}\n\n"
        f"Текст ответа ИИ:\n{answer_text[:60000 if text_only else 6000]}\n\n"
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
    try:
        confidence = float(parsed.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return LLMVerdict(
        found=bool(parsed.get("found")),
        mention_types=[str(t) for t in (parsed.get("mention_types") or [])],
        confidence=confidence,
        quote=str(parsed.get("quote") or ""),
        reasoning=str(parsed.get("reasoning") or ""),
        model=model,
    )
