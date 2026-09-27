"""Calendar-based mention matrices and exports share the same daily measurements."""
import io
import json
from collections import Counter
from datetime import date, timedelta
from typing import Literal
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import load_only

from server.models import CloudResult, ControlProject, utcnow

SERVICES = {"google_aio": "Google AI Overview", "chatgpt": "ChatGPT", "perplexity": "Perplexity",
            "alice": "Алиса AI", "yandex_neuro": "Яндекс Нейро"}
LABELS = {"found": "Упоминание", "not_found": "Нет упоминания", "skipped": "Нет AI-блока",
          "error": "Ошибка", "captcha": "Капча", "auth_required": "Нужен вход", "limit_reached": "Лимит сервиса"}


class ReportOptions(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    compare: bool = False
    include_cards: bool = True
    service: str = Field(default="", max_length=40)
    group: str | None = Field(default=None, max_length=120)
    search: str = Field(default="", max_length=2000)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)
    date_offset: int = Field(default=0, ge=0)
    date_limit: int = Field(default=4, ge=1, le=14)


def owned_project(db, user_id, project_id):
    project = db.get(ControlProject, project_id)
    if not project or project.user_id != user_id or project.archived:
        raise HTTPException(404, "Проект не найден")
    return project


def found(row, cards):
    kinds = set(json.loads(row.mention_types_json or "[]"))
    return row.status == "found" and (cards or not kinds or bool(kinds - {"marketplace"}))


def empty_stats():
    return {"found": 0, "checked": 0, "issues": 0, "skipped": 0, "visibility_pct": None}


def count(stats, row, cards):
    if row.status in ("found", "not_found"):
        stats["checked"] += 1
        stats["found"] += int(found(row, cards))
        stats["visibility_pct"] = round(100 * stats["found"] / stats["checked"], 1)
    elif row.status == "skipped":
        stats["skipped"] += 1
    else:
        stats["issues"] += 1


def collect_report(db, project, options, *, with_sources=False):
    scope = (CloudResult.user_id == project.user_id, CloudResult.project_id == project.id)
    available_dates = list(db.scalars(select(CloudResult.scan_date).where(*scope).distinct()
                                      .order_by(CloudResult.scan_date)))
    end = options.date_to or (date.fromisoformat(available_dates[-1]) if available_dates else utcnow().date())
    start = options.date_from or end - timedelta(days=29)
    if start > end or (end - start).days > 365:
        raise HTTPException(422, "Выберите период от 1 до 366 дней, начало не позже конца")
    if options.service and options.service not in SERVICES:
        raise HTTPException(422, "Неизвестная ИИ-система")
    queries = {q["id"]: {"id": q["id"], "text": q["text"], "group_tag": q.get("group_tag", ""), "cells": {}}
               for q in json.loads(project.queries_json)}
    by_text = {q["text"]: q["id"] for q in queries.values()}
    columns = [
        CloudResult.id, CloudResult.query_id, CloudResult.query_text, CloudResult.group_tag,
        CloudResult.service, CloudResult.scan_date, CloudResult.status, CloudResult.mention_types_json,
    ]
    if with_sources:
        columns += [CloudResult.sources_json, CloudResult.evidence_quote]
    measurements = db.scalars(select(CloudResult).options(load_only(*columns)).where(
        *scope, CloudResult.scan_date >= start.isoformat(), CloudResult.scan_date <= end.isoformat(),
        CloudResult.service.in_([options.service] if options.service else SERVICES))
      .order_by(CloudResult.id.desc())).all()
    daily = {}
    for row in measurements:
        key = row.query_id if row.query_id in queries else by_text.get(row.query_text, row.query_id or "text:" + row.query_text)
        queries.setdefault(key, {"id": key, "text": row.query_text, "group_tag": row.group_tag or "", "cells": {}})
        daily.setdefault((key, row.service, row.scan_date), row)
    group_names = sorted({q["group_tag"] for q in queries.values() if q["group_tag"]}, key=str.casefold)
    queries = {key: q for key, q in queries.items()
               if (options.group is None or q["group_tag"] == options.group)
               and options.search.casefold() in q["text"].casefold()}
    daily = {key: row for key, row in daily.items() if key[0] in queries
             and (not options.service or row.service == options.service)}
    configured = json.loads(project.config_json).get("services", [])
    service_ids = [s for s in SERVICES if s in set(configured) | {key[1] for key in daily}]
    if options.service:
        service_ids = [options.service]
    dates = sorted({key[2] for key in daily})
    table_dates = sorted({start.isoformat(), end.isoformat()}) if options.compare else dates
    # Page dates from the most recent measurements, then present each window chronologically.
    window = table_dates if options.compare else sorted(list(reversed(table_dates))[options.date_offset:options.date_offset + options.date_limit])
    summary = empty_stats()
    by_date = {}
    for i in range((end - start).days + 1):
        day = (start + timedelta(days=i)).isoformat()
        by_date[day] = {**empty_stats(), "services": {s: empty_stats() for s in service_ids}}
    selected_measurements = []
    for (key, service_id, day), row in daily.items():
        count(by_date[day], row, options.include_cards)
        count(by_date[day]["services"][service_id], row, options.include_cards)
        if not options.compare or day in table_dates:
            count(summary, row, options.include_cards)
            selected_measurements.append((queries[key], row))
        queries[key]["cells"].setdefault(day, {})[service_id] = {
            "id": row.id, "status": row.status, "found": bool(found(row, options.include_cards))}
    rows = list(queries.values())
    comparison = {"from": by_date[start.isoformat()], "to": by_date[end.isoformat()]}
    left, right = comparison["from"]["visibility_pct"], comparison["to"]["visibility_pct"]
    comparison["delta"] = round(right - left, 1) if left is not None and right is not None else None
    return {"date_from": start.isoformat(), "date_to": end.isoformat(), "available_dates": available_dates,
            "dates": table_dates, "visible_dates": window, "services": service_ids, "groups": group_names,
            "summary": summary, "comparison": comparison,
            "timeline": [{"date": d, **stats} for d, stats in by_date.items()],
            "total": len(rows), "rows": rows, "measurements": selected_measurements,
            "filters": {"include_cards": options.include_cards, "group": options.group,
                        "service": options.service, "search": options.search, "compare": options.compare}}


def workbook(report, project, kind):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook(write_only=True)
    def sheet(title, headers, widths):
        ws = wb.create_sheet(title)
        ws.freeze_panes = "C2" if kind == "mentions" else "A2"
        for i, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = width
        header = []
        for value in headers:
            cell = WriteOnlyCell(ws, value=ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="493266")
            header.append(cell)
        ws.append(header)
        return ws
    def append(ws, values):
        # Prompts and external pages are untrusted: export all strings as text, never formulas.
        cells = []
        for value in values:
            cell = WriteOnlyCell(ws, value=ILLEGAL_CHARACTERS_RE.sub("", value) if isinstance(value, str) else value)
            if isinstance(value, str):
                cell.data_type = "s"
            cells.append(cell)
        ws.append(cells)
    if kind == "mentions":
        columns = [(d, s) for d in report["dates"] for s in report["services"]]
        if len(columns) * len(report["rows"]) > 2_000_000:
            raise HTTPException(422, "Выгрузка слишком большая. Сократите период или выберите группу.")
        ws = sheet("Упоминаемость", ["Запрос", "Группа"] + [f"{d} · {SERVICES[s]}" for d, s in columns],
                   [65, 25] + [28] * len(columns))
        for q in report["rows"]:
            values = [q["text"], q["group_tag"]]
            for day, service in columns:
                cell = q["cells"].get(day, {}).get(service)
                values.append("Не проверялся" if cell is None else "Карточки исключены" if cell["status"] == "found" and not cell["found"]
                              else LABELS.get(cell["status"], cell["status"]))
            append(ws, values)
    else:
        domains = json.loads(project.config_json).get("brand_domains", [])
        own = set()
        for domain in domains:
            try:
                host = urlsplit(domain if "://" in domain else "https://" + domain).hostname
                if host:
                    own.add(host.lower().removeprefix("www."))
            except ValueError:
                continue
        ws = sheet("Внешние источники", ["Источник", "Домен", "Дата", "ИИ-система", "Запрос", "Группа", "Контекст в ответе ИИ"],
                   [65, 28, 14, 24, 65, 25, 90])
        counts = Counter()
        for query, row in report["measurements"]:
            for source in dict.fromkeys(json.loads(row.sources_json or "[]")):
                try:
                    parsed = urlsplit(source)
                    host = (parsed.hostname or "").lower()
                except ValueError:
                    continue
                if parsed.scheme not in ("http", "https") or not host or any(
                    host == d or host.endswith("." + d) for d in own if d):
                    continue
                counts[host] += 1
                append(ws, [source, host, row.scan_date, SERVICES.get(row.service, row.service),
                            query["text"], query["group_tag"], row.evidence_quote or ""])
        stats = sheet("Домены", ["Домен", "Ссылок в ответах"], [45, 24])
        for host, number in counts.most_common():
            append(stats, [host, number])
    notes = sheet("О выгрузке", ["Параметр", "Значение"], [30, 100])
    append(notes, ["Проект", project.name])
    append(notes, ["Период", report["date_from"] + " — " + report["date_to"]])
    filters = report["filters"]
    append(notes, ["Режим", "Сравнение двух дат" if filters["compare"] else "За период"])
    append(notes, ["Карточки товаров", "Учитываются" if filters["include_cards"] else "Исключены из упоминаний"])
    append(notes, ["Группа", "Все группы" if filters["group"] is None else filters["group"] or "Без группы"])
    append(notes, ["ИИ-система", SERVICES.get(filters["service"], "Все системы")])
    append(notes, ["Поиск", filters["search"]])
    append(notes, ["Упоминаемость", "Доля ответов с упоминанием среди успешных проверок. Ошибки и отсутствие AI-блока не входят в знаменатель."])
    append(notes, ["Внешние источники", "Сохранённые ссылки из ответов ИИ, без доменов бренда. Контекст — фрагмент ответа ИИ, не цитата с внешнего сайта."])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def register_reports(app, db_session, current_user):
    router = APIRouter(prefix="/api/v1/control/projects/{project_id}/mentions")

    @router.get("")
    def report(project_id: str, options: ReportOptions = Depends(), user=Depends(current_user), db=Depends(db_session)):
        data = collect_report(db, owned_project(db, user.id, project_id), options)
        data.pop("measurements")
        data["rows"] = [{**q, "cells": {d: cells for d, cells in q["cells"].items() if d in data["visible_dates"]}}
                        for q in data["rows"][options.offset:options.offset + options.limit]]
        return data

    @router.get("/results/{result_id}")
    def detail(project_id: str, result_id: int, user=Depends(current_user), db=Depends(db_session)):
        owned_project(db, user.id, project_id)
        row = db.get(CloudResult, result_id)
        if not row or row.user_id != user.id or row.project_id != project_id:
            raise HTTPException(404, "Результат не найден")
        return {"query_text": row.query_text, "service": row.service, "scan_date": row.scan_date,
                "status": row.status, "answer_text": row.answer_text, "evidence_quote": row.evidence_quote,
                "sources": json.loads(row.sources_json or "[]"), "check_id": row.check_id}

    @router.get("/export/{kind}")
    def export(project_id: str, kind: Literal["mentions", "sources"], options: ReportOptions = Depends(),
               user=Depends(current_user), db=Depends(db_session)):
        project = owned_project(db, user.id, project_id)
        data = collect_report(db, project, options, with_sources=kind == "sources")
        filename = f"{kind}-{project.id[:8]}-{data['date_from']}-{data['date_to']}.xlsx"
        return Response(workbook(data, project, kind), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}", "Cache-Control": "no-store"})

    app.include_router(router)
