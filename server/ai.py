"""Server-owned OpenRouter models and prompts. Client input never selects a model."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx


class AIError(RuntimeError):
    pass


PRIMARY_SYSTEM = """Проверь, упоминается ли заданный бренд именно в ответе ИИ-поисковика.
Считай название и его формы, домен, ссылку, товар или карточку бренда, однозначное
косвенное упоминание, а также текст или логотип на приложенном скриншоте.
Не считай бренд только в вопросе, похожие компании и догадки без доказательств.
Верни только JSON: {"found": bool, "mention_types": ["text"|"link"|"marketplace"|"url"|"card"|"indirect"],
"confidence": 0.0, "quote": "короткое доказательство или пусто", "reasoning": "одно предложение"}."""

ARBITER_SYSTEM = """Ты окончательный арбитр спорного упоминания бренда. Первая модель
сочла упоминание найденным, но правила точного поиска его не подтвердили.
Проверяй ответ, ссылки, товарные карточки и скриншот. Не считай похожий бренд,
бренд только в вопросе или предположение. При сомнении верни found=false.
Верни только JSON: {"found": bool, "mention_types": ["text"|"link"|"marketplace"|"url"|"card"|"indirect"|"source"],
"confidence": 0.0, "quote": "дословное доказательство или пусто", "reasoning": "одно предложение"}."""


@dataclass(frozen=True)
class AIResult:
    raw: str
    model: str
    usage: dict


class OpenRouterAI:
    def __init__(self, api_key: str, model: str | None = None, arbiter_model: str | None = None):
        self.api_key = api_key
        self.model = model or os.environ.get("OPENROUTER_PRIMARY_MODEL", "google/gemini-3.1-flash-lite")
        self.arbiter_model = arbiter_model or os.environ.get("OPENROUTER_ARBITER_MODEL", "google/gemini-3.8-flash")

    def analyze(self, _system: str, content: list[dict]) -> AIResult:
        return self._call(self.model, PRIMARY_SYSTEM, content)

    def arbitrate(self, _system: str, content: list[dict]) -> AIResult:
        return self._call(self.arbiter_model, ARBITER_SYSTEM, content)

    def _call(self, model: str, system: str, content: list[dict]) -> AIResult:
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 3000,
            "response_format": {"type": "json_object"},
            "usage": {"include": True},
        }
        try:
            with httpx.Client(timeout=90) as client:
                response = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "X-Title": "AIParser"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                raw = data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise AIError("Модель временно недоступна") from exc
        if not isinstance(raw, str):
            raise AIError("Модель вернула пустой ответ")
        start, end = raw.find("{"), raw.rfind("}")
        try:
            verdict = json.loads(raw[start:end + 1])
        except (ValueError, TypeError) as exc:
            raise AIError("Не удалось разобрать ответ модели") from exc
        if not isinstance(verdict, dict) or not isinstance(verdict.get("found"), bool):
            raise AIError("Модель вернула неполный ответ")
        return AIResult(raw[start:end + 1], model, data.get("usage") or {})
