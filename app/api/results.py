"""Данные для дашборда: карточки метрик, ряды графика, таблица запросов."""

from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from app import services
from app.db import repo

router = APIRouter(prefix="/api", tags=["results"])

# Статусы, которые попадают в знаменатель видимости. Ошибка, требование логина
# и «AI-блок не показан» — это отсутствие данных, а не отсутствие бренда, и
# занижать ими процент нельзя.
COUNTED = ("found", "not_found")


def _pct(found: int, checked: int) -> float | None:
    return round(found * 100 / checked, 1) if checked else None


@router.get("/projects/{project_id}/dashboard")
def dashboard(project_id: int, days: int = 30, scan_id: int | None = None) -> dict:
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")

    scans = repo.list_scans(project_id, limit=days + 2)
    if not scans:
        return {
            "project": project,
            "empty": True,
            "days": [],
            "series": {},
            "cards": {},
            "rows": [],
            "scan": None,
            "prev_scan": None,
        }

    current = next((s for s in scans if s["id"] == scan_id), scans[0]) if scan_id else scans[0]
    prev = next((s for s in scans if s["started_at"] < current["started_at"]), None)

    # --- ряды графика -----------------------------------------------------
    raw = repo.visibility_by_day(project_id, days=days)
    day_list = sorted({r["scan_date"] for r in raw})[-days:]
    by_day: dict[tuple[str, str], dict] = {(r["scan_date"], r["service"]): r for r in raw}

    series: dict[str, list[float | None]] = {}
    for s in services.SERVICES:
        series[s.id] = [
            _pct(by_day[(d, s.id)]["found"], by_day[(d, s.id)]["checked"]) if (d, s.id) in by_day else None
            for d in day_list
        ]
    series["_total"] = []
    for d in day_list:
        f = sum(by_day[(d, s.id)]["found"] for s in services.SERVICES if (d, s.id) in by_day)
        c = sum(by_day[(d, s.id)]["checked"] for s in services.SERVICES if (d, s.id) in by_day)
        series["_total"].append(_pct(f, c))

    # --- таблица и карточки ----------------------------------------------
    rows_now = repo.results_for_scan(current["id"])
    rows_prev = repo.results_for_scan(prev["id"]) if prev else []
    prev_status = {(r["query_id"], r["service"]): r["status"] for r in rows_prev}

    per_query: dict[int, dict] = {}
    per_service: dict[str, dict[str, int]] = defaultdict(lambda: {"found": 0, "checked": 0})
    review_count = error_count = not_checked_count = 0

    for r in rows_now:
        q = per_query.setdefault(
            r["query_id"],
            {
                "query_id": r["query_id"],
                "text": r["query_text"],
                "group_tag": r["group_tag"],
                "statuses": {},
                "checked_at": r["created_at"],
            },
        )
        was = prev_status.get((r["query_id"], r["service"]))
        q["statuses"][r["service"]] = {
            "status": r["status"],
            "needs_review": bool(r["needs_review"]),
            "change": "new" if r["status"] == "found" and was == "not_found"
            else "lost" if r["status"] == "not_found" and was == "found"
            else None,
        }
        q["checked_at"] = max(q["checked_at"], r["created_at"])

        if r["status"] in COUNTED:
            per_service[r["service"]]["checked"] += 1
            if r["status"] == "found":
                per_service[r["service"]]["found"] += 1
        if r["needs_review"]:
            review_count += 1
        if r["status"] in ("error", "captcha", "auth_required"):
            error_count += 1
        # limit_reached — не ошибка программы, а неизрасходованная квота
        # аккаунта: запрос просто не проверяли. Считаем отдельно, чтобы не
        # выдавать исчерпанный тариф за сбой.
        if r["status"] == "limit_reached":
            not_checked_count += 1

    total_found = sum(v["found"] for v in per_service.values())
    total_checked = sum(v["checked"] for v in per_service.values())

    svc_cards = []
    for s in services.SERVICES:
        v = per_service.get(s.id)
        if not v:
            continue
        svc_cards.append({"id": s.id, "name": s.name, "pct": _pct(v["found"], v["checked"]), **v})
    ranked = sorted([c for c in svc_cards if c["pct"] is not None], key=lambda c: c["pct"])

    prev_total = None
    if len(series["_total"]) >= 2:
        prev_total = series["_total"][-2]
    now_total = _pct(total_found, total_checked)

    cards = {
        "visibility": now_total,
        "visibility_delta": round(now_total - prev_total, 1) if now_total is not None and prev_total is not None else None,
        "found": total_found,
        "checked": total_checked,
        "queries": len(per_query),
        "best": ranked[-1] if ranked else None,
        "worst": ranked[0] if ranked else None,
        "needs_review": review_count,
        "errors": error_count,
        "not_checked": not_checked_count,
        "by_service": svc_cards,
    }

    rows = sorted(per_query.values(), key=lambda q: q["text"])

    return {
        "project": project,
        "empty": False,
        "days": day_list,
        "series": series,
        "cards": cards,
        "rows": rows,
        "scan": current,
        "prev_scan": prev,
    }


def _cell_stats(found: int, checked: int) -> dict:
    return {"found": found, "checked": checked, "pct": _pct(found, checked)}


def _delta(now: float | None, before: float | None) -> float | None:
    return round(now - before, 1) if now is not None and before is not None else None


@router.get("/projects/{project_id}/overview")
def overview(project_id: int, days: int = 30) -> dict:
    """Всё для дашборда в виде Топвизора: даты в столбцах, запросы в строках.

    Одна дата — один срез: если за день было несколько сканов, на каждую пару
    «запрос × сервис» берётся один результат (repo.pick_result). Сводка сверху
    считается по тем же ячейкам, что и таблица, — цифры не расходятся.
    """
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")

    dates = repo.project_dates(project_id, max(1, min(days, 365)))
    results = repo.results_by_date(project_id, dates)

    cells: dict[int, dict[str, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    counts: dict[str, dict[str, list[int]]] = {d: defaultdict(lambda: [0, 0]) for d in dates}
    issues = {d: {"needs_review": 0, "errors": 0, "not_checked": 0} for d in dates}
    with_data: set[str] = set()

    for r in results:
        d, svc, status = r["scan_date"], r["service"], r["status"]
        cells[r["query_id"]][d][svc] = {
            "status": status,
            "needs_review": bool(r["needs_review"]),
            "result_id": r["id"],
        }
        with_data.add(svc)
        if status in COUNTED:
            for key in (svc, "_all"):
                counts[d][key][1] += 1
                if status == "found":
                    counts[d][key][0] += 1
        if r["needs_review"]:
            issues[d]["needs_review"] += 1
        if status in ("error", "captcha", "auth_required"):
            issues[d]["errors"] += 1
        if status == "limit_reached":
            issues[d]["not_checked"] += 1

    stats = {d: {k: _cell_stats(*v) for k, v in counts[d].items()} for d in dates}

    rows = []
    for q in repo.list_queries(project_id):
        qc = cells.get(q["id"])
        if not q["is_active"] and not qc:
            continue
        rows.append({
            "query_id": q["id"],
            "text": q["text"],
            "group_tag": q["group_tag"],
            "is_active": bool(q["is_active"]),
            "cells": {d: dict(v) for d, v in (qc or {}).items()},
        })

    summary = None
    if dates:
        last = dates[-1]
        prev = dates[-2] if len(dates) > 1 else None

        def pct_of(d: str | None, key: str) -> float | None:
            return stats[d].get(key, {}).get("pct") if d else None

        total = stats[last].get("_all", _cell_stats(0, 0))
        summary = {
            "date": last,
            "prev_date": prev,
            "total": {**total, "delta": _delta(total["pct"], pct_of(prev, "_all"))},
            "by_service": [
                {
                    "id": s.id,
                    "name": s.name,
                    **stats[last][s.id],
                    "delta": _delta(stats[last][s.id]["pct"], pct_of(prev, s.id)),
                }
                for s in services.SERVICES
                if s.id in stats[last]
            ],
            "queries": sum(1 for r in rows if last in r["cells"]),
            **issues[last],
        }

    return {
        "project": project,
        "dates": dates,
        "services": [s.id for s in services.SERVICES if s.id in with_data],
        "rows": rows,
        "stats": stats,
        "summary": summary,
    }


@router.get("/queries/{query_id}/detail")
def query_detail(query_id: int, scan_id: int | None = None, date: str | None = None) -> dict:
    """Карточка запроса: результат по каждому сервису плюс история по дням.

    `date` — срез дня (как в таблице overview), `scan_id` — один конкретный скан.
    """
    if date:
        rows = repo.query_results_on_date(query_id, date)
    elif scan_id is not None:
        rows = [r for r in repo.results_for_scan(scan_id) if r["query_id"] == query_id]
    else:
        raise HTTPException(400, "Нужен date или scan_id")
    if not rows:
        raise HTTPException(404, "Результатов по этому запросу в срезе нет")

    out = {}
    for r in rows:
        out[r["service"]] = {
            "status": r["status"],
            "mention_types": json.loads(r["mention_types_json"]),
            "confidence": r["confidence"],
            "evidence_quote": r["evidence_quote"],
            "answer_text": r["answer_text"],
            "sources": json.loads(r["sources_json"]),
            "screenshot": f"/shots/{r['screenshot_path']}" if r["screenshot_path"] else None,
            "detected_by": r["detected_by"],
            "needs_review": bool(r["needs_review"]),
            "llm_model": r["llm_model"],
            "error_message": r["error_message"],
            "history": repo.query_history(query_id, r["service"]),
        }

    return {"query_id": query_id, "text": rows[0]["query_text"], "by_service": out}
