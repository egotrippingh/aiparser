from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import repo

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand_name: str = Field(min_length=1, max_length=120)
    brand_aliases: list[str] = []
    brand_domains: list[str] = []
    region_code: str | None = None
    deep_check_depth: int = 0
    notes: str | None = None
    parallel_scan: bool = False


class ProjectPatch(BaseModel):
    name: str | None = None
    brand_name: str | None = None
    brand_aliases: list[str] | None = None
    brand_domains: list[str] | None = None
    region_code: str | None = None
    deep_check_depth: int | None = None
    notes: str | None = None
    # Сканировать выбранные ИИ-системы одновременно, каждую в своём браузере.
    parallel_scan: bool | None = None


@router.get("")
def list_projects() -> list[dict]:
    return repo.list_projects()


@router.post("", status_code=201)
def create_project(body: ProjectIn) -> dict:
    try:
        pid = repo.create_project(**body.model_dump())
    except Exception as exc:  # UNIQUE(name)
        raise HTTPException(409, f"Проект с таким именем уже есть: {exc}") from exc
    return repo.get_project(pid)


@router.get("/{project_id}")
def get_project(project_id: int) -> dict:
    p = repo.get_project(project_id)
    if not p:
        raise HTTPException(404, "Проект не найден")
    return p


@router.patch("/{project_id}")
def patch_project(project_id: int, body: ProjectPatch) -> dict:
    if not repo.get_project(project_id):
        raise HTTPException(404, "Проект не найден")
    repo.update_project(project_id, **body.model_dump(exclude_none=True))
    return repo.get_project(project_id)


@router.delete("/{project_id}", status_code=204, response_model=None)
def delete_project(project_id: int) -> None:
    repo.delete_project(project_id)
