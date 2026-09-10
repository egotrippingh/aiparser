from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.db import repo

router = APIRouter(prefix="/api/projects/{project_id}/queries", tags=["queries"])


class QueriesIn(BaseModel):
    text: str          # список запросов, по одному в строке
    group_tag: str | None = None


@router.get("")
def list_queries(project_id: int, only_active: bool = False) -> list[dict]:
    return repo.list_queries(project_id, only_active=only_active)


@router.post("", status_code=201)
def add_queries(project_id: int, body: QueriesIn) -> dict:
    if not repo.get_project(project_id):
        raise HTTPException(404, "Проект не найден")
    lines = [ln for ln in body.text.splitlines() if ln.strip()]
    added = repo.add_queries(project_id, lines, body.group_tag)
    return {"added": added, "skipped": len(lines) - added, "total": len(repo.list_queries(project_id))}


@router.post("/upload", status_code=201)
async def upload_queries(project_id: int, file: UploadFile, group_tag: str | None = None) -> dict:
    """Импорт из txt или csv.

    В csv берём первую колонку, в txt — строку целиком. Разделитель csv
    определяем автоматически: выгрузки из Топвизора и Excel в русской локали
    приходят с точкой с запятой.
    """
    if not repo.get_project(project_id):
        raise HTTPException(404, "Проект не найден")

    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    name = (file.filename or "").lower()

    if name.endswith(".csv"):
        try:
            dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        lines = [row[0] for row in csv.reader(io.StringIO(raw), dialect) if row and row[0].strip()]
    else:
        lines = [ln for ln in raw.splitlines() if ln.strip()]

    added = repo.add_queries(project_id, lines, group_tag)
    return {"added": added, "skipped": len(lines) - added, "total": len(repo.list_queries(project_id))}


@router.patch("/{query_id}")
def toggle_query(project_id: int, query_id: int, is_active: bool) -> dict:
    repo.set_query_active(query_id, is_active)
    return {"ok": True}


@router.delete("/{query_id}", status_code=204, response_model=None)
def delete_query(project_id: int, query_id: int) -> None:
    repo.delete_query(query_id)
