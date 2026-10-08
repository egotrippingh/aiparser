"""Платный клиент получает вердикт без локального ключа OpenRouter."""

import asyncio

from app import billing
from app.detect import llm


def test_managed_llm_uses_reserved_check(monkeypatch):
    received = []

    async def analyze(check_id, system, content):
        received.append((check_id, system, content))
        return {"model": "google/gemini-3.8-flash",
                "raw": '{"found": true, "mention_types": ["card"], "confidence": 0.95, "quote": "товар"}'}

    monkeypatch.setattr(billing, "analyze", analyze)
    verdict = asyncio.run(llm.evaluate(
        brand_name="Brand", aliases=[], answer_text="Товар Brand", sources=[],
        screenshot_bytes=None, api_key="", model="google/gemini-3.8-flash",
        query="Где купить?", managed_check_id="run:1:chatgpt",
    ))
    assert verdict.found and verdict.mention_types == ["card"]
    assert received[0][0] == "run:1:chatgpt"
    assert "Brand" in received[0][2][0]["text"]
