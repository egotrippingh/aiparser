"""Durable server capture and analysis for XMLRiver-backed services."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import or_, select, update

from app.detect import rules
from app.detect.merge import merge, with_arbiter
from server.checks import analyze_check, arbitrate_check, complete_check, reserve_checks
from server.models import Check, CloudResult, ControlRun, ServerCapture, User, utcnow
from shared.detection import _build_prompt, parse_verdict
from shared.xmlriver import XMLRiverClient, AdapterError, XMLRiverResponseError, ProviderQuotaError, CollectionCancelled

CLOUD = {"google_aio", "yandex_neuro"}
LEASE = timedelta(minutes=5)


def _pairs(snapshot):
    return [(q, s) for s in snapshot["cloud_services"] for q in snapshot["queries"]]


def _claim(sessions):
    """A bounded lease with a token CAS; another worker may safely take an expired run."""
    with sessions() as db:
        now = utcnow()
        runs = db.scalars(select(ControlRun).where(ControlRun.phase == "cloud",
            ControlRun.state.in_(("queued", "running", "paused")),
            ControlRun.desired_state != "paused",
            or_(ControlRun.lease_until.is_(None), ControlRun.lease_until < now))
            .order_by(ControlRun.created_at).limit(20)).all()
        for run in runs:
            snap = json.loads(run.snapshot_json)
            token = uuid.uuid4().hex
            result = db.execute(update(ControlRun).where(ControlRun.id == run.id,
                ControlRun.phase == "cloud", ControlRun.state.in_(("queued", "running", "paused")),
                or_(ControlRun.lease_until.is_(None), ControlRun.lease_until < now))
                .values(lease_token=token, lease_until=now + LEASE, state="running", updated_at=now)
                .execution_options(synchronize_session=False))
            if result.rowcount == 1:
                db.commit()
                return run.id, token, snap
            db.rollback()
    return None


def _owned(db, run_id, token):
    run = db.get(ControlRun, run_id)
    until = run.lease_until if run else None
    if until and until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return run if run and run.phase == "cloud" and run.lease_token == token and until and until >= utcnow() else None


def _owned_locked(db, run_id, token):
    db.execute(select(ControlRun).where(ControlRun.id == run_id).with_for_update()
        .execution_options(populate_existing=True)).scalar_one_or_none()
    return _owned(db, run_id, token)


def _renew(sessions, run_id, token, *, need_running=False):
    with sessions() as db:
        now = utcnow()
        conditions = [ControlRun.id == run_id, ControlRun.phase == "cloud",
                      ControlRun.lease_token == token, ControlRun.lease_until >= now]
        if need_running:
            conditions.append(ControlRun.desired_state == "running")
        result = db.execute(update(ControlRun).where(*conditions).values(lease_until=now + LEASE)
            .execution_options(synchronize_session=False))
        db.commit()
        return result.rowcount == 1


def _finish_item(db, run, snapshot):
    db.flush()
    complete = db.execute(select(CloudResult.query_id, CloudResult.service).where(
        CloudResult.run_id == run.id, CloudResult.user_id == run.user_id)).all()
    count = len(set(complete))
    progress = json.loads(run.progress_json)
    progress["cloud_done"] = count
    run.progress_json = json.dumps(progress)
    run.lease_token = run.lease_until = None
    if run.desired_state == "cancelled":
        run.state = "cancelled"
        run.active_project_key = None
    elif run.desired_state == "paused":
        run.state = "paused"
    elif count == len(_pairs(snapshot)):
        if len(snapshot["config"]["services"]) > len(snapshot["cloud_services"]):
            run.phase, run.state = "agent", "queued"
        else:
            run.state, run.active_project_key = "done", None
    run.updated_at = utcnow()


def _record(db, run, snapshot, query, service, check_id, capture, verdict=None, *, status=None, error=None):
    if db.scalar(select(CloudResult.id).where(CloudResult.run_id == run.id,
            CloudResult.query_id == query["id"], CloudResult.service == service)):
        return
    result_status = status or verdict.status
    stamped = run.scheduled_for or run.created_at
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    scan_date = stamped.astimezone(ZoneInfo(snapshot["schedule"]["timezone"])).date().isoformat()
    db.add(CloudResult(user_id=run.user_id, device_id=None, local_result_id=None, local_project_id=None,
        project_name=snapshot["name"], brand_name=snapshot["brand_name"], query_text=query["text"],
        group_tag=query.get("group_tag") or None, service=service,
        scan_date=scan_date, status=result_status,
        mention_types_json=json.dumps(verdict.mention_types if verdict else [], ensure_ascii=False),
        evidence_quote=(verdict.evidence_quote if verdict else None),
        answer_text=(capture.get("answer_text") or "")[:60000] or None,
        error_message=error, sources_json=json.dumps(capture.get("sources", [])[:50], ensure_ascii=False),
        check_id=check_id, project_id=run.project_id, query_id=query["id"], run_id=run.id))


def _analyze_saved(sessions, run_id, token, check_id, content, ai_client):
    with sessions() as db:
        run = db.execute(select(ControlRun).where(ControlRun.id == run_id).with_for_update()).scalar_one_or_none()
        run = _owned(db, run_id, token) if run else None
        if not run:
            return None
        user = db.get(User, run.user_id)
        check = db.scalar(select(Check).where(Check.user_id == user.id, Check.client_check_id == check_id))
        if run.desired_state != "running" and not (check and check.analysis_json):
            return None
        return analyze_check(db, user, check_id, "", content, ai_client,
            retry_saved=bool(check and check.analysis_attempts))


def _arbitrate_saved(sessions, run_id, token, check_id, content, ai_client):
    with sessions() as db:
        run = db.execute(select(ControlRun).where(ControlRun.id == run_id).with_for_update()).scalar_one_or_none()
        run = _owned(db, run_id, token) if run else None
        if not run:
            return None
        user = db.get(User, run.user_id)
        check = db.scalar(select(Check).where(Check.user_id == user.id, Check.client_check_id == check_id))
        if run.desired_state != "running" and not (check and check.arbitration_json):
            return None
        return arbitrate_check(db, user, check_id, "", content, ai_client,
            retry_saved=bool(check and check.arbitration_attempts))


def _clear_invalid_verdict(sessions, run_id, token, check_id, stage, raw):
    """Discard only an unparseable cloud model cache; preserve attempt counters."""
    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run:
            return
        check = db.execute(select(Check).where(Check.user_id == run.user_id,
            Check.client_check_id == check_id).with_for_update()).scalar_one_or_none()
        if check is None:
            return
        field = "analysis_json" if stage == "analysis" else "arbitration_json"
        if getattr(check, field) != raw:
            return
        setattr(check, field, None)
        db.commit()


def _release_unstarted(sessions, run_id, token, check_id, snapshot):
    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run:
            return False
        complete_check(db, db.get(User, run.user_id), check_id, "skipped", commit=False)
        _finish_item(db, run, snapshot)
        db.commit()
    return True


def _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload):
    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run:
            return False
        if run.desired_state == "running":
            return None
        if run.desired_state == "cancelled":
            complete_check(db, db.get(User, run.user_id), check_id, "error", commit=False)
            _record(db, run, snapshot, query, service, check_id, payload, status="error",
                    error="Проверка остановлена до завершения анализа")
            _finish_item(db, run, snapshot)
        else:
            run.state = "paused"
            run.lease_token = run.lease_until = None
        db.commit()
        return True


async def cloud_tick(sessions, ai_client, price, collector_factory=XMLRiverClient):
    """Process one saved or fresh answer. Returns whether a cloud run was advanced."""
    claim = _claim(sessions)
    if not claim:
        return False
    run_id, token, snapshot = claim
    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run:
            return False
        done = {(q, s) for q, s in db.execute(select(CloudResult.query_id, CloudResult.service).where(
            CloudResult.run_id == run.id, CloudResult.user_id == run.user_id))}
        saved = {(c.query_id, c.service): c for c in db.scalars(select(ServerCapture).where(
            ServerCapture.run_id == run.id))}
        pending = [(q, s) for q, s in _pairs(snapshot) if (q["id"], s) not in done]
        if not pending:
            _finish_item(db, run, snapshot)
            db.commit()
            return True
        # Once stopped, drain only a previously committed answer.
        item = (next(((q, s) for q, s in pending if (q["id"], s) in saved), None)
                if run.desired_state != "running" else pending[0])
        if item is None:
            for check in db.scalars(select(Check).where(Check.user_id == run.user_id,
                    Check.client_check_id.startswith(run.id + ":"), Check.status == "reserved")):
                complete_check(db, db.get(User, run.user_id), check.client_check_id, "skipped", commit=False)
            _finish_item(db, run, snapshot)
            db.commit()
            return True
        query, service = item
        check_id = f"{run.id}:{query['id']}:{service}"
        user = db.get(User, run.user_id)
        capture_row = saved.get((query["id"], service))
        needs_collect = capture_row is None
        if not capture_row:
            try:
                reserve_checks(db, user, [check_id], price, ai_client)
            except HTTPException as exc:
                run = _owned_locked(db, run_id, token)
                if run:
                    run.state, run.desired_state = "paused", "paused"
                    run.error = str(exc.detail)[:1000]
                    run.lease_token = run.lease_until = None
                    db.commit()
                return True
        else:
            payload = json.loads(capture_row.answer_json)

    if needs_collect:
        if not _renew(sessions, run_id, token, need_running=True):
            return _release_unstarted(sessions, run_id, token, check_id, snapshot)
        try:
            geo = snapshot["cloud_geography"][service]
            payload = await collector_factory(service, geo).collect(query["text"],
                should_continue=lambda: _renew(sessions, run_id, token, need_running=True))
            payload = {**payload, "brand_names": [snapshot["brand_name"], *snapshot["config"].get("brand_aliases", [])],
                       "brand_domains": snapshot["config"].get("brand_domains", [])}
        except CollectionCancelled:
            return _release_unstarted(sessions, run_id, token, check_id, snapshot)
        except (AdapterError, XMLRiverResponseError, ProviderQuotaError) as exc:
            name = type(exc).__name__
            status = "limit_reached" if name == "ProviderQuotaError" else "auth_required" if "Auth" in name else "error"
            payload = {"shown": False, "answer_text": "", "sources": [], "error_status": status,
                       "error_message": str(exc)[:1000], "brand_names": [snapshot["brand_name"], *snapshot["config"].get("brand_aliases", [])],
                       "brand_domains": snapshot["config"].get("brand_domains", [])}
        with sessions() as saved_db:
            run = _owned_locked(saved_db, run_id, token)
            if not run:
                return False
            capture_row = ServerCapture(run_id=run_id, query_id=query["id"], service=service,
                check_id=check_id, answer_json=json.dumps(payload, ensure_ascii=False))
            saved_db.add(capture_row)
            saved_db.commit()  # Raw answer survives model failure and process restart.

    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run:
            return False
        if payload.get("error_status") or not payload.get("shown"):
            status = payload.get("error_status") or "skipped"
            complete_check(db, db.get(User, run.user_id), check_id, status, commit=False)
            _record(db, run, snapshot, query, service, check_id, payload, status=status,
                    error=payload.get("error_message") or ("AI-блок не показан" if status == "skipped" else None))
            _finish_item(db, run, snapshot)
            db.commit()
            return True

    config = snapshot["config"]
    sources = payload.get("sources", [])[:50]
    answer = payload.get("answer_text") or ""
    rule = rules.evaluate(payload.get("main_text") or answer, sources, snapshot["brand_name"],
        config.get("brand_aliases", []), config.get("brand_domains", []), card_text=payload.get("cards_text", ""))
    clarification = config.get("brand_clarification", "")
    llm = None
    if clarification or not rule.found:
        content = [{"type": "text", "text": _build_prompt(snapshot["brand_name"],
            config.get("brand_aliases", []), answer, sources, query["text"], clarification,
            text_only=True)}]
        try:
            if not _renew(sessions, run_id, token):
                return False
            response = await run_in_threadpool(_analyze_saved, sessions, run_id, token, check_id, content, ai_client)
            if response is None:
                return _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload) or False
            llm = parse_verdict(response["raw"], response["model"])
            if llm is None:
                _clear_invalid_verdict(sessions, run_id, token, check_id, "analysis", response["raw"])
                raise ValueError("Модель вернула неполное решение")
        except (HTTPException, ValueError) as exc:
            disposition = _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload)
            if disposition is not None:
                return disposition
            with sessions() as db:
                run = _owned_locked(db, run_id, token)
                if run:
                    run.state = run.desired_state = "paused"
                    run.error = "Сохранённый ответ ожидает повторного анализа"
                    run.lease_token = run.lease_until = None
                    db.commit()
            return True
    verdict = merge(rule, llm, confidence_threshold=0.7, semantic_authoritative=bool(clarification))
    if verdict.needs_review and llm is not None:
        text = content[0]["text"] + "\n\nПервая модель сочла упоминание найденным: " + (llm.quote or "")
        try:
            if not _renew(sessions, run_id, token):
                return False
            response = await run_in_threadpool(_arbitrate_saved, sessions, run_id, token, check_id,
                [{"type": "text", "text": text}], ai_client)
            if response is None:
                return _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload) or False
            arbiter = parse_verdict(response["raw"], response["model"])
            if arbiter is None:
                _clear_invalid_verdict(sessions, run_id, token, check_id, "arbitration", response["raw"])
                raise ValueError("Арбитр вернул неполное решение")
            verdict = with_arbiter(verdict, arbiter)
        except (HTTPException, ValueError):
            disposition = _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload)
            if disposition is not None:
                return disposition
            with sessions() as db:
                run = _owned_locked(db, run_id, token)
                if run:
                    run.state = run.desired_state = "paused"
                    run.error = "Сохранённый ответ ожидает повторного арбитража"
                    run.lease_token = run.lease_until = None
                    db.commit()
            return True
    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run:
            return False
        user = db.get(User, run.user_id)
        complete_check(db, user, check_id, verdict.status, commit=False)
        _record(db, run, snapshot, query, service, check_id, payload, verdict)
        _finish_item(db, run, snapshot)
        db.commit()
    return True


async def worker(sessions, ai_client, price):
    while True:
        try:
            advanced = await cloud_tick(sessions, ai_client, price)
        except Exception:
            import logging
            # Database exceptions may embed bound answer text in their parameters.
            logging.getLogger(__name__).error("Cloud scan tick failed; retrying")
            advanced = False
        await asyncio.sleep(0.2 if advanced else 3)
