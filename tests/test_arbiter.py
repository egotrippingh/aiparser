"""Арбитр: спорные строки решает вторая модель, а не человек.

Спорная строка — та, где правила молчат, а первая модель сказала «найдено».
Сеть не нужна: вызов модели подменён. Проверяется то, за что отвечает арбитр:
решение окончательно (пометка снимается), «не найдено» не тащит за собой
цитату первой модели, а несостоявшийся вызов пометку НЕ снимает.
"""

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db = Path(tempfile.gettempdir()) / "aiparser_test_arbiter.db"
_tmp_db.unlink(missing_ok=True)

from app import config  # noqa: E402

config.DB_PATH = _tmp_db

from fastapi.testclient import TestClient  # noqa: E402

from app.api import create_app  # noqa: E402
from app.db import repo  # noqa: E402
from app.detect import recheck  # noqa: E402
from app.detect.llm import LLMVerdict  # noqa: E402
from app.detect.merge import MergedVerdict, merge, with_arbiter  # noqa: E402
from app.detect.rules import RuleVerdict  # noqa: E402

client = TestClient(create_app())
_n = 0
calls: list[dict] = []
ANSWERS: dict[str, LLMVerdict] = {}


async def fake_arbitrate(**kw) -> LLMVerdict:
    calls.append(kw)
    return ANSWERS.get(kw["answer_text"], LLMVerdict(found=False, confidence=0.9, model="test/arbiter"))


recheck.llm_mod.arbitrate = fake_arbitrate
recheck.billing.enabled = lambda: True


def _project_with_review(answers: list[tuple[str, bool]]) -> tuple[int, list[int]]:
    """Проект, где каждый ответ уже записан как спорный (found + needs_review)."""
    global _n
    _n += 1
    pid = repo.create_project(f"Арбитр {_n}", "Геософт", brand_domains=["geosoft-dent.ru"])
    repo.add_queries(pid, [f"запрос {i}" for i in range(len(answers))])
    qs = repo.list_queries(pid)
    scan_id = repo.create_scan(pid, ["perplexity"], {"billing_run_id": f"test-run-{_n}"})
    ids = []
    for q, (text, _) in zip(qs, answers):
        repo.save_result(scan_id, q["id"], "perplexity", "found", mention_types=["indirect"],
                         confidence=0.7, evidence_quote="так сказала первая модель",
                         answer_text=text, sources=["https://example.com"],
                         detected_by="llm", needs_review=True, llm_model="test/first")
    for r in repo.results_for_review(pid):
        ids.append(r["id"])
    return pid, ids


def test_arbiter_confirms_and_clears_the_flag():
    v = LLMVerdict(found=True, mention_types=["indirect"], confidence=0.88, quote="дистрибьютор Геософт",
                   model="test/arbiter")
    m = with_arbiter(MergedVerdict(status="found", evidence_quote="старая цитата"), v)
    assert (m.status, m.needs_review, m.detected_by) == ("found", False, "arbiter")
    assert m.evidence_quote == "дистрибьютор Геософт" and m.confidence == 0.88


def test_arbiter_rejects_and_drops_the_quote():
    m = with_arbiter(MergedVerdict(status="found", evidence_quote="выдумка первой модели"),
                     LLMVerdict(found=False, confidence=0.95, model="test/arbiter"))
    assert (m.status, m.needs_review, m.mention_types) == ("not_found", False, [])
    assert m.evidence_quote is None


def test_scan_marks_review_only_without_arbiter():
    # Исходное состояние спорной строки: правила молчат, модель нашла.
    rule = RuleVerdict(found=False)
    llm = LLMVerdict(found=True, mention_types=["indirect"], confidence=0.8, quote="цитата", model="test/first")
    m = merge(rule, llm, confidence_threshold=0.6)
    assert m.needs_review and m.status == "found"


def test_recheck_resolves_all_and_updates_db():
    ANSWERS.clear()
    ANSWERS["есть упоминание"] = LLMVerdict(found=True, mention_types=["text"], confidence=0.9,
                                            quote="Геософт Дент", model="test/arbiter")
    pid, ids = _project_with_review([("есть упоминание", True), ("нет упоминания", False)])
    out = asyncio.run(recheck.recheck_project(pid))
    assert (out["total"], out["resolved"], out["failed"]) == (2, 2, 0)
    assert (out["found"], out["not_found"], out["changed"]) == (1, 1, 1)
    assert repo.results_for_review(pid) == []

    rows = {r["answer_text"]: r for r in repo.results_for_scan(repo.latest_scan(pid)["id"])}
    ok = rows["есть упоминание"]
    assert (ok["status"], ok["needs_review"], ok["detected_by"]) == ("found", 0, "arbiter")
    assert ok["evidence_quote"] == "Геософт Дент" and ok["llm_model"] == "test/arbiter"
    no = rows["нет упоминания"]
    assert (no["status"], no["needs_review"]) == ("not_found", 0)
    assert no["evidence_quote"] is None


def test_failed_arbiter_call_keeps_the_flag():
    ANSWERS.clear()
    ANSWERS["сеть отвалилась"] = LLMVerdict(found=False, model="test/arbiter", error="ConnectError")
    pid, _ = _project_with_review([("сеть отвалилась", False)])
    out = asyncio.run(recheck.recheck_project(pid))
    assert (out["resolved"], out["failed"]) == (0, 1)
    # Вердикт первой модели молча принимать нельзя — строка ждёт дальше.
    assert len(repo.results_for_review(pid)) == 1


def test_external_check_does_not_clear_the_flag():
    # update_result_mention без needs_review не трогает пометку: проверка
    # внешних источников о ручной проверке ничего не знает.
    pid, ids = _project_with_review([("внешний источник", True)])
    repo.update_result_mention(ids[0], status="found", mention_types=["source"],
                               evidence_quote="На сайте-источнике…", detected_by="deep", confidence=0.9)
    assert len(repo.results_for_review(pid)) == 1


def test_review_endpoints():
    ANSWERS.clear()
    pid, _ = _project_with_review([("нет упоминания", False)])
    r = client.get(f"/api/projects/{pid}/review")
    assert r.status_code == 200 and r.json()["pending"] == 1
    r = client.post(f"/api/projects/{pid}/review/resolve")
    assert r.status_code == 200, r.text
    assert r.json()["resolved"] == 1
    assert client.get(f"/api/projects/{pid}/review").json()["pending"] == 0
    assert client.get("/api/projects/99999/review").status_code == 404


if __name__ == "__main__":
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
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
