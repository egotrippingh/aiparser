"""A resumed service must retry old errors and retain failures in its snapshot."""

import asyncio

import pytest

from app.scanner import orchestrator as mod


@pytest.mark.parametrize("completed_first", [False, True])
def test_retry_ignores_old_error_rows(monkeypatch, completed_first):
    ctl = mod.ScanController(91, 2, 2, "2026-09-26")
    queries = [{"id": 1}, {"id": 2}]
    rows = [{"query_id": q["id"], "service": "chatgpt", "status": "auth_required"}
            for q in queries]
    calls, finished = [], []

    async def run_service(project, service, pending, *args):
        calls.append([q["id"] for q in pending])
        if len(calls) == 1:
            if completed_first:
                rows[0]["status"] = "found"
                ctl.advance(service, 1)
            raise RuntimeError("renderer failed")
        for q in pending:
            rows[q["id"] - 1]["status"] = "found"
            ctl.advance(service, q["id"])

    monkeypatch.setattr(mod, "_run_service", run_service)
    monkeypatch.setattr(mod.repo, "results_for_scan", lambda _: rows)
    monkeypatch.setattr(mod.repo, "finish_scan", lambda _, status: finished.append(status))
    asyncio.run(mod._run_scan({"parallel_scan": True}, ["chatgpt"], queries, set(),
                             {"llm_mode": "never", "typing_speed": 1}, ctl))
    assert calls == [[1, 2], [2] if completed_first else [1, 2]]
    assert ctl.done == 2
    assert finished == ["done"]


def test_service_failure_remains_in_snapshot(monkeypatch):
    ctl = mod.ScanController(92, 2, 1, "2026-09-26")

    async def fail(*args):
        raise RuntimeError("composer unavailable")

    monkeypatch.setattr(mod, "_run_service", fail)
    monkeypatch.setattr(mod.repo, "results_for_scan", lambda _: [])
    monkeypatch.setattr(mod.repo, "finish_scan", lambda *args, **kwargs: None)
    asyncio.run(mod._run_scan({"parallel_scan": True}, ["chatgpt"], [{"id": 1}], set(),
                             {"llm_mode": "never", "typing_speed": 1}, ctl))
    snap = ctl.snapshot()
    assert snap["running_services"] == []
    assert snap["services"]["chatgpt"] == {
        "done": 0, "total": 1, "state": "failed", "error": "composer unavailable",
    }
