"""Перерешение спорных строк арбитром — по сохранённым данным, без браузера."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import repo
from app.detect import recheck as recheck_mod

router = APIRouter(prefix="/api", tags=["recheck"])


@router.get("/projects/{project_id}/review")
def review_count(project_id: int) -> dict:
    """Сколько строк ждёт решения арбитра и чем он будет решать."""
    if not repo.get_project(project_id):
        raise HTTPException(404, "Проект не найден")
    _, model, on = recheck_mod.arbiter_settings()
    return {"pending": len(repo.results_for_review(project_id)), "model": model, "enabled": on}


@router.post("/projects/{project_id}/review/resolve")
async def resolve(project_id: int, limit: int | None = None) -> dict:
    """Решает спорные строки второй моделью и снимает пометку «требует проверки»."""
    try:
        return await recheck_mod.recheck_project(project_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
