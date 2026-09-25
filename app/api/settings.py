from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.db import repo
from app.scanner import humanize

router = APIRouter(prefix="/api/settings", tags=["settings"])

DEFAULTS = {
    "screenshot_retention_days": "90",
    # Скорость задаётся одним профилем, а не тремя отдельными полями пауз:
    # два источника правды неминуемо разъезжаются. Конкретные значения
    # разворачиваются из профиля в app/scanner/humanize.py.
    "speed_profile": humanize.DEFAULT_PROFILE,   # careful | balanced | fast
}


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screenshot_retention_days: str | None = None
    speed_profile: str | None = None


@router.get("")
def get_settings() -> dict:
    stored = repo.all_settings()
    out = {key: stored.get(key, value) for key, value in DEFAULTS.items()}

    # Отдаём и сам справочник профилей: интерфейс показывает рядом с выбором
    # реальные секунды, чтобы решение «ускориться» принималось осознанно, а
    # не вслепую — это размен на живучесть аккаунтов.
    out["speed_profiles"] = humanize.PROFILES
    return out


@router.put("")
def put_settings(body: SettingsIn) -> dict:
    data = body.model_dump(exclude_none=True)

    if "speed_profile" in data and data["speed_profile"] not in humanize.PROFILES:
        data["speed_profile"] = humanize.DEFAULT_PROFILE

    for k, v in data.items():
        repo.set_setting(k, v)

    return get_settings()
