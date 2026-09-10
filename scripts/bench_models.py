"""Сравнение LLM-моделей на реально собранных ответах.

Зачем: выбирать модель по описанию в прайс-листе — гадание. Здесь берутся
настоящие ответы из базы и прогоняются через несколько моделей, чтобы увидеть,
кто что находит и где они расходятся.

Выборка делится на две части:

* **контроль** — ответы, где правила НАШЛИ бренд. Модель обязана согласиться;
  если не согласилась, она слепая, и доверять ей находки нельзя.
* **основная** — ответы, где правила ничего не нашли. Здесь и проверяется,
  добавляет ли модель что-то сверх правил (косвенные упоминания) или просто
  выдумывает.

Использование:  python scripts/bench_models.py [сколько_основных] [сколько_контроля]
"""
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.db import repo  # noqa: E402
from app.detect import llm as L  # noqa: E402

MODELS = [
    "google/gemini-2.5-flash-lite",
    "google/gemini-3.1-flash-lite",
    "google/gemini-3-flash-preview",
]

N_MAIN = int(sys.argv[1]) if len(sys.argv) > 1 else 10
N_CONTROL = int(sys.argv[2]) if len(sys.argv) > 2 else 3
SCAN_ID = 15


def load_sample() -> tuple[dict, list[sqlite3.Row], list[sqlite3.Row]]:
    con = sqlite3.connect("data/aiparser.db")
    con.row_factory = sqlite3.Row
    proj = con.execute("SELECT * FROM projects WHERE id = 2").fetchone()

    def pick(status: str, n: int):
        return con.execute(
            "SELECT r.query_id, q.text AS qtext, r.answer_text, r.sources_json, r.screenshot_path "
            "FROM results r JOIN queries q ON q.id = r.query_id "
            "WHERE r.scan_id = ? AND r.status = ? AND LENGTH(r.answer_text) > 400 "
            "ORDER BY r.query_id LIMIT ?",
            (SCAN_ID, status, n),
        ).fetchall()

    return proj, pick("not_found", N_MAIN), pick("found", N_CONTROL)


async def run_model(model: str, proj, rows, key: str, with_shot: bool) -> dict:
    aliases = json.loads(proj["brand_aliases_json"])
    found, errors, elapsed = 0, 0, 0.0
    details = []

    for r in rows:
        shot = None
        if with_shot and r["screenshot_path"]:
            f = config.SCREENSHOTS_DIR / r["screenshot_path"]
            if f.exists():
                shot = f.read_bytes()

        t = time.monotonic()
        v = await L.evaluate(
            brand_name=proj["brand_name"], aliases=aliases,
            answer_text=r["answer_text"], sources=json.loads(r["sources_json"]),
            screenshot_bytes=shot, api_key=key, model=model,
        )
        elapsed += time.monotonic() - t

        if v.error:
            errors += 1
        elif v.found:
            found += 1
            details.append((r["qtext"], v.confidence, v.quote, v.reasoning))

    return {"found": found, "errors": errors, "sec": elapsed, "details": details}


async def main() -> None:
    repo.init_db()
    key, _ = L.load_credentials()
    if not key:
        print("ключ OpenRouter не задан"); return

    proj, main_rows, control_rows = load_sample()
    print(f"бренд: {proj['brand_name']} | алиасы: {json.loads(proj['brand_aliases_json'])}")
    print(f"выборка: {len(main_rows)} «не найдено» + {len(control_rows)} контрольных «найдено»\n")

    print("=" * 74)
    print("КОНТРОЛЬ — правила нашли бренд, модель обязана согласиться")
    print("=" * 74)
    for m in MODELS:
        res = await run_model(m, proj, control_rows, key, with_shot=False)
        verdict = "OK" if res["found"] == len(control_rows) else "ПРОПУСКИ"
        print(f"  {m:34} согласилась {res['found']}/{len(control_rows)}  {verdict}")

    print()
    print("=" * 74)
    print("ОСНОВНАЯ — правила ничего не нашли; что добавит модель")
    print("=" * 74)
    for m in MODELS:
        res = await run_model(m, proj, main_rows, key, with_shot=True)
        print(f"\n  {m}")
        print(f"    нашла сверх правил: {res['found']}/{len(main_rows)} | "
              f"ошибок: {res['errors']} | {res['sec']/max(len(main_rows),1):.1f}с на запрос")
        for q, conf, quote, why in res["details"][:4]:
            print(f"      • «{q[:46]}» ({conf:.2f})")
            print(f"        {(why or '')[:120]}")


asyncio.run(main())
