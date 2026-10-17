import asyncio
import threading
from pathlib import Path

from app import billing, config
from app.db import repo
from app.detect import llm
from app.detect.llm import LLMVerdict
from app.detect.merge import merge, should_call_llm
from app.detect.rules import RuleVerdict, evaluate
from app.detect import recheck


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


def test_text_candidate_is_checked_in_smart_mode_but_own_domain_is_not():
    assert should_call_llm(RuleVerdict(found=True, mention_types=["text"], semantic_required=True), "smart")
    assert not should_call_llm(RuleVerdict(found=True, mention_types=["link"]), "smart")


def test_verified_domain_keeps_fast_path_when_text_also_matches():
    rule = evaluate("Brand recommended", ["https://brand.example/about"], "Brand", [], ["brand.example"])
    assert rule.found and not rule.semantic_required


def test_candidate_low_confidence_positive_or_negative_requires_arbiter():
    rule = RuleVerdict(found=True, mention_types=["text"], semantic_required=True)
    low_positive = LLMVerdict(found=True, confidence=0.2, model="test")
    low_negative = LLMVerdict(found=False, confidence=0.2, model="test")
    assert merge(rule, low_positive, confidence_threshold=0.6).needs_review
    assert merge(RuleVerdict(found=False), low_negative, confidence_threshold=0.6).needs_review


def test_missing_negative_confidence_does_not_request_arbiter():
    result = merge(RuleVerdict(found=True, semantic_required=True),
                   LLMVerdict(found=False, model="test"), confidence_threshold=0.6)
    assert result.status == "not_found" and not result.needs_review


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
