"""Досканирование: что за дату уже проверено и что осталось.

Готовое считается по ВСЕМ сканам даты, а не только по последнему: прерванный
утренний скан плюс отдельный прогон одной Алисы днём — досканировать нужно
только то, чего нет ни в одном из них. Браузер не нужен: результаты пишутся
в базу напрямую.
"""

import asyncio
import sys
import tempfile
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db = Path(tempfile.gettempdir()) / "aiparser_test_scan_plan.db"
_tmp_db.unlink(missing_ok=True)

from app import config  # noqa: E402

config.DB_PATH = _tmp_db

from fastapi.testclient import TestClient  # noqa: E402

from app.api import create_app  # noqa: E402
from app.db import repo  # noqa: E402
from app.scanner import orchestrator  # noqa: E402

client = TestClient(create_app())
TODAY = date.today().isoformat()
_n = 0


def _project(n_queries: int = 3) -> tuple[int, list[int]]:
    global _n
    _n += 1
    p = client.post("/api/projects", json={"name": f"План {_n}", "brand_name": "Бренд"}).json()
    texts = "\n".join(f"запрос {i}" for i in range(n_queries))
    client.post(f"/api/projects/{p['id']}/queries", json={"text": texts})
    return p["id"], [q["id"] for q in client.get(f"/api/projects/{p['id']}/queries").json()]


def _scan(pid: int, services: list[str], done: dict[str, list[int]], *, day: str = TODAY,
          status: str = "stopped", failed: dict[str, list[int]] | None = None) -> int:
    sid = repo.create_scan(pid, services, {})
    repo._exec("UPDATE scans SET scan_date = ?, status = ? WHERE id = ?", (day, status, sid))
    for svc, qids in done.items():
        for q in qids:
            repo.save_result(sid, q, svc, "not_found")
    for svc, qids in (failed or {}).items():
        for q in qids:
            repo.save_result(sid, q, svc, "error")
    return sid


def test_interrupted_scan_counts_only_leftovers():
    pid, q = _project()
    sid = _scan(pid, ["perplexity", "google_aio"], {"perplexity": q[:2]}, failed={"google_aio": q[:1]})
    plan = orchestrator.plan_scan(pid, ["perplexity", "google_aio"])
    assert plan["continue_scan_id"] == sid and plan["date"] == TODAY
    assert plan["by_service"]["perplexity"] == {"done": 2, "total": 3}
    # Ошибка — не готовый результат: такую пару берём заново.
    assert plan["by_service"]["google_aio"] == {"done": 0, "total": 3}
    assert (plan["total"], plan["remaining"]) == (6, 4)


def test_other_scans_of_the_day_count_too():
    pid, q = _project()
    _scan(pid, ["perplexity", "google_aio"], {"perplexity": q[:2]})
    # Днём отдельно прогнали только Алису — целиком. Последний скан теперь
    # законченный, но хвост Perplexity и Google за сегодня никуда не делся.
    _scan(pid, ["alice"], {"alice": q}, status="done")
    assert repo.find_resumable_scan(pid, scannable=set(orchestrator.ADAPTERS)) is None
    plan = orchestrator.plan_scan(pid, ["perplexity", "google_aio", "alice"])
    assert plan["continue_scan_id"] is None and plan["date"] == TODAY
    assert plan["by_service"]["alice"]["done"] == 3
    assert plan["remaining"] == 1 + 3 + 0
    assert orchestrator.plan_scan(pid, ["alice"])["remaining"] == 0


def test_leftover_scan_does_not_look_unfinished():
    # Досканировали хвост одного сервиса в новый скан — сам по себе он
    # неполный, но вместе с утренним срез за день закрыт.
    pid, q = _project()
    _scan(pid, ["perplexity"], {"perplexity": q[:2]})
    _scan(pid, ["perplexity"], {"perplexity": q[2:]}, status="done")
    assert repo.find_resumable_scan(pid, scannable=set(orchestrator.ADAPTERS)) is None


def test_old_unfinished_scan_is_continued_in_its_date():
    pid, q = _project()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    sid = _scan(pid, ["chatgpt"], {"chatgpt": q[:1]}, day=yesterday)
    plan = orchestrator.plan_scan(pid, ["chatgpt"])
    assert (plan["continue_scan_id"], plan["date"], plan["remaining"]) == (sid, yesterday, 2)
    # Сервиса не было в том скане — в чужой замер не дописываем: новый за сегодня.
    plan = orchestrator.plan_scan(pid, ["alice"])
    assert (plan["continue_scan_id"], plan["date"], plan["remaining"]) == (None, TODAY, 3)


def test_start_over_ignores_done():
    pid, q = _project()
    _scan(pid, ["perplexity"], {"perplexity": q})
    assert orchestrator.plan_scan(pid, ["perplexity"])["remaining"] == 0
    plan = orchestrator.plan_scan(pid, ["perplexity"], resume=False)
    assert (plan["continue_scan_id"], plan["remaining"]) == (None, 3)


def test_start_with_nothing_left_creates_no_scan():
    pid, q = _project()
    _scan(pid, ["perplexity"], {"perplexity": q}, status="done")
    before = len(repo.list_scans(pid))
    try:
        asyncio.run(orchestrator.start_scan(pid, ["perplexity"]))
        raise AssertionError("должен был отказать: всё уже проверено")
    except ValueError as exc:
        assert "всё уже проверено" in str(exc)
    assert len(repo.list_scans(pid)) == before


def test_plan_endpoint():
    pid, q = _project()
    _scan(pid, ["perplexity"], {"perplexity": q[:1]})
    r = client.get(f"/api/projects/{pid}/scan-plan?services=perplexity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["remaining"] == 2 and set(body["by_service"]) == set(orchestrator.ADAPTERS)
    assert client.get("/api/projects/99999/scan-plan").status_code == 404


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
