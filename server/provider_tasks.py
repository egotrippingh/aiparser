"""Database-wide admission and recovery of paid provider tasks."""
from __future__ import annotations

import asyncio
import json
import hmac
import os
import time
import uuid
from datetime import timedelta, timezone

from sqlalchemy import func, select, update

from server.models import Check, ControlRun, ProviderAccount, ProviderTask, ServerCapture, User, utcnow
from server.scrapeless import CollectionDeferred, Rejected, SubmissionUnknown
from server import scrapeless

ACTIVE = ("submitting", "submitted", "uncertain")


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def paused_at(account, timestamp):
    if account.paused:
        return True
    cutoff = account.last_paused_at
    if not cutoff:
        return False
    return _aware(timestamp) <= _aware(cutoff)


def paused_for_run(account, run):
    return paused_at(account, run.scheduled_for or run.created_at)


def _skip_and_release(db, run, task, check_id, query_id, service, now):
    """Terminalize unadmitted work and release any unused reservation atomically."""
    if task is None:
        task = ProviderTask(check_id=check_id, run_id=run.id, query_id=query_id,
            service=service, submission_token=uuid.uuid4().hex, state="skipped")
        db.add(task)
    else:
        task.state, task.updated_at = "skipped", now
    check = db.scalar(select(Check).where(Check.user_id == run.user_id,
        Check.client_check_id == check_id))
    if check and check.status == "reserved":
        from server.checks import complete_check
        complete_check(db, db.get(User, run.user_id), check_id, "skipped", commit=False)
    return task


def skip_if_paused(sessions, run_id, token, query_id, service):
    """Durably skip only work excluded by a pause, without admitting fresh work."""
    check_id = f"{run_id}:{query_id}:{service}"
    with sessions() as db:
        if not db.execute(update(ProviderAccount).where(ProviderAccount.service == service)
                .values(revision=ProviderAccount.revision + 1)).rowcount:
            raise RuntimeError("Provider account migration is missing")
        task = db.get(ProviderTask, check_id)
        if task and task.state != "rejected":
            db.commit()
            return task if task.state == "skipped" else None
        run = db.get(ControlRun, run_id)
        now = utcnow()
        if (not run or run.lease_token != token or not run.lease_until or
                _aware(run.lease_until) < now or run.desired_state != "running"):
            return None
        account = db.get(ProviderAccount, service)
        if not paused_for_run(account, run):
            db.commit()
            return None
        task = _skip_and_release(db, run, task, check_id, query_id, service, now)
        db.commit()
        return task


def admit(sessions, run_id, token, query_id, service, limit):
    """Account lock is separate from the wallet reservation's committing transaction."""
    check_id = f"{run_id}:{query_id}:{service}"
    with sessions() as db:
        # UPDATE locks on both PostgreSQL and SQLite, including concurrent first admission.
        if not db.execute(update(ProviderAccount).where(ProviderAccount.service == service)
                .values(revision=ProviderAccount.revision + 1)).rowcount:
            raise RuntimeError("Provider account migration is missing")
        task = db.get(ProviderTask, check_id)
        if task and task.state not in ("rejected", "expired"):
            db.commit()
            return task, False
        run = db.get(ControlRun, run_id)
        now = utcnow()
        if task and task.state == "expired" and (not run or
                json.loads(run.snapshot_json).get("collection_policy") != "complete"):
            db.commit()
            return task, False
        if (not run or run.lease_token != token or not run.lease_until or
                _aware(run.lease_until) < now or run.desired_state != "running"):
            return None, False
        account = db.get(ProviderAccount, service)
        # A manual pause discards not-yet-admitted work from older runs.  It is
        # deliberately not a cooldown: resuming must not recreate that backlog.
        if paused_for_run(account, run):
            task = _skip_and_release(db, run, task, check_id, query_id, service, now)
            db.commit()
            return task, False
        if account.cooldown_until and _aware(account.cooldown_until) > now:
            return None, False
        active = db.scalar(select(func.count()).select_from(ProviderTask).where(
            ProviderTask.service == service, ProviderTask.state.in_(ACTIVE)))
        if active >= limit:
            return None, False
        if task:
            if task.attempts >= 3 or task.state == "expired":
                if json.loads(run.snapshot_json).get("collection_policy") != "complete":
                    raise CollectionDeferred("Лимит попыток сбора исчерпан; требуется проверка администратора")
                # Keep retrying new checks after a durable cooldown, without a paid retry storm.
                if _aware(task.updated_at) + timedelta(minutes=15) > now:
                    raise CollectionDeferred("Сервис сбора временно недоступен; автоматическая перепроверка ожидает повторной попытки")
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
    # Authenticated POST confirmation takes precedence over an early notification.
    with sessions() as db:
        db.execute(update(ProviderAccount).where(ProviderAccount.service == task.service)
            .values(revision=ProviderAccount.revision + 1))
        db.execute(update(ProviderTask).where(ProviderTask.check_id == task.check_id,
            ProviderTask.submission_token == task.submission_token,
            ProviderTask.state.in_(ACTIVE)).values(task_id=task_id, state="submitted", updated_at=utcnow()))
        db.commit()


def failed(sessions, task, *, uncertain=False, expired=False, cooldown=30, no_handle=False):
    with sessions() as db:
        db.execute(update(ProviderAccount).where(ProviderAccount.service == task.service)
            .values(revision=ProviderAccount.revision + 1))
        account = db.get(ProviderAccount, task.service)
        if account and cooldown > 0:
            deadline = utcnow() + timedelta(seconds=cooldown)
            if not account.cooldown_until or _aware(account.cooldown_until) < deadline:
                account.cooldown_until = deadline
        conditions = [ProviderTask.check_id == task.check_id,
            ProviderTask.submission_token == task.submission_token,
            ProviderTask.state != "completed"]
        if uncertain or no_handle:
            conditions.append(ProviderTask.task_id.is_(None))
        db.execute(update(ProviderTask).where(*conditions).values(
                state="expired" if expired else "uncertain" if uncertain else "rejected", updated_at=utcnow()))
        db.commit()


def callback(sessions, check_id, capability, task_id):
    """The capability identifies one attempt; its body is never answer evidence."""
    from fastapi import HTTPException
    with sessions() as db:
        task = db.get(ProviderTask, check_id)
        if (not task or task.service not in scrapeless.SERVICES or
                not hmac.compare_digest(task.submission_token, capability)):
            raise HTTPException(404, 'Задача не найдена')
        db.execute(update(ProviderAccount).where(ProviderAccount.service == task.service)
            .values(revision=ProviderAccount.revision + 1))
        db.refresh(task)
        if not hmac.compare_digest(task.submission_token, capability):
            raise HTTPException(404, 'Задача не найдена')
        if task.task_id and task.task_id != task_id:
            raise HTTPException(409, 'Идентификатор задачи не совпадает')
        if task.state in ACTIVE and not task.task_id:
            task.task_id, task.state, task.updated_at = task_id, 'submitted', utcnow()
        db.commit()


def recover_scrapeless(sessions):
    """Retire only unknown handles; known tasks remain recoverable by GET."""
    now = utcnow()
    with sessions() as db:
        for service in sorted(scrapeless.SERVICES):
            db.execute(update(ProviderAccount).where(ProviderAccount.service == service)
                .values(revision=ProviderAccount.revision + 1))
            tasks = db.scalars(select(ProviderTask).where(ProviderTask.service == service,
                ProviderTask.state.in_(('submitting', 'uncertain')),
                ProviderTask.task_id.is_(None), ProviderTask.updated_at <= now - timedelta(minutes=15))).all()
            for task in tasks:
                run = db.get(ControlRun, task.run_id)
                if (task.state == 'submitting' and run and run.lease_token and run.lease_until
                        and _aware(run.lease_until) >= now):
                    continue
                task.history_json = json.dumps([*json.loads(task.history_json),
                    {'task_id': None, 'state': task.state}])
                task.submission_token = uuid.uuid4().hex
                if run and run.desired_state == 'cancelled':
                    _skip_and_release(db, run, task, task.check_id, task.query_id, service, now)
                else:
                    eligible = (run and run.state in ('queued', 'running', 'paused') and
                        json.loads(run.snapshot_json).get('collection_policy') == 'complete')
                    task.state = 'rejected' if eligible and task.attempts < 3 else 'retry_exhausted'
            db.commit()


def recover_xml(sessions):
    # A read timeout is not a total deadline; never free a live owner's slot.
    with sessions() as db:
        live_owner = select(ControlRun.id).where(ControlRun.id == ProviderTask.run_id,
            ControlRun.lease_token.is_not(None), ControlRun.lease_until >= utcnow()).exists()
        for service in ("google_aio", "yandex_neuro"):
            db.execute(update(ProviderAccount).where(ProviderAccount.service == service)
                .values(revision=ProviderAccount.revision + 1))
            db.execute(update(ProviderTask).where(ProviderTask.service == service,
                ProviderTask.state.in_(ACTIVE), ProviderTask.updated_at < utcnow() - timedelta(minutes=15),
                ~live_owner)
                .values(state="rejected", updated_at=utcnow()))
        db.commit()


def save(sessions, task, payload):
    """Commit the answer and release capacity atomically, independently of run ownership."""
    with sessions() as db:
        db.execute(update(ProviderAccount).where(ProviderAccount.service == task.service)
            .values(revision=ProviderAccount.revision + 1))
        current = db.get(ProviderTask, task.check_id)
        if not current or current.submission_token != task.submission_token or current.state == "completed":
            return False
        current.answer_json = json.dumps(payload, ensure_ascii=False)
        current.state, current.updated_at = "completed", utcnow()
        if not db.scalar(select(ServerCapture.id).where(ServerCapture.check_id == task.check_id)):
            db.add(ServerCapture(run_id=task.run_id, query_id=task.query_id, service=task.service,
                check_id=task.check_id, answer_json=current.answer_json))
        db.commit()
        return True


async def collect(sessions, client, run_id, token, query, service, country, limit,
                  should_start, should_drain, enrich):
    with sessions() as db:
        task = db.get(ProviderTask, f"{run_id}:{query['id']}:{service}")
        complete = bool(task and task.state == "expired" and
            json.loads(db.get(ControlRun, run_id).snapshot_json).get("collection_policy") == "complete")
    fresh = False
    if complete:
        if _aware(task.updated_at) + timedelta(minutes=15) > utcnow():
            raise CollectionDeferred("Автоматическая перепроверка ожидает повторной попытки")
        if not should_drain():
            raise CollectionDeferred("Созданная задача ожидает получения сохранённого ответа")
        # Recheck the old handle before buying another task after a terminal expiry.
        status, payload = await client.poll(task.task_id)
        if status == "success":
            payload = enrich(payload)
            if not save(sessions, task, payload):
                raise CollectionDeferred('Ответ сохранён другой попыткой')
            return payload
        if status not in ("expired", "failed"):
            raise CollectionDeferred("Созданная задача ожидает получения сохранённого ответа")
    if task and task.state in ("rejected", "expired"):
        task = None
    admission_deadline = time.monotonic() + 5
    while task is None:
        if not should_start():
            return None
        task, fresh = admit(sessions, run_id, token, query["id"], service, limit)
        if task is None:
            if time.monotonic() >= admission_deadline:
                raise CollectionDeferred("Свободный слот сбора ожидается; запрос остаётся в очереди")
            await asyncio.sleep(.5)
    if task.state == "completed":
        return json.loads(task.answer_json)
    if task.state == "skipped":
        return None
    if task.state == 'retry_exhausted':
        raise CollectionDeferred('Не получено подтверждение после трёх отправок; требуется сверка сервиса сбора')
    if task.state == "expired":
        raise CollectionDeferred("Срок хранения ответа истёк; требуется сверка оплаченной задачи администратором")
    if fresh:
        if not should_start():
            failed(sessions, task, cooldown=0, no_handle=True)
            return None
        try:
            public_base = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
            webhook_url = (f'{public_base}/api/v1/webhooks/scrapeless/{task.check_id}/{task.submission_token}'
                if scrapeless.safe_url(public_base) and public_base.startswith('https://') else None)
            kwargs = {'webhook_url': webhook_url} if webhook_url else {}
            task_id = await client.submit(service, query["text"], country, **kwargs)
        except Rejected as exc:
            cooldown = 10 if exc.status == 429 else 60 if exc.status in (401, 402, 403) else 0
            failed(sessions, task, cooldown=cooldown, no_handle=True)
            raise CollectionDeferred(str(exc)) from exc
        except SubmissionUnknown:
            failed(sessions, task, uncertain=True, cooldown=0)
            with sessions() as db:
                current = db.get(ProviderTask, task.check_id)
                task_id = current.task_id if current.submission_token == task.submission_token else None
            if not task_id:
                raise
        except asyncio.CancelledError:
            failed(sessions, task, uncertain=True, cooldown=0)
            raise
        else:
            submitted(sessions, task, task_id)
    else:
        # A concurrent old owner can still finish its POST and durably save the handle.
        if not task.task_id:
            with sessions() as db:
                current = db.get(ProviderTask, task.check_id)
                task_id = current.task_id
            if not task_id:
                raise SubmissionUnknown("Отправленная задача не подтверждена; требуется сверка у сервиса сбора")
        else:
            task_id = task.task_id
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        # Stop/Pause must drain accepted tasks; shutdown leaves them for a new worker.
        if not should_drain():
            raise CollectionDeferred("Созданная задача ожидает получения сохранённого ответа")
        with sessions() as db:
            current = db.get(ProviderTask, task.check_id)
            if current.submission_token != task.submission_token:
                raise CollectionDeferred('Отправка уже заменена новой попыткой')
            if current.state == 'completed':
                return json.loads(current.answer_json)
            task_id = current.task_id or task_id
        status, payload = await client.poll(task_id)
        if status == "success":
            payload = enrich(payload)
            if not save(sessions, task, payload):
                raise CollectionDeferred('Ответ сохранён другой попыткой')
            return payload
        if status in ("failed", "expired"):
            failed(sessions, task, expired=status == "expired", cooldown=0)
            raise CollectionDeferred("Сервис сбора не завершил задачу; запрос ожидает повторной обработки")
        await asyncio.sleep(1)
    raise CollectionDeferred("Сервис сбора ещё не завершил задачу; получение продолжится по её идентификатору")


async def collect_xml(sessions, collector, run_id, token, query, service, limit, should_start, enrich):
    task = None
    admission_deadline = time.monotonic() + 5
    while task is None:
        if not should_start():
            return None
        task, fresh = admit(sessions, run_id, token, query["id"], service, limit)
        if task is None:
            if time.monotonic() >= admission_deadline:
                raise CollectionDeferred("Свободный слот сбора ожидается; запрос остаётся в очереди")
            await asyncio.sleep(.5)
    if task.state == "completed":
        return json.loads(task.answer_json)
    if task.state == "skipped":
        return None
    if not fresh:
        # XMLRiver has no result handle; its six 90s calls + backoff are bounded below 15m.
        if _aware(task.updated_at) + timedelta(minutes=15) < utcnow():
            failed(sessions, task, cooldown=0)
        raise CollectionDeferred("Предыдущий запрос поиска ожидает восстановления")
    try:
        payload = enrich(await collector.collect(query["text"], should_continue=should_start))
    except BaseException as exc:
        from shared.xmlriver import XMLRiverResponseError, CollectionCancelled
        # Query failures retain their own retry budget, not an account-wide pause.
        cooldown = 0 if isinstance(exc, (XMLRiverResponseError, CollectionCancelled, asyncio.CancelledError)) else 30
        failed(sessions, task, cooldown=cooldown)
        raise
    save(sessions, task, payload)
    return payload
