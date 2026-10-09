"""Очередь «запрос × сервис»: сердце скана.

По умолчанию — один сервис за другим. Если в проекте включён параллельный
скан, выбранные сервисы идут одновременно: у каждого свой браузер со своим
профилем и своя очередь. Внутри сервиса запросы всегда строго по одному, с
человекоподобными паузами: сайт видит одного неторопливого пользователя,
а не пачку запросов.

Три вещи, которые здесь стоит понимать сразу:

**Одна вкладка на сервис.** Сайт грузится один раз в `ensure_ready`, дальше
между запросами адаптер только сбрасывает состояние (клик «Новый чат»).
Раньше вкладка создавалась на каждый запрос и сайт грузился заново — это и
были те самые «бесконечные перезапуски браузера», примерно 6 секунд впустую
на каждой паре «запрос × сервис».

**Стена лимита.** Бесплатные тарифы ChatGPT и Perplexity выдерживают около
сорока запросов, после чего страница перестаёт показывать поле ввода. В
прогоне 28.08.2026 это стоило 115 бессмысленных таймаутов по 30 секунд и
наполовину мусорную статистику. Теперь адаптер бросает
`ServiceUnavailableError`, а оркестратор, увидев их подряд, прекращает сервис
целиком и честно помечает остаток статусом `limit_reached`.

**Дозапуск.** Раз база в сотню запросов физически не проходит за один прогон,
скан можно продолжить: пары, по которым уже есть годный результат, при
дозапуске пропускаются, а дописываем мы в ТОТ ЖЕ скан — иначе дашборд,
показывающий последний скан за день, увидел бы только хвост базы.

Прогресс публикуется и потоком (SSE, `app/api/scans.py`), и снимком состояния
(`ScanController.snapshot`) — второе нужно, чтобы подключиться к идущему скану
после переключения вкладки или перезапуска приложения.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import date, datetime
from types import SimpleNamespace

from app import billing, config, imaging, services
from app.db import repo
from app.detect import llm as llm_mod
from app.detect import deep as deep_mod
from app.detect import rules
from app.detect.merge import merge, should_call_llm, with_arbiter, with_deep
from app.scanner import humanize
from app.scanner.adapters import ADAPTERS, get_adapter
from app.scanner.adapters import xmlriver
from app.scanner.adapters.base import (
    AdapterError,
    AuthRequiredError,
    CaptchaError,
    ProviderQuotaError,
    ServiceUnavailableError,
)
from app.scanner.browser import open_captcha_window, service_context

log = logging.getLogger("aiparser.orchestrator")

# Сколько «сервис не принимает запросы» подряд считаем стеной лимита.
# Единичный сбой бывает случайным (подвисла вёрстка), три подряд — это уже
# не совпадение, а состояние аккаунта.
LIMIT_STRIKES = 3
_BROWSER_TASK_TIMEOUT = 900
_BROWSER_CANCEL_GRACE = 10


class BrowserTaskTimeout(AdapterError):
    pass


class AdaptivePacer:
    """Frozen per-service pause policy; elapsed work counts towards the deadline."""
    def __init__(self, policy: dict | None, lo: float, hi: float) -> None:
        self.policy = policy or {}
        self.floor = max(lo, float(self.policy.get("floor_sec", lo)))
        self.ceiling = max(self.floor, float(self.policy.get("ceiling_sec", hi)))
        self.delay = self.floor
        self.hi = max(self.floor, hi)
        self.successes = 0
        self.next_at = time.monotonic()

    def throttled(self) -> None:
        self.delay = min(self.ceiling, max(self.floor, self.delay * 2))
        self.successes = 0

    def clean(self) -> None:
        self.successes += 1
        if self.successes >= 3:
            self.delay = max(self.floor, self.delay - float(self.policy.get("recovery_sec", 1)))
            self.successes = 0

    def completed(self, throttled: bool, clean: bool, idx: int, break_every: int) -> None:
        if throttled:
            self.throttled()
        elif clean:
            self.clean()
        delay = min(self.ceiling, random.uniform(self.delay, max(self.delay, self.hi)))
        if break_every and idx % break_every == 0:
            delay = max(delay, random.uniform(60, 180))
        self.next_at = time.monotonic() + delay

    async def wait(self) -> None:
        remaining = self.next_at - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)


class ScanAlreadyRunning(RuntimeError):
    pass


class ScanController:
    """Состояние одного запущенного скана: события + прогресс + флаги управления."""

    def __init__(self, scan_id: int, project_id: int, total: int, scan_date: str,
                 billing_run_id: str = "") -> None:
        self.scan_id = scan_id
        self.project_id = project_id
        # Дата среза берётся из самого скана, а не из «сегодня»: при дозапуске
        # на следующий день результаты и скриншоты должны лечь к своему срезу.
        self.scan_date = scan_date
        self.billing_run_id = billing_run_id
        self.billing_pairs: dict[tuple[int, str], str] = {}
        self.total = total
        self.done = 0
        self.current_service: str | None = None
        # Все сервисы, которые идут прямо сейчас: при параллельном скане их
        # несколько, current_service остаётся для совместимости.
        self.running: list[str] = []
        self.state = "running"          # running | paused | stopping | finished
        self.started_at = time.time()
        # Прогресс по каждому сервису. При параллельном скане общая средняя
        # скорость врёт: Google проходит запрос за 20–40 с, Perplexity — за
        # минуты, и когда Google закончит, общий прогноз окажется заниженным.
        # {service: {"done", "total", "started"}} — заполняет _run_scan.
        self.per_service: dict[str, dict] = {}
        self.completed_pairs: set[tuple[int, str]] = set()
        self.parallel = False
        self.analysis_queue: asyncio.Queue | None = None
        self.analysis_worker: asyncio.Task | None = None
        self.analysis_workers: list[asyncio.Task] = []
        self.scan_task: asyncio.Task | None = None
        self.admitted_pairs: set[tuple[int, str]] = set()
        self.bearer: str | None = None
        self.browser_tasks: set[asyncio.Task] = set()
        self.browser_phase: dict[str, dict] = {}
        self.browser_timeout_services: set[str] = set()

        # Своя очередь у каждого подписчика. Раньше очередь была одна на скан,
        # и два подключения делили события между собой — каждое доставалось
        # кому-то одному. 10.09.2026 сторонний наблюдатель так «не увидел»
        # результаты #104, #109, #112: их забрало окно приложения, а оно,
        # в свою очередь, недосчиталось бы того, что забрал наблюдатель.
        self._subscribers: list[asyncio.Queue[dict]] = []
        self.stop_requested = False
        self.stop_signal = asyncio.Event()
        self.paused = asyncio.Event()
        self.paused.set()               # не на паузе

    # --- управление -------------------------------------------------------

    def emit(self, event: str, **data) -> None:
        item = {"event": event, **data}
        for q in list(self._subscribers):
            q.put_nowait(item)

    def timing(self, phase: str, seconds: float, **data) -> None:
        """Ephemeral phase evidence; results retain only total duration."""
        seconds = round(seconds, 3)
        log.info("scan %s %s %.3fs", self.scan_id, phase, seconds)
        self.emit("phase_timing", phase=phase, seconds=seconds, **data)

    def subscribe(self) -> "asyncio.Queue[dict]":
        q: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue[dict]") -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def pause(self) -> None:
        self.state = "paused"
        self.paused.clear()
        repo.set_scan_status(self.scan_id, "paused")
        self.emit("paused", **self.snapshot())

    def resume(self) -> None:
        self.state = "running"
        self.paused.set()
        repo.set_scan_status(self.scan_id, "running")
        self.emit("resumed", **self.snapshot())

    def stop(self) -> None:
        self.stop_requested = True
        self.state = "stopping"
        self.paused.set()   # разбудить, если стояли на паузе, чтобы выйти из цикла
        self.stop_signal.set()
        self.emit("stopping", **self.snapshot())

    # --- прогресс ---------------------------------------------------------

    def advance(self, service_id: str, query_id: int | None = None) -> None:
        if query_id is not None:
            self.completed_pairs.add((query_id, service_id))
        self.done += 1
        if service_id in self.per_service:
            self.per_service[service_id]["done"] += 1
        self.emit("progress", service=service_id, **self.snapshot())

    def _eta(self, now: float) -> int | None:
        """Сколько ещё идти: по скорости каждого сервиса отдельно.

        Параллельно — сколько осталось самому медленному; по очереди — сумма.
        Сервис, по которому ещё нет ни одного результата, оцениваем по общей
        средней скорости прогона.
        """
        overall = (now - self.started_at) / self.done if self.done else None
        if not self.per_service:
            return int(overall * (self.total - self.done)) if overall and self.total > self.done else None
        etas = []
        for st in self.per_service.values():
            left = st["total"] - st["done"]
            if left <= 0:
                continue
            if st["done"] and st["started"]:
                per_check = (now - st["started"]) / st["done"]
            elif overall:
                per_check = overall
            else:
                return None
            etas.append(per_check * left)
        if not etas:
            return None
        return round(max(etas) if self.parallel else sum(etas))

    def snapshot(self) -> dict:
        """Текущий прогресс + оценка остатка.

        Оценка считается по фактической средней скорости этого прогона, а не
        по нормативу: реальное время на запрос зависит от того, насколько
        долго думает конкретная нейросеть, и предсказать его заранее нельзя.
        """
        now = time.time()
        elapsed = now - self.started_at
        eta = self._eta(now)
        browser_tasks = {service: {**phase, "phase_elapsed_sec": round(time.monotonic() - phase["started"], 1),
                                   "phase_timeout_sec": _BROWSER_TASK_TIMEOUT}
                         for service, phase in self.browser_phase.items()}
        for phase in browser_tasks.values():
            phase.pop("started")
        return {
            "scan_id": self.scan_id,
            "project_id": self.project_id,
            "done": self.done,
            "total": self.total,
            "percent": round(self.done * 100 / self.total, 1) if self.total else 0.0,
            "state": self.state,
            "current_service": self.current_service,
            "running_services": list(self.running),
            "parallel": self.parallel,
            "elapsed_sec": int(elapsed),
            "eta_sec": eta,
            "browser_task": next(iter(browser_tasks.values()), None),
            "browser_tasks": browser_tasks,
            "services": {s: {"done": st["done"], "total": st["total"],
                             "state": st.get("state", "pending"), "error": st.get("error")}
                         for s, st in self.per_service.items()},
        }


_active: dict[int, ScanController] = {}
_scan_start_lock = asyncio.Lock()


def scan_start_lock() -> asyncio.Lock:
    """Serialize reservation setup with the agent's idle outbox recovery."""
    return _scan_start_lock


def get_controller(scan_id: int) -> ScanController | None:
    return _active.get(scan_id)


def active_controller() -> ScanController | None:
    """Единственный идущий скан, если он есть (одновременно допускается один)."""
    return next(iter(_active.values()), None)


async def stop_active_scans() -> None:
    """Stop and join scan workers before their shared HTTP client closes."""
    tasks = []
    for controller in list(_active.values()):
        controller.stop()
        if controller.scan_task and not controller.scan_task.done():
            controller.scan_task.cancel()
            tasks.append(controller.scan_task)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    for controller in list(_active.values()):
        if controller.scan_task is None or controller.scan_task.done():
            _active.pop(controller.scan_id, None)


def _settings_snapshot(services: list[str] | None = None) -> dict:
    """Разворачивает выбранный профиль скорости в конкретные значения.

    Профиль — единственная ручка скорости: держать рядом ещё и отдельные
    поля пауз значило бы иметь два источника правды, которые разъедутся.
    Развёрнутые значения кладём в снимок, чтобы задним числом было видно, в
    каком режиме собирались данные.
    """
    name = humanize.DEFAULT_PROFILE
    prof = humanize.profile(name)
    service_ids = services or list(ADAPTERS)
    per_service_timing = {}
    for service_id in service_ids:
        resolved = humanize.profile(name, service_id)
        own_lo, own_hi = getattr(get_adapter(service_id), "min_delay_sec", (0.0, 0.0))
        delay_lo = max(float(resolved["delay_min_sec"]), own_lo)
        per_service_timing[service_id] = {
            "delay_min_sec": delay_lo,
            "delay_max_sec": max(float(resolved["delay_max_sec"]), own_hi, delay_lo),
            "break_every_n": int(resolved["break_every_n"]),
            "typing_speed": float(resolved["typing"]),
        }
    workers = repo.all_settings().get("analysis_workers", "1")
    return {
        "llm_mode": "smart",
        "llm_confidence_threshold": 0.6,
        # Спорные строки решает вторая модель прямо в скане — иначе они
        # копились бы непроверенными до тех пор, пока до них дойдут руки.
        "arbiter": True,
        "arbiter_model": llm_mod.ARBITER_MODEL_DEFAULT,
        "speed_profile": name,
        "delay_min_sec": float(prof["delay_min_sec"]),
        "delay_max_sec": float(prof["delay_max_sec"]),
        "break_every_n": int(prof["break_every_n"]),
        "typing_speed": float(prof["typing"]),
        "per_service_timing": per_service_timing,
        "adaptive_pacing": {"version": 1, "floor_sec": 0, "ceiling_sec": 60,
                              "recovery_sec": 1},
        "analysis_workers": 2 if workers == "2" else 1,
    }


def _record_auth_state(service_id: str, state: str, *, backend: str = "browser") -> None:
    """Запоминает, что сервис ответил на попытку входа — для статуса в настройках.

    Cookie в профиле говорит «сессия на диске есть», а принял ли её сервис —
    знает только фактический прогон. Храним обе половины.
    """
    repo.set_setting(
        f"{'xmlriver_state' if backend == 'xmlriver' else 'auth_state'}:{service_id}",
        json.dumps({"state": state, "at": datetime.now().isoformat(timespec="seconds")}),
    )


async def start_scan(project_id: int, service_ids: list[str], *, resume: bool = True,
                     headless: bool = False, managed_job: dict | None = None) -> int:
    from app import updates
    async with _scan_start_lock:
        if updates.busy():
            raise ScanAlreadyRunning("Идёт обновление приложения")
        return await _start_scan_unlocked(project_id, service_ids, resume=resume,
                                          headless=headless, managed_job=managed_job)


async def _start_scan_unlocked(project_id: int, service_ids: list[str], *, resume: bool,
                               headless: bool, managed_job: dict | None = None) -> int:
    if _active:
        raise ScanAlreadyRunning("Скан уже выполняется — дождитесь завершения или остановите его")

    project = repo.get_project(project_id)
    if not project:
        raise ValueError("Проект не найден")

    # Сервисы без готового адаптера отсекаем здесь, а не в цикле: иначе они
    # попадут в services_json и навсегда сделают скан «незавершённым» —
    # ожидаемое число проверок никогда не сойдётся с фактическим.
    known = [s for s in service_ids if s in ADAPTERS]
    if not known:
        raise ValueError("Ни для одного из выбранных сервисов нет адаптера")

    queries = repo.list_queries(project_id, only_active=True)

    billing_user = await billing.identity() if billing.enabled() else None
    plan = _plan_for_billing_user(project_id, known, resume,
                                  billing_user["id"] if billing_user else None)
    if managed_job:
        previous_id = int(repo.get_setting(f"managed_scan:{managed_job['id']}", "0") or 0)
        previous = repo.get_scan(previous_id) if previous_id else None
        if previous and previous["status"] == "abandoned":
            raise ValueError("Сохранённые ответы этого задания были завершены без анализа")
        plan = {"date": managed_job["date"], "continue_scan_id": previous_id if previous else None,
                "done_pairs": {(r["query_id"], r["service"]) for r in repo.results_for_scan(previous_id)
                               if r["status"] in repo.CONCLUSIVE_STATUSES} if previous else set()}
    done_pairs = plan["done_pairs"]
    retained_scans = repo._rows('''SELECT DISTINCT c.scan_id FROM captures c
        JOIN scans s ON s.id=c.scan_id WHERE s.project_id=? AND c.state IN ('pending','analyzing','error')''',
                                      (project_id,))
    if any(row['scan_id'] != plan['continue_scan_id'] for row in retained_scans):
        raise ScanAlreadyRunning('Есть сохранённые ответы: сначала продолжите предыдущий скан с его сервисами и аккаунтом')
    work = [(svc, q) for svc in known for q in queries if (q["id"], svc) not in done_pairs]
    saved = repo.pending_captures(plan['continue_scan_id']) if plan['continue_scan_id'] else []
    saved_pairs = {(r['query_id'], r['service']) for r in saved}
    for row in saved:
        pair = (row['query_id'], row['service'])
        if row['service'] in known:
            done_pairs.discard(pair)
            if not any(q['id'] == row['query_id'] for q in queries):
                query = json.loads(row['query_json'])
                queries.append(query)
                done_pairs |= {(query['id'], svc) for svc in known if (query['id'], svc) not in saved_pairs}
            if not any(svc == row['service'] and q['id'] == row['query_id'] for svc, q in work):
                work.append((row['service'], json.loads(row['query_json'])))
    if not queries:
        raise ValueError('В проекте нет активных запросов')
    if managed_job and managed_job.get('drain_only'):
        work = [(svc, q) for svc, q in work if (q['id'], svc) in saved_pairs]
        queries = [q for q in queries if any((q['id'], svc) in saved_pairs for svc in known)]
        done_pairs |= {(q['id'], svc) for q in queries for svc in known if (q['id'], svc) not in saved_pairs}
    if not work:
        if managed_job and plan["continue_scan_id"]:
            repo.set_scan_status(plan["continue_scan_id"], "done")
            return plan["continue_scan_id"]
        raise ValueError(f"За {plan['date']} по выбранным сервисам всё уже проверено — нечего досканировать")

    snapshot = _settings_snapshot(known)
    if plan["continue_scan_id"]:
        old_scan = repo.get_scan(plan["continue_scan_id"])
        old_settings = json.loads(old_scan["settings_snapshot_json"] or "{}")
        if "xmlriver" in old_settings:
            snapshot["xmlriver"] = old_settings["xmlriver"]
        else:
            snapshot.pop("xmlriver", None)
        for key in ("speed_profile", "delay_min_sec", "delay_max_sec", "break_every_n", "typing_speed"):
            if key in old_settings:
                snapshot[key] = old_settings[key]
        snapshot["analysis_workers"] = old_settings.get("analysis_workers", 1)
        if "per_service_timing" in old_settings:
            snapshot["per_service_timing"] = old_settings["per_service_timing"]
        else:
            snapshot.pop("per_service_timing", None)
        if "adaptive_pacing" in old_settings:
            snapshot["adaptive_pacing"] = old_settings["adaptive_pacing"]
        else:
            snapshot.pop("adaptive_pacing", None)
    elif xmlriver.configured():
        region = str(project.get("region_code") or "213")
        snapshot["xmlriver"] = {service: xmlriver.geography(service, region)
                                for service in known if service in ("google_aio", "yandex_neuro")}
    needs_api = any((q["id"], svc) not in saved_pairs and
                    (svc == "yandex_neuro" or svc in snapshot.get("xmlriver", {})) for svc, q in work)
    if needs_api and not xmlriver.configured():
        raise ValueError("Для API-источников настройте AIPARSER_XMLRIVER_USER и AIPARSER_XMLRIVER_KEY")
    # В снимок настроек скана, а не в отдельный аргумент: так задним числом
    # видно, в каком режиме собирались данные — это важно при разборе капч.
    snapshot["headless"] = headless
    if managed_job:
        snapshot.update(cloud_job_id=managed_job["id"], cloud_project_id=managed_job["project_id"],
                        cloud_query_map=managed_job["query_map"], cloud_queries=managed_job["queries"])
    billing_run_id = ""
    reserved: dict[tuple[int, str], str] = {}
    if billing.enabled():
        await billing.recover_interrupted_scans(billing_user["id"])
        if plan["continue_scan_id"]:
            billing_run_id = old_settings.get("billing_run_id") or f"legacy-{old_scan['id']}"
        else:
            billing_run_id = uuid.uuid4().hex
        if managed_job:
            billing_run_id = managed_job["id"]
        reserved = {
            (q["id"], svc): billing.canonical_check_id(
                {**snapshot, "billing_run_id": billing_run_id}, q["id"], svc)
            for svc, q in work
        }
        # Если сеть оборвётся после резервирования, эти записи позволят
        # освободить сумму при следующем запуске.
        new_reservations = [key for pair, key in reserved.items() if pair not in saved_pairs]
        for check_key in new_reservations:
            repo.queue_billing(check_key, "release")
        try:
            reservation = (await billing.reserve(new_reservations) if new_reservations else
                           {'managed_detection': old_settings.get('managed_llm'),
                            'detection_model': old_settings.get('managed_model'),
                            'arbiter_model': old_settings.get('arbiter_model')})
        except billing.BillingError:
            try:
                await billing.flush_outbox(billing_user["id"])
            except billing.BillingError:
                pass  # очередь сохранена для следующего запуска
            raise
        snapshot["billing_run_id"] = billing_run_id
        snapshot["billing_user_id"] = billing_user["id"]
        snapshot["billing_reserved_ids"] = list(reserved.values())
        snapshot["managed_llm"] = bool(reservation.get("managed_detection"))
        snapshot["managed_model"] = reservation.get("detection_model") or llm_mod.DEFAULT_MODEL
        snapshot["arbiter_model"] = reservation.get("arbiter_model") or llm_mod.ARBITER_MODEL_DEFAULT
    if plan["continue_scan_id"]:
        scan_id = plan["continue_scan_id"]
        if reserved:
            repo.extend_billing_reservations(scan_id, billing_run_id, list(reserved.values()))
        repo.set_scan_status(scan_id, "running")
        log.info("Продолжаю скан %s: осталось %s проверок", scan_id, len(work))
    else:
        try:
            scan_id = repo.create_scan(project_id, known, snapshot)
            if managed_job:
                repo._exec("UPDATE scans SET scan_date=? WHERE id=?", (plan["date"], scan_id))
                repo.set_setting(f"managed_scan:{managed_job['id']}", str(scan_id))
        except Exception:
            if reserved:
                await billing.release(list(reserved.values()))
            raise

    controller = ScanController(scan_id, project_id, total=len(work), scan_date=plan["date"],
                                billing_run_id=billing_run_id)
    controller.billing_pairs = reserved
    controller.bearer = billing.token() if billing.enabled() else None
    if reserved:
        repo.billing_sent(list(reserved.values()))
    _active[scan_id] = controller

    controller.scan_task = asyncio.create_task(_run_scan(project, known, queries, done_pairs, snapshot, controller))
    return scan_id


def _plan(project_id: int, service_ids: list[str], resume: bool) -> dict:
    """За какую дату сканируем и какие пары «запрос × сервис» уже готовы.

    resume=True — досканировать: пропускаем всё, по чему за дату уже есть
    годный результат в ЛЮБОМ скане этого дня (дашборд так же собирает срез).
    Дата — сегодняшняя, кроме одного случая: последний скан проекта не
    закончен, а выбранные сервисы входят в его состав — тогда дописываем в
    него и в его дату (база в сотню запросов на бесплатных тарифах не
    проходит за день). Сервис, которого в том скане не было, в чужой замер
    не дописываем — для него это новый скан за сегодня.

    resume=False — начать заново: проверяем всё, новые результаты за
    сегодня перекроют прежние.
    """
    today = date.today().isoformat()
    continue_scan_id = None
    scan_date = today
    done_pairs: set[tuple[int, str]] = set()
    if resume:
        prev = repo.find_resumable_scan(project_id, scannable=set(ADAPTERS))
        if prev and set(service_ids) <= set(json.loads(prev["services_json"])):
            continue_scan_id, scan_date = prev["id"], prev["scan_date"]
        done_pairs = repo.conclusive_pairs_on_date(project_id, scan_date)
    return {"date": scan_date, "continue_scan_id": continue_scan_id, "done_pairs": done_pairs}


def _plan_for_billing_user(project_id: int, service_ids: list[str], resume: bool,
                           user_id: str | None) -> dict:
    plan = _plan(project_id, service_ids, resume)
    if user_id:
        latest = repo.latest_scan(project_id)
        if latest:
            owner = json.loads(latest["settings_snapshot_json"] or "{}").get("billing_user_id")
            if owner != user_id:
                # A new payer must not inherit earlier results or reservations.
                return _plan(project_id, service_ids, False)
    return plan


def plan_scan(project_id: int, service_ids: list[str], *, resume: bool = True) -> dict:
    """Что сделает запуск скана с этими сервисами — для экрана «Скан».

    by_service — по каждому сервису с адаптером (не только выбранным), чтобы
    было видно, где остались хвосты, ещё до того, как расставлены галочки;
    remaining и total — только по выбранным.
    """
    known = [s for s in service_ids if s in ADAPTERS]
    queries = repo.list_queries(project_id, only_active=True)
    plan = _plan(project_id, known, resume)
    done_pairs = plan.pop("done_pairs")
    ids = {q["id"] for q in queries}
    saved = {(r['query_id'], r['service']) for r in repo.pending_captures(plan['continue_scan_id'])}
    done_pairs -= saved
    pairs = {(q, svc) for q in ids for svc in ADAPTERS} | saved
    by_service = {
        s: {'done': sum(1 for pair in done_pairs & pairs if pair[1] == s),
            'total': sum(1 for pair in pairs if pair[1] == s)}
        for s in ADAPTERS
    }
    total = sum(by_service[s]['total'] for s in known)
    return {
        **plan,
        "by_service": by_service,
        "total": total,
        "remaining": total - sum(by_service[s]["done"] for s in known),
        'pending_analysis': sum(1 for _, svc in saved if svc in known),
    }


async def _run_scan(
    project: dict,
    service_ids: list[str],
    queries: list[dict],
    done_pairs: set,
    settings: dict,
    ctl: ScanController,
) -> None:
    api_key = ""
    llm_model = settings.get("managed_model", llm_mod.DEFAULT_MODEL)
    llm_mode = settings["llm_mode"] if settings.get("managed_llm") else "never"
    parallel = bool(project.get("parallel_scan"))
    ctl.parallel = parallel
    for s in service_ids:
        n = sum(1 for q in queries if (q["id"], s) not in done_pairs)
        if n:
            ctl.per_service[s] = {"done": 0, "total": n, "started": None, "state": "pending"}
    ctl.emit("scan_started", **ctl.snapshot())

    failed_services: list[str] = []

    # ponytail: bounded two-worker experiment; widen only after live measurement.
    ctl.analysis_queue = asyncio.Queue(maxsize=2)
    bearer_context = billing.scan_bearer.set(ctl.bearer)

    async def analyze_worker() -> None:
        while (item := await ctl.analysis_queue.get()) is not None:
            query_id, service_id, retry_saved, queued_at = item
            ctl.timing("wait_for_analyzer", time.monotonic() - queued_at,
                       query_id=query_id, service=service_id)
            row = repo.capture(ctl.scan_id, query_id, service_id)
            if row is None:
                raise RuntimeError('Сохранённый ответ отсутствует')
            if row['payer_id'] != settings.get('billing_user_id'):
                raise billing.BillingError('Сохранённый ответ принадлежит другому аккаунту')
            repo.capture_state(ctl.scan_id, query_id, service_id, 'analyzing')
            started = time.monotonic()
            await _run_one(project, {'id': query_id}, service_id, None, None, settings,
                           0, api_key, llm_model, llm_mode, ctl, cap=row, retry_saved=retry_saved)
            ctl.timing("analysis", time.monotonic() - started, query_id=query_id, service=service_id)
            ctl.advance(service_id, query_id)

    count = 2 if settings.get("analysis_workers") == 2 else 1
    ctl.analysis_workers = [asyncio.create_task(analyze_worker()) for _ in range(count)]
    ctl.analysis_worker = ctl.analysis_workers[0]
    def worker_done(task):
        if not task.cancelled() and task.exception() is not None:
            ctl.stop()
    for worker in ctl.analysis_workers:
        worker.add_done_callback(worker_done)

    async def run_service(service_id: str) -> None:
        pending = [q for q in queries if (q["id"], service_id) not in done_pairs]
        if not pending or ctl.stop_requested:
            return

        ctl.running.append(service_id)
        ctl.current_service = service_id
        if service_id in ctl.per_service:
            ctl.per_service[service_id]["started"] = time.time()
            ctl.per_service[service_id]["state"] = "running"
        ctl.emit("progress", **ctl.snapshot())
        ctl.emit("service_started", service=service_id,
                 name=services.get(service_id).name, pending=len(pending))
        try:
            for attempt in range(2):
                try:
                    await _run_service(
                        project, service_id, pending, settings,
                        api_key, llm_model, llm_mode, ctl,
                    )
                    break
                except Exception as exc:
                    # После падения браузера создаём новый контекст один раз.
                    import telemetry
                    telemetry.capture(exc, component="agent", operation="scan_query", provider=service_id,
                                      user_id=settings.get("billing_user_id"))
                    # Уже записанные результаты и их счётчики не повторяем.
                    log.exception("Сервис %s упал (попытка %s)", service_id, attempt + 1)
                    if service_id in ctl.browser_timeout_services:
                        failed_services.append(service_id)
                        break
                    if attempt == 0 and not ctl.stop_requested:
                        # Старые ошибки дозапуска ещё лежат в results. Они не
                        # означают, что запрос обработан в текущей попытке.
                        pending = [q for q in pending
                                   if (q["id"], service_id) not in ctl.completed_pairs | ctl.admitted_pairs]
                        if not pending:
                            break
                        ctl.emit("service_retry", service=service_id, remaining=len(pending))
                        await asyncio.sleep(1)
                        continue
                    failed_services.append(service_id)
                    ctl.per_service[service_id].update(state="failed", error=str(exc))
                    ctl.emit("service_error", service=service_id, error=str(exc))
                    break
        finally:
            st = ctl.per_service[service_id]
            if st["state"] != "failed":
                st["state"] = "finished" if st["done"] == st["total"] else "analyzing"
            if service_id in ctl.running:
                ctl.running.remove(service_id)
            ctl.current_service = ctl.running[-1] if ctl.running else None
            ctl.emit("progress", **ctl.snapshot())

    try:
        # Explicit continuation retries saved analysis, including crash-left and error rows.
        for row in repo.pending_captures(ctl.scan_id):
            pair = (row['query_id'], row['service'])
            if row['service'] in service_ids and pair not in done_pairs:
                await _enqueue_analysis(ctl, pair, retry_saved=True)
        if parallel:
            # У каждого сервиса свой persistent-профиль, а значит свой
            # процесс браузера: друг другу они не мешают, и ограничивать их
            # незачем. Стена лимита, пауза и стоп работают для каждого сам по
            # себе — всё это проверяется внутри _run_service.
            await asyncio.gather(*(run_service(s) for s in service_ids))
        else:
            for service_id in service_ids:
                if ctl.stop_requested:
                    break
                await run_service(service_id)

        for _ in ctl.analysis_workers:
            await _enqueue_analysis(ctl, None)
        await asyncio.gather(*ctl.analysis_workers)
        for svc, st in ctl.per_service.items():
            if st['state'] != 'failed':
                st['state'] = 'finished' if st['done'] == st['total'] else 'stopped'
            ctl.emit('service_finished', service=svc, state=st['state'])

        if ctl.billing_pairs:
            completed = {(r["query_id"], r["service"]): r["status"]
                         for r in repo.results_for_scan(ctl.scan_id)}
            retained = {(r['query_id'], r['service']) for r in repo.captures_for_scan(ctl.scan_id)}
            for pair, check_key in ctl.billing_pairs.items():
                if pair not in retained and completed.get(pair) not in ("found", "not_found"):
                    repo.queue_billing(check_key, "release")
            try:
                await billing.flush_outbox(settings.get("billing_user_id"))
            except billing.BillingError as exc:
                ctl.emit("billing_error", error=str(exc))
                log.warning("Биллинг скана %s ожидает повторной отправки: %s", ctl.scan_id, exc)

        unresolved = any(
            row["service"] in service_ids
            and row["status"] not in repo.CONCLUSIVE_STATUSES
            for row in repo.results_for_scan(ctl.scan_id)
        )
        status = ('failed' if repo.pending_captures(ctl.scan_id) else
                  "stopped" if ctl.stop_requested else
                  "failed" if failed_services or ctl.done < ctl.total or unresolved else "done")
        ctl.state = "finished"
        repo.finish_scan(ctl.scan_id, status=status)
        ctl.emit("scan_finished", status=status, **ctl.snapshot())
    except Exception as exc:
        log.exception('Очередь анализа скана %s остановлена', ctl.scan_id)
        ctl.stop()
        repo.finish_scan(ctl.scan_id, status='failed')
        ctl.state = 'finished'
        ctl.emit('scan_finished', status='failed', error=str(exc), **ctl.snapshot())
    finally:
        for worker in ctl.analysis_workers:
            if not worker.done():
                worker.cancel()
        await asyncio.gather(*ctl.analysis_workers, return_exceptions=True)
        billing.scan_bearer.reset(bearer_context)
        _active.pop(ctl.scan_id, None)


async def _enqueue_analysis(ctl: ScanController, pair: tuple[int, str] | None,
                            *, retry_saved: bool = False) -> None:
    """Bound admission without hanging if the only consumer fails."""
    item = None if pair is None else (*pair, retry_saved, time.monotonic())
    put = asyncio.create_task(ctl.analysis_queue.put(item))
    try:
        workers = tuple(ctl.analysis_workers or [ctl.analysis_worker])
        await asyncio.wait((put, *workers), return_when=asyncio.FIRST_COMPLETED)
        for worker in workers:
            if worker.done():
                worker.result()
            if not put.done():
                raise RuntimeError('Очередь анализа закрыта')
        await put
        if pair is not None:
            ctl.admitted_pairs.add(pair)
    finally:
        if not put.done():
            put.cancel()
        await asyncio.gather(put, return_exceptions=True)


async def _run_service(
    project: dict,
    service_id: str,
    pending: list[dict],
    settings: dict,
    api_key: str,
    llm_model: str,
    llm_mode: str,
    ctl: ScanController,
) -> None:
    """Один сервис целиком: одна вкладка, одна загрузка сайта, N запросов.

    Без окон капчу решить некому. Поймав её, выходим из headless-контекста,
    открываем окно на той же странице, ждём человека и возвращаемся обратно
    без окон — с того же запроса. Остальные сервисы в это время идут своим
    ходом, их это не касается.
    """
    adapter = get_adapter(service_id)
    if settings.get("xmlriver", {}).get(service_id):
        adapter = xmlriver.XMLRiverAdapter(service_id, settings["xmlriver"][service_id])
    headless = bool(settings.get("headless"))
    queue = [q for q in pending if (q['id'], service_id) not in ctl.admitted_pairs]
    done = 0

    recorded = settings.get("per_service_timing", {}).get(service_id)
    if recorded:
        speed = float(recorded["typing_speed"])
        delay_lo = float(recorded["delay_min_sec"])
        delay_hi = float(recorded["delay_max_sec"])
        break_every = int(recorded["break_every_n"])
    else:
        # Legacy snapshots predate per-service timings; retain their old floor behavior.
        own_lo, own_hi = getattr(adapter, "min_delay_sec", (0.0, 0.0))
        speed = float(settings["typing_speed"])
        delay_lo = max(settings["delay_min_sec"], own_lo)
        delay_hi = max(settings["delay_max_sec"], own_hi, delay_lo)
        break_every = settings["break_every_n"]
    if delay_lo:
        log.info("%s: пауза между запросами %.0f–%.0f с", service_id, delay_lo, delay_hi)
    pacer = (AdaptivePacer(settings["adaptive_pacing"], delay_lo, delay_hi)
             if settings.get("adaptive_pacing") else None)
    pipeline = ctl.analysis_queue is not None

    async def session() -> str | None:
        """Проход по очереди в одном контексте. Вернёт адрес страницы с капчей."""
        nonlocal done, queue
        async with service_context(service_id, headless=headless) as context:
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                ready = await adapter.ensure_ready(page)
            except AdapterError:
                if isinstance(adapter, xmlriver.XMLRiverAdapter):
                    _record_auth_state(service_id, "error", backend="xmlriver")
                raise
            if not isinstance(adapter, xmlriver.XMLRiverAdapter):
                _record_auth_state(service_id, "ok" if ready.ok else (ready.reason or "error"))

            if not ready.ok:
                # Сессия не открылась — записываем причину сразу всем запросам
                # сервиса, чтобы в таблице было видно «почему пусто», а не дыра.
                for q in queue:
                    repo.save_result(ctl.scan_id, q["id"], service_id, ready.reason or "error")
                    ctl.advance(service_id, q["id"])
                queue = []
                ctl.emit("service_blocked", service=service_id, reason=ready.reason)
                return None

            strikes = 0

            while queue:
                if ctl.stop_requested:
                    return None
                await ctl.paused.wait()
                if ctl.stop_requested:
                    return None
                if pacer:
                    await pacer.wait()
                    await ctl.paused.wait()
                    if ctl.stop_requested:
                        return None

                # Вкладка могла умереть (краш рендерера) — поднимаем новую и
                # заново открываем сессию, иначе весь остаток сервиса посыплется.
                if page.is_closed():
                    log.warning("Вкладка %s закрылась — открываю заново", service_id)
                    page = await context.new_page()
                    if not (await adapter.ensure_ready(page)).ok:
                        return None

                q = queue[0]
                try:
                    status = await _run_one(
                        project, q, service_id, adapter, page, settings, speed,
                        api_key, llm_model, llm_mode, ctl, **({"capture_only": True} if pipeline else {}),
                    )
                except asyncio.CancelledError:
                    if ctl.stop_requested:
                        return None
                    raise

                if pacer:
                    pacer.completed(getattr(adapter, 'throttled', False) or status == 'quota',
                                    status in ('captured', 'found', 'not_found', 'skipped'),
                                    done + 1, break_every)

                if pipeline and status == "captured":
                    queue.pop(0)
                    done += 1
                    # put() is deliberate backpressure: the browser cannot
                    # submit the next query until this durable answer is admitted.
                    await _enqueue_analysis(ctl, (q['id'], service_id))
                    strikes = 0
                    if queue and not pacer:
                        await humanize.between_queries(done, lo=delay_lo, hi=delay_hi,
                                                       break_every=break_every)
                    continue

                if status == "browser_timeout":
                    queue.pop(0)
                    done += 1
                    ctl.advance(service_id, q["id"])
                    message = "Browser ask/capture timed out; remaining prompts were not submitted"
                    ctl.browser_timeout_services.add(service_id)
                    ctl.per_service[service_id].update(state="failed", error=message)
                    ctl.emit("service_error", service=service_id, error=message)
                    return None

                if status == "captcha" and headless:
                    # Запрос остаётся в очереди и будет задан заново: результат
                    # «капча» уже записан, повтор его перезапишет. Счётчик
                    # прогресса не трогаем — проверка ещё не состоялась.
                    return page.url

                queue.pop(0)
                done += 1
                ctl.advance(service_id, q["id"])

                if status == 'quota':
                    _mark_limit_reached(ctl, service_id, [q] + queue, q)
                    queue = []
                    return None
                if status == "unavailable":
                    strikes += 1
                    if strikes >= LIMIT_STRIKES:
                        _mark_limit_reached(ctl, service_id, [q] + queue, q)
                        queue = []
                        return None
                else:
                    strikes = 0

                # Паузы и длинные перерывы — по счётчику ЭТОГО сервиса: при
                # параллельном скане общий счётчик растёт в несколько раз быстрее,
                # и сервисы отдыхали бы не в свой ритм.
                if queue and not pacer:
                    await humanize.between_queries(
                        done,
                        lo=delay_lo,
                        hi=delay_hi,
                        break_every=break_every,
                    )
        return None

    while queue:
        captcha_url = await session()
        if not captcha_url:
            return
        ctl.emit("captcha_wait", service=service_id, name=services.get(service_id).name,
                 url=captcha_url)
        solved = await open_captcha_window(service_id, captcha_url)
        ctl.emit("captcha_solved" if solved else "captcha_timeout", service=service_id,
                 name=services.get(service_id).name)
        if not solved:
            log.warning("%s: капча не решена — останавливаю сервис", service_id)
            return


def _mark_limit_reached(ctl: ScanController, service_id: str, pending: list[dict], stopped_at: dict) -> None:
    """Помечает необработанный хвост сервиса как упёршийся в лимит.

    Пишем именно `limit_reached`, а не `error`: это не сбой программы, а
    исчерпанная квота аккаунта, и в статистике видимости такие запросы не
    должны считаться ни «найдено», ни «не найдено» — данных по ним просто нет.
    Дозапуск потом возьмёт их заново.
    """
    idx = pending.index(stopped_at)
    rest = pending[idx + 1:]
    for q in rest:
        repo.save_result(
            ctl.scan_id, q["id"], service_id, "limit_reached",
            error_message="Лимит тарифа: сервис перестал принимать запросы",
        )
        ctl.advance(service_id, q["id"])

    log.warning("Сервис %s упёрся в лимит, пропускаю оставшиеся %s запросов", service_id, len(rest))
    ctl.emit("service_limit", service=service_id, skipped=len(rest))


async def _ask_and_capture(adapter, page, project: dict, query: dict, service_id: str,
                           speed: float, ctl: ScanController):
    phase = {"service": service_id, "query_id": query["id"],
             "phase": "ask", "started": time.monotonic()}
    ctl.browser_phase[service_id] = phase
    aborted = False
    async def work():
        if aborted or ctl.stop_requested:
            raise asyncio.CancelledError
        await adapter.ask(page, query["text"], project.get("region_code"), speed=speed)
        while True:
            if aborted or ctl.stop_requested:
                raise asyncio.CancelledError
            phase.update(phase="capture", started=time.monotonic())
            try:
                return await adapter.capture(page)
            except xmlriver.XMLRiverResponseError:
                if aborted or ctl.stop_requested:
                    raise asyncio.CancelledError
                phase.update(phase="ask", started=time.monotonic())
                if not await adapter.retry():
                    raise

    task = asyncio.create_task(work())
    ctl.browser_tasks.add(task)
    def finished(child):
        ctl.browser_tasks.discard(child)
        if ctl.browser_phase.get(service_id) is phase:
            ctl.browser_phase.pop(service_id)
        if not child.cancelled():
            child.exception()
    task.add_done_callback(finished)
    stopped = asyncio.create_task(ctl.stop_signal.wait())
    deadline = time.monotonic() + _BROWSER_TASK_TIMEOUT
    try:
        await asyncio.wait((task, stopped), timeout=_BROWSER_TASK_TIMEOUT,
                           return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            return task.result()
        if ctl.stop_requested:
            if phase['phase'] == 'capture':
                # Finish the current capture before stopping; adapters can hold
                # answer/image evidence while they await source extraction.
                await asyncio.wait((task,), timeout=max(0, deadline - time.monotonic()))
                if task.done():
                    return task.result()
            else:
                aborted = True
                task.cancel()
                await asyncio.wait((task,), timeout=_BROWSER_CANCEL_GRACE)
                raise asyncio.CancelledError
        aborted = True
        task.cancel()
        await asyncio.wait((task,), timeout=_BROWSER_CANCEL_GRACE)
        raise BrowserTaskTimeout(
            f"{service_id} query {query['id']}: {phase['phase']} exceeded "
            f"{_BROWSER_TASK_TIMEOUT}s"
        )
    finally:
        stopped.cancel()
        if not task.done():
            aborted = True
            task.cancel()


async def _run_one(
    project: dict,
    query: dict,
    service_id: str,
    adapter,
    page,
    settings: dict,
    speed: float,
    api_key: str,
    llm_model: str,
    llm_mode: str,
    ctl: ScanController,
    *,
    cap=None,
    capture_only: bool = False,
    retry_saved: bool = False,
) -> str:
    """Одна пара «запрос × сервис». Возвращает записанный статус."""
    started = time.monotonic()
    capture_attempted = False
    def record_api_failure() -> None:
        if capture_attempted and isinstance(adapter, xmlriver.XMLRiverAdapter):
            _record_auth_state(service_id, "error", backend="xmlriver")
    def retain_capture_error(exc: Exception) -> None:
        # A capture may not exist yet (browser-side failure); updating zero rows
        # is intentional.  Once it exists, ordinary analysis failures stay for
        # an explicit retry and are never re-submitted to the provider.
        repo.capture_state(ctl.scan_id, query["id"], service_id, "error", str(exc))
    try:
        stored = cap if isinstance(cap, dict) else None
        if cap is None:
            stored = repo.capture(ctl.scan_id, query['id'], service_id)
        if stored is not None:
            if stored["state"] == "abandoned":
                return "abandoned"
            if stored['payer_id'] != settings.get('billing_user_id'):
                raise billing.BillingError('Сохранённый ответ принадлежит другому аккаунту')
            project = json.loads(stored['project_json'])
            query = json.loads(stored['query_json'])
            settings = json.loads(stored['settings_json'])
            llm_model = settings.get('managed_model', llm_model)
            llm_mode = settings['llm_mode'] if settings.get('managed_llm') else 'never'
            cap = SimpleNamespace(shown=bool(stored['shown']), answer_text=stored['answer_text'],
                                  sources=json.loads(stored['sources_json']), extra=json.loads(stored['extra_json']),
                                  screenshot_bytes=stored['screenshot_bytes'])
        browser_capture = cap is None
        if cap is None:
            capture_started = time.monotonic()
            capture_attempted = True
            cap = await _ask_and_capture(adapter, page, project, query, service_id, speed, ctl)
            capture_attempted = False
            if isinstance(adapter, xmlriver.XMLRiverAdapter):
                _record_auth_state(service_id, "ok", backend="xmlriver")
            ctl.timing("browser_capture", time.monotonic() - capture_started,
                       query_id=query["id"], service=service_id)
        check_id = (stored['check_id'] if stored else
                    billing.canonical_check_id(settings, query['id'], service_id) if ctl.billing_run_id else None)

        scan_date = ctl.scan_date
        shot_name = f"{ctl.scan_id}_{query['id']}_{service_id}.webp"
        rel_path = f"{project['id']}/{scan_date}/{shot_name}" if cap.shown else None
        if browser_capture:
            # Save the raw image before conversion/export; a disk or codec failure cannot lose the answer.
            repo.save_capture(ctl.scan_id, query['id'], service_id, project=project, query=query,
                              settings=settings, check_id=check_id, payer_id=settings.get('billing_user_id'),
                              shown=cap.shown, answer_text=cap.answer_text, sources=cap.sources, extra=cap.extra or {},
                              screenshot_bytes=cap.screenshot_bytes, screenshot_path=rel_path)
        if capture_only:
            return 'captured'

        if not cap.shown:
            repo.finalize_capture(ctl.scan_id, query['id'], service_id, 'skipped',
                                  {'error_message': 'AI-блок не показан'}, check_id)
            ctl.emit("query_result", query_id=query["id"], service=service_id, status="skipped")
            return "skipped"

        # Адаптеры отдают сырой PNG/JPEG (это всё, что умеет Playwright) —
        # в WebP конвертируем один раз здесь, а не в каждом адаптере.
        webp_bytes = imaging.to_webp(cap.screenshot_bytes)

        shot_dir = config.screenshot_dir(project["id"], scan_date)
        (shot_dir / shot_name).write_bytes(webp_bytes)

        # Адаптер, умеющий отделять карточки (источники, товары, организации),
        # отдаёт текст ответа и текст карточек порознь: бренд только в
        # карточке — упоминание своего типа «card», а не «text».
        extra = cap.extra or {}
        analysis_text = extra.get("plain_text", cap.answer_text)
        rule_verdict = rules.evaluate(
            extra.get("main_text", cap.answer_text), cap.sources, project["brand_name"],
            project["brand_aliases"], project["brand_domains"],
            card_text=extra.get("cards_text", ""),
        )
        brand_clarification = project.get("brand_clarification") or ""

        llm_verdict = None
        llm_error_text = None
        if brand_clarification or should_call_llm(rule_verdict, llm_mode):
            managed_check_id = check_id if settings.get('managed_llm') else None
            llm_verdict = await llm_mod.evaluate(
                query=query["text"],
                brand_name=project["brand_name"],
                aliases=project["brand_aliases"],
                answer_text=analysis_text,
                sources=cap.sources,
                screenshot_bytes=webp_bytes,
                api_key=api_key,
                model=llm_model,
                managed_check_id=managed_check_id,
                brand_clarification=brand_clarification,
                retry_saved=retry_saved,
            )
            if llm_verdict.error:
                llm_error_text = llm_verdict.error
                # Вызов не состоялся (сеть, прокси, исчерпанный ключ) — это
                # отсутствие проверки, а не вердикт «не найдено». До 10.09.2026
                # такой результат всё равно уходил в merge и получал пометку
                # «проверено LLM» с именем модели: в вечернем прогоне 09.09 так
                # записались ответы, которые модель в глаза не видела.
                log.warning("LLM-проверка не состоялась (%s, запрос %s): %s",
                            service_id, query["id"], llm_verdict.error)
                ctl.emit("llm_error", service=service_id, query_id=query["id"],
                         error=llm_verdict.error)
                llm_verdict = None

        result = merge(rule_verdict, llm_verdict,
                       confidence_threshold=settings["llm_confidence_threshold"],
                       semantic_authoritative=bool(brand_clarification))

        # Последний рубеж: если ни правила, ни LLM не нашли бренд в самом
        # ответе, идём на процитированные страницы и ищем его там. Только для
        # not_found — по найденному искать нечего, а на ошибках и лимитах
        # источников попросту нет.
        depth = int(project.get("deep_check_depth") or 0)
        if not brand_clarification and result.status == "not_found" and depth > 0 and cap.sources:
            hit = await deep_mod.check_sources(
                cap.sources, project["brand_name"], project["brand_aliases"],
                project["brand_domains"], depth=depth,
            )
            if hit.found and hit.url:
                result = with_deep(result, hit.url, hit.quote)

        if llm_error_text and (brand_clarification or result.status == "not_found"):
            result.status = "error"

        # Спорная строка (правила молчат, а модель нашла) — второй, более
        # сильный арбитр решает окончательно, вместо ручной проверки.
        if result.needs_review and settings.get("arbiter") and settings.get("managed_llm"):
            arbiter_check_id = check_id
            verdict = await llm_mod.arbitrate(
                brand_name=project["brand_name"],
                aliases=project["brand_aliases"],
                domains=project["brand_domains"],
                answer_text=analysis_text,
                sources=cap.sources,
                screenshot_bytes=webp_bytes,
                api_key=api_key,
                model=settings["arbiter_model"],
                first_verdict=llm_verdict,
                first_quote=result.evidence_quote or "",
                query=query["text"],
                managed_check_id=arbiter_check_id,
                brand_clarification=brand_clarification,
                retry_saved=retry_saved,
            )
            if verdict.error:
                # Арбитр не ответил — строка остаётся на ручную проверку, как
                # было раньше. Молча принимать вердикт первой модели нельзя.
                log.warning("Арбитр не ответил (%s, запрос %s): %s", service_id, query["id"], verdict.error)
                ctl.emit("llm_error", service=service_id, query_id=query["id"], error=verdict.error)
                if brand_clarification:
                    result.status = "error"
                    llm_error_text = verdict.error
            else:
                result = with_arbiter(result, verdict)

        settlement_started = time.monotonic()
        repo.finalize_capture(ctl.scan_id, query["id"], service_id, result.status, {
            "mention_types": result.mention_types, "confidence": result.confidence,
            "evidence_quote": result.evidence_quote, "answer_text": cap.answer_text,
            "sources": cap.sources, "screenshot_path": rel_path, "detected_by": result.detected_by,
            "needs_review": result.needs_review, "llm_model": result.llm_model,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "error_message": llm_error_text if result.status == "error" else None,
        }, check_id)
        if ctl.billing_run_id and result.status in ("found", "not_found"):
            try:
                await billing.flush_outbox(settings.get("billing_user_id"))
            except billing.BillingError as exc:
                log.warning("Ответ сохранён, списание ожидает повторной отправки: %s", exc)
                ctl.emit("billing_error", error=str(exc))
                ctl.stop()
        ctl.timing("settlement", time.monotonic() - settlement_started,
                   query_id=query["id"], service=service_id)
        # A queued durable capture starts before this call, so this is only the
        # analysis stage; duration_ms keeps its historical meaning below.
        ctl.timing("analysis_stage", time.monotonic() - started,
                   query_id=query["id"], service=service_id)
        ctl.emit("query_result", query_id=query["id"], service=service_id, status=result.status)
        return result.status

    except ProviderQuotaError as exc:
        record_api_failure()
        retain_capture_error(exc)
        repo.save_result(ctl.scan_id, query["id"], service_id, "limit_reached", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="limit_reached")
        return "quota"
    except ServiceUnavailableError as exc:
        record_api_failure()
        retain_capture_error(exc)
        import telemetry
        telemetry.capture(exc, component="agent", operation="scan_query", provider=service_id,
                          run_id=ctl.billing_run_id)
        repo.save_result(ctl.scan_id, query["id"], service_id, "limit_reached", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="limit_reached")
        return "unavailable"
    except AuthRequiredError as exc:
        record_api_failure()
        retain_capture_error(exc)
        _record_auth_state(service_id, "auth_required")
        repo.save_result(ctl.scan_id, query["id"], service_id, "auth_required", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="auth_required")
        return "auth_required"
    except CaptchaError as exc:
        record_api_failure()
        retain_capture_error(exc)
        repo.save_result(ctl.scan_id, query["id"], service_id, "captcha", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="captcha")
        return "captcha"
    except BrowserTaskTimeout as exc:
        record_api_failure()
        repo.save_result(ctl.scan_id, query["id"], service_id, "error", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="browser_timeout")
        return "browser_timeout"
    except AdapterError as exc:
        record_api_failure()
        retain_capture_error(exc)
        # The detailed exception can contain answer excerpts; it belongs in the private result only.
        import telemetry
        telemetry.capture(exc, component="agent", operation="scan_query", provider=service_id,
                          run_id=ctl.billing_run_id)
        log.warning("Сервис %s, запрос %s: %s (причина сохранена в результате)", service_id, query["id"], type(exc).__name__)
        repo.save_result(ctl.scan_id, query["id"], service_id, "error", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="error")
        return "error"
    except Exception as exc:
        record_api_failure()
        if "Target page, context or browser has been closed" in str(exc):
            # Весь браузер умер: внешний цикл поднимет новый профиль и
            # повторит текущий запрос. Не записываем ложный результат.
            raise
        retain_capture_error(exc)
        import telemetry
        telemetry.capture(exc, component="agent", operation="scan_query", provider=service_id,
                          run_id=ctl.billing_run_id)
        log.exception("Ошибка на запросе %s / %s", query["text"], service_id)
        repo.save_result(ctl.scan_id, query["id"], service_id, "error", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="error")
        return "error"
