"""Слой LLM-детекции через OpenRouter.

Вызывается, когда правила ничего не нашли (или всегда, в зависимости от
llm_mode из настроек). Модель получает и текст, и скриншот — часть косвенных
упоминаний видна только на картинке (лого партнёра, товар в карусели).
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field

import httpx

from app import net, secrets_store
from app.db import repo

log = logging.getLogger("aiparser.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """Ты проверяешь, упоминается ли конкретный бренд в ответе ИИ-поисковика.
Упоминание засчитывается, даже если бренд не назван прямо: например, "обратитесь к
официальному дистрибьютору X" или узнаваемое косвенное описание компании.
Также считаются: ссылка на домен бренда, товар/карточка бренда на маркетплейсе,
упоминание бренда на скриншоте (лого, текст на картинке), которого нет в тексте ответа,
бренд в карточке внутри ответа (карточка организации, товара, источника) — тип "card".
НЕ засчитывай: упоминание похожих, но других компаний; общие термины отрасли;
сам вопрос пользователя (бренд мог прозвучать в вопросе — важно, назван ли он в ОТВЕТЕ).
Ответь СТРОГО валидным JSON без markdown-обрамления:
{"found": bool, "mention_types": ["text"|"link"|"marketplace"|"card"|"indirect"],
 "confidence": 0.0-1.0, "quote": "короткая цитата-доказательство или пусто",
 "reasoning": "одно предложение на русском"}"""


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
    timeout: float = 45.0,
    query: str | None = None,
) -> LLMVerdict:
    if not api_key:
        return LLMVerdict(found=False, error="Ключ OpenRouter не задан")

    content: list[dict] = [{"type": "text", "text": _build_prompt(brand_name, aliases, answer_text, sources, query)}]
    if screenshot_bytes:
        b64 = base64.b64encode(screenshot_bytes).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{b64}"}})

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": content},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    try:
        # Через net.proxied_client, а не голый httpx: системный прокси Windows
        # приезжает со схемой https:// для HTTP-прокси, и клиент по умолчанию
        # падает мгновенным ConnectError. Молча, под видом «OpenRouter
        # недоступен» — то есть LLM-детекция просто не работала бы.
        async with net.proxied_client(timeout=timeout) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://local.aiparser",
                    "X-Title": "AI Mentions Tracker",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        log.warning("OpenRouter HTTP %s: %s", exc.response.status_code, exc.response.text[:300])
        return LLMVerdict(found=False, model=model, error=f"OpenRouter вернул {exc.response.status_code}")
    except Exception as exc:
        # Имя класса обязательно: у ConnectError текст бывает пустым, и в логе
        # 09.09.2026 осталось бесполезное «OpenRouter недоступен: » — без
        # единой зацепки, что именно сломалось.
        reason = f"{type(exc).__name__}: {exc}".rstrip(": ")
        log.warning("OpenRouter недоступен: %s", reason)
        return LLMVerdict(found=False, model=model, error=reason)

    try:
        raw = data["choices"][0]["message"]["content"]
        parsed = json.loads(raw)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return LLMVerdict(found=False, model=model, error=f"Не удалось разобрать ответ модели: {exc}")

    return LLMVerdict(
        found=bool(parsed.get("found")),
        mention_types=list(parsed.get("mention_types") or []),
        confidence=float(parsed.get("confidence") or 0),
        quote=str(parsed.get("quote") or ""),
        reasoning=str(parsed.get("reasoning") or ""),
        model=model,
    )


def load_credentials() -> tuple[str, str]:
    """Ключ (расшифрованный) и модель из настроек — то, что вводится в UI в две строки."""
    key = secrets_store.unprotect(repo.get_setting("openrouter_api_key"))
    model = repo.get_setting("openrouter_model", "anthropic/claude-sonnet-5") or "anthropic/claude-sonnet-5"
    return key, model
