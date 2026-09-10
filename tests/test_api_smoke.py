"""Сквозной smoke-тест API без браузера и без реального сервера.

FastAPI TestClient гоняет запросы прямо через ASGI, in-process — секунды на
прогон. Ловит ровно тот класс багов, что уже стоил времени в разработке:
приложение импортируется, но падает на конкретном роуте (несовместимость
статус-кода 204 с `from __future__ import annotations`, отсутствие
python-multipart и т.п.) — такое не видно, пока не дёрнешь эндпоинт.

Использует отдельный временный файл БД, а не data/aiparser.db, чтобob не
портить реальные данные пользователя при каждом прогоне тестов.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db = Path(tempfile.gettempdir()) / "aiparser_test.db"
_tmp_db.unlink(missing_ok=True)

from app import config  # noqa: E402

config.DB_PATH = _tmp_db  # подменяем ДО создания приложения — repo читает config.DB_PATH лениво

from fastapi.testclient import TestClient  # noqa: E402

from app.api import create_app  # noqa: E402

client = TestClient(create_app())


def test_meta_lists_all_services():
    r = client.get("/api/meta")
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()["services"]}
    assert ids == {"perplexity", "chatgpt", "yandex_neuro", "alice", "google_aio"}


def test_project_lifecycle():
    r = client.post("/api/projects", json={
        "name": "Smoke-проект", "brand_name": "Тестбренд",
        "brand_aliases": ["testbrand"], "brand_domains": ["testbrand.ru"],
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    assert r.json()["brand_name"] == "Тестбренд"

    r = client.patch(f"/api/projects/{pid}", json={"region_code": "213"})
    assert r.status_code == 200
    assert r.json()["region_code"] == "213"

    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 204          # именно этот код ловил баг с `-> None`
    assert r.content == b""

    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 404


def test_queries_add_and_toggle():
    pid = client.post("/api/projects", json={"name": "Запросы-тест", "brand_name": "X"}).json()["id"]

    r = client.post(f"/api/projects/{pid}/queries", json={"text": "запрос один\nзапрос два\nзапрос один"})
    assert r.status_code == 201
    body = r.json()
    assert body["added"] == 2          # дубликат внутри пачки схлопнулся
    assert body["skipped"] == 1

    qs = client.get(f"/api/projects/{pid}/queries").json()
    assert len(qs) == 2
    qid = qs[0]["id"]

    r = client.patch(f"/api/projects/{pid}/queries/{qid}", params={"is_active": "false"})
    assert r.status_code == 200
    assert client.get(f"/api/projects/{pid}/queries?only_active=true").json().__len__() == 1

    r = client.delete(f"/api/projects/{pid}/queries/{qid}")
    assert r.status_code == 204          # тот же 204-баг, другой роут


def test_dashboard_empty_before_first_scan():
    pid = client.post("/api/projects", json={"name": "Дашборд-тест", "brand_name": "Y"}).json()["id"]
    r = client.get(f"/api/projects/{pid}/dashboard")
    assert r.status_code == 200
    assert r.json()["empty"] is True


def test_settings_roundtrip():
    r = client.put("/api/settings", json={"llm_mode": "always", "openrouter_model": "test/model"})
    assert r.status_code == 200
    body = r.json()
    assert body["llm_mode"] == "always"
    assert body["openrouter_model"] == "test/model"
    assert body["openrouter_api_key_set"] is False


def test_browser_status_reports_installed_flag():
    r = client.get("/api/browser/status")
    assert r.status_code == 200
    assert "installed" in r.json()


def test_scan_on_unknown_project_is_404():
    r = client.post("/api/projects/999999/scans", json={"services": ["perplexity"]})
    assert r.status_code == 404


def test_scan_rejects_unknown_service():
    pid = client.post("/api/projects", json={"name": "Скан-тест", "brand_name": "Z"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/scans", json={"services": ["not_a_real_service"]})
    assert r.status_code == 400


if __name__ == "__main__":
    import traceback

    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
            passed += 1
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    try:
        _tmp_db.unlink(missing_ok=True)  # Windows держит файл, пока жив коннекшн — не критично
    except PermissionError:
        pass
    sys.exit(1 if failed else 0)
