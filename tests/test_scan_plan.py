"""Досканирование: что за дату уже проверено и что осталось.

Готовое считается по ВСЕМ сканам даты, а не только по последнему: прерванный
утренний скан плюс отдельный прогон одной Алисы днём — досканировать нужно
только то, чего нет ни в одном из них. Браузер не нужен: результаты пишутся
в базу напрямую.
"""

import asyncio
import json
import sys
import tempfile
import traceback
import pytest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

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


@pytest.fixture(autouse=True)
def standalone_local_api(monkeypatch):
    # These tests exercise the standalone planner; managed agents are read-only.
    monkeypatch.setattr(config, "ACCOUNT_URL", "")


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


def test_new_payer_never_continues_previous_accounts_scan():
    pid, queries = _project(2)
    old_scan = _scan(pid, ["perplexity"], {"perplexity": queries[:1]})
    repo._exec("UPDATE scans SET settings_snapshot_json = ? WHERE id = ?",
               (json.dumps({"billing_user_id": "account-a"}), old_scan))
    own = orchestrator._plan_for_billing_user(pid, ["perplexity"], True, "account-a")
    changed = orchestrator._plan_for_billing_user(pid, ["perplexity"], True, "account-b")
    assert own["continue_scan_id"] == old_scan
    assert own["done_pairs"] == {(queries[0], "perplexity")}
    assert changed["continue_scan_id"] is None
    assert changed["done_pairs"] == set()


def test_start_with_nothing_left_creates_no_scan(monkeypatch):
    monkeypatch.setattr(orchestrator.billing, "enabled", lambda: False)
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


def test_browser_crash_retries_only_unsaved_queries(monkeypatch):
    pid, query_ids = _project(2)
    sid = repo.create_scan(pid, ["perplexity"], {})
    controller = orchestrator.ScanController(sid, pid, 2, TODAY)
    attempts = []

    async def interrupted(_project, service, pending, _settings, _speed, _key,
                          _model, _mode, ctl):
        attempts.append([item["id"] for item in pending])
        if len(attempts) == 1:
            repo.save_result(sid, query_ids[0], service, "not_found")
            ctl.advance(service, query_ids[0])
            raise RuntimeError("browser context closed")
        repo.save_result(sid, query_ids[1], service, "not_found")
        ctl.advance(service, query_ids[1])

    monkeypatch.setattr(orchestrator, "_run_service", interrupted)
    asyncio.run(orchestrator._run_scan(
        repo.get_project(pid), ["perplexity"], repo.list_queries(pid), set(),
        {"llm_mode": "never", "typing_speed": 0.5}, controller,
    ))
    assert attempts == [query_ids, query_ids[1:]]
    assert controller.done == 2
    assert repo.get_scan(sid)["status"] == "done"


def test_browser_crash_with_unchecked_tail_is_failed(monkeypatch):
    pid, query_ids = _project(2)
    sid = repo.create_scan(pid, ["perplexity"], {})
    controller = orchestrator.ScanController(sid, pid, 2, TODAY)

    async def interrupted(_project, service, pending, _settings, _speed, _key,
                          _model, _mode, ctl):
        if ctl.done == 0:
            repo.save_result(sid, query_ids[0], service, "not_found")
            ctl.advance(service, query_ids[0])
        raise RuntimeError("browser context closed")

    monkeypatch.setattr(orchestrator, "_run_service", interrupted)
    asyncio.run(orchestrator._run_scan(
        repo.get_project(pid), ["perplexity"], repo.list_queries(pid), set(),
        {"llm_mode": "never", "typing_speed": 0.5}, controller,
    ))
    assert controller.done == 1
    assert repo.get_scan(sid)["status"] == "failed"
    assert orchestrator.plan_scan(pid, ["perplexity"])["remaining"] == 1


def test_completed_attempts_with_error_remain_failed(monkeypatch):
    pid, query_ids = _project(1)
    sid = repo.create_scan(pid, ["google_aio"], {})
    controller = orchestrator.ScanController(sid, pid, 1, TODAY)

    async def failed_attempt(_project, service, _pending, _settings, _speed, _key,
                             _model, _mode, ctl):
        repo.save_result(sid, query_ids[0], service, "error", error_message="Анализ недоступен")
        ctl.advance(service, query_ids[0])

    monkeypatch.setattr(orchestrator, "_run_service", failed_attempt)
    asyncio.run(orchestrator._run_scan(
        repo.get_project(pid), ["google_aio"], repo.list_queries(pid), set(),
        {"llm_mode": "never", "typing_speed": 0.5}, controller,
    ))
    assert controller.done == 1
    assert repo.get_scan(sid)["status"] == "failed"


def test_llm_error_is_saved_with_result(monkeypatch, tmp_path):
    pid, _ = _project(1)
    sid = repo.create_scan(pid, ["google_aio"], {})
    controller = orchestrator.ScanController(sid, pid, 1, TODAY)
    capture = SimpleNamespace(shown=True, screenshot_bytes=b"raw",
                              answer_text="Компания предлагает услуги", sources=[], extra={})

    class Adapter:
        async def ask(self, *_args, **_kwargs):
            pass

        async def capture(self, _page):
            return capture

    async def unavailable(**_kwargs):
        return SimpleNamespace(error="Сервер анализа вернул HTTP 422")

    monkeypatch.setattr(orchestrator.imaging, "to_webp", lambda _: b"webp")
    monkeypatch.setattr(orchestrator.config, "screenshot_dir", lambda *_: tmp_path)
    monkeypatch.setattr(orchestrator.llm_mod, "evaluate", unavailable)
    status = asyncio.run(orchestrator._run_one(
        repo.get_project(pid), repo.list_queries(pid)[0], "google_aio", Adapter(),
        object(), {"managed_llm": True, "llm_confidence_threshold": 0.6,
                   "arbiter": False}, 0.5, "", "test-model", "smart", controller,
    ))
    result = repo.results_for_scan(sid)[0]
    assert status == result["status"] == "error"
    assert result["error_message"] == "Сервер анализа вернул HTTP 422"
    assert result["answer_text"] == capture.answer_text


def test_closed_browser_is_retried_without_error_result():
    pid, _ = _project(1)
    sid = repo.create_scan(pid, ["perplexity"], {})
    controller = orchestrator.ScanController(sid, pid, 1, TODAY)

    class Adapter:
        async def ask(self, *_args, **_kwargs):
            raise RuntimeError("Mouse.wheel: Target page, context or browser has been closed")

    try:
        asyncio.run(orchestrator._run_one(
            repo.get_project(pid), repo.list_queries(pid)[0], "perplexity", Adapter(),
            object(), {}, 0.5, "", "", "never", controller,
        ))
        raise AssertionError("Закрытие браузера должно попасть в повтор сервиса")
    except RuntimeError as exc:
        assert "browser has been closed" in str(exc)
    assert repo.results_for_scan(sid) == []


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
