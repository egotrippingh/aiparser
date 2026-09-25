"""Перерешение спорных строк арбитром — по уже сохранённым данным.

Строка «требует проверки» это та, где правила молчат, а первая модель сказала
«найдено»: именно там она чаще всего выдумывает. Вторая, более сильная модель
выносит окончательный вердикт, и пометка снимается — перепроверять руками
больше нечего. Браузер не нужен: берём сохранённые текст ответа, ссылки и
скриншот того самого прогона.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from app import billing, config
from app.db import repo
from app.detect import llm as llm_mod
from app.detect.merge import MergedVerdict, with_arbiter

log = logging.getLogger("aiparser.recheck")

# Больше — упираемся в лимиты OpenRouter, меньше — 94 строки идут слишком долго.
CONCURRENCY = 4


def arbiter_settings() -> tuple[str, str, bool]:
    """Model and key are owned by the account server."""
    return "", llm_mod.ARBITER_MODEL_DEFAULT, billing.enabled()


def _screenshot_bytes(rel_path: str | None) -> bytes | None:
    if not rel_path:
        return None
    p = Path(config.SCREENSHOTS_DIR) / rel_path
    try:
        return p.read_bytes()
    except OSError:
        return None


def apply_verdict(row: dict, verdict: llm_mod.LLMVerdict) -> dict:
    """Поля для записи в базу по решению арбитра — та же логика, что в скане."""
    before = MergedVerdict(status=row.get("status", "not_found"), evidence_quote=row.get("evidence_quote"))
    m = with_arbiter(before, verdict)
    return {
        "status": m.status,
        "mention_types": m.mention_types,
        "evidence_quote": m.evidence_quote,
        "confidence": m.confidence,
        "detected_by": m.detected_by,
        "needs_review": m.needs_review,
        "llm_model": m.llm_model,
    }


async def recheck_project(project_id: int, *, limit: int | None = None) -> dict:
    """Перерешает все спорные строки проекта. Возвращает сводку по изменениям."""
    project = repo.get_project(project_id)
    if not project:
        raise ValueError("Проект не найден")

    api_key, model, on = arbiter_settings()
    if not on:
        raise ValueError("Подключите агент к личному кабинету для серверного арбитража")

    rows = repo.results_for_review(project_id)
    if limit:
        rows = rows[:limit]
    out = {"total": len(rows), "resolved": 0, "found": 0, "not_found": 0, "failed": 0,
           "changed": 0, "model": model, "errors": []}
    if not rows:
        return out

    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(row: dict) -> None:
        snapshot = json.loads(row.get("settings_snapshot_json") or "{}")
        run_id = snapshot.get("billing_run_id")
        if not run_id:
            out["failed"] += 1
            if len(out["errors"]) < 5:
                out["errors"].append("Старая локальная проверка не привязана к оплаченному чеку")
            return
        async with sem:
            verdict = await llm_mod.arbitrate(
                brand_name=project["brand_name"],
                aliases=project["brand_aliases"],
                domains=project["brand_domains"],
                answer_text=row["answer_text"] or "",
                sources=json.loads(row["sources_json"] or "[]"),
                screenshot_bytes=_screenshot_bytes(row["screenshot_path"]),
                api_key=api_key,
                model=model,
                first_quote=row.get("evidence_quote") or "",
                query=row.get("query_text"),
                managed_check_id=billing.check_id(run_id, row["query_id"], row["service"]),
            )
        if verdict.error:
            out["failed"] += 1
            if len(out["errors"]) < 5:
                out["errors"].append(verdict.error)
            log.warning("Арбитр не ответил по результату %s: %s", row["id"], verdict.error)
            return

        fields = apply_verdict(row, verdict)
        repo.update_result_mention(row["id"], **fields)
        out["resolved"] += 1
        out["found" if fields["status"] == "found" else "not_found"] += 1
        if fields["status"] != row["status"]:
            out["changed"] += 1

    await asyncio.gather(*(one(r) for r in rows))
    log.info("Арбитр перерешил %s строк проекта %s: %s осталось «найдено», %s стало «не найдено», %s не удалось",
             out["resolved"], project_id, out["found"], out["not_found"], out["failed"])
    return out
