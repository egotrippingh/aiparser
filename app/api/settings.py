from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import secrets_store
from app.db import repo
from app.scanner import humanize

router = APIRouter(prefix="/api/settings", tags=["settings"])

KEY_OPENROUTER = "openrouter_api_key"

DEFAULTS = {
    "openrouter_model": "anthropic/claude-sonnet-5",
    "llm_mode": "smart",            # always | smart | never
    "llm_confidence_threshold": "0.6",
    "screenshot_retention_days": "90",
    # Скорость задаётся одним профилем, а не тремя отдельными полями пауз:
    # два источника правды неминуемо разъезжаются. Конкретные значения
    # разворачиваются из профиля в app/scanner/humanize.py.
    "speed_profile": humanize.DEFAULT_PROFILE,   # careful | balanced | fast
}


class SettingsIn(BaseModel):
    openrouter_api_key: str | None = None    # пустая строка — стереть ключ
    openrouter_model: str | None = None
    llm_mode: str | None = None
    llm_confidence_threshold: str | None = None
    screenshot_retention_days: str | None = None
    speed_profile: str | None = None


@router.get("")
def get_settings() -> dict:
    stored = repo.all_settings()
    out = {**DEFAULTS, **stored}
    key = secrets_store.unprotect(repo.get_setting(KEY_OPENROUTER))
    out["openrouter_api_key_masked"] = secrets_store.mask(key)
    out["openrouter_api_key_set"] = bool(key)
    out["secrets_encrypted"] = secrets_store.is_encrypted()

    # Отдаём и сам справочник профилей: интерфейс показывает рядом с выбором
    # реальные секунды, чтобы решение «ускориться» принималось осознанно, а
    # не вслепую — это размен на живучесть аккаунтов.
    out["speed_profiles"] = humanize.PROFILES
    return out


@router.put("")
def put_settings(body: SettingsIn) -> dict:
    data = body.model_dump(exclude_none=True)

    if "openrouter_api_key" in data:
        raw = data.pop("openrouter_api_key").strip()
        repo.set_setting(KEY_OPENROUTER, secrets_store.protect(raw) if raw else None, is_secret=True)

    if "speed_profile" in data and data["speed_profile"] not in humanize.PROFILES:
        data["speed_profile"] = humanize.DEFAULT_PROFILE

    for k, v in data.items():
        repo.set_setting(k, v)

    return get_settings()
