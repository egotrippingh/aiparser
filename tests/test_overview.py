"""Эндпоинт overview — источник Топвизор-таблицы и сводки на дашборде.

Главное, что здесь проверяется: за одну дату на пару «запрос × сервис»
приходится ровно один результат. Несколько сканов за день (дозапуск после
лимита, перепроверка) не должны ни удваивать видимость, ни затирать уже
полученный ответ свежей ошибкой.

Работает на отдельном временном файле БД — данные пользователя не трогает.
"""

import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db = Path(tempfile.gettempdir()) / "aiparser_test_overview.db"
_tmp_db.unlink(missing_ok=True)

from app import config  # noqa: E402

config.DB_PATH = _tmp_db

from fastapi.testclient import TestClient  # noqa: E402

from app.api import create_app  # noqa: E402
from app.db import repo  # noqa: E402

client = TestClient(create_app())


def _project(name: str, queries: list[str]) -> tuple[int, dict[str, int]]:
    pid = client.post("/api/projects", json={"name": name, "brand_name": "Бренд"}).json()["id"]
    client.post(f"/api/projects/{pid}/queries", json={"text": "\n".join(queries)})
    ids = {q["text"]: q["id"] for q in client.get(f"/api/projects/{pid}/queries").json()}
    return pid, ids


def _scan(pid: int, date: str, services: list[str]) -> int:
    sid = repo.create_scan(pid, services, {})
    repo._exec("UPDATE scans SET scan_date = ? WHERE id = ?", (date, sid))
    return sid


def test_empty_project_has_rows_but_no_dates():
    pid, _ = _project("Пустой", ["запрос один", "запрос два"])
    d = client.get(f"/api/projects/{pid}/overview").json()
    assert d["dates"] == []
    assert d["summary"] is None
    assert d["services"] == []
    assert [r["text"] for r in d["rows"]] == ["запрос один", "запрос два"]
    assert all(r["cells"] == {} for r in d["rows"])


def test_one_result_per_query_service_date_and_deltas():
    pid, q = _project("Дедуп", ["альфа", "бета"])
    a, b = q["альфа"], q["бета"]

    s1 = _scan(pid, "2026-09-01", ["chatgpt"])
    repo.save_result(s1, a, "chatgpt", "found")
    repo.save_result(s1, b, "chatgpt", "not_found")

    # Второй день, два скана. В первом альфа найдена, во втором по ней
    # ошибка — показывать надо найденную. По бете сначала found, потом
    # not_found — показывать последний конклюзивный, то есть not_found.
    s2 = _scan(pid, "2026-09-02", ["chatgpt"])
    repo.save_result(s2, a, "chatgpt", "found")
    repo.save_result(s2, b, "chatgpt", "found")
    s3 = _scan(pid, "2026-09-02", ["chatgpt"])
    repo.save_result(s3, a, "chatgpt", "error", error_message="таймаут")
    repo.save_result(s3, b, "chatgpt", "not_found")

    d = client.get(f"/api/projects/{pid}/overview").json()
    assert d["dates"] == ["2026-09-01", "2026-09-02"]
    assert d["services"] == ["chatgpt"]

    rows = {r["text"]: r for r in d["rows"]}
    assert rows["альфа"]["cells"]["2026-09-02"]["chatgpt"]["status"] == "found"
    assert rows["бета"]["cells"]["2026-09-02"]["chatgpt"]["status"] == "not_found"

    # Ровно две проверки за день, а не четыре, как было бы при сложении сканов.
    day2 = d["stats"]["2026-09-02"]
    assert day2["_all"] == {"found": 1, "checked": 2, "pct": 50.0}
    assert d["stats"]["2026-09-01"]["_all"]["pct"] == 50.0

    s = d["summary"]
    assert s["date"] == "2026-09-02" and s["prev_date"] == "2026-09-01"
    assert s["total"]["delta"] == 0.0
    assert s["by_service"][0]["id"] == "chatgpt"
    assert s["queries"] == 2
    # Ошибка по альфе перекрыта найденным результатом — в сводке её нет.
    assert s["errors"] == 0


def test_errors_and_limits_do_not_count_into_visibility():
    pid, q = _project("Ошибки", ["гамма", "дельта", "эпсилон"])
    s = _scan(pid, "2026-09-05", ["perplexity"])
    repo.save_result(s, q["гамма"], "perplexity", "found")
    repo.save_result(s, q["дельта"], "perplexity", "captcha")
    repo.save_result(s, q["эпсилон"], "perplexity", "limit_reached")

    d = client.get(f"/api/projects/{pid}/overview").json()
    assert d["stats"]["2026-09-05"]["perplexity"] == {"found": 1, "checked": 1, "pct": 100.0}
    assert d["summary"]["errors"] == 1
    assert d["summary"]["not_checked"] == 1
    assert d["summary"]["total"]["delta"] is None     # одна дата — сравнивать не с чем


def test_detail_by_date_uses_same_pick_and_history_is_deduped():
    pid, q = _project("Карточка", ["зета"])
    z = q["зета"]
    s1 = _scan(pid, "2026-09-03", ["alice"])
    repo.save_result(s1, z, "alice", "found", evidence_quote="Бренд — лучший")
    s2 = _scan(pid, "2026-09-03", ["alice"])
    repo.save_result(s2, z, "alice", "auth_required")

    r = client.get(f"/api/queries/{z}/detail", params={"date": "2026-09-03"})
    assert r.status_code == 200, r.text
    info = r.json()["by_service"]["alice"]
    assert info["status"] == "found"
    assert info["evidence_quote"] == "Бренд — лучший"
    assert [h["scan_date"] for h in info["history"]] == ["2026-09-03"]


def test_detail_needs_date_or_scan():
    _, q = _project("Без параметров", ["эта"])
    r = client.get(f"/api/queries/{q['эта']}/detail")
    assert r.status_code == 400


def test_inactive_query_without_results_is_hidden():
    pid, q = _project("Неактивные", ["тета", "йота"])
    client.patch(f"/api/projects/{pid}/queries/{q['йота']}", params={"is_active": False})
    d = client.get(f"/api/projects/{pid}/overview").json()
    assert [r["text"] for r in d["rows"]] == ["тета"]


def test_unknown_project_is_404():
    assert client.get("/api/projects/999999/overview").status_code == 404


# --- календарь: выбор срезов как в Топвизоре ------------------------------

_calendar_n = 0


def _calendar_project() -> int:
    # Имя проекта уникально в БД — каждому тесту свой проект.
    global _calendar_n
    _calendar_n += 1
    pid, q = _project(f"Календарь {_calendar_n}", ["каппа"])
    for d, st in [
        ("2026-07-10", "not_found"), ("2026-07-25", "found"),
        ("2026-08-05", "found"), ("2026-08-30", "not_found"),
        ("2026-09-02", "found"),
    ]:
        s = _scan(pid, d, ["chatgpt"])
        repo.save_result(s, q["каппа"], "chatgpt", st)
    return pid


def test_scan_dates_for_calendar():
    pid = _calendar_project()
    d = client.get(f"/api/projects/{pid}/scan-dates").json()["dates"]
    assert [x["date"] for x in d] == [
        "2026-07-10", "2026-07-25", "2026-08-05", "2026-08-30", "2026-09-02",
    ]
    assert d[0]["checks"] == 1 and d[0]["services"] == ["chatgpt"]


def test_period_range_filters_dates():
    pid = _calendar_project()
    d = client.get(f"/api/projects/{pid}/overview",
                   params={"date_from": "2026-08-01", "date_to": "2026-08-31"}).json()
    assert d["dates"] == ["2026-08-05", "2026-08-30"]
    assert d["selection"]["available"] == 2 and d["selection"]["truncated"] is False
    assert d["selection"]["first_scan"] == "2026-07-10"


def test_two_dates_compares_first_and_last_of_range():
    pid = _calendar_project()
    d = client.get(f"/api/projects/{pid}/overview",
                   params={"mode": "two", "date_from": "2026-07-01", "date_to": "2026-09-30"}).json()
    assert d["dates"] == ["2026-07-10", "2026-09-02"]
    s = d["summary"]
    assert s["prev_date"] == "2026-07-10" and s["date"] == "2026-09-02"
    assert s["total"]["delta"] == 100.0      # было 0% (not_found), стало 100%


def test_monthly_takes_last_check_of_each_month():
    pid = _calendar_project()
    d = client.get(f"/api/projects/{pid}/overview", params={"mode": "monthly"}).json()
    assert d["dates"] == ["2026-07-25", "2026-08-30", "2026-09-02"]


def test_custom_dates_and_truncation():
    pid = _calendar_project()
    d = client.get(f"/api/projects/{pid}/overview",
                   params={"mode": "custom", "dates": "2026-07-10,2026-08-30,2099-01-01"}).json()
    assert d["dates"] == ["2026-07-10", "2026-08-30"]

    d = client.get(f"/api/projects/{pid}/overview", params={"max_dates": 2}).json()
    assert d["dates"] == ["2026-08-30", "2026-09-02"]
    assert d["selection"]["available"] == 5 and d["selection"]["truncated"] is True


def test_two_and_monthly_without_range_use_all_history():
    pid = _calendar_project()
    d = client.get(f"/api/projects/{pid}/overview", params={"mode": "two", "days": 2}).json()
    # days ограничивает только «Период»: сравнение берёт первую проверку за всё время
    assert d["dates"] == ["2026-07-10", "2026-09-02"]
    d = client.get(f"/api/projects/{pid}/overview", params={"mode": "period", "days": 2}).json()
    assert d["dates"] == ["2026-08-30", "2026-09-02"]


def test_bad_calendar_params_are_400():
    pid = _calendar_project()
    assert client.get(f"/api/projects/{pid}/overview", params={"mode": "weekly"}).status_code == 400
    assert client.get(f"/api/projects/{pid}/overview", params={"date_from": "10.09.2026"}).status_code == 400


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
