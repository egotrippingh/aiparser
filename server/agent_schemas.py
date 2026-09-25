"""Validated payloads shared by the account website and desktop agent API."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

SERVICE_IDS = {"perplexity", "chatgpt", "yandex_neuro", "alice", "google_aio"}
SCHEDULABLE_IDS = SERVICE_IDS - {"yandex_neuro"}
RESULT_STATUSES = {"found", "not_found", "skipped", "error", "auth_required", "captcha", "limit_reached"}


class ScanPreferencesIn(BaseModel):
    revision: int = Field(ge=0)
    enabled: bool
    local_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    month_days: list[int] = Field(min_length=1, max_length=31)
    browser_mode: str = Field(pattern=r"^(headless|headful)$")
    services: list[str] = Field(min_length=1, max_length=5)
    speed_profile: str = Field(pattern=r"^(careful|balanced|fast)$")

    @field_validator("month_days")
    @classmethod
    def check_month_days(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value) or any(day not in range(1, 32) for day in value):
            raise ValueError("Выберите числа месяца от 1 до 31 без повторов")
        return sorted(value)

    @field_validator("services")
    @classmethod
    def check_services(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(service not in SCHEDULABLE_IDS for service in value):
            raise ValueError("Выбран ИИ-сервис без готового адаптера или сервис повторяется")
        return value


class AgentHeartbeatIn(BaseModel):
    device_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=100)
    local_time_zone: str = Field(default="", max_length=80)
    active_scan: bool = False


class CloudResultIn(BaseModel):
    local_result_id: int = Field(gt=0)
    local_project_id: int = Field(gt=0)
    project_name: str = Field(min_length=1, max_length=120)
    brand_name: str = Field(min_length=1, max_length=120)
    query_text: str = Field(min_length=1, max_length=2000)
    group_tag: str | None = Field(default=None, max_length=120)
    service: str
    scan_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: str
    mention_types: list[str] = Field(default_factory=list, max_length=8)
    evidence_quote: str | None = Field(default=None, max_length=12000)
    answer_text: str | None = Field(default=None, max_length=60000)
    sources: list[str] = Field(default_factory=list, max_length=50)
    check_id: str | None = Field(default=None, max_length=100)

    @field_validator("service")
    @classmethod
    def check_service(cls, value: str) -> str:
        if value not in SERVICE_IDS:
            raise ValueError("Неизвестный ИИ-сервис")
        return value

    @field_validator("status")
    @classmethod
    def check_status(cls, value: str) -> str:
        if value not in RESULT_STATUSES:
            raise ValueError("Неизвестный статус")
        return value

    @field_validator("scan_date")
    @classmethod
    def check_scan_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @field_validator("sources")
    @classmethod
    def check_sources(cls, value: list[str]) -> list[str]:
        if any(len(source) > 2000 or urlparse(source).scheme not in ("http", "https")
               for source in value):
            raise ValueError("Источники должны быть ссылками http или https не длиннее 2000 символов")
        return value


class CloudResultsIn(BaseModel):
    device_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    results: list[CloudResultIn] = Field(min_length=1, max_length=100)
