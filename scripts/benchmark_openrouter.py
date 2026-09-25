"""Small reproducible pricing/quality probe using synthetic brand mentions.

Reads the API key from stdin so it never appears in the command line or Git.
Prints aggregate usage/cost and verdicts, never the key or request bodies.
"""

from __future__ import annotations

import base64
import io
import json
import msvcrt
import statistics
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from app.detect.llm import _ARBITER_SYSTEM, _SYSTEM, _build_prompt
from server.ai import ARBITER_SYSTEM, PRIMARY_SYSTEM


MODELS = (
    "google/gemini-3.1-flash-lite",
    "google/gemini-2.5-flash",
    "google/gemini-3.8-flash",
)
CASES = (
    ("plain", True, "В ответе рекомендована клиника Альтодент.", []),
    ("domain", True, "Подробнее: https://altodent.example/price", []),
    ("product", True, "Подходящий товар: зубная паста Альтодент, 75 мл.", []),
    ("question_only", False, "Для поиска врача изучите независимые отзывы.", []),
    ("similar", False, "Рекомендована клиника Альтодентал.", []),
    ("no_mention", False, "Выберите стоматологию с лицензией и проверенными отзывами.", []),
)


def image_part() -> dict:
    image = Image.new("RGB", (640, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 35), "Shopping results", fill="black")
    draw.text((30, 110), "ALTODENT - toothpaste 75 ml", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=75)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": "data:image/webp;base64," + encoded}}


def long_image_parts() -> list[dict]:
    parts = []
    for index in range(3):
        image = Image.new("RGB", (1000, 2500), "white")
        draw = ImageDraw.Draw(image)
        for y in range(40, 2480, 55):
            draw.text((25, y), f"Result {index + 1}: example product and source card {y}", fill="black")
        if index == 1:
            draw.text((25, 1300), "ALTODENT toothpaste", fill="black")
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=70)
        parts.append({"type": "image_url", "image_url": {
            "url": "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")}})
    return parts


def call(client: httpx.Client, key: str, model: str, system: str, content: list[dict]) -> dict:
    started = time.monotonic()
    response = client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + key, "X-Title": "AIParser pricing probe"},
        json={"model": model, "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": content}],
              "temperature": 0, "max_tokens": 1200,
              "response_format": {"type": "json_object"},
              "usage": {"include": True}},
    )
    elapsed = round(time.monotonic() - started, 2)
    if response.status_code != 200:
        return {"error": response.status_code, "latency_s": elapsed}
    data = response.json()
    raw = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
    try:
        verdict = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        found = verdict.get("found")
    except (ValueError, TypeError):
        found = None
    usage = data.get("usage") or {}
    return {"found": found, "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "cost_usd": usage.get("cost"), "latency_s": elapsed,
            "finish_reason": data.get("choices", [{}])[0].get("finish_reason")}


def main() -> None:
    selected_server = "--selected-server" in sys.argv
    if selected_server:
        lines = (Path(__file__).resolve().parents[1] / "server" / ".env").read_text(encoding="utf-8").splitlines()
        key = next(line.split("=", 1)[1] for line in lines if line.startswith("OPENROUTER_API_KEY="))
    else:
        print("OpenRouter key: ", end="", flush=True)
        chars = []
        while (char := msvcrt.getwch()) not in ("\r", "\n"):
            chars.append(char)
        print(flush=True)
        key = "".join(chars)
    if not key.startswith("sk-or-v1-"):
        raise SystemExit("OpenRouter key required on stdin")
    results = []
    with httpx.Client(timeout=90, trust_env=True) as client:
        for model in ((MODELS[0],) if selected_server else MODELS):
            if "--long-only" in sys.argv:
                prompt = _build_prompt("Альтодент", ["Altodent"], "Ниже показаны товары.", [],
                                       "Какую пасту выбрать?")
                result = call(client, key, model, _SYSTEM,
                              [{"type": "text", "text": prompt}, *long_image_parts()])
                results.append({"model": model, "case": "three_tall_images", "expected": True, **result})
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
                continue
            for name, expected, answer, sources in CASES:
                prompt = _build_prompt("Альтодент", ["Altodent"], answer, sources,
                                       "Где лечить зубы у Альтодент?")
                result = call(client, key, model, PRIMARY_SYSTEM if selected_server else _SYSTEM,
                              [{"type": "text", "text": prompt}])
                results.append({"model": model, "case": name, "expected": expected, **result})
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
            prompt = _build_prompt("Альтодент", ["Altodent"],
                                   "Ниже показаны товары.", [], "Какую пасту выбрать?")
            result = call(client, key, model, PRIMARY_SYSTEM if selected_server else _SYSTEM,
                          [{"type": "text", "text": prompt}, image_part()])
            results.append({"model": model, "case": "image_product", "expected": True, **result})
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
        for model in (() if "--long-only" in sys.argv else
                      (MODELS[2],) if selected_server else MODELS):
            prompt = _build_prompt("Альтодент", ["Altodent"],
                                   "Рекомендована клиника Альтодентал.", [],
                                   "Где лечить зубы у Альтодент?")
            prompt += ("\n\nДомены бренда: altodent.example\n"
                       "Первая модель сказала found=true, цитата: Альтодентал."
                       " Правила точного совпадения бренд не нашли.")
            result = call(client, key, model, ARBITER_SYSTEM if selected_server else _ARBITER_SYSTEM,
                          [{"type": "text", "text": prompt}])
            results.append({"model": model, "case": "arbiter_false_positive",
                            "expected": False, **result})
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    print("SUMMARY")
    for model in MODELS:
        rows = [r for r in results if r["model"] == model]
        costs = [r["cost_usd"] for r in rows if isinstance(r.get("cost_usd"), (int, float))]
        correct = sum(r.get("found") == r["expected"] for r in rows)
        print(json.dumps({"model": model, "correct": correct, "total": len(rows),
                          "cost_usd_mean": statistics.mean(costs) if costs else None,
                          "cost_usd_max": max(costs) if costs else None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
