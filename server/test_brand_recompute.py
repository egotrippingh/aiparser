import json
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from server.ai import AIError
from server.app import create_app
from server.models import Check, CloudResult, ControlProject, LedgerEntry, Screenshot, User, Wallet, make_session_factory, utcnow


FEATURE_USER = "919cc8bbbdc74156bb21e9020a99564a"


class FakeAI:
    model = "fake"

    def __init__(self, fail=False):
        self.fail = fail

    def recompute(self, clarification, content):
        if self.fail:
            raise AIError("down")
        assert "Reflo" in clarification and "Сохранённый ответ" in content[0]["text"]
        return type("Result", (), {"raw": '{"found": false, "mention_types": [], "quote": "Reflo не Refprom"}'})()


def feature_setup(tmp_path, monkeypatch, ai=None, screenshot_storage=None):
    monkeypatch.setenv("BRAND_CLARIFICATIONS_USER_ID", FEATURE_USER)
    monkeypatch.setattr("server.app.uuid.uuid4", lambda: type("Id", (), {"hex": FEATURE_USER})())
    url = f"sqlite:///{tmp_path / 'recompute.db'}"
    client = TestClient(create_app(database_url=url, ai_client=ai or FakeAI(), screenshot_storage=screenshot_storage))
    res = client.post("/api/v1/auth/register", json={"email": "admin@test.example", "password": "long-test-password-123"})
    assert res.status_code == 201, res.text
    headers = {"Authorization": "Bearer " + res.json()["token"]}
    _, sessions = make_session_factory(url)
    with sessions() as db:
        db.get(User, FEATURE_USER).is_admin = True
        db.get(Wallet, FEATURE_USER).balance_kopeks = 1000
        db.commit()
    return client, headers, sessions


def test_recompute_uses_latest_visible_answer_once_and_keeps_failure_free(tmp_path, monkeypatch):
    client, headers, sessions = feature_setup(tmp_path, monkeypatch)
    body = {"name": "Refprom", "brand_name": "Refprom", "queries": [{"text": "Refprom review"}],
            "config": {"services": ["chatgpt"], "brand_clarification": "Reflo — не наш бренд"}}
    project = client.post("/api/v1/control/projects", headers=headers, json=body).json()
    today = utcnow().date().isoformat()
    yesterday = (utcnow().date() - timedelta(days=1)).isoformat()
    with sessions() as db:
        for local_id, day, text in ((1, today, "old visible answer"), (2, today, "new visible answer"), (3, yesterday, "another answer")):
            db.add(CloudResult(user_id=FEATURE_USER, device_id="a" * 32, local_result_id=local_id, local_project_id=1,
                project_id=project["id"], query_id=project["queries"][0]["id"], project_name="Refprom",
                brand_name="Refprom", query_text="Refprom review", group_tag="", service="chatgpt", scan_date=day,
                status="found", answer_text=text, sources_json="[]", evidence_quote="answer", mention_types_json='["text"]'))
        db.commit()
        rows = list(db.query(CloudResult).order_by(CloudResult.id))
        old_id, latest_id, yesterday_id = [row.id for row in rows]

    quote = client.get(f"/api/v1/control/projects/{project['id']}/recompute/quote", headers=headers,
                       params={"from_date": today}).json()
    assert quote["result_ids"] == [str(latest_id)] and quote["total_kopeks"] == 80
    done = client.post(f"/api/v1/control/projects/{project['id']}/recompute/{latest_id}", headers=headers,
                       json={"from_date": today, "revision": project["revision"]})
    assert done.status_code == 200 and done.json()["charged_kopeks"] == 80
    again = client.post(f"/api/v1/control/projects/{project['id']}/recompute/{latest_id}", headers=headers,
                        json={"from_date": today, "revision": project["revision"]})
    assert again.json()["charged_kopeks"] == 0
    assert client.post(f"/api/v1/control/projects/{project['id']}/recompute/{old_id}", headers=headers,
                       json={"from_date": today, "revision": project["revision"]}).json()["status"] == "skipped"
    with sessions() as db:
        assert db.get(Wallet, FEATURE_USER).balance_kopeks == 920
        assert db.get(CloudResult, latest_id).status == "not_found"
        assert db.get(CloudResult, yesterday_id).status == "found"
        assert len(list(db.query(LedgerEntry).filter_by(kind="recompute"))) == 1
        report = client.get(f"/api/v1/control/projects/{project['id']}/mentions", headers=headers,
                            params={"date_from": today, "date_to": today}).json()
        assert report["summary"]["found"] == 0 and report["summary"]["checked"] == 1
        # A newer error owns this daily graph cell, so its older answer is not billable.
        db.add(CloudResult(user_id=FEATURE_USER, device_id="a" * 32, local_result_id=4, local_project_id=1,
            project_id=project["id"], query_id=project["queries"][0]["id"], project_name="Refprom",
            brand_name="Refprom", query_text="Refprom review", group_tag="", service="chatgpt", scan_date=today,
            status="error", answer_text=None, sources_json="[]"))
        db.commit()
    assert client.get(f"/api/v1/control/projects/{project['id']}/recompute/quote", headers=headers,
                      params={"from_date": today}).json()["count"] == 0

    # Model failure never changes the saved verdict or wallet.
    failed_path = tmp_path / "failed"
    failed_path.mkdir()
    client_fail, fail_headers, fail_sessions = feature_setup(failed_path, monkeypatch, FakeAI(fail=True))
    failed_project = client_fail.post("/api/v1/control/projects", headers=fail_headers, json=body).json()
    with fail_sessions() as db:
        db.add(CloudResult(user_id=FEATURE_USER, device_id="b" * 32, local_result_id=7, local_project_id=1,
            project_id=failed_project["id"], query_id=failed_project["queries"][0]["id"], project_name="Refprom",
            brand_name="Refprom", query_text="Refprom review", group_tag="", service="chatgpt", scan_date=today,
            status="found", answer_text="answer", evidence_quote="answer", sources_json="[]"))
        db.commit(); result_id = db.query(CloudResult).one().id
    failed = client_fail.post(f"/api/v1/control/projects/{failed_project['id']}/recompute/{result_id}", headers=fail_headers,
                              json={"from_date": today, "revision": failed_project["revision"]})
    assert failed.json()["status"] == "error"
    with fail_sessions() as db:
        assert db.get(Wallet, FEATURE_USER).balance_kopeks == 1000
        assert db.get(CloudResult, result_id).status == "found"


def test_brand_clarification_is_exact_admin_feature_flag(tmp_path, monkeypatch):
    client, headers, _ = feature_setup(tmp_path, monkeypatch)
    assert client.get("/api/v1/me", headers=headers).json()["brand_clarifications_enabled"] is True
    monkeypatch.setattr("server.app.uuid.uuid4", uuid4)
    other = client.post("/api/v1/auth/register", json={"email": "other@test.example", "password": "long-test-password-123"})
    other_headers = {"Authorization": "Bearer " + other.json()["token"]}
    body = {"name": "P", "brand_name": "Brand", "config": {"brand_clarification": "only me"}}
    assert client.post("/api/v1/control/projects", headers=other_headers, json=body).status_code == 403


def test_guidance_is_frozen_only_for_an_agent_that_advertises_support(tmp_path, monkeypatch):
    client, headers, _ = feature_setup(tmp_path, monkeypatch)
    device = "a" * 32
    agent = client.post("/api/v1/control/agent/enroll", headers=headers,
                        json={"device_id": device, "name": "PC"}).json()["token"]
    agent_headers = {"Authorization": "Bearer " + agent}
    project = client.post("/api/v1/control/projects", headers=headers, json={
        "name": "P", "brand_name": "Brand", "device_id": device, "queries": [{"text": "Brand"}],
        "config": {"services": ["chatgpt"], "brand_clarification": "Not a similar brand"},
    }).json()
    assert client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=headers,
                       json={"request_id": "b" * 32, "revision": project["revision"]}).status_code == 422
    client.post("/api/v1/control/agent/poll", headers=agent_headers,
                json={"capabilities": {"brand_clarification": True, "installed": False}})
    run = client.post(f"/api/v1/control/projects/{project['id']}/runs", headers=headers,
                      json={"request_id": "c" * 32, "revision": project["revision"]})
    assert run.status_code == 201 and run.json()["id"]
    assert client.post("/api/v1/control/agent/poll", headers=agent_headers,
                       json={"capabilities": {"installed": True}}).json()["run"] is None
    claimed = client.post("/api/v1/control/agent/poll", headers=agent_headers,
                          json={"capabilities": {"installed": True, "brand_clarification": True}}).json()
    assert claimed["run"]["id"] == run.json()["id"]
    assert client.post("/api/v1/control/agent/poll", headers=agent_headers,
                       json={"capabilities": {"installed": True}}).json()["run"] is None


def test_recompute_uses_report_query_mapping_and_flagged_off_save_preserves_note(tmp_path, monkeypatch):
    client, headers, sessions = feature_setup(tmp_path, monkeypatch)
    project = client.post("/api/v1/control/projects", headers=headers, json={
        "name": "P", "brand_name": "Refprom", "queries": [{"text": "find Refprom"}],
        "config": {"services": ["chatgpt"], "brand_clarification": "Reflo — не наш бренд"},
    }).json()
    today = utcnow().date().isoformat()
    with sessions() as db:
        for local_id, query_id in ((1, "old-query"), (2, project["queries"][0]["id"])):
            db.add(CloudResult(user_id=FEATURE_USER, device_id="a" * 32, local_result_id=local_id,
                local_project_id=1, project_id=project["id"], query_id=query_id, project_name="P",
                brand_name="Refprom", query_text="find Refprom", group_tag="", service="chatgpt",
                scan_date=today, status="found", answer_text="Refprom", evidence_quote="Refprom", sources_json="[]"))
        db.commit()
        ids = [row.id for row in db.query(CloudResult).order_by(CloudResult.id)]
    quote = client.get(f"/api/v1/control/projects/{project['id']}/recompute/quote", headers=headers,
                       params={"from_date": today}).json()
    assert quote["result_ids"] == [str(ids[-1])]
    monkeypatch.setenv("BRAND_CLARIFICATIONS_USER_ID", "")
    # A disabled feature redacts the note, but unrelated edits do not erase it.
    client_without_flag = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'recompute.db'}", ai_client=FakeAI()))
    hidden = client_without_flag.get(f"/api/v1/control/projects/{project['id']}", headers=headers).json()
    assert "brand_clarification" not in hidden["config"]
    body = {key: hidden[key] for key in ("revision", "name", "brand_name", "device_id", "config", "schedule", "queries")}
    body["name"] = "Renamed"
    saved = client_without_flag.put(f"/api/v1/control/projects/{project['id']}", headers=headers, json=body)
    assert saved.status_code == 200, saved.text
    with sessions() as db:
        assert json.loads(db.get(ControlProject, project["id"]).config_json)["brand_clarification"] == "Reflo — не наш бренд"


def test_rule_cycle_can_recompute_original_state_again(tmp_path, monkeypatch):
    class CyclingAI:
        def recompute(self, clarification, _content):
            found = clarification.endswith(" B")
            return type("Result", (), {"raw": json.dumps({"found": found,
                "mention_types": ["text"] if found else [], "quote": "Brand" if found else ""})})()

    client, headers, sessions = feature_setup(tmp_path, monkeypatch, CyclingAI())
    project = client.post("/api/v1/control/projects", headers=headers, json={
        "name": "P", "brand_name": "Brand", "queries": [{"text": "query"}],
        "config": {"services": ["chatgpt"], "brand_clarification": "Rule A"},
    }).json()
    today = utcnow().date().isoformat()
    with sessions() as db:
        row = CloudResult(user_id=FEATURE_USER, device_id="a" * 32, local_result_id=1,
            local_project_id=1, project_id=project["id"], query_id=project["queries"][0]["id"],
            project_name="P", brand_name="Brand", query_text="query", group_tag="", service="chatgpt",
            scan_date=today, status="found", answer_text="Brand", evidence_quote="Brand", sources_json="[]",
            mention_types_json='["text"]')
        db.add(row); db.commit(); result_id = row.id
    for note, expected in (("Rule A", "not_found"), ("Rule B", "found"), ("Rule A", "not_found")):
        if project["config"]["brand_clarification"] != note:
            body = {key: project[key] for key in ("revision", "name", "brand_name", "device_id", "config", "schedule", "queries")}
            body["config"] = {**body["config"], "brand_clarification": note}
            project = client.put(f"/api/v1/control/projects/{project['id']}", headers=headers, json=body).json()
        quoted = client.get(f"/api/v1/control/projects/{project['id']}/recompute/quote", headers=headers,
                            params={"from_date": today}).json()
        assert quoted["result_ids"] == [str(result_id)]
        result = client.post(f"/api/v1/control/projects/{project['id']}/recompute/{result_id}", headers=headers,
                             json={"from_date": today, "revision": project["revision"]})
        assert result.status_code == 200 and result.json()["charged_kopeks"] == 80
        with sessions() as db:
            assert db.get(CloudResult, result_id).status == expected
    with sessions() as db:
        assert db.get(Wallet, FEATURE_USER).balance_kopeks == 760
        assert db.query(LedgerEntry).filter_by(kind="recompute").count() == 3


def test_recompute_uses_saved_screenshot_and_full_text(tmp_path, monkeypatch):
    class StoredImage:
        def __init__(self): self.fail = False
        def read(self, _key):
            if self.fail: raise __import__("server.storage", fromlist=["StorageError"]).StorageError("missing")
            return b"RIFF0000WEBP"

    class EvidenceAI:
        def recompute(self, _clarification, content):
            assert "text-at-end" in content[0]["text"]
            assert "source-at-end" in content[0]["text"]
            assert content[1]["type"] == "image_url"
            return type("Result", (), {"raw": '{"found": true, "mention_types": ["card"], "quote": "Brand"}'})()

    storage = StoredImage()
    client, headers, sessions = feature_setup(tmp_path, monkeypatch, EvidenceAI(), storage)
    project = client.post("/api/v1/control/projects", headers=headers, json={
        "name": "P", "brand_name": "Brand", "queries": [{"text": "query"}],
        "config": {"services": ["chatgpt"], "brand_clarification": "Only Brand"},
    }).json()
    today = utcnow().date().isoformat()
    with sessions() as db:
        check = Check(user_id=FEATURE_USER, client_check_id="check", price_kopeks=0, status="settled")
        db.add(check); db.flush()
        db.add(Screenshot(check_id=check.id, object_key="saved.webp", size_bytes=12))
        row = CloudResult(user_id=FEATURE_USER, device_id="a" * 32, local_result_id=1,
            local_project_id=1, project_id=project["id"], query_id=project["queries"][0]["id"],
            project_name="P", brand_name="Brand", query_text="query", group_tag="", service="chatgpt",
            scan_date=today, status="found", answer_text="x" * 12000 + "text-at-end",
            sources_json=json.dumps(["x" * 4000 + "source-at-end"]), mention_types_json='["card"]', check_id="check")
        db.add(row); db.commit(); result_id = row.id
    storage.fail = True
    failed = client.post(f"/api/v1/control/projects/{project['id']}/recompute/{result_id}", headers=headers,
                         json={"from_date": today, "revision": project["revision"]})
    assert failed.json()["charged_kopeks"] == 0 and failed.json()["status"] == "error"
    storage.fail = False
    result = client.post(f"/api/v1/control/projects/{project['id']}/recompute/{result_id}", headers=headers,
                         json={"from_date": today, "revision": project["revision"]})
    assert result.status_code == 200 and result.json()["charged_kopeks"] == 80


def test_recompute_skips_unsaved_deep_source_evidence(tmp_path, monkeypatch):
    client, headers, sessions = feature_setup(tmp_path, monkeypatch)
    project = client.post("/api/v1/control/projects", headers=headers, json={
        "name": "P", "brand_name": "Brand", "queries": [{"text": "query"}],
        "config": {"services": ["chatgpt"], "brand_clarification": "Only Brand"},
    }).json()
    today = utcnow().date().isoformat()
    with sessions() as db:
        row = CloudResult(user_id=FEATURE_USER, device_id="a" * 32, local_result_id=1,
            local_project_id=1, project_id=project["id"], query_id=project["queries"][0]["id"],
            project_name="P", brand_name="Brand", query_text="query", group_tag="", service="chatgpt",
            scan_date=today, status="found", answer_text="A cited page was fetched separately",
            sources_json='["https://source.example"]', mention_types_json='["source"]')
        db.add(row); db.commit(); result_id = row.id
    quote = client.get(f"/api/v1/control/projects/{project['id']}/recompute/quote", headers=headers,
                       params={"from_date": today}).json()
    assert quote["count"] == 0 and quote["skipped"] == 1
    result = client.post(f"/api/v1/control/projects/{project['id']}/recompute/{result_id}", headers=headers,
                         json={"from_date": today, "revision": project["revision"]}).json()
    assert result["status"] == "skipped" and result["charged_kopeks"] == 0
    with sessions() as db:
        assert db.get(Wallet, FEATURE_USER).balance_kopeks == 1000
        assert db.get(CloudResult, result_id).status == "found"


def test_recompute_skips_image_only_positive_with_text_label(tmp_path, monkeypatch):
    client, headers, sessions = feature_setup(tmp_path, monkeypatch)
    project = client.post("/api/v1/control/projects", headers=headers, json={
        "name": "P", "brand_name": "Brand", "queries": [{"text": "query"}],
        "config": {"services": ["chatgpt"], "brand_clarification": "Only Brand"},
    }).json()
    today = utcnow().date().isoformat()
    with sessions() as db:
        row = CloudResult(user_id=FEATURE_USER, device_id="a" * 32, local_result_id=1,
            local_project_id=1, project_id=project["id"], query_id=project["queries"][0]["id"],
            project_name="P", brand_name="Brand", query_text="query", group_tag="", service="chatgpt",
            scan_date=today, status="found", answer_text="Unrelated visible text", evidence_quote="Brand logo",
            sources_json="[]", mention_types_json='["text"]')
        db.add(row); db.commit(); result_id = row.id
    quote = client.get(f"/api/v1/control/projects/{project['id']}/recompute/quote", headers=headers,
                       params={"from_date": today}).json()
    assert quote["count"] == 0 and quote["skipped"] == 1
    result = client.post(f"/api/v1/control/projects/{project['id']}/recompute/{result_id}", headers=headers,
                         json={"from_date": today, "revision": project["revision"]}).json()
    assert result["status"] == "skipped" and result["charged_kopeks"] == 0
    with sessions() as db:
        assert db.get(Wallet, FEATURE_USER).balance_kopeks == 1000
        assert db.get(CloudResult, result_id).status == "found"


def test_text_only_recompute_can_be_repeated_after_model_paraphrases_quote(tmp_path, monkeypatch):
    class ParaphraseAI:
        def recompute(self, _clarification, _content):
            return type("Result", (), {"raw": '{"found": true, "mention_types": ["text"], "quote": "paraphrase"}'})()

    client, headers, sessions = feature_setup(tmp_path, monkeypatch, ParaphraseAI())
    project = client.post("/api/v1/control/projects", headers=headers, json={
        "name": "P", "brand_name": "Brand", "queries": [{"text": "query"}],
        "config": {"services": ["chatgpt"], "brand_clarification": "Rule A"},
    }).json()
    today = utcnow().date().isoformat()
    with sessions() as db:
        row = CloudResult(user_id=FEATURE_USER, device_id="a" * 32, local_result_id=1,
            local_project_id=1, project_id=project["id"], query_id=project["queries"][0]["id"],
            project_name="P", brand_name="Brand", query_text="query", group_tag="", service="chatgpt",
            scan_date=today, status="found", answer_text="Brand in the answer", evidence_quote="Brand",
            sources_json="[]", mention_types_json='["text"]')
        db.add(row); db.commit(); result_id = row.id
    route = f"/api/v1/control/projects/{project['id']}/recompute/{result_id}"
    assert client.post(route, headers=headers, json={"from_date": today,
        "revision": project["revision"]}).json()["charged_kopeks"] == 80
    body = {key: project[key] for key in ("revision", "name", "brand_name", "device_id", "config", "schedule", "queries")}
    body["config"] = {**body["config"], "brand_clarification": "Rule B"}
    changed = client.put(f"/api/v1/control/projects/{project['id']}", headers=headers, json=body).json()
    quote = client.get(f"/api/v1/control/projects/{project['id']}/recompute/quote", headers=headers,
                       params={"from_date": today}).json()
    assert quote["result_ids"] == [str(result_id)]
    assert client.post(route, headers=headers, json={"from_date": today,
        "revision": changed["revision"]}).json()["charged_kopeks"] == 80
