"""Project membership checks shared by control, reports, and feedback."""
from fastapi import HTTPException
from sqlalchemy import select

from server.models import ControlProject, ProjectMember


def project_access(db, user_id, project_id, *, edit=False, lock=False):
    query = select(ControlProject).where(ControlProject.id == project_id,
                                         ControlProject.archived.is_(False))
    if lock:
        query = query.with_for_update()
    project = db.scalar(query)
    if project is None:
        raise HTTPException(404, "Проект не найден")
    if project.user_id == user_id:
        return project, "owner"
    member = db.get(ProjectMember, {"project_id": project.id, "user_id": user_id})
    if member is None or (edit and member.role != "editor"):
        raise HTTPException(404, "Проект не найден")
    return project, member.role


def owner_project(db, user_id, project_id, *, lock=False):
    project, role = project_access(db, user_id, project_id, lock=lock)
    if role != "owner":
        raise HTTPException(403, "Управлять доступом к проекту может только владелец")
    return project
