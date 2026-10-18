"""The selected primary runs once; uncertainty, rather than every answer, needs an arbiter."""

import json

import pytest
from sqlalchemy import select

from server.ai import AIError, AIResult
from server.models import Check, CloudResult, ControlRun
from server.test_cloud_scans import Collector, project_and_run, setup, tick


class RouteAI:
    model = "qwen/qwen3.8-flash"
    arbiter_model = "deepseek/deepseek-v4-pro-0813"

    def __init__(self, found, confidence, *, fail_arbiter_once=False):
        self.found, self.confidence = found, confidence
        self.fail_arbiter_once = fail_arbiter_once
        self.primary_calls = self.arbiter_calls = 0

    def analyze(self, system, content):
        self.primary_calls += 1
        return AIResult(json.dumps({"found": self.found, "confidence": self.confidence}),
                        self.model, {"cost": 0.0001})

    def arbitrate(self, system, content):
        self.arbiter_calls += 1
        if self.fail_arbiter_once and self.arbiter_calls == 1:
            raise AIError("temporary transport failure")
        return AIResult('{"found":false,"confidence":0.95}', self.arbiter_model,
                        {"cost": 0.0002})


@pytest.mark.parametrize("answer,found,confidence,arbiters,status", [
    ("No recommendation in this answer.", False, 0.95, 0, "not_found"),
    ("Brand is recommended.", True, 0.95, 0, "found"),
    ("No recommendation in this answer.", False, 0.1, 1, "not_found"),
    ("Brand is recommended.", True, 0.1, 1, "not_found"),
    ("An indirect recommendation.", True, 0.95, 1, "not_found"),
])
def test_only_uncertain_answers_need_the_second_model(
        tmp_path, monkeypatch, answer, found, confidence, arbiters, status):
    ai = RouteAI(found, confidence)
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai)
    monkeypatch.setattr(Collector, "calls", [])
    monkeypatch.setattr(Collector, "answer", {
        "shown": True, "main_text": answer, "answer_text": answer,
        "cards_text": "", "sources": [], "source_cards": [], "products": [],
    })
    project_and_run(client, owner)
    assert tick(sessions, ai)
    assert (ai.primary_calls, ai.arbiter_calls) == (1, arbiters)
    assert len(Collector.calls) == 1
    with sessions() as db:
        result = db.scalar(select(CloudResult))
        check = db.scalar(select(Check))
        assert result.status == status
        assert check.analysis_attempts == 1 and check.arbitration_attempts == arbiters
        assert check.analysis_model == ai.model
        assert check.arbitration_model == (ai.arbiter_model if arbiters else None)
    client.close()


def test_arbiter_transport_retry_reuses_capture_and_successful_primary(tmp_path, monkeypatch):
    ai = RouteAI(False, 0.1, fail_arbiter_once=True)
    client, owner, _, _, sessions = setup(tmp_path, monkeypatch, ai=ai)
    monkeypatch.setattr(Collector, "calls", [])
    monkeypatch.setattr(Collector, "answer", {
        "shown": True, "main_text": "Nothing here.", "answer_text": "Nothing here.",
        "sources": [], "cards_text": "", "source_cards": [], "products": [],
    })
    project, run = project_and_run(client, owner)
    assert tick(sessions, ai)
    with sessions() as db:
        assert db.get(ControlRun, run["id"]).state == "paused"
        assert db.scalar(select(CloudResult)) is None
    response = client.post(f"/api/v1/control/runs/{run['id']}/command", headers=owner,
                           json={"action": "resume"})
    assert response.status_code == 200, response.text
    assert tick(sessions, ai)
    assert (ai.primary_calls, ai.arbiter_calls, len(Collector.calls)) == (1, 2, 1)
    with sessions() as db:
        check = db.scalar(select(Check))
        assert check.analysis_attempts == 1 and check.arbitration_attempts == 2
        assert db.scalar(select(CloudResult)).status == "not_found"
        assert db.get(ControlRun, run["id"]).state == "done"
    client.close()
