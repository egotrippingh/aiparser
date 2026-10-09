"""Durable server capture and analysis for XMLRiver-backed services."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import and_, or_, select, update

from app.detect import rules
from app.detect.merge import merge, with_arbiter
from server.checks import analyze_check, arbitrate_check, complete_check, reserve_checks
from server.models import Check, CloudResult, ControlRun, ServerCapture, User, utcnow
from shared.detection import _build_prompt, parse_verdict
from shared.xmlriver import XMLRiverClient, AdapterError, XMLRiverResponseError, ProviderQuotaError, ProviderThrottleError, CollectionCancelled, account_limits

CLOUD = {"google_aio", "yandex_neuro"}
LEASE = timedelta(minutes=5)


def _pairs(snapshot):
    return [(q, s) for s in snapshot["cloud_services"] for q in snapshot["queries"]]


def _claim(sessions, blocked_services=()):
    """A bounded lease with a token CAS; another worker may safely take an expired run."""
    with sessions() as db:
        now = utcnow()
        base = (select(ControlRun).where(ControlRun.phase == "cloud",
            ControlRun.state.in_(("queued", "running", "paused")),
            ControlRun.desired_state != "paused",
            or_(ControlRun.lease_until.is_(None), ControlRun.lease_until < now))
            .order_by(ControlRun.created_at, ControlRun.id))
        cursor = None
        while True:
            page = base
            if cursor is not None:
                created, run_id = cursor
                page = page.where(or_(ControlRun.created_at > created,
                    and_(ControlRun.created_at == created, ControlRun.id > run_id)))
            runs = db.scalars(page.limit(20)).all()
            next_cursor = (runs[-1].created_at, runs[-1].id) if runs else None
            for run in runs:
                snap = json.loads(run.snapshot_json)
                if blocked_services and run.desired_state == "running":
                    done = set(db.execute(select(CloudResult.query_id, CloudResult.service).where(
                        CloudResult.run_id == run.id, CloudResult.user_id == run.user_id)).all())
                    saved = set(db.execute(select(ServerCapture.query_id, ServerCapture.service).where(
                        ServerCapture.run_id == run.id)).all())
                    pending = [(q["id"], s) for q, s in _pairs(snap) if (q["id"], s) not in done]
                    if pending and not any(pair in saved or pair[1] not in blocked_services for pair in pending):
                        continue
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
            if not blocked_services or len(runs) < 20:
                break
            cursor = next_cursor
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
        completed = set(complete)
        saved = db.execute(select(ServerCapture.query_id, ServerCapture.service).where(
            ServerCapture.run_id == run.id)).all()
        pending_capture = any(pair not in completed for pair in saved)
        pending_check = db.scalar(select(Check.id).where(Check.user_id == run.user_id,
            Check.client_check_id.startswith(run.id + ":"), Check.status == "reserved")) is not None
        if pending_capture or pending_check:
            run.state = "running"
        else:
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
            retry_saved=bool(check and check.analysis_attempts), accumulate_usage=True)


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
            retry_saved=bool(check and check.arbitration_attempts), accumulate_usage=True)


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


def _parse_cloud_verdict(response):
    try:
        return parse_verdict(response["raw"], response["model"])
    except (TypeError, ValueError):
        return None


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


def _finish_exhausted(sessions, run_id, token, snapshot, query, service, check_id, payload, stage):
    """Turn an exhausted model budget into one durable error and settled/released check."""
    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run:
            return False
        check = db.execute(select(Check).where(Check.user_id == run.user_id,
            Check.client_check_id == check_id).with_for_update()).scalar_one_or_none()
        if not check:
            return False
        attempts = check.analysis_attempts if stage == "analysis" else check.arbitration_attempts
        cached = check.analysis_json if stage == "analysis" else check.arbitration_json
        if attempts < 4 or cached:
            return None
        complete_check(db, db.get(User, run.user_id), check_id, "error", commit=False)
        error = ("Не удалось проанализировать ответ: исчерпан лимит попыток" if stage == "analysis"
                 else "Не удалось разрешить спорный результат: исчерпан лимит попыток")
        _record(db, run, snapshot, query, service, check_id, payload, status="error", error=error)
        _finish_item(db, run, snapshot)
        db.commit()
        return True


def _yield_shutdown(sessions, run_id, token):
    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run:
            return False
        run.lease_token = run.lease_until = None
        db.commit()
        return True


def _provider_error(exc, snapshot):
    name = type(exc).__name__
    status = "limit_reached" if isinstance(exc, ProviderQuotaError) else "auth_required" if "Auth" in name else "error"
    return {"shown": False, "answer_text": "", "sources": [], "error_status": status,
            "error_message": str(exc)[:1000],
            "brand_names": [snapshot["brand_name"], *snapshot["config"].get("brand_aliases", [])],
            "brand_domains": snapshot["config"].get("brand_domains", [])}


async def _prefetch_batch(sessions, run_id, token, snapshot, ai_client, price,
                          collector_factory, limits, shutdown_event, cooldowns, clock):
    """Reserve a bounded affordable set, then commit each returned answer independently."""
    selected = []
    counts = {service: 0 for service in snapshot["cloud_services"]}
    with sessions() as db:
        run = _owned_locked(db, run_id, token)
        if not run or run.desired_state != "running":
            return
        done = set(db.execute(select(CloudResult.query_id, CloudResult.service).where(
            CloudResult.run_id == run.id, CloudResult.user_id == run.user_id)).all())
        saved = set(db.execute(select(ServerCapture.query_id, ServerCapture.service).where(
            ServerCapture.run_id == run.id)).all())
        pending = [(q, s) for q, s in _pairs(snapshot) if (q["id"], s) not in done]
        if any((q["id"], s) in saved for q, s in pending):
            return
        user = db.get(User, run.user_id)
        for query, service in pending:
            if shutdown_event and shutdown_event.is_set():
                break
            if cooldowns and cooldowns.get(service, 0) > clock():
                continue
            if counts[service] >= max(1, min(int(limits.get(service, 1)), 10)):
                continue
            run = _owned_locked(db, run_id, token)
            if not run or run.desired_state != "running":
                break
            check_id = f"{run.id}:{query['id']}:{service}"
            try:
                reserve_checks(db, user, [check_id], price, ai_client)
            except HTTPException as exc:
                if exc.status_code != 402 or not selected:
                    run = _owned_locked(db, run_id, token)
                    if run and run.desired_state == "running":
                        run.state = run.desired_state = "paused"
                        run.error = str(exc.detail)[:1000]
                        db.commit()
                break
            selected.append((query, service, check_id))
            counts[service] += 1

    blocked = set()

    async def collect_one(query, service, check_id):
        def may_continue():
            return (not (shutdown_event and shutdown_event.is_set()) and service not in blocked
                    and _renew(sessions, run_id, token, need_running=True)
                    and not (shutdown_event and shutdown_event.is_set()) and service not in blocked)

        try:
            if not may_continue():
                return query, service, check_id, None, False
            geo = snapshot["cloud_geography"][service]
            payload = await collector_factory(service, geo, max_attempts=6).collect(
                query["text"], should_continue=may_continue)
            payload = {**payload,
                       "brand_names": [snapshot["brand_name"], *snapshot["config"].get("brand_aliases", [])],
                       "brand_domains": snapshot["config"].get("brand_domains", [])}
        except CollectionCancelled:
            payload = None
        except ProviderQuotaError as exc:
            blocked.add(service)
            if isinstance(exc, ProviderThrottleError) and cooldowns is not None:
                cooldowns[service] = max(cooldowns.get(service, 0), clock() + exc.retry_after)
            payload = _provider_error(exc, snapshot)
        except (AdapterError, XMLRiverResponseError) as exc:
            payload = _provider_error(exc, snapshot)
        except Exception as exc:
            logging.getLogger(__name__).error("Cloud batch collection failed (%s)", type(exc).__name__)
            return query, service, check_id, None, True
        return query, service, check_id, payload, False

    tasks = [asyncio.create_task(collect_one(*item)) for item in selected]
    failed = False
    for task in asyncio.as_completed(tasks):
        try:
            query, service, check_id, payload, collection_failed = await task
        except Exception as exc:
            logging.getLogger(__name__).error("Cloud batch task failed (%s)", type(exc).__name__)
            failed = True
            continue
        failed |= collection_failed
        if collection_failed:
            continue  # Keep the reservation for an explicit retry; never record false absence.
        try:
            with sessions() as db:
                run = _owned_locked(db, run_id, token)
                if not run:
                    continue
                if payload is None:
                    if not (shutdown_event and shutdown_event.is_set()):
                        complete_check(db, db.get(User, run.user_id), check_id, "skipped", commit=False)
                else:
                    db.add(ServerCapture(run_id=run_id, query_id=query["id"], service=service,
                        check_id=check_id, answer_json=json.dumps(payload, ensure_ascii=False)))
                db.commit()
        except Exception as exc:
            logging.getLogger(__name__).error("Cloud batch save failed (%s)", type(exc).__name__)
            failed = True
    if failed:
        with sessions() as db:
            run = _owned_locked(db, run_id, token)
            if run and run.desired_state == "running":
                run.state = run.desired_state = "paused"
                run.error = "Сбор части ответов прервался; сохранённые ответы доступны после возобновления"
                run.lease_token = run.lease_until = None
                db.commit()
        return
    if blocked:
        with sessions() as db:
            run = _owned_locked(db, run_id, token)
            if run and run.desired_state == "running":
                run.desired_state = "paused"
                run.error = "XMLRiver ограничил частоту или баланс; сохранённые ответы доступны после возобновления"
                db.commit()


async def cloud_tick(sessions, ai_client, price, collector_factory=XMLRiverClient,
                     *, prefetch_limits=None, shutdown_event=None, cooldowns=None, clock=time.monotonic):
    """Process one saved or fresh answer. Returns whether a cloud run was advanced."""
    blocked_services = {service for service, until in (cooldowns or {}).items() if until > clock()}
    claim = _claim(sessions, blocked_services)
    if not claim:
        return False
    run_id, token, snapshot = claim
    if shutdown_event and shutdown_event.is_set():
        return _yield_shutdown(sessions, run_id, token)
    if prefetch_limits:
        await _prefetch_batch(sessions, run_id, token, snapshot, ai_client, price,
                              collector_factory, prefetch_limits, shutdown_event, cooldowns, clock)
    if shutdown_event and shutdown_event.is_set():
        return _yield_shutdown(sessions, run_id, token)
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
        # Drain committed answers before starting another provider request, even
        # after a partial batch crash that saved only a later pair.
        item = next(((q, s) for q, s in pending if (q["id"], s) in saved), None)
        if item is None and run.desired_state == "running":
            item = next(((q, s) for q, s in pending if not cooldowns or
                cooldowns.get(s, 0) <= clock()), None)
        if item is None:
            if run.desired_state == "running":
                run.lease_token = run.lease_until = None
                db.commit()
                return False
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
        if shutdown_event and shutdown_event.is_set():
            return _yield_shutdown(sessions, run_id, token)
        if not _renew(sessions, run_id, token, need_running=True):
            return _release_unstarted(sessions, run_id, token, check_id, snapshot)
        try:
            geo = snapshot["cloud_geography"][service]
            payload = await collector_factory(service, geo).collect(query["text"],
                should_continue=lambda: not (shutdown_event and shutdown_event.is_set())
                    and _renew(sessions, run_id, token, need_running=True))
            payload = {**payload, "brand_names": [snapshot["brand_name"], *snapshot["config"].get("brand_aliases", [])],
                       "brand_domains": snapshot["config"].get("brand_domains", [])}
        except CollectionCancelled:
            if shutdown_event and shutdown_event.is_set():
                return _yield_shutdown(sessions, run_id, token)
            return _release_unstarted(sessions, run_id, token, check_id, snapshot)
        except (AdapterError, XMLRiverResponseError, ProviderQuotaError) as exc:
            payload = _provider_error(exc, snapshot)
        with sessions() as saved_db:
            run = _owned_locked(saved_db, run_id, token)
            if not run:
                return False
            capture_row = ServerCapture(run_id=run_id, query_id=query["id"], service=service,
                check_id=check_id, answer_json=json.dumps(payload, ensure_ascii=False))
            saved_db.add(capture_row)
            saved_db.commit()  # Raw answer survives model failure and process restart.

    if shutdown_event and shutdown_event.is_set():
        return _yield_shutdown(sessions, run_id, token)

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
            if shutdown_event and shutdown_event.is_set():
                return _yield_shutdown(sessions, run_id, token)
            if not _renew(sessions, run_id, token):
                return False
            response = await run_in_threadpool(_analyze_saved, sessions, run_id, token, check_id, content, ai_client)
            if response is None:
                return _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload) or False
            llm = _parse_cloud_verdict(response)
            if llm is None:
                _clear_invalid_verdict(sessions, run_id, token, check_id, "analysis", response["raw"])
                raise ValueError("Модель вернула неполное решение")
        except (HTTPException, ValueError) as exc:
            disposition = _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload)
            if disposition is not None:
                return disposition
            exhausted = _finish_exhausted(sessions, run_id, token, snapshot, query, service,
                check_id, payload, "analysis")
            if exhausted is not None:
                return exhausted
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
            if shutdown_event and shutdown_event.is_set():
                return _yield_shutdown(sessions, run_id, token)
            if not _renew(sessions, run_id, token):
                return False
            response = await run_in_threadpool(_arbitrate_saved, sessions, run_id, token, check_id,
                [{"type": "text", "text": text}], ai_client)
            if response is None:
                return _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload) or False
            arbiter = _parse_cloud_verdict(response)
            if arbiter is None:
                _clear_invalid_verdict(sessions, run_id, token, check_id, "arbitration", response["raw"])
                raise ValueError("Арбитр вернул неполное решение")
            verdict = with_arbiter(verdict, arbiter)
        except (HTTPException, ValueError):
            disposition = _defer_or_cancel(sessions, run_id, token, snapshot, query, service, check_id, payload)
            if disposition is not None:
                return disposition
            exhausted = _finish_exhausted(sessions, run_id, token, snapshot, query, service,
                check_id, payload, "arbitration")
            if exhausted is not None:
                return exhausted
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


def _run_tick_in_thread(sessions, ai_client, price, limits=None, shutdown_event=None,
                        cooldowns=None):
    # The tick contains synchronous SQLAlchemy calls and must not block uvicorn's loop.
    return asyncio.run(cloud_tick(sessions, ai_client, price,
        prefetch_limits=limits, shutdown_event=shutdown_event, cooldowns=cooldowns))


async def worker(sessions, ai_client, price, *, prefetch_limits=None):
    if prefetch_limits is None:
        prefetch_limits = await account_limits()
    shutdown_event = threading.Event()
    cooldowns = {}
    while True:
        current = asyncio.create_task(asyncio.to_thread(_run_tick_in_thread, sessions, ai_client,
            price, prefetch_limits, shutdown_event, cooldowns))
        try:
            advanced = await asyncio.shield(current)
        except asyncio.CancelledError:
            # Prevent another provider retry, then drain the current bounded request.
            shutdown_event.set()
            try:
                await current
            except Exception:
                pass
            raise
        except Exception:
            import logging
            # Database exceptions may embed bound answer text in their parameters.
            logging.getLogger(__name__).error("Cloud scan tick failed; retrying")
            advanced = False
        await asyncio.sleep(0.2 if advanced else 3)
