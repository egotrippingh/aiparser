"""Холостой прогон глубокой проверки по уже собранным ответам.

Ничего не пишет в базу — только показывает, что изменилось бы, если бы
глубокая проверка была включена во время скана. Нужен, чтобы оценить пользу
и точность до того, как включать её в рабочий прогон.

Использование:  python scripts/dryrun_deep.py <scan_id> [сколько]
"""
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detect import deep  # noqa: E402

SCAN_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 15
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 12
DEPTH = 3


async def main() -> None:
    con = sqlite3.connect("data/aiparser.db")
    con.row_factory = sqlite3.Row

    scan = con.execute("SELECT project_id FROM scans WHERE id = ?", (SCAN_ID,)).fetchone()
    proj = con.execute("SELECT * FROM projects WHERE id = ?", (scan["project_id"],)).fetchone()
    brand = proj["brand_name"]
    aliases = json.loads(proj["brand_aliases_json"])
    domains = json.loads(proj["brand_domains_json"])

    print(f"проект: {proj['name']} | бренд: {brand} | алиасы: {aliases or '—'}")
    print(f"домены: {domains}\n")

    rows = con.execute(
        "SELECT r.query_id, q.text, r.sources_json FROM results r "
        "JOIN queries q ON q.id = r.query_id "
        "WHERE r.scan_id = ? AND r.status = 'not_found' AND r.sources_json != '[]' "
        "ORDER BY r.query_id LIMIT ?",
        (SCAN_ID, LIMIT),
    ).fetchall()

    print(f"проверяю {len(rows)} ответов «не найдено», по {DEPTH} источника на каждый\n")

    hits = 0
    started = time.monotonic()
    for r in rows:
        sources = json.loads(r["sources_json"])
        t = time.monotonic()
        hit = await deep.check_sources(sources, brand, aliases, domains, depth=DEPTH)
        took = time.monotonic() - t

        if hit.found:
            hits += 1
            print(f"  [НАЙДЕНО] «{r['text'][:52]}» ({took:.1f}с)")
            print(f"            {hit.url}")
            print(f"            {(hit.quote or '')[:130]}")
        else:
            print(f"  [  нет  ] «{r['text'][:52]}» ({took:.1f}с)")

    total = time.monotonic() - started
    print(f"\nитого: {hits} из {len(rows)} перешли бы в «найдено»")
    print(f"время: {total:.0f}с на {len(rows)} проверок = {total/max(len(rows),1):.1f}с на запрос")


asyncio.run(main())
