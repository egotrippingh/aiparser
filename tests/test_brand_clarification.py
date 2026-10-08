import asyncio
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

from app import billing, config
from app.db import repo
from app.detect import llm
from app.detect.llm import LLMVerdict
from app.detect.merge import merge
from app.detect.rules import RuleVerdict
from app.detect import recheck
from app.scanner import orchestrator


def test_legacy_project_db_gains_clarification_and_materializes_snapshot(tmp_path, monkeypatch):
    legacy = sqlite3.connect(":memory:")
    legacy.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, parallel_scan INTEGER NOT NULL DEFAULT 0)")
    repo._migrate(legacy)
    assert "brand_clarification" in {row[1] for row in legacy.execute("PRAGMA table_info(projects)")}

    monkeypatch.setattr(repo, "_local", threading.local())
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    repo.init_db()
    project_id, _ = __import__("app.control_agent", fromlist=["materialize"]).materialize({
        "id": "run", "created_at": "2026-10-01T00:00:00+00:00",
        "snapshot": {"id": "cloud-project", "name": "Project", "brand_name": "Brand",
                     "config": {"brand_aliases": [], "brand_domains": [], "brand_clarification": "Only the Moscow firm",
                                "region_code": "213", "parallel": False, "speed_profile": "balanced"},
                     "queries": [{"id": "cloud-query", "text": "query", "group_tag": "", "active": True}],
                     "schedule": {}},
    }, "user")
    assert repo.get_project(project_id)["brand_clarification"] == "Only the Moscow firm"


def test_clarification_is_in_primary_and_arbiter_prompts(monkeypatch):
    seen = []

    async def ask(*args):
        seen.append(args[2][0]["text"])
        return {"model": "test", "raw": '{"found": false}'}

    monkeypatch.setattr(billing, "analyze", ask)
    monkeypatch.setattr(billing, "arbitrate", ask)
    kwargs = {"brand_name": "Brand", "aliases": [], "answer_text": "answer", "sources": [],
              "screenshot_bytes": None, "api_key": "", "model": "test", "managed_check_id": "run:1:chatgpt",
              "brand_clarification": "Only the Moscow firm"}
    asyncio.run(llm.evaluate(**kwargs))
    asyncio.run(llm.arbitrate(**kwargs, domains=[], first_quote="quote"))
    assert all("Only the Moscow firm" in prompt for prompt in seen)


def test_clarification_negative_verdict_overrides_rule_but_empty_keeps_rule():
    rule = RuleVerdict(found=True, mention_types=["text"], evidence_quote="Brand")
    negative = LLMVerdict(found=False, model="test")
    assert merge(rule, negative, confidence_threshold=0.6, semantic_authoritative=True).status == "not_found"
    assert merge(rule, negative, confidence_threshold=0.6).status == "found"


def test_clarification_forces_semantic_check_and_failure_is_not_billed(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "_local", threading.local())
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    repo.init_db()
    project_id = repo.create_project("Project", "Brand", brand_clarification="Only the Moscow firm")
    repo.add_queries(project_id, ["query"])
    scan_id = repo.create_scan(project_id, ["chatgpt"], {})
    controller = orchestrator.ScanController(scan_id, project_id, 1, "2026-10-01", billing_run_id="run")

    class Adapter:
        async def ask(self, *_args, **_kwargs):
            pass

        async def capture(self, *_args):
            return SimpleNamespace(shown=True, screenshot_bytes=b"raw", answer_text="Brand", sources=[], extra={})

    called = []
    async def unavailable(**kwargs):
        called.append(kwargs["brand_clarification"])
        return LLMVerdict(found=False, error="model unavailable")

    monkeypatch.setattr(orchestrator.imaging, "to_webp", lambda _: b"webp")
    monkeypatch.setattr(orchestrator.config, "screenshot_dir", lambda *_: tmp_path)
    monkeypatch.setattr(orchestrator.llm_mod, "evaluate", unavailable)
    status = asyncio.run(orchestrator._run_one(
        repo.get_project(project_id), repo.list_queries(project_id)[0], "chatgpt", Adapter(), object(),
        {"managed_llm": False, "llm_confidence_threshold": 0.6, "arbiter": False},
        1, "", "test", "never", controller,
    ))
    assert status == "error" and called == ["Only the Moscow firm"]
    assert repo.pending_billing() == []


def test_clarification_does_not_allow_cached_deep_rule_to_override_semantic_negative(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "_local", threading.local())
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    repo.init_db()
    project_id = repo.create_project("Project", "Brand", deep_check_depth=1, brand_clarification="Only the Moscow firm")
    repo.add_queries(project_id, ["query"])
    scan_id = repo.create_scan(project_id, ["chatgpt"], {})
    controller = orchestrator.ScanController(scan_id, project_id, 1, "2026-10-01")

    class Adapter:
        async def ask(self, *_args, **_kwargs): pass
        async def capture(self, *_args):
            return SimpleNamespace(shown=True, screenshot_bytes=b"raw", answer_text="answer",
                                   sources=["https://example.test"], extra={})

    async def negative(**_kwargs):
        return LLMVerdict(found=False, model="test")

    async def unexpected(*_args, **_kwargs):
        raise AssertionError("clarified scan must not reuse deep-rule cache")

    monkeypatch.setattr(orchestrator.imaging, "to_webp", lambda _: b"webp")
    monkeypatch.setattr(orchestrator.config, "screenshot_dir", lambda *_: tmp_path)
    monkeypatch.setattr(orchestrator.llm_mod, "evaluate", negative)
    monkeypatch.setattr(orchestrator.deep_mod, "check_sources", unexpected)
    status = asyncio.run(orchestrator._run_one(
        repo.get_project(project_id), repo.list_queries(project_id)[0], "chatgpt", Adapter(), object(),
        {"managed_llm": True, "llm_confidence_threshold": 0.6, "arbiter": False},
        1, "", "test", "never", controller,
    ))
    assert status == "not_found"


def test_recheck_uses_current_clarification(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "_local", threading.local())
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "agent.db")
    repo.init_db()
    project_id = repo.create_project("Project", "Brand", brand_clarification="Current identity")
    repo.add_queries(project_id, ["query"])
    query = repo.list_queries(project_id)[0]
    scan_id = repo.create_scan(project_id, ["chatgpt"], {"billing_run_id": "run"})
    repo.save_result(scan_id, query["id"], "chatgpt", "found", answer_text="answer", needs_review=True)
    seen = []

    async def arbitrate(**kwargs):
        seen.append(kwargs["brand_clarification"])
        return LLMVerdict(found=False, model="test")

    monkeypatch.setattr(recheck.billing, "enabled", lambda: True)
    monkeypatch.setattr(recheck.llm_mod, "arbitrate", arbitrate)
    assert asyncio.run(recheck.recheck_project(project_id))["resolved"] == 1
    assert seen == ["Current identity"]
