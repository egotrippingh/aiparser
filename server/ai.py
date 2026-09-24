"""Один серверный вызов OpenRouter на оплаченную проверку."""

from __future__ import annotations

import json

import httpx


class AIError(RuntimeError):
    pass


class OpenRouterAI:
    def __init__(self, api_key: str, model: str = "google/gemini-3.8-flash"):
        self.api_key = api_key
        self.model = model

    def analyze(self, system: str, content: list[dict]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 3000,
            "response_format": {"type": "json_object"},
        }
        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "X-Title": "AIParser"}, json=payload,
                )
                response.raise_for_status()
                raw = response.json()["choices"][0]["message"]["content"]
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
        return raw[start:end + 1]
