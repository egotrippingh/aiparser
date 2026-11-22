import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import server.admin_dashboard
from server.models import (
    Check, CloudResult, ControlProject, ControlRun, FreeScanBalance, LedgerEntry,
    PaymentOrder, ProviderAccount, ProviderTask, ServerCapture, User, Wallet,
)
from server.test_cloud_scans import postgres_url, setup


@pytest.fixture(autouse=True)
def _offline_cbr(monkeypatch):
    # Dashboard tests must not call the live CBR mirror.
    monkeypatch.setattr("server.admin_dashboard._cbr_usd_rub_kopeks", lambda client=None: None)
    server.admin_dashboard._FX_CACHE = None


def test_cost_known_and_manual_exchange_resolution():
    from decimal import Decimal
    from server.admin_dashboard import _cost_known, _resolve_exchange
    assert _cost_known([]) == (Decimal(0), True)
    assert _cost_known([Decimal(1), None, Decimal(2)]) == (Decimal(3), False)
    assert _cost_known([None, None]) == (None, False)
    assert _resolve_exchange(7800) == (7800, "manual")
    assert _resolve_exchange(None) == (None, "none")


def _project(owner, slug, *, enabled=True, archived=False, zone="Europe/Moscow",
             time="23:00", services=("chatgpt", "gemini"), effective_from=None):
    return ControlProject(id=slug * 32, user_id=owner, name=f"Project {slug}", brand_name="Brand",
        archived=archived, config_json=json.dumps({"services": services}),
        queries_json=json.dumps([{"active": True}, {"active": True}, {"active": False}]),
        schedule_json=json.dumps({"enabled": enabled, "month_days": [1, 31], "last_day": True,
                                  "time": time, "timezone": zone, "effective_from": effective_from}))


def _run(project, slug, when, *, state="done", scheduled=None, progress=None, retry=None):
    return ControlRun(id=slug * 32, project_id=project.id, user_id=project.user_id, request_key=slug,
        phase="cloud", state=state, created_at=when, updated_at=when, scheduled_for=scheduled, retry_at=retry,
        snapshot_json=json.dumps({"name": project.name, "queries": [{}, {}],
                                   "config": {"services": ["chatgpt"]}, "cloud_services": ["chatgpt"]}),
        progress_json=json.dumps(progress or {"cloud_done": 2}),
        error="PRIVATE_ERROR", lease_token="PRIVATE_LEASE")


def _result(run, when, service="chatgpt", query_id=None, check_id=None):
    return CloudResult(user_id=run.user_id, project_id=run.project_id, run_id=run.id,
        project_name="Saved project", brand_name="Brand", query_text="Private answer prompt", service=service,
        scan_date=when.date().isoformat(), status="error", created_at=when, query_id=query_id, check_id=check_id)


def test_dashboard_cash_ledger_and_observed_provider_coverage(tmp_path, monkeypatch):
    client, admin, other, user_id, sessions = setup(tmp_path, monkeypatch)
    now = datetime(2026, 12, 15, 9, tzinfo=timezone.utc)
    start = datetime(2026, 11, 30, 21, tzinfo=timezone.utc)
    monkeypatch.setattr("server.admin_dashboard.utcnow", lambda: now)
    with sessions() as db:
        db.get(Wallet, user_id).balance_kopeks = 12300
        db.add_all([
            Check(user_id=user_id, client_check_id="hold", price_kopeks=165),
            Check(user_id=user_id, client_check_id="free-hold", price_kopeks=0, free_scan_service="chatgpt"),
            FreeScanBalance(user_id=user_id, service="chatgpt", remaining=9),
        ])
        for i, (status, test, date) in enumerate([
            ("paid", False, start), ("paid", True, start), ("pending", False, start),
            ("paid", False, start - timedelta(seconds=1)),
        ]):
            db.add(PaymentOrder(id=f"order{i}", user_id=user_id, created_at=start - timedelta(days=1),
                                amount_kopeks=30000, method="sbp", status=status, test_mode=test))
            db.add(LedgerEntry(user_id=user_id, kind="topup", reference=f"payment:order{i}",
                               amount_kopeks=30000, created_at=date))
        for kind, amount, reference in [("admin_credit", 4000, "credit"), ("check", -165, "paid-check"),
                                        ("recompute", -80, "recomp"), ("recompute", 0, "admin-recomp")]:
            db.add(LedgerEntry(user_id=user_id, kind=kind, reference=reference,
                               amount_kopeks=amount, created_at=start))
        project = _project(user_id, "a", enabled=False)
        db.add(project)
        db.flush()
        run = _run(project, "1", start, scheduled=start)
        db.add(run)
        db.add(_result(run, start))
        db.add_all([
            Check(user_id=user_id, client_check_id="analysis-cost", price_kopeks=0, status="settled",
                  created_at=start, analysis_attempts=1, arbitration_attempts=1,
                  analysis_usage_json='{"cost":0.0002}', arbitration_usage_json='{"cost":0.0003}'),
            Check(user_id=user_id, client_check_id="missing-cost", price_kopeks=0, status="released",
                  created_at=start, analysis_attempts=1, analysis_usage_json='{"cost":true}'),
            Check(user_id=user_id, client_check_id="older-cost", price_kopeks=0, status="settled",
                  created_at=start - timedelta(seconds=1), analysis_attempts=1, analysis_usage_json='{"cost":0.01}'),
        ])
        db.commit()

    path = "/api/v1/admin/dashboard"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=other).status_code == 403
    for params in ({"chatgpt": "-1"}, {"analysis": "1.234"}, {"usd_rub_kopeks": "0"}, {"recompute": "1000001"}):
        assert client.get(path, headers=admin, params=params).status_code == 422
    monkeypatch.setattr("server.admin_dashboard._cbr_usd_rub_kopeks", lambda client=None: 9000)
    server.admin_dashboard._FX_CACHE = None
    partial = client.get(path, headers=admin).json()
    assert partial["usd_rub_source"] == "cbr" and partial["usd_rub_kopeks"] == 9000
    assert partial["api_cost_complete"] is False
    assert "chatgpt" in partial["missing_rates"] and "recompute" in partial["missing_rates"]
    # OpenRouter usage converts with the automatic FX even before collector rates are set.
    assert partial["api_cost_kopeks"] == 6 and partial["margin_kopeks"] == 239
    response = client.get(path, headers=admin, params={"chatgpt": "0.10", "recompute": 5, "usd_rub_kopeks": 10000})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["month"] == "2026-12"
    assert data["usd_rub_source"] == "manual" and data["api_cost_complete"] is True
    assert data["paid_topups_kopeks"] == 30000
    assert (data["check_charges_kopeks"], data["recompute_charges_kopeks"], data["observed_recomputes"]) == (165, 80, 2)
    assert (data["balance_kopeks"], data["reserved_kopeks"], data["available_kopeks"]) == (12300, 165, 12135)
    assert (data["free_scans"], data["reserved_free_scans"]) == (9, 1)
    assert (data["openrouter_recorded_cost_usd"], data["openrouter_usage_checks"],
            data["openrouter_missing_usage_checks"]) == (0.0005, 1, 1)
    assert data["api_cost_kopeks"] == 27 and data["margin_kopeks"] == 218
    assert data["runs_this_month"] == 1 and data["recent_run_states"] == {"done": 1}
    providers = {row["provider"]: row for row in data["providers"]}
    assert providers["scrapeless"]["observed_cost"] == 0.001
    assert providers["openrouter"]["observed_cost"] == 0.0017


@pytest.mark.parametrize("database", ["sqlite", "postgres_url"])
def test_forecast_schedule_calendar_and_manual_pace(tmp_path, monkeypatch, request, database):
    url = request.getfixturevalue(database) if database == "postgres_url" else None
    client, admin, _, user_id, sessions = setup(tmp_path, monkeypatch, database_url=url)
    now = datetime(2026, 12, 31, 19, tzinfo=timezone.utc)
    monkeypatch.setattr("server.admin_dashboard.utcnow", lambda: now)
    monkeypatch.setattr("server.admin_dashboard._cbr_usd_rub_kopeks", lambda client=None: None)
    server.admin_dashboard._FX_CACHE = None
    with sessions() as db:
        primary = _project(user_id, "a")
        west = _project(user_id, "b", zone="America/Los_Angeles", time="14:00", services=("yandex_neuro",),
                        effective_from="2027-01-01T00:00:00+00:00")
        archived = _project(user_id, "c", archived=True)
        db.add_all([primary, west, archived,
                    _project(user_id, "d", enabled=False)])
        db.get(ProviderAccount, "gemini").paused = True
        db.flush()
        recent = now - timedelta(days=1)
        manual = _run(primary, "1", recent)
        scheduled = _run(primary, "2", recent, scheduled=recent)
        old = _run(primary, "3", now - timedelta(days=29))
        pending = _run(primary, "4", now, state="paused", scheduled=now)
        snapshot = json.loads(pending.snapshot_json)
        snapshot["cloud_services"].append("gemini")
        snapshot["config"]["services"].append("gemini")
        pending.snapshot_json = json.dumps(snapshot)
        historical = _run(archived, "5", recent)
        db.add_all([manual, scheduled, old, pending, historical])
        db.add(_result(pending, now, query_id="q1"))
        db.add(ProviderTask(run_id=pending.id, check_id="skip", query_id="q1", service="chatgpt",
                            submission_token="already-skipped", state="skipped"))
        db.add(ProviderTask(run_id=pending.id, check_id="submitted", query_id="q2", service="gemini",
                            submission_token="already-submitted", state="completed"))
        db.add(ServerCapture(run_id=pending.id, check_id="submitted", query_id="q2", service="gemini", answer_json="{}"))
        db.add(LedgerEntry(user_id=user_id, kind="recompute", reference="recomp",
                           amount_kopeks=0, created_at=recent))
        db.add_all([_result(manual, recent) for _ in range(27)])
        # Track two very different service costs; the second uses a managed ID before a result is linked.
        managed_id = f"{historical.id}:{'a' * 32}:gemini"
        db.add_all([_result(manual, recent, check_id="recent-usage"),
                    _result(scheduled, recent), _result(old, old.created_at),
                    _result(historical, recent, service="gemini")])
        db.add_all([
            Check(user_id=user_id, client_check_id="recent-usage", price_kopeks=0, status="settled",
                  created_at=recent, analysis_attempts=1, analysis_usage_json='{"cost":0.029}'),
            Check(user_id=user_id, client_check_id=managed_id, price_kopeks=0, status="settled",
                  created_at=recent, analysis_attempts=1, analysis_usage_json='{"cost":0.01}'),
        ])
        db.commit()

    params = {"chatgpt": "0.10", "gemini": 0, "yandex_neuro": "3.5", "usd_rub_kopeks": 10000, "recompute": 3}
    response = client.get("/api/v1/admin/dashboard", params=params, headers=admin)
    assert response.status_code == 200
    data = response.json()
    services = {row["service"]: row for row in data["services"]}
    assert (data["active_projects"], data["scheduled_projects"]) == (3, 2)
    assert (data["current_month_scheduled_runs"], data["next_month_scheduled_runs"]) == (1, 3)
    assert data["next_month"] == "2027-01"
    assert data["lookback_start"] == "2026-12-03" and data["lookback_end"] == "2026-12-31"
    assert services["chatgpt"]["recent_checks"] == 29
    assert services["chatgpt"]["recent_manual_checks"] == 28
    assert (services["chatgpt"]["remaining_checks"], services["chatgpt"]["next_month_checks"]) == (2, 4)
    assert (services["chatgpt"]["remaining_manual_checks"], services["chatgpt"]["next_month_manual_checks"]) == (0, 31)
    assert services["gemini"]["next_month_manual_checks"] == services["gemini"]["next_month_checks"] == 0
    assert (services["yandex_neuro"]["remaining_checks"], services["yandex_neuro"]["next_month_checks"]) == (0, 2)
    assert (data["backlog_runs"], services["chatgpt"]["backlog_checks"]) == (1, 1)
    assert services["gemini"]["backlog_checks"] == 1  # Paused provider still drains previously admitted work.
    assert (data["recent_recomputes"], data["remaining_recomputes"], data["next_month_recomputes"]) == (1, 0, 1)
    assert services["chatgpt"]["openrouter_rate_source"] == "service"
    assert services["chatgpt"]["openrouter_rate_usd"] == 0.001
    assert services["gemini"]["openrouter_rate_usd"] == 0.01
    assert services["gemini"]["recent_checks"] == 1 and services["gemini"]["recent_manual_checks"] == 0
    assert services["yandex_neuro"]["openrouter_rate_source"] == "pooled"
    assert data["next_month_api_cost_kopeks"] == 736
    assert data["current_month_api_cost_kopeks"] == 863
    providers = {row["provider"]: row for row in data["providers"]}
    assert providers["openrouter"]["next_month_cost"] == 0.0379
    assert providers["xmlriver"]["next_month_cost"] == 0.07
    different_fx = client.get("/api/v1/admin/dashboard",
                              params={**params, "usd_rub_kopeks": 7000}, headers=admin).json()
    changed = {row["provider"]: row for row in different_fx["providers"]}
    assert changed["scrapeless"] == providers["scrapeless"]
    assert different_fx["next_month_api_cost_kopeks"] < data["next_month_api_cost_kopeks"]


def test_dashboard_series_auth_range_points_and_week(tmp_path, monkeypatch):
    client, admin, other, user_id, sessions = setup(tmp_path, monkeypatch)
    day = datetime(2026, 12, 10, 12, tzinfo=timezone.utc)  # Thursday MSK midday
    monday = datetime(2026, 12, 7, 10, tzinfo=timezone.utc)
    with sessions() as db:
        db.add(PaymentOrder(id="series-paid", user_id=user_id, created_at=day - timedelta(days=1),
                            amount_kopeks=50000, method="sbp", status="paid", test_mode=False))
        db.add(PaymentOrder(id="series-test", user_id=user_id, created_at=day - timedelta(days=1),
                            amount_kopeks=50000, method="sbp", status="paid", test_mode=True))
        db.add_all([
            LedgerEntry(user_id=user_id, kind="topup", reference="payment:series-paid",
                        amount_kopeks=50000, created_at=day),
            LedgerEntry(user_id=user_id, kind="topup", reference="payment:series-test",
                        amount_kopeks=50000, created_at=day),
            LedgerEntry(user_id=user_id, kind="check", reference="series-check",
                        amount_kopeks=-165, created_at=day),
            LedgerEntry(user_id=user_id, kind="recompute", reference="series-recomp",
                        amount_kopeks=-80, created_at=day),
        ])
        project = _project(user_id, "s", enabled=False)
        db.add(project)
        db.flush()
        run = _run(project, "s", day)
        db.add(run)
        db.add_all([
            _result(run, day, query_id="q1"),
            _result(run, day, query_id="q1", service="gemini"),
            _result(run, day, query_id="q2"),
        ])
        db.add(Check(user_id=user_id, client_check_id="series-usage", price_kopeks=0, status="settled",
                     created_at=day, analysis_attempts=1, analysis_usage_json='{"cost":0.01}'))
        db.add(User(id="newuser" + "0" * 25, email="series-new@test.example",
                    password_hash="x", is_admin=False, created_at=day))
        db.add(LedgerEntry(user_id=user_id, kind="check", reference="series-monday",
                           amount_kopeks=-165, created_at=monday))
        db.commit()

    path = "/api/v1/admin/dashboard/series"
    params = {"from": "2026-12-09", "to": "2026-12-11"}
    assert client.get(path, params=params).status_code == 401
    assert client.get(path, params=params, headers=other).status_code == 403
    assert client.get(path, headers=admin, params={"from": "2026-12-11", "to": "2026-12-09"}).status_code == 422
    assert client.get(path, headers=admin, params={"from": "2025-01-01", "to": "2026-12-31"}).status_code == 422
    assert client.get(path, headers=admin, params={**params, "granularity": "hour"}).status_code == 422

    rate_params = {"chatgpt": "0.10", "gemini": "0", "usd_rub_kopeks": 10000, "recompute": 5}
    response = client.get(path, headers=admin, params={**params, **rate_params})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["from"] == "2026-12-09" and data["to"] == "2026-12-11"
    assert data["granularity"] == "day" and data["timezone"] == "Europe/Moscow"
    assert [point["bucket"] for point in data["points"]] == ["2026-12-09", "2026-12-10", "2026-12-11"]
    empty, active, trailing = data["points"]
    assert empty == {
        "bucket": "2026-12-09", "revenue_kopeks": 0, "charges_kopeks": 0, "api_cost_kopeks": 0,
        "api_cost_complete": True, "margin_kopeks": 0, "cloud_results": 0, "queries_distinct": 0,
        "new_users": 0,
    }
    assert active["bucket"] == "2026-12-10"
    assert (active["revenue_kopeks"], active["charges_kopeks"], active["new_users"]) == (50000, 245, 1)
    assert (active["cloud_results"], active["queries_distinct"]) == (3, 2)
    # 2×chatgpt@0.10¢→20 + gemini@0 + OpenRouter 0.01$→100 + recompute 5
    assert active["api_cost_complete"] is True and active["api_cost_kopeks"] == 125
    assert active["margin_kopeks"] == 120
    assert trailing["bucket"] == "2026-12-11" and trailing["revenue_kopeks"] == 0
    assert data["totals"]["revenue_kopeks"] == 50000
    assert data["totals"]["charges_kopeks"] == 245
    assert data["totals"]["cloud_results"] == 3
    assert data["totals"]["queries_distinct"] == 2
    assert data["totals"]["new_users"] == 1

    week = client.get(path, headers=admin, params={
        "from": "2026-12-07", "to": "2026-12-13", "granularity": "week", **rate_params,
    }).json()
    assert week["granularity"] == "week"
    assert [point["bucket"] for point in week["points"]] == ["2026-12-07"]
    assert week["points"][0]["charges_kopeks"] == 410
    assert week["totals"]["charges_kopeks"] == 410


def test_run_journal_filters_cross_user_and_redacts_private_fields(tmp_path, monkeypatch):
    client, admin, other, user_id, sessions = setup(tmp_path, monkeypatch)
    now = datetime(2026, 12, 15, 9, tzinfo=timezone.utc)
    monkeypatch.setattr("server.admin_dashboard.utcnow", lambda: now)
    with sessions() as db:
        other_id = db.scalar(select(User.id).where(User.id != user_id))
        a, b = _project(user_id, "a"), _project(other_id, "b")
        db.add_all([a, b])
        db.flush()
        db.add_all([
            _run(a, "1", now, state="done", retry=now + timedelta(minutes=1)),
            _run(b, "2", now, state="running", progress={"cloud_done": 1, "agent_done": "PRIVATE_PROGRESS"},
                 retry=now + timedelta(minutes=1)),
            _run(b, "3", now - timedelta(days=1), state="paused", retry=now - timedelta(minutes=1)),
        ])
        db.flush()
        running = db.get(ControlRun, "2" * 32)
        running.desired_state = "cancelled"
        running.lease_until = now - timedelta(seconds=1)
        db.commit()
    url = "/api/v1/admin/runs"
    assert client.get(url, headers=other).status_code == 403
    page = client.get(url, headers=admin, params={"limit": 1})
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    assert page.json()["total"] == 3
    row = page.json()["runs"][0]
    assert row["email"] == "other@test.example"
    assert row["id"] == "2" * 32 and row["planned_checks"] == 2 and row["done_checks"] == 1
    assert row["retry_at"] == (now + timedelta(minutes=1)).isoformat()
    assert row["desired_state"] == "cancelled" and row["connection_lost"] is True
    assert "PRIVATE_" not in page.text
    assert client.get(url, headers=admin, params={"limit": 1, "offset": 1}).json()["runs"][0]["id"] == "1" * 32
    assert client.get(url, headers=admin, params={"status": "paused", "search": "PROJECT b"}).json()["runs"][0]["retry_at"] is None
    assert client.get(url, headers=admin, params={"search": "%"}).json()["total"] == 0
    assert client.get(url, headers=admin, params={"search": "2" * 32}).json()["total"] == 1
