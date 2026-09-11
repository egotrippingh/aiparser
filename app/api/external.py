"""Внешние источники среза: проверка сайтов и выгрузка в Excel."""

from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.api.results import _check_date as check_date_param
from app.db import repo
from app.detect import external

router = APIRouter(prefix="/api/projects/{project_id}/external-sources", tags=["external"])


def _resolve(project_id: int, date: str | None) -> tuple[dict, str]:
    project = repo.get_project(project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    date = check_date_param(date, "date")
    if not date:
        dates = repo.scan_dates(project_id)
        if not dates:
            raise HTTPException(404, "По проекту ещё не было сканов")
        date = dates[-1]["date"]
    return project, date


@router.post("/check")
async def check(project_id: int, date: str | None = None) -> dict:
    """Проверить сайты-источники среза; находки засчитываются как упоминания."""
    project, date = _resolve(project_id, date)
    return await external.check_date(project, date)


@router.get(".xlsx")
async def export_xlsx(project_id: int, date: str | None = None) -> Response:
    """Excel «источник + текст упоминания». Непроверенные страницы проверяются тут же."""
    project, date = _resolve(project_id, date)
    result = await external.check_date(project, date)
    body = external.build_xlsx(result["sites"])
    name = re.sub(r"[^\w.-]+", "-", f"внешние-источники-{project['name']}-{date}").strip("-") + ".xlsx"
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
