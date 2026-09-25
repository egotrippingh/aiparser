"""Account-wide schedule and private cloud report contract."""

from datetime import date, datetime

from fastapi.testclient import TestClient

from app.agent import schedule_due
from server.app import create_app
from server.models import Check, make_session_factory


def _register(client: TestClient, email: str) -> tuple[dict, str]:
    response = client.post("/api/v1/auth/register", json={
        "email": email, "password": "a-long-test-password",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["user"]["id"]


def test_month_day_schedule_and_report_ownership(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'accounts.db'}"
    client = TestClient(create_app(database_url=database_url))
    headers, user_id = _register(client, "owner@example.test")
    other_headers, _ = _register(client, "other@example.test")

    initial = client.get("/api/v1/scan-preferences", headers=headers).json()
    assert initial["enabled"] is False
    assert initial["month_days"] == [1]
    changed = {**initial, "enabled": True, "local_time": "14:30", "month_days": [15, 1, 31]}
    response = client.put("/api/v1/scan-preferences", headers=headers, json=changed)
    assert response.status_code == 200, response.text
    assert response.json()["month_days"] == [1, 15, 31]
    assert client.put("/api/v1/scan-preferences", headers=headers,
                      json={**response.json(), "month_days": [0, 31]}).status_code == 422
    assert client.put("/api/v1/scan-preferences", headers=headers,
                      json={**response.json(), "services": ["yandex_neuro"]}).status_code == 422
    assert client.put("/api/v1/scan-preferences", headers=headers, json=changed).status_code == 409
    assert client.get("/api/v1/scan-preferences", headers=other_headers).json()["enabled"] is False

    preferences = response.json()
    assert not schedule_due(preferences, datetime(2026, 4, 15, 14, 29))
    assert schedule_due(preferences, datetime(2026, 4, 15, 14, 30))
    assert not schedule_due(preferences, datetime(2026, 4, 16, 14, 30))
    assert not schedule_due({**preferences, "month_days": [31]}, datetime(2026, 4, 30, 15))

    device_id = "a" * 32
    heartbeat = {"device_id": device_id, "name": "Тестовый агент",
                 "local_time_zone": "MSK", "active_scan": False}
    assert client.post("/api/v1/agent/heartbeat", headers=headers, json=heartbeat).status_code == 200
    assert len(client.get("/api/v1/agent/devices", headers=headers).json()) == 1
    assert client.get("/api/v1/agent/devices", headers=other_headers).json() == []

    _, sessions = make_session_factory(database_url)
    with sessions() as db:
        db.add(Check(user_id=user_id, client_check_id="paid-check", price_kopeks=150,
                     status="settled", result_status="found"))
        db.commit()

    today = date.today().isoformat()
    result = {"local_result_id": 1, "local_project_id": 7, "project_name": "Проект",
              "brand_name": "Бренд", "query_text": "Тестовый запрос", "group_tag": None,
              "service": "chatgpt", "scan_date": today, "status": "found",
              "mention_types": ["marketplace"], "evidence_quote": "Бренд",
              "answer_text": "Бренд в карточке товара", "sources": ["https://example.test/item"],
              "check_id": "paid-check"}
    body = {"device_id": device_id, "results": [result]}
    assert client.post("/api/v1/agent/results", headers=other_headers, json=body).status_code == 409
    assert client.post("/api/v1/agent/results", headers=headers, json=body).status_code == 200
    assert client.post("/api/v1/agent/results", headers=headers, json=body).status_code == 200
    assert client.post("/api/v1/agent/results", headers=headers,
                       json={"device_id": device_id, "results": [{**result, "local_result_id": 2,
                             "check_id": None}]}).status_code == 422

    project = client.get("/api/v1/reports/projects", headers=headers).json()[0]["key"]
    assert client.get("/api/v1/reports/projects", headers=other_headers).json() == []
    report = client.get("/api/v1/reports", headers=headers,
                        params={"project": project, "days": 7, "include_cards": "false"})
    assert report.status_code == 200, report.text
    assert report.json()["total"] == 1
    assert report.json()["summary"] == {"found": 0, "checked": 1,
                                         "visibility_pct": 0, "by_service": {"chatgpt": {"found": 0, "checked": 1}},
                                         "by_date": {today: {"found": 0, "checked": 1}}}
    report_with_cards = client.get("/api/v1/reports", headers=headers,
                                   params={"project": project, "days": 7})
    assert report_with_cards.json()["summary"]["found"] == 1
