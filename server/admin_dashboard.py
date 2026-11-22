"""Read-only operating metrics for the admin site."""
import calendar
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session, load_only

from server.control import CLOUD_SERVICES, TERMINAL, Schedule, aware
from server.models import (
    Check, CloudResult, ControlProject, ControlRun, FreeScanBalance, LedgerEntry,
    PaymentOrder, ProviderAccount, ProviderTask, ServerCapture, User, Wallet, utcnow,
)
from server.provider_tasks import ACTIVE as PENDING_TASK_STATES
from server.scrapeless import SERVICES as SCRAPELESS_SERVICES

MOSCOW = ZoneInfo("Europe/Moscow")
MANAGED_CHECK = re.compile(r"[a-f0-9]{32}:[a-f0-9]{32}:[a-z_]+")
CostRate = Annotated[Decimal | None, Field(ge=0, le=1_000_000, decimal_places=2)]
DollarRate = Annotated[Decimal | None, Field(ge=0, le=1_000_000, decimal_places=4)]
_FX_CACHE: tuple[datetime, int] | None = None
_FX_TTL = timedelta(hours=6)
_CBR_DAILY = "https://www.cbr-xml-daily.ru/daily_json.js"


class CostRates(BaseModel):
    chatgpt: DollarRate = None
    perplexity: DollarRate = None
    gemini: DollarRate = None
    google_aio: CostRate = None
    yandex_neuro: CostRate = None
    recompute: CostRate = None
    analysis: CostRate = None
    usd_rub_kopeks: int | None = Field(default=None, ge=1, le=1_000_000)


@dataclass
class ScheduledWork:
    runs: int = 0
    checks: Counter[str] = field(default_factory=Counter)


@dataclass
class StageUsage:
    cost: Decimal = Decimal(0)
    recorded: int = 0
    missing: int = 0

    def add(self, cost: Decimal | None, attempted: bool) -> None:
        if cost is not None:
            self.cost += cost
            self.recorded += 1
        elif attempted:
            self.missing += 1

    def estimate(self) -> Decimal | None:
        if not self.missing:
            return self.cost
        return self.cost * (self.recorded + self.missing) / self.recorded if self.recorded else None


@dataclass
class AnalysisUsage:
    primary: StageUsage = field(default_factory=StageUsage)
    arbiter: StageUsage = field(default_factory=StageUsage)
    recorded_checks: int = 0
    missing_checks: int = 0

    def add(self, primary: Decimal | None, arbiter: Decimal | None, primary_attempted: bool,
            arbiter_attempted: bool) -> None:
        self.primary.add(primary, primary_attempted)
        self.arbiter.add(arbiter, arbiter_attempted)
        self.recorded_checks += int(primary is not None or arbiter is not None)
        self.missing_checks += int((primary_attempted and primary is None) or (arbiter_attempted and arbiter is None))

    @property
    def cost(self) -> Decimal:
        return self.primary.cost + self.arbiter.cost

    def estimate(self) -> Decimal | None:
        return _cost_total([self.primary.estimate(), self.arbiter.estimate()])

def _estimate(count: int, rate: Decimal | None) -> Decimal | None:
    if not count:
        return Decimal(0)
    return count * rate if rate is not None else None


def _cost_total(costs: list[Decimal | None]) -> Decimal | None:
    if any(cost is None for cost in costs):
        return None
    return sum((cost for cost in costs if cost is not None), Decimal(0))


def _cost_known(costs: list[Decimal | None]) -> tuple[Decimal | None, bool]:
    """Sum known parts; complete is False when any part is still unknown."""
    if any(cost is None for cost in costs):
        known = [cost for cost in costs if cost is not None]
        return (sum(known, Decimal(0)) if known else None), False
    return sum(costs, Decimal(0)), True


def _rounded_kopeks(amount: Decimal | None) -> int | None:
    return int(amount.to_integral_value(rounding=ROUND_HALF_UP)) if amount is not None else None


def _cbr_usd_rub_kopeks(client: httpx.Client | None = None) -> int | None:
    """Official CBR USD rate mirrored as JSON; returns rubles×100 (kopeks per $1)."""
    global _FX_CACHE
    now = utcnow()
    if _FX_CACHE and now - _FX_CACHE[0] < _FX_TTL:
        return _FX_CACHE[1]
    try:
        own = client is None
        http = client or httpx.Client(timeout=4.0)
        try:
            response = http.get(_CBR_DAILY)
            response.raise_for_status()
            value = Decimal(str(response.json()["Valute"]["USD"]["Value"]))
        finally:
            if own:
                http.close()
        if not value.is_finite() or value <= 0 or value > 10_000:
            return None
        kopeks = int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))
        if not 1 <= kopeks <= 1_000_000:
            return None
        _FX_CACHE = (now, kopeks)
        return kopeks
    except (httpx.HTTPError, ValueError, KeyError, TypeError, InvalidOperation):
        return _FX_CACHE[1] if _FX_CACHE else None


def _resolve_exchange(manual: int | None) -> tuple[int | None, Literal["manual", "cbr", "none"]]:
    if manual is not None:
        return manual, "manual"
    automatic = _cbr_usd_rub_kopeks()
    return (automatic, "cbr") if automatic is not None else (None, "none")


def _usd_from_kopeks(amount: Decimal | None, exchange_rate: int | None) -> Decimal | None:
    if amount == 0:
        return Decimal(0)
    return amount / exchange_rate if amount is not None and exchange_rate else None


def _kopeks_from_usd(amount: Decimal | None, exchange_rate: int | None) -> Decimal | None:
    if amount == 0:
        return Decimal(0)
    return amount * exchange_rate if amount is not None and exchange_rate else None


def _usage_cost(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        usage = json.loads(raw, parse_float=Decimal)
        value = usage.get("cost") if isinstance(usage, dict) else None
    except (ValueError, InvalidOperation):
        return None
    if type(value) is int:
        value = Decimal(value)
    return value if isinstance(value, Decimal) and value.is_finite() and 0 <= value <= 1_000_000 else None


def _analysis_usage(db: Session, month_start: datetime, pace_start: datetime, pace_end: datetime,
                    now: datetime) -> tuple[AnalysisUsage, AnalysisUsage, dict[str, AnalysisUsage]]:
    current, recent = AnalysisUsage(), AnalysisUsage()
    by_service = {service: AnalysisUsage() for service in CLOUD_SERVICES}
    # Historical check IDs may be local. Only associate results owned by the same account.
    links = select(CloudResult.user_id, CloudResult.check_id, func.min(CloudResult.service).label("service")).where(
        CloudResult.created_at >= min(month_start, pace_start), CloudResult.check_id.is_not(None),
        CloudResult.service.in_(CLOUD_SERVICES),
    ).group_by(CloudResult.user_id, CloudResult.check_id).having(
        func.min(CloudResult.service) == func.max(CloudResult.service)).subquery()
    stmt = select(
        Check.created_at, Check.analysis_usage_json, Check.arbitration_usage_json,
        Check.analysis_attempts, Check.arbitration_attempts, Check.client_check_id, links.c.service, ControlRun.id,
    ).select_from(Check).outerjoin(links, (links.c.user_id == Check.user_id) & (links.c.check_id == Check.client_check_id)).outerjoin(
        ControlRun, (ControlRun.id == func.substr(Check.client_check_id, 1, 32)) & (ControlRun.user_id == Check.user_id),
    ).where(
        Check.created_at >= min(month_start, pace_start), Check.created_at <= now,
        (Check.analysis_attempts > 0) | (Check.arbitration_attempts > 0) |
        Check.analysis_usage_json.is_not(None) | Check.arbitration_usage_json.is_not(None)
    ).execution_options(yield_per=500)
    for created, primary, arbiter, primary_attempts, arbiter_attempts, check_id, service, run_id in db.execute(stmt):
        costs = (_usage_cost(primary), _usage_cost(arbiter), primary_attempts > 0, arbiter_attempts > 0)
        timestamp = aware(created)
        if timestamp >= month_start:
            current.add(*costs)
        if pace_start <= timestamp < pace_end:
            recent.add(*costs)
            if not service and run_id and MANAGED_CHECK.fullmatch(check_id):
                service = check_id.rsplit(":", 1)[-1]
            if service in by_service:
                by_service[service].add(*costs)
    return current, recent, by_service

def _native_costs(provider: str, currency: str, observed: Decimal | None,
                  remaining: Decimal | None, next_month: Decimal | None) -> dict[str, object]:
    return {"provider": provider, "currency": currency,
            "observed_cost": float(observed) if observed is not None else None,
            "remaining_cost": float(remaining) if remaining is not None else None,
            "next_month_cost": float(next_month) if next_month is not None else None}


def _next_month(start: datetime) -> datetime:
    return start + timedelta(days=calendar.monthrange(start.year, start.month)[1])


def _count_slots(schedule: Schedule, start: datetime, end: datetime) -> int:
    if start >= end:
        return 0
    zone = ZoneInfo(schedule.timezone)
    local_time = time.fromisoformat(schedule.time)
    day, last = start.astimezone(zone).date(), end.astimezone(zone).date()
    count = 0
    while day <= last:
        if day.day in schedule.month_days or (
            schedule.last_day and day.day == calendar.monthrange(day.year, day.month)[1]
        ):
            slot = datetime.combine(day, local_time, zone).astimezone(timezone.utc)
            count += int(start <= slot < end)
        day += timedelta(days=1)
    return count


def _scheduled_work(db: Session, now: datetime, next_month: datetime, after_next: datetime,
                    paused: set[str]) -> tuple[int, int, ScheduledWork, ScheduledWork]:
    active_projects = scheduled_projects = 0
    remaining, following = ScheduledWork(), ScheduledWork()
    projects = select(ControlProject.schedule_json, ControlProject.config_json, ControlProject.queries_json)
    for schedule_json, config_json, queries_json in db.execute(
        projects.where(ControlProject.archived.is_(False)).execution_options(yield_per=100)
    ):
        active_projects += 1
        schedule_data = json.loads(schedule_json)
        schedule = Schedule.model_validate(schedule_data)
        if not schedule.enabled:
            continue
        scheduled_projects += 1
        services = CLOUD_SERVICES.intersection(json.loads(config_json).get("services", ["google_aio"])) - paused
        queries = sum(query["active"] for query in json.loads(queries_json))
        if not services or not queries:
            continue
        enabled_at = schedule_data.get("effective_from")
        first_slot = aware(datetime.fromisoformat(enabled_at)) if enabled_at else now
        for work, start, end in ((remaining, now, next_month), (following, next_month, after_next)):
            slots = _count_slots(schedule, max(start, first_slot), end)
            work.runs += slots
            for service in services:
                work.checks[service] += queries * slots
    return active_projects, scheduled_projects, remaining, following


def _backlog(db: Session, now: datetime, paused: set[str]) -> tuple[int, Counter[str]]:
    runs = select(ControlRun.id, ControlRun.user_id, ControlRun.snapshot_json, ControlRun.desired_state).where(
        ControlRun.phase == "cloud", ControlRun.state.in_(("queued", "running", "paused")),
        (ControlRun.scheduled_for.is_(None) | (ControlRun.scheduled_for <= now)),
    )
    active = runs.with_only_columns(ControlRun.id, ControlRun.user_id, ControlRun.desired_state).subquery()
    saved = select(CloudResult.run_id, CloudResult.query_id, CloudResult.service).join(
        active, (active.c.id == CloudResult.run_id) & (active.c.user_id == CloudResult.user_id)
    ).where(CloudResult.query_id.is_not(None))
    skipped = select(ProviderTask.run_id, ProviderTask.query_id, ProviderTask.service).join(
        active, active.c.id == ProviderTask.run_id
    ).where(ProviderTask.state == "skipped")
    pairs = saved.union(skipped).subquery()
    done = {(run, service): count for run, service, count in db.execute(
        select(pairs.c.run_id, pairs.c.service, func.count()).group_by(pairs.c.run_id, pairs.c.service))}
    # Pause/cancel blocks fresh work, but submitted tasks and durable captures may still drain.
    admitted = select(ProviderTask.run_id, ProviderTask.query_id, ProviderTask.service).join(
        active, active.c.id == ProviderTask.run_id
    ).where((active.c.desired_state != "running") | ProviderTask.service.in_(paused),
            ProviderTask.state.in_((*PENDING_TASK_STATES, "completed")))
    captured = select(ServerCapture.run_id, ServerCapture.query_id, ServerCapture.service).join(
        active, active.c.id == ServerCapture.run_id
    ).where((active.c.desired_state != "running") | ServerCapture.service.in_(paused))
    pending = admitted.union(captured).subquery()
    finished = select(pairs.c.run_id).where(pairs.c.run_id == pending.c.run_id,
        pairs.c.query_id == pending.c.query_id, pairs.c.service == pending.c.service).exists()
    admitted_counts = {(run, service): count for run, service, count in db.execute(
        select(pending.c.run_id, pending.c.service, func.count()).where(~finished)
        .group_by(pending.c.run_id, pending.c.service))}
    work = Counter()
    run_count = 0
    for run_id, _, raw, desired in db.execute(runs.execution_options(yield_per=100)):
        snapshot = json.loads(raw)
        queries = len(snapshot["queries"])
        services = CLOUD_SERVICES.intersection(snapshot.get("cloud_services", []))
        remaining = {
            service: admitted_counts.get((run_id, service), 0) if service in paused or desired != "running"
            else max(0, queries - done.get((run_id, service), 0))
            for service in services
        }
        work.update(remaining)
        run_count += int(any(remaining.values()))
    return run_count, work


def _pace_projection(count: int, span: timedelta) -> int:
    unit = timedelta(seconds=1)
    window = timedelta(days=28) // unit
    return (count * span // unit + window // 2) // window


def _progress_count(progress: dict, field_name: str) -> int:
    value = progress.get(field_name)
    return value if type(value) is int and value >= 0 else 0


def _journal_row(run: ControlRun, email: str, project_name: str, now: datetime) -> dict[str, object]:
    snapshot = json.loads(run.snapshot_json)
    progress = json.loads(run.progress_json)
    planned = len(snapshot["queries"]) * len(snapshot["config"]["services"])
    if snapshot.get("cloud_services"):
        done = _progress_count(progress, "cloud_done") + _progress_count(progress, "agent_done")
    else:
        done = _progress_count(progress, "done")
    retry = aware(run.retry_at) if run.retry_at and run.state not in TERMINAL else None
    return {
        "id": run.id, "email": email, "project_id": run.project_id, "project_name": project_name,
        "state": run.state, "phase": run.phase, "desired_state": run.desired_state,
        "connection_lost": bool(run.state in {"running", "paused"} and run.lease_until
                                and aware(run.lease_until) < now),
        "planned_checks": planned, "done_checks": min(done, planned),
        "scheduled_for": aware(run.scheduled_for).isoformat() if run.scheduled_for else None,
        "created_at": aware(run.created_at).isoformat(), "updated_at": aware(run.updated_at).isoformat(),
        "retry_at": retry.isoformat() if retry and retry > now else None,
    }


def _msk_day(value: datetime) -> date:
    return aware(value).astimezone(MOSCOW).date()


def _series_bucket(day: date, granularity: Literal["day", "week"]) -> date:
    return day - timedelta(days=day.weekday()) if granularity == "week" else day


def _series_axis(day_from: date, day_to: date, granularity: Literal["day", "week"]) -> list[date]:
    step = timedelta(days=7 if granularity == "week" else 1)
    cursor = _series_bucket(day_from, granularity)
    last = _series_bucket(day_to, granularity)
    axis: list[date] = []
    while cursor <= last:
        axis.append(cursor)
        cursor += step
    return axis


def _series_api_cost(service_counts: Counter[str], analysis_usd: Decimal, analysis_gaps: int,
                     recomputes: int, rates: CostRates, exchange: int | None) -> tuple[int | None, bool]:
    """Observed collector + OpenRouter cost for one series bucket; mirrors monthly completeness."""
    parts: list[Decimal | None] = []
    for service, rate in rates.model_dump(exclude={"analysis", "recompute", "usd_rub_kopeks"}).items():
        count = service_counts.get(service, 0)
        if not count:
            continue
        observed = _estimate(count, rate)
        if observed is None:
            parts.append(None)
            continue
        native = observed / Decimal(100)
        parts.append(
            _kopeks_from_usd(native, exchange) if service in SCRAPELESS_SERVICES else native * 100
        )
    if analysis_usd or analysis_gaps:
        converted = _kopeks_from_usd(analysis_usd, exchange)
        if analysis_gaps:
            parts.extend([converted, None] if converted is not None else [None])
        else:
            parts.append(converted)
    if recomputes:
        parts.append(_estimate(recomputes, rates.recompute))
    if not parts:
        return 0, True
    total, complete = _cost_known(parts)
    return _rounded_kopeks(total), complete


@dataclass
class _SeriesBucket:
    revenue: int = 0
    charges: int = 0
    cloud_results: int = 0
    query_ids: set[str] = field(default_factory=set)
    new_users: int = 0
    services: Counter[str] = field(default_factory=Counter)
    analysis_usd: Decimal = Decimal(0)
    analysis_gaps: int = 0
    recomputes: int = 0


def register_dashboard(router: APIRouter, db_session: Callable, admin: Callable) -> None:
    @router.get("/dashboard")
    def dashboard(response: Response, rates: CostRates = Depends(),
                  _user: User = Depends(admin), db: Session = Depends(db_session)) -> dict[str, object]:
        response.headers["Cache-Control"] = "no-store"
        now = utcnow()
        month = now.astimezone(MOSCOW).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = _next_month(month)
        month_start = month.astimezone(timezone.utc)
        next_boundary, after_next = next_month.astimezone(timezone.utc), _next_month(next_month).astimezone(timezone.utc)
        paused = set(db.scalars(select(ProviderAccount.service).where(ProviderAccount.paused.is_(True))))
        active_projects, scheduled_projects, remaining, following = _scheduled_work(
            db, now + timedelta(microseconds=1), next_boundary, after_next, paused)
        backlog_runs, backlog = _backlog(db, now, paused)

        reserved = select(Check.price_kopeks, Check.free_scan_service).where(Check.status == "reserved").subquery()
        users, balance, held, free, held_free = db.execute(select(
            select(func.count(User.id)).scalar_subquery(),
            select(func.coalesce(func.sum(Wallet.balance_kopeks), 0)).scalar_subquery(),
            select(func.coalesce(func.sum(reserved.c.price_kopeks), 0)).scalar_subquery(),
            select(func.coalesce(func.sum(FreeScanBalance.remaining), 0)).scalar_subquery(),
            select(func.count(reserved.c.free_scan_service)).scalar_subquery(),
        )).one()

        ledger_period = (LedgerEntry.created_at >= month_start, LedgerEntry.created_at <= now)
        cash = db.scalar(select(func.coalesce(func.sum(LedgerEntry.amount_kopeks), 0))
            .join(PaymentOrder, (LedgerEntry.reference == literal("payment:") + PaymentOrder.id)
                  & (LedgerEntry.user_id == PaymentOrder.user_id))
            .where(*ledger_period, LedgerEntry.kind == "topup", PaymentOrder.status == "paid",
                   PaymentOrder.test_mode.is_(False)))
        charges = {kind: (count, -amount) for kind, count, amount in db.execute(
            select(LedgerEntry.kind, func.count(), func.sum(LedgerEntry.amount_kopeks)).where(
                *ledger_period, LedgerEntry.kind.in_(("check", "recompute"))).group_by(LedgerEntry.kind))}
        _, check_charges = charges.get("check", (0, 0))
        recomputes, recompute_charges = charges.get("recompute", (0, 0))
        recompute_cost = _estimate(recomputes, rates.recompute)

        observed = dict(db.execute(select(CloudResult.service, func.count()).where(
            CloudResult.created_at >= month_start, CloudResult.created_at <= now,
            CloudResult.service.in_(CLOUD_SERVICES)).group_by(CloudResult.service)).all())
        lookback_end = now.astimezone(MOSCOW).replace(hour=0, minute=0, second=0, microsecond=0)
        lookback_start = lookback_end - timedelta(days=28)
        pace_start, pace_end = lookback_start.astimezone(timezone.utc), lookback_end.astimezone(timezone.utc)
        recent = dict(db.execute(select(CloudResult.service, func.count()).where(
            CloudResult.created_at >= pace_start, CloudResult.created_at < pace_end,
            CloudResult.service.in_(CLOUD_SERVICES)).group_by(CloudResult.service)).all())
        manual = dict(db.execute(select(CloudResult.service, func.count()).join(
            ControlRun, (CloudResult.run_id == ControlRun.id) & (CloudResult.user_id == ControlRun.user_id)).join(
            ControlProject, (ControlProject.id == ControlRun.project_id) & (ControlProject.user_id == ControlRun.user_id)
        ).where(ControlProject.archived.is_(False), ControlRun.scheduled_for.is_(None), CloudResult.created_at >= pace_start,
            CloudResult.created_at < pace_end, CloudResult.service.in_(CLOUD_SERVICES)).group_by(
            CloudResult.service)).all())
        current_span, following_span = next_boundary - now, after_next - next_boundary
        recent_recomputes = db.scalar(select(func.count(LedgerEntry.id)).where(
            LedgerEntry.kind == "recompute", LedgerEntry.created_at >= pace_start, LedgerEntry.created_at < pace_end))
        remaining_recomputes = _pace_projection(recent_recomputes, current_span)
        next_recomputes = _pace_projection(recent_recomputes, following_span)
        remaining_recompute_cost = _estimate(remaining_recomputes, rates.recompute)
        next_recompute_cost = _estimate(next_recomputes, rates.recompute)
        recorded, baseline, service_usage = _analysis_usage(db, month_start, pace_start, pace_end, now)
        exchange, exchange_source = _resolve_exchange(rates.usd_rub_kopeks)
        pace_checks = sum(recent.values())
        observed_checks_total = sum(observed.values())
        analysis_rate_usd = _usd_from_kopeks(rates.analysis, exchange)
        baseline_cost = baseline.estimate()
        if rates.analysis is None and baseline.recorded_checks and pace_checks and baseline_cost is not None:
            analysis_rate_usd = baseline_cost / pace_checks
        if recorded.recorded_checks or recorded.missing_checks:
            analysis_observed_usd = recorded.estimate()
            manual_analysis_usd = _usd_from_kopeks(_estimate(observed_checks_total, rates.analysis), exchange)
            if analysis_observed_usd is None and rates.analysis is not None and manual_analysis_usd is not None:
                analysis_observed_usd = max(recorded.cost, manual_analysis_usd)
        else:
            analysis_observed_usd = _estimate(observed_checks_total, analysis_rate_usd)
        analysis_observed_kopeks = _kopeks_from_usd(analysis_observed_usd, exchange)
        if analysis_observed_kopeks is None and not recorded.cost and rates.analysis is not None:
            analysis_observed_kopeks = _estimate(observed_checks_total, rates.analysis)

        rows = []
        collectors = {"scrapeless": [[], [], []], "xmlriver": [[], [], []]}
        remaining_checks_total = following_checks_total = 0
        remaining_model_costs = []
        following_model_costs = []
        missing_rates: list[str] = []
        for service, rate in rates.model_dump(exclude={"analysis", "recompute", "usd_rub_kopeks"}).items():
            observed_checks = observed.get(service, 0)
            recent_manual = manual.get(service, 0)
            # Project the recent manual pace in proportion to the exact remaining calendar time.
            remaining_manual, next_manual = (
                _pace_projection(recent_manual, period) if service not in paused else 0
                for period in (current_span, following_span)
            )
            remaining_count = remaining.checks[service] + remaining_manual + backlog[service]
            next_count = following.checks[service] + next_manual
            remaining_checks_total += remaining_count
            following_checks_total += next_count
            sample = service_usage[service]
            if rates.analysis is not None:
                model_rate, model_source = analysis_rate_usd, "scenario"
            elif sample.recorded_checks and recent.get(service) and (sample_cost := sample.estimate()) is not None:
                model_rate, model_source = sample_cost / recent[service], "service"
            else:
                model_rate = analysis_rate_usd
                model_source = "pooled" if model_rate is not None else "unknown"
            remaining_model_costs.append(_estimate(remaining_count, model_rate))
            following_model_costs.append(_estimate(next_count, model_rate))
            observed_cost = _estimate(observed_checks, rate)
            remaining_cost = _estimate(remaining_count, rate)
            following_cost = _estimate(next_count, rate)
            if rate is None and (observed_checks or remaining_count or next_count):
                missing_rates.append(service)
            provider = "scrapeless" if service in SCRAPELESS_SERVICES else "xmlriver"
            currency = "USD" if provider == "scrapeless" else "RUB"
            native_costs = [cost / 100 if cost is not None else None
                            for cost in (observed_cost, remaining_cost, following_cost)]
            for bucket, amount in zip(collectors[provider], native_costs):
                bucket.append(amount)
            observed_kopeks, remaining_kopeks, following_kopeks = (
                _kopeks_from_usd(amount, exchange) if currency == "USD"
                else amount * 100 if amount is not None else None
                for amount in native_costs
            )
            rows.append({
                "service": service, "currency": currency, "rate_minor": float(rate) if rate is not None else None,
                "observed_cost": float(native_costs[0]) if native_costs[0] is not None else None,
                "remaining_cost": float(native_costs[1]) if native_costs[1] is not None else None,
                "next_month_cost": float(native_costs[2]) if native_costs[2] is not None else None,
                "observed_checks": observed_checks, "recent_checks": recent.get(service, 0),
                "remaining_checks": remaining.checks[service], "next_month_checks": following.checks[service],
                "backlog_checks": backlog[service], "openrouter_rate_source": model_source,
                "openrouter_rate_usd": float(model_rate) if model_rate is not None else None,
                "openrouter_recent_usage_checks": sample.recorded_checks,
                "recent_manual_checks": recent_manual, "remaining_manual_checks": remaining_manual,
                "next_month_manual_checks": next_manual, "observed_cost_kopeks": _rounded_kopeks(observed_kopeks),
                "remaining_cost_kopeks": _rounded_kopeks(remaining_kopeks), "next_month_cost_kopeks": _rounded_kopeks(following_kopeks),
            })

        analysis_remaining, analysis_remaining_complete = _cost_known(remaining_model_costs)
        analysis_following, analysis_following_complete = _cost_known(following_model_costs)
        remaining_analysis_kopeks = (
            _estimate(remaining_checks_total, rates.analysis) if rates.analysis is not None
            else _kopeks_from_usd(analysis_remaining, exchange)
        )
        next_analysis_kopeks = (
            _estimate(following_checks_total, rates.analysis) if rates.analysis is not None
            else _kopeks_from_usd(analysis_following, exchange)
        )
        if rates.recompute is None and (recomputes or remaining_recomputes or next_recomputes):
            missing_rates.append("recompute")
        if rates.analysis is None and analysis_rate_usd is None and (
                remaining_checks_total or following_checks_total or observed_checks_total):
            missing_rates.append("analysis")
        if exchange is None and any(
            total is not None for total in (
                analysis_observed_usd, analysis_remaining, analysis_following,
                _cost_known(collectors["scrapeless"][0])[0],
                _cost_known(collectors["scrapeless"][1])[0],
                _cost_known(collectors["scrapeless"][2])[0],
            )
        ):
            missing_rates.append("usd_rub_kopeks")
        scrapeless_parts = [_cost_known(amounts) for amounts in collectors["scrapeless"]]
        scrapeless_usd = [total for total, _complete in scrapeless_parts]
        scrapeless_complete = all(complete for _total, complete in scrapeless_parts)
        xmlriver_parts = [_cost_known(amounts) for amounts in collectors["xmlriver"]]
        xmlriver_rub = [total for total, _complete in xmlriver_parts]
        xmlriver_complete = all(complete for _total, complete in xmlriver_parts)
        scrapeless_kopeks = [_kopeks_from_usd(total, exchange) for total in scrapeless_usd]
        xmlriver_kopeks = [total * 100 if total is not None else None for total in xmlriver_rub]
        openrouter_kopeks = [
            _cost_known([analysis_observed_kopeks, recompute_cost])[0],
            _cost_known([remaining_analysis_kopeks, remaining_recompute_cost])[0],
            _cost_known([next_analysis_kopeks, next_recompute_cost])[0],
        ]
        openrouter_complete = all(
            _cost_known(parts)[1] for parts in (
                [analysis_observed_kopeks, recompute_cost],
                [remaining_analysis_kopeks, remaining_recompute_cost],
                [next_analysis_kopeks, next_recompute_cost],
            )
        )
        analysis_cost_usd = [analysis_observed_usd, analysis_remaining, analysis_following]
        recompute_costs = [recompute_cost, remaining_recompute_cost, next_recompute_cost]
        providers = [
            _native_costs("scrapeless", "USD", *scrapeless_usd),
            _native_costs("xmlriver", "RUB", *xmlriver_rub),
            _native_costs("openrouter", "USD", *(
                _cost_known([analysis, _usd_from_kopeks(recompute, exchange)])[0]
                for analysis, recompute in zip(analysis_cost_usd, recompute_costs)
            )),
        ]
        # Period totals use known provider parts; completeness needs every part known.
        period_totals = []
        period_complete = []
        for i in range(3):
            total, complete = _cost_known([scrapeless_kopeks[i], xmlriver_kopeks[i], openrouter_kopeks[i]])
            period_totals.append(total)
            period_complete.append(
                complete and scrapeless_complete and xmlriver_complete and openrouter_complete
                and (i == 0 or analysis_remaining_complete) and (i != 2 or analysis_following_complete)
            )
        cost, remaining_total, following_total = period_totals
        api_cost_complete = period_complete[0]
        forecast_complete = period_complete[0] and period_complete[1]
        next_complete = period_complete[2]
        rounded_cost = _rounded_kopeks(cost)
        run_counts = dict(db.execute(select(ControlRun.state, func.count()).where(
            ControlRun.created_at >= month_start, ControlRun.created_at <= now).group_by(ControlRun.state)).all())
        # Deduplicate while preserving first-seen order for stable UI copy.
        gaps = list(dict.fromkeys(missing_rates))
        return {
            "month": month.strftime("%Y-%m"), "next_month": next_month.strftime("%Y-%m"),
            "lookback_start": lookback_start.date().isoformat(), "lookback_end": lookback_end.date().isoformat(),
            "users": users, "active_projects": active_projects, "scheduled_projects": scheduled_projects,
            "balance_kopeks": balance, "reserved_kopeks": held, "available_kopeks": balance - held,
            "free_scans": free, "reserved_free_scans": held_free, "paid_topups_kopeks": cash,
            "check_charges_kopeks": check_charges, "recompute_charges_kopeks": recompute_charges,
            "api_cost_kopeks": rounded_cost,
            "api_cost_complete": api_cost_complete,
            "forecast_complete": forecast_complete,
            "next_month_complete": next_complete,
            "missing_rates": gaps,
            "usd_rub_kopeks": exchange,
            "usd_rub_source": exchange_source,
            "margin_kopeks": check_charges + recompute_charges - rounded_cost if rounded_cost is not None else None,
            "current_month_api_cost_kopeks": _rounded_kopeks(_cost_known([cost, remaining_total])[0]),
            "next_month_api_cost_kopeks": _rounded_kopeks(following_total),
            "current_month_scheduled_runs": remaining.runs, "next_month_scheduled_runs": following.runs,
            "runs_this_month": sum(run_counts.values()), "recent_run_states": run_counts, "services": rows,
            "backlog_runs": backlog_runs, "recent_recomputes": recent_recomputes,
            "remaining_recomputes": remaining_recomputes, "next_month_recomputes": next_recomputes,
            "remaining_recompute_cost_kopeks": _rounded_kopeks(remaining_recompute_cost),
            "next_month_recompute_cost_kopeks": _rounded_kopeks(next_recompute_cost),
            "observed_recomputes": recomputes,
            "recompute_rate_kopeks": float(rates.recompute) if rates.recompute is not None else None,
            "recompute_cost_kopeks": _rounded_kopeks(recompute_cost), "providers": providers,
            "openrouter_recorded_cost_usd": float(recorded.cost),
            "openrouter_usage_checks": recorded.recorded_checks,
            "openrouter_missing_usage_checks": recorded.missing_checks,
            "openrouter_lookback_missing_usage_checks": baseline.missing_checks,
        }

    @router.get("/dashboard/series")
    def series(response: Response,
               day_from: date = Query(alias="from"),
               day_to: date = Query(alias="to"),
               granularity: Literal["day", "week"] = "day",
               rates: CostRates = Depends(),
               _user: User = Depends(admin), db: Session = Depends(db_session)) -> dict[str, object]:
        response.headers["Cache-Control"] = "no-store"
        if day_from > day_to or (day_to - day_from).days > 365:
            raise HTTPException(422, "Выберите период от 1 до 366 дней, начало не позже конца")
        start_utc = datetime.combine(day_from, time.min, MOSCOW).astimezone(timezone.utc)
        end_utc = datetime.combine(day_to + timedelta(days=1), time.min, MOSCOW).astimezone(timezone.utc)
        exchange, _source = _resolve_exchange(rates.usd_rub_kopeks)
        buckets: dict[date, _SeriesBucket] = defaultdict(_SeriesBucket)
        period_queries: set[str] = set()

        topups = select(LedgerEntry.created_at, LedgerEntry.amount_kopeks).join(
            PaymentOrder, (LedgerEntry.reference == literal("payment:") + PaymentOrder.id)
            & (LedgerEntry.user_id == PaymentOrder.user_id)
        ).where(LedgerEntry.created_at >= start_utc, LedgerEntry.created_at < end_utc,
                LedgerEntry.kind == "topup", PaymentOrder.status == "paid", PaymentOrder.test_mode.is_(False))
        for created, amount in db.execute(topups):
            buckets[_series_bucket(_msk_day(created), granularity)].revenue += amount

        charges = select(LedgerEntry.created_at, LedgerEntry.amount_kopeks, LedgerEntry.kind).where(
            LedgerEntry.created_at >= start_utc, LedgerEntry.created_at < end_utc,
            LedgerEntry.kind.in_(("check", "recompute")))
        for created, amount, kind in db.execute(charges):
            key = _series_bucket(_msk_day(created), granularity)
            buckets[key].charges += -amount
            if kind == "recompute":
                buckets[key].recomputes += 1

        for created, in db.execute(select(User.created_at).where(
                User.created_at >= start_utc, User.created_at < end_utc)):
            buckets[_series_bucket(_msk_day(created), granularity)].new_users += 1

        results = select(CloudResult.created_at, CloudResult.query_id, CloudResult.service).where(
            CloudResult.created_at >= start_utc, CloudResult.created_at < end_utc)
        for created, query_id, service in db.execute(results):
            key = _series_bucket(_msk_day(created), granularity)
            row = buckets[key]
            row.cloud_results += 1
            if query_id:
                row.query_ids.add(query_id)
                period_queries.add(query_id)
            if service in CLOUD_SERVICES:
                row.services[service] += 1

        usage = select(
            Check.created_at, Check.analysis_usage_json, Check.arbitration_usage_json,
            Check.analysis_attempts, Check.arbitration_attempts,
        ).where(Check.created_at >= start_utc, Check.created_at < end_utc,
                (Check.analysis_attempts > 0) | (Check.arbitration_attempts > 0) |
                Check.analysis_usage_json.is_not(None) | Check.arbitration_usage_json.is_not(None))
        for created, primary, arbiter, primary_attempts, arbiter_attempts in db.execute(usage):
            key = _series_bucket(_msk_day(created), granularity)
            row = buckets[key]
            for raw, attempted in ((primary, primary_attempts > 0), (arbiter, arbiter_attempts > 0)):
                cost = _usage_cost(raw)
                if cost is not None:
                    row.analysis_usd += cost
                elif attempted:
                    row.analysis_gaps += 1

        points = []
        totals = _SeriesBucket()
        for bucket in _series_axis(day_from, day_to, granularity):
            row = buckets[bucket]
            api_cost, complete = _series_api_cost(
                row.services, row.analysis_usd, row.analysis_gaps, row.recomputes, rates, exchange)
            margin = row.charges - api_cost if api_cost is not None else None
            points.append({
                "bucket": bucket.isoformat(),
                "revenue_kopeks": row.revenue,
                "charges_kopeks": row.charges,
                "api_cost_kopeks": api_cost,
                "api_cost_complete": complete,
                "margin_kopeks": margin,
                "cloud_results": row.cloud_results,
                "queries_distinct": len(row.query_ids),
                "new_users": row.new_users,
            })
            totals.revenue += row.revenue
            totals.charges += row.charges
            totals.cloud_results += row.cloud_results
            totals.new_users += row.new_users
            totals.services.update(row.services)
            totals.analysis_usd += row.analysis_usd
            totals.analysis_gaps += row.analysis_gaps
            totals.recomputes += row.recomputes

        total_cost, total_complete = _series_api_cost(
            totals.services, totals.analysis_usd, totals.analysis_gaps, totals.recomputes, rates, exchange)
        return {
            "from": day_from.isoformat(),
            "to": day_to.isoformat(),
            "granularity": granularity,
            "timezone": "Europe/Moscow",
            "points": points,
            "totals": {
                "revenue_kopeks": totals.revenue,
                "charges_kopeks": totals.charges,
                "api_cost_kopeks": total_cost,
                "api_cost_complete": total_complete,
                "margin_kopeks": totals.charges - total_cost if total_cost is not None else None,
                "cloud_results": totals.cloud_results,
                "queries_distinct": len(period_queries),
                "new_users": totals.new_users,
            },
        }

    @router.get("/runs")
    def runs(response: Response, search: str = Query(default="", max_length=200),
             status: Literal["", "queued", "running", "paused", "done", "failed", "cancelled", "missed"] = "",
             offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
             _user: User = Depends(admin), db: Session = Depends(db_session)) -> dict[str, object]:
        response.headers["Cache-Control"] = "no-store"
        scope = select(ControlRun, User.email, ControlProject.name).join(User, User.id == ControlRun.user_id).join(
            ControlProject, ControlProject.id == ControlRun.project_id)
        if search:
            scope = scope.where(User.email.icontains(search, autoescape=True) |
                                ControlProject.name.icontains(search, autoescape=True) |
                                ControlRun.id.icontains(search, autoescape=True))
        if status:
            scope = scope.where(ControlRun.state == status)
        total = db.scalar(select(func.count()).select_from(scope.with_only_columns(ControlRun.id).subquery()))
        entries = db.execute(scope.options(load_only(
            ControlRun.id, ControlRun.project_id, ControlRun.state, ControlRun.phase,
            ControlRun.snapshot_json, ControlRun.progress_json, ControlRun.created_at, ControlRun.updated_at,
            ControlRun.scheduled_for, ControlRun.retry_at, ControlRun.desired_state, ControlRun.lease_until,
        )).order_by(ControlRun.created_at.desc(), ControlRun.id.desc()).offset(offset).limit(limit))
        now = utcnow()
        return {"total": total, "runs": [_journal_row(row, email, project, now) for row, email, project in entries]}
