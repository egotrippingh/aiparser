"""Слой LLM-детекции через OpenRouter.

Вызывается, когда правила ничего не нашли (или всегда, в зависимости от
llm_mode из настроек). Модель получает и текст, и скриншот — часть косвенных
упоминаний видна только на картинке (лого партнёра, товар в карусели).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field

from app import billing, imaging

log = logging.getLogger("aiparser.llm")

DEFAULT_MODEL = "google/gemini-3.1-flash-lite"

# Значения по умолчанию для арбитра держим здесь, а не в app/api/settings.py:
# их читают и сканер, и перерешение сохранённых строк, а импорт слоя API из
# слоя детекции замкнул бы кольцо (API → сканер → детекция → API).
ARBITER_MODEL_DEFAULT = "google/gemini-3.8-flash"
ARBITER_DEFAULT = "on"

_SYSTEM = """Ты проверяешь, упоминается ли конкретный бренд в ответе ИИ-поисковика.
Упоминание засчитывается, даже если бренд не назван прямо: например, "обратитесь к
официальному дистрибьютору X" или узнаваемое косвенное описание компании.
Также считаются: ссылка на домен бренда, товар/карточка бренда на маркетплейсе,
упоминание бренда на скриншоте (лого, текст на картинке), которого нет в тексте ответа,
бренд в карточке внутри ответа (карточка организации, товара, источника) — тип "card".
НЕ засчитывай: упоминание похожих, но других компаний; общие термины отрасли;
сам вопрос пользователя (бренд мог прозвучать в вопросе — важно, назван ли он в ОТВЕТЕ).
Ответь СТРОГО валидным JSON без markdown-обрамления:
{"found": bool, "mention_types": ["text"|"link"|"marketplace"|"url"|"card"|"indirect"],
 "confidence": 0.0-1.0, "quote": "короткая цитата-доказательство или пусто",
 "reasoning": "одно предложение на русском"}"""


# Второй заход по спорным строкам. Отдельный промпт, а не тот же самый:
# первый вызов ищет упоминание, а этот — выносит окончательное решение вместо
# человека, поэтому требует прямого ответа и запрещает «возможно».
_ARBITER_SYSTEM = """Ты выносишь ОКОНЧАТЕЛЬНОЕ решение: упоминается ли бренд в ответе ИИ-поисковика.
Первая модель уже сказала «найдено», но правила дословного поиска бренд не нашли — то есть
прямого совпадения по названию или домену в тексте нет. Твоя задача — проверить это и решить
за человека: перепроверять твой ответ никто не будет.
Считается упоминанием: название бренда или его форма в тексте ответа; ссылка на домен бренда;
товар или карточка бренда (организация, товар, источник); бренд, видимый только на скриншоте;
однозначное косвенное указание именно на эту компанию («официальный дистрибьютор X»).
НЕ считается: похожие, но другие компании; отрасль и общие термины; бренд, прозвучавший только
в вопросе пользователя; догадка «наверное, имелась в виду эта компания».
Если доказательства нет — отвечай found=false. Сомнение трактуй как отсутствие упоминания.
Ответь СТРОГО валидным JSON без markdown-обрамления:
{"found": bool, "mention_types": ["text"|"link"|"marketplace"|"url"|"card"|"indirect"|"source"],
 "confidence": 0.0-1.0, "quote": "дословная цитата-доказательство или пусто",
 "reasoning": "одно предложение на русском: почему решил именно так"}"""


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
    brand_name: str, aliases: list[str], answer_text: str, sources: list[str], query: str | None = None
) -> str:
    forms = ", ".join([brand_name, *aliases]) if aliases else brand_name
    src = "\n".join(f"- {s}" for s in sources[:10]) or "(источников нет)"
    # Вопрос передаём явно и помечаем: в брендовых запросах имя бренда стоит
    # в самом вопросе, и без пометки модель засчитывает его за упоминание.
    asked = f"Вопрос пользователя (НЕ считается упоминанием): {query}\n\n" if query else ""
    return (
        asked +
        f"Бренд и его известные формы: {forms}\n\n"
        f"Текст ответа ИИ:\n{answer_text[:6000]}\n\n"
        f"Ссылки-источники в ответе:\n{src}\n\n"
        "Проверь также приложенный скриншот на упоминания, которых нет в тексте."
    )


async def evaluate(
    *,
    brand_name: str,
    aliases: list[str],
    answer_text: str,
    sources: list[str],
    screenshot_bytes: bytes | None,
    api_key: str,
    model: str,
    managed_check_id: str | None = None,
    timeout: float = 45.0,
    query: str | None = None,
) -> LLMVerdict:
    if not managed_check_id:
        return LLMVerdict(found=False, error="Серверный анализ недоступен")

    content: list[dict] = [{"type": "text", "text": _build_prompt(brand_name, aliases, answer_text, sources, query)}]
    content += _image_parts(screenshot_bytes)

    return await _ask_model(_SYSTEM, content, api_key=api_key, model=model,
                            timeout=timeout, managed_check_id=managed_check_id)


def _image_parts(screenshot_bytes: bytes | None) -> list[dict]:
    """Скриншот для модели: высокий режется на несколько картинок."""
    if not screenshot_bytes:
        return []
    try:
        parts = imaging.for_llm(screenshot_bytes)
    except Exception as exc:
        log.info("Не удалось подготовить скриншот для модели (%s) — шлю как есть", exc)
        parts = [screenshot_bytes]
    return [
        {"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{base64.b64encode(p).decode('ascii')}"}}
        for p in parts
    ]


async def arbitrate(
    *,
    brand_name: str,
    aliases: list[str],
    domains: list[str],
    answer_text: str,
    sources: list[str],
    screenshot_bytes: bytes | None,
    api_key: str,
    model: str,
    first_verdict: "LLMVerdict | None" = None,
    first_quote: str = "",
    timeout: float = 90.0,
    query: str | None = None,
    managed_check_id: str | None = None,
) -> LLMVerdict:
    """Окончательное решение по спорной строке — вместо ручной проверки.

    Спорная строка это та, где правила молчат, а первая модель сказала
    «найдено»: именно там она чаще всего выдумывает. Сюда идёт вторая, более
    сильная модель, ей показывают текст, источники, скриншот и вывод первой
    модели — и требуют однозначного ответа.
    """
    if not managed_check_id:
        return LLMVerdict(found=False, error="Серверный арбитр недоступен")

    said = first_quote or (first_verdict.quote if first_verdict else "")
    why = first_verdict.reasoning if first_verdict else ""
    doms = ", ".join(domains) if domains else "(не заданы)"
    text = (
        _build_prompt(brand_name, aliases, answer_text, sources, query)
        + f"\n\nДомены бренда: {doms}\n\n"
        "Первая модель сочла это упоминанием и сослалась на:\n"
        f"цитата: {said or '(цитаты не дала)'}\n"
        f"объяснение: {why or '(без объяснения)'}\n\n"
        "Проверь это. Правила дословного поиска бренда в тексте и ссылках ничего не нашли."
    )
    content: list[dict] = [{"type": "text", "text": text}]
    content += _image_parts(screenshot_bytes)

    return await _ask_model(_ARBITER_SYSTEM, content, api_key=api_key, model=model,
                            timeout=timeout, managed_check_id=managed_check_id,
                            managed_arbiter=True)


async def _ask_model(system: str, content: list[dict], *, api_key: str, model: str, timeout: float,
                     retry: bool = True, managed_check_id: str | None = None,
                     managed_arbiter: bool = False) -> LLMVerdict:
    if not managed_check_id:
        return LLMVerdict(found=False, model=model, error="Серверный анализ недоступен")
    try:
        result = (await billing.arbitrate(managed_check_id, system, content)
                  if managed_arbiter else await billing.analyze(managed_check_id, system, content))
        return parse_verdict(result["raw"], result["model"]) or LLMVerdict(
            found=False, model=model, error="Не удалось разобрать ответ серверной модели")
    except (billing.BillingError, KeyError) as exc:
        if retry:
            await asyncio.sleep(2)
            return await _ask_model(system, content, api_key=api_key, model=model,
                                    timeout=timeout, retry=False, managed_check_id=managed_check_id,
                                    managed_arbiter=managed_arbiter)
        return LLMVerdict(found=False, model=model, error=str(exc))


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
