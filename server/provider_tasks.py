"""Database-wide admission and recovery of paid provider tasks."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import timedelta, timezone

from sqlalchemy import func, select, update

from server.models import ControlRun, ProviderAccount, ProviderTask, ServerCapture, utcnow
from server.scrapeless import CollectionDeferred, Rejected, SubmissionUnknown, SERVICES as SCRAPELESS_SERVICES

ACTIVE = ("submitting", "submitted", "uncertain")
_MAX_ADMIT_DELAY = 30.0
POLL_SECONDS = 600
STALE_AFTER = timedelta(minutes=15)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def admit_delay(sessions, service, *, attempt: int = 0) -> float:
    """How long to wait before the next admission try. Honors shared cooldown first."""
    with sessions() as db:
        account = db.get(ProviderAccount, service)
        now = utcnow()
        if account and account.cooldown_until and _aware(account.cooldown_until) > now:
            return min(_MAX_ADMIT_DELAY, max(0.5, (_aware(account.cooldown_until) - now).total_seconds()))
    # Full slots / brief races: exponential backoff with a small jitter, capped.
    base = min(8.0, 0.5 * (2 ** min(max(attempt, 0), 4)))
    return min(_MAX_ADMIT_DELAY, base + (attempt % 3) * 0.05)


def admit(sessions, run_id, token, query_id, service, limit):
    """Account lock is separate from the wallet reservation's committing transaction."""
    check_id = f"{run_id}:{query_id}:{service}"
    with sessions() as db:
        # UPDATE locks on both PostgreSQL and SQLite, including concurrent first admission.
        if not db.execute(update(ProviderAccount).where(ProviderAccount.service == service)
                .values(revision=ProviderAccount.revision + 1)).rowcount:
            raise RuntimeError("Provider account migration is missing")
        task = db.get(ProviderTask, check_id)
        if task and task.state != "rejected":
            db.commit()
            return task, False
        run = db.get(ControlRun, run_id)
        now = utcnow()
        if (not run or run.lease_token != token or not run.lease_until or
                _aware(run.lease_until) < now or run.desired_state != "running"):
            return None, False
        account = db.get(ProviderAccount, service)
        if account.cooldown_until and _aware(account.cooldown_until) > now:
            return None, False
        active = db.scalar(select(func.count()).select_from(ProviderTask).where(
            ProviderTask.service == service, ProviderTask.state.in_(ACTIVE)))
        if active >= limit:
            return None, False
        if task:
            if task.attempts >= 3:
                raise CollectionDeferred("Лимит попыток сбора исчерпан; требуется проверка администратора",
                                         account=True)
            task.history_json = json.dumps([*json.loads(task.history_json),
                {"task_id": task.task_id, "state": task.state}])
            task.attempts += 1
            task.state, task.task_id = "submitting", None
            task.submission_token = uuid.uuid4().hex
            task.updated_at = now
        else:
            task = ProviderTask(check_id=check_id, run_id=run_id, query_id=query_id,
                service=service, submission_token=uuid.uuid4().hex, state="submitting")
            db.add(task)
        db.commit()
        return task, True


def submitted(sessions, task, task_id):
    # A late successful POST must retain its handle even when the run lease changed.
    with sessions() as db:
        db.execute(update(ProviderTask).where(ProviderTask.check_id == task.check_id,
            ProviderTask.submission_token == task.submission_token,
            ProviderTask.task_id.is_(None)).values(task_id=task_id, state="submitted", updated_at=utcnow()))
        db.commit()


def failed(sessions, task, *, uncertain=False, expired=False, cooldown=30):
    with sessions() as db:
        db.execute(update(ProviderAccount).where(ProviderAccount.service == task.service)
            .values(revision=ProviderAccount.revision + 1,
                    cooldown_until=utcnow() + timedelta(seconds=cooldown)))
        db.execute(update(ProviderTask).where(ProviderTask.check_id == task.check_id,
            ProviderTask.submission_token == task.submission_token,
            ProviderTask.state != "completed").values(
                state="expired" if expired else "uncertain" if uncertain else "rejected", updated_at=utcnow()))
        db.commit()


def set_cooldown(sessions, service, seconds):
    if seconds <= 0:
        return
    with sessions() as db:
        db.execute(update(ProviderAccount).where(ProviderAccount.service == service)
            .values(revision=ProviderAccount.revision + 1,
                    cooldown_until=utcnow() + timedelta(seconds=seconds)))
        db.commit()


def recover_xml(sessions):
    """Free slots left by a dead owner. Never drop a Scrapeless handle that can still be polled."""
    with sessions() as db:
        live_owner = select(ControlRun.id).where(ControlRun.id == ProviderTask.run_id,
            ControlRun.lease_token.is_not(None), ControlRun.lease_until >= utcnow()).exists()
        cutoff = utcnow() - STALE_AFTER
        for account in db.scalars(select(ProviderAccount)):
            db.execute(update(ProviderAccount).where(ProviderAccount.service == account.service)
                .values(revision=ProviderAccount.revision + 1))
            if account.service in SCRAPELESS_SERVICES:
                # submitting/uncertain have no pollable id; retrying POST could double-charge.
                db.execute(update(ProviderTask).where(ProviderTask.service == account.service,
                    ProviderTask.state.in_(("submitting", "uncertain")),
                    ProviderTask.updated_at < cutoff, ~live_owner)
                    .values(state="expired", updated_at=utcnow()))
            else:
                db.execute(update(ProviderTask).where(ProviderTask.service == account.service,
                    ProviderTask.state.in_(ACTIVE), ProviderTask.updated_at < cutoff, ~live_owner)
                    .values(state="rejected", updated_at=utcnow()))
        db.commit()


def save(sessions, task, payload):
    """Commit the answer and release capacity atomically, independently of run ownership."""
    with sessions() as db:
        db.execute(update(ProviderAccount).where(ProviderAccount.service == task.service)
            .values(revision=ProviderAccount.revision + 1))
        current = db.get(ProviderTask, task.check_id)
        if current.submission_token != task.submission_token or current.state == "completed":
            return
        current.answer_json = json.dumps(payload, ensure_ascii=False)
        current.state, current.updated_at = "completed", utcnow()
        if not db.scalar(select(ServerCapture.id).where(ServerCapture.check_id == task.check_id)):
            db.add(ServerCapture(run_id=task.run_id, query_id=task.query_id, service=task.service,
                check_id=task.check_id, answer_json=current.answer_json))
        db.commit()


async def collect(sessions, client, run_id, token, query, service, country, limit,
                  should_start, should_drain, enrich):
    with sessions() as db:
        task = db.get(ProviderTask, f"{run_id}:{query['id']}:{service}")
    fresh = False
    if task and task.state == "rejected":
        task = None
    attempt = 0
    while task is None:
        if not should_start():
            return None
        task, fresh = admit(sessions, run_id, token, query["id"], service, limit)
        if task is None:
            await asyncio.sleep(admit_delay(sessions, service, attempt=attempt))
            attempt += 1
    if task.state == "completed":
        return json.loads(task.answer_json)
    if task.state == "expired":
        raise CollectionDeferred("Срок хранения ответа истёк; требуется сверка оплаченной задачи администратором",
                                 account=True)
    if fresh:
        if not should_start():
            failed(sessions, task, cooldown=0)
            return None
        try:
            task_id = await client.submit(service, query["text"], country)
        except Rejected as exc:
            failed(sessions, task, cooldown=60 if exc.status != 429 else 10)
            raise CollectionDeferred(str(exc), account=True) from exc
        except (SubmissionUnknown, asyncio.CancelledError):
            failed(sessions, task, uncertain=True)
            raise
        submitted(sessions, task, task_id)
    else:
        # A concurrent old owner can still finish its POST and durably save the handle.
        if not task.task_id:
            with sessions() as db:
                current = db.get(ProviderTask, task.check_id)
                task_id = current.task_id
            if not task_id:
                if _aware(task.updated_at) + STALE_AFTER < utcnow():
                    failed(sessions, task, expired=True, cooldown=0)
                    raise CollectionDeferred(
                        "Срок хранения ответа истёк; требуется сверка оплаченной задачи администратором",
                        account=True)
                raise SubmissionUnknown("Отправленная задача не подтверждена; требуется сверка у сервиса сбора")
        else:
            task_id = task.task_id
    deadline = time.monotonic() + POLL_SECONDS
    while time.monotonic() < deadline:
        # Stop/Pause must drain accepted tasks; shutdown leaves them for a new worker.
        if not should_drain():
            raise CollectionDeferred("Созданная задача ожидает получения сохранённого ответа")
        status, payload = await client.poll(task_id)
        if status == "success":
            payload = enrich(payload)
            save(sessions, task, payload)
            return payload
        if status in ("failed", "expired"):
            failed(sessions, task, expired=status == "expired")
            raise CollectionDeferred("Сервис сбора не завершил задачу; запрос ожидает повторной обработки",
                                     account=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(1.0, remaining))
    # Handle stays submitted; siblings keep their slots. Another tick will poll it.
    return None


async def collect_xml(sessions, collector, run_id, token, query, service, limit, should_start, enrich):
    task = None
    attempt = 0
    while task is None:
        if not should_start():
            return None
        task, fresh = admit(sessions, run_id, token, query["id"], service, limit)
        if task is None:
            await asyncio.sleep(admit_delay(sessions, service, attempt=attempt))
            attempt += 1
    if task.state == "completed":
        return json.loads(task.answer_json)
    if not fresh:
        # XMLRiver has no result handle; its six 90s calls + backoff are bounded below 15m.
        if _aware(task.updated_at) + timedelta(minutes=15) < utcnow():
            failed(sessions, task, cooldown=0)
        raise CollectionDeferred("Предыдущий запрос поиска ожидает восстановления")
    try:
        payload = enrich(await collector.collect(query["text"], should_continue=should_start))
    except BaseException:
        failed(sessions, task)
        raise
    save(sessions, task, payload)
    return payload
