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
import time
import uuid
from datetime import date, datetime

from app import billing, config, imaging, services
from app.db import repo
from app.detect import llm as llm_mod
from app.detect import deep as deep_mod
from app.detect import rules
from app.detect.merge import merge, should_call_llm, with_arbiter, with_deep
from app.scanner import humanize
from app.scanner.adapters import ADAPTERS, get_adapter
from app.scanner.adapters.base import (
    AdapterError,
    AuthRequiredError,
    CaptchaError,
    ServiceUnavailableError,
)
from app.scanner.browser import open_captcha_window, service_context

log = logging.getLogger("aiparser.orchestrator")

# Сколько «сервис не принимает запросы» подряд считаем стеной лимита.
# Единичный сбой бывает случайным (подвисла вёрстка), три подряд — это уже
# не совпадение, а состояние аккаунта.
LIMIT_STRIKES = 3


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
        self.parallel = False

        # Своя очередь у каждого подписчика. Раньше очередь была одна на скан,
        # и два подключения делили события между собой — каждое доставалось
        # кому-то одному. 10.09.2026 сторонний наблюдатель так «не увидел»
        # результаты #104, #109, #112: их забрало окно приложения, а оно,
        # в свою очередь, недосчиталось бы того, что забрал наблюдатель.
        self._subscribers: list[asyncio.Queue[dict]] = []
        self.stop_requested = False
        self.paused = asyncio.Event()
        self.paused.set()               # не на паузе

    # --- управление -------------------------------------------------------

    def emit(self, event: str, **data) -> None:
        item = {"event": event, **data}
        for q in list(self._subscribers):
            q.put_nowait(item)

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
        self.emit("stopping", **self.snapshot())

    # --- прогресс ---------------------------------------------------------

    def advance(self, service_id: str) -> None:
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
        return {
            "scan_id": self.scan_id,
            "project_id": self.project_id,
            "done": self.done,
            "total": self.total,
            "percent": round(self.done * 100 / self.total, 1) if self.total else 0.0,
            "state": self.state,
            "current_service": self.current_service,
            "running_services": list(self.running),
            "elapsed_sec": int(elapsed),
            "eta_sec": eta,
            "services": {s: {"done": st["done"], "total": st["total"]} for s, st in self.per_service.items()},
        }


_active: dict[int, ScanController] = {}


def get_controller(scan_id: int) -> ScanController | None:
    return _active.get(scan_id)


def active_controller() -> ScanController | None:
    """Единственный идущий скан, если он есть (одновременно допускается один)."""
    return next(iter(_active.values()), None)


def _settings_snapshot() -> dict:
    """Разворачивает выбранный профиль скорости в конкретные значения.

    Профиль — единственная ручка скорости: держать рядом ещё и отдельные
    поля пауз значило бы иметь два источника правды, которые разъедутся.
    Развёрнутые значения кладём в снимок, чтобы задним числом было видно, в
    каком режиме собирались данные.
    """
    s = repo.all_settings()
    name = s.get("speed_profile", humanize.DEFAULT_PROFILE)
    prof = humanize.profile(name)
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
    }


def _record_auth_state(service_id: str, state: str) -> None:
    """Запоминает, что сервис ответил на попытку входа — для статуса в настройках.

    Cookie в профиле говорит «сессия на диске есть», а принял ли её сервис —
    знает только фактический прогон. Храним обе половины.
    """
    repo.set_setting(
        f"auth_state:{service_id}",
        json.dumps({"state": state, "at": datetime.now().isoformat(timespec="seconds")}),
    )


async def start_scan(project_id: int, service_ids: list[str], *, resume: bool = True,
                     headless: bool = False) -> int:
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
    if not queries:
        raise ValueError("В проекте нет активных запросов")

    billing_user = await billing.identity() if billing.enabled() else None
    plan = _plan_for_billing_user(project_id, known, resume,
                                  billing_user["id"] if billing_user else None)
    done_pairs = plan["done_pairs"]
    work = [(svc, q) for svc in known for q in queries if (q["id"], svc) not in done_pairs]
    if not work:
        raise ValueError(f"За {plan['date']} по выбранным сервисам всё уже проверено — нечего досканировать")

    snapshot = _settings_snapshot()
    # В снимок настроек скана, а не в отдельный аргумент: так задним числом
    # видно, в каком режиме собирались данные — это важно при разборе капч.
    snapshot["headless"] = headless
    billing_run_id = ""
    reserved: dict[tuple[int, str], str] = {}
    if billing.enabled():
        await billing.recover_interrupted_scans()
        try:
            await billing.flush_screenshot_outbox()
        except billing.ScreenshotError as exc:
            log.warning("Скриншоты ожидают повторной отправки: %s", exc)
        if plan["continue_scan_id"]:
            old_scan = repo.get_scan(plan["continue_scan_id"])
            old_settings = json.loads(old_scan["settings_snapshot_json"] or "{}")
            billing_run_id = old_settings.get("billing_run_id") or f"legacy-{old_scan['id']}"
        else:
            billing_run_id = uuid.uuid4().hex
        reserved = {
            (q["id"], svc): billing.check_id(billing_run_id, q["id"], svc)
            for svc, q in work
        }
        # Если сеть оборвётся после резервирования, эти записи позволят
        # освободить сумму при следующем запуске.
        for check_key in reserved.values():
            repo.queue_billing(check_key, "release")
        try:
            reservation = await billing.reserve(list(reserved.values()))
        except billing.BillingError:
            try:
                await billing.flush_outbox()
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
        except Exception:
            if reserved:
                await billing.release(list(reserved.values()))
            raise

    controller = ScanController(scan_id, project_id, total=len(work), scan_date=plan["date"],
                                billing_run_id=billing_run_id)
    controller.billing_pairs = reserved
    if reserved:
        repo.billing_sent(list(reserved.values()))
    _active[scan_id] = controller

    asyncio.create_task(_run_scan(project, known, queries, done_pairs, snapshot, controller))
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
    by_service = {
        s: {"done": sum(1 for q, svc in done_pairs if svc == s and q in ids), "total": len(ids)}
        for s in ADAPTERS
    }
    total = len(ids) * len(known)
    return {
        **plan,
        "by_service": by_service,
        "total": total,
        "remaining": total - sum(by_service[s]["done"] for s in known),
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
    speed = settings["typing_speed"]

    parallel = bool(project.get("parallel_scan"))
    ctl.parallel = parallel
    for s in service_ids:
        n = sum(1 for q in queries if (q["id"], s) not in done_pairs)
        if n:
            ctl.per_service[s] = {"done": 0, "total": n, "started": None}
    ctl.emit("scan_started", parallel=parallel, **ctl.snapshot())

    failed_services: list[str] = []

    async def run_service(service_id: str) -> None:
        pending = [q for q in queries if (q["id"], service_id) not in done_pairs]
        if not pending or ctl.stop_requested:
            return

        ctl.running.append(service_id)
        ctl.current_service = service_id
        if service_id in ctl.per_service:
            ctl.per_service[service_id]["started"] = time.time()
        ctl.emit("service_started", service=service_id,
                 name=services.get(service_id).name, pending=len(pending))
        try:
            for attempt in range(2):
                try:
                    await _run_service(
                        project, service_id, pending, settings, speed,
                        api_key, llm_model, llm_mode, ctl,
                    )
                    break
                except Exception as exc:
                    # После падения браузера создаём новый контекст один раз.
                    # Уже записанные результаты и их счётчики не повторяем.
                    log.exception("Сервис %s упал (попытка %s)", service_id, attempt + 1)
                    if attempt == 0 and not ctl.stop_requested:
                        recorded = {row["query_id"] for row in repo.results_for_scan(ctl.scan_id)
                                    if row["service"] == service_id}
                        pending = [q for q in pending if q["id"] not in recorded]
                        if not pending:
                            break
                        ctl.emit("service_retry", service=service_id, remaining=len(pending))
                        await asyncio.sleep(1)
                        continue
                    failed_services.append(service_id)
                    ctl.emit("service_error", service=service_id, error=str(exc))
                    break
        finally:
            if service_id in ctl.running:
                ctl.running.remove(service_id)
            ctl.current_service = ctl.running[-1] if ctl.running else None
        ctl.emit("service_finished", service=service_id)

    try:
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

        if ctl.billing_pairs:
            completed = {(r["query_id"], r["service"]): r["status"]
                         for r in repo.results_for_scan(ctl.scan_id)}
            for pair, check_key in ctl.billing_pairs.items():
                if completed.get(pair) not in ("found", "not_found"):
                    repo.queue_billing(check_key, "release")
            try:
                await billing.flush_outbox()
            except billing.BillingError as exc:
                ctl.emit("billing_error", error=str(exc))
                log.warning("Биллинг скана %s ожидает повторной отправки: %s", ctl.scan_id, exc)

        unresolved = any(
            row["service"] in service_ids
            and row["status"] not in repo.CONCLUSIVE_STATUSES
            for row in repo.results_for_scan(ctl.scan_id)
        )
        status = ("stopped" if ctl.stop_requested else
                  "failed" if failed_services or ctl.done < ctl.total or unresolved else "done")
        ctl.state = "finished"
        repo.finish_scan(ctl.scan_id, status=status)
        ctl.emit("scan_finished", status=status, **ctl.snapshot())
    finally:
        _active.pop(ctl.scan_id, None)


async def _run_service(
    project: dict,
    service_id: str,
    pending: list[dict],
    settings: dict,
    speed: float,
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
    headless = bool(settings.get("headless"))
    queue = list(pending)
    done = 0

    # У сервиса может быть своя нижняя граница паузы: ChatGPT считает частые
    # запросы спамом раньше остальных и перекрывает поле ввода. Берём большее
    # из профиля скорости и требования адаптера — ускорить сервис профилем
    # «Быстро» нельзя, а замедлить «Осторожным» можно.
    own_lo, own_hi = getattr(adapter, "min_delay_sec", (0.0, 0.0))
    delay_lo = max(settings["delay_min_sec"], own_lo)
    delay_hi = max(settings["delay_max_sec"], own_hi, delay_lo)
    if own_lo:
        log.info("%s: пауза между запросами %.0f–%.0f с", service_id, delay_lo, delay_hi)

    async def session() -> str | None:
        """Проход по очереди в одном контексте. Вернёт адрес страницы с капчей."""
        nonlocal done, queue
        async with service_context(service_id, headless=headless) as context:
            page = context.pages[0] if context.pages else await context.new_page()

            ready = await adapter.ensure_ready(page)
            _record_auth_state(service_id, "ok" if ready.ok else (ready.reason or "error"))

            if not ready.ok:
                # Сессия не открылась — записываем причину сразу всем запросам
                # сервиса, чтобы в таблице было видно «почему пусто», а не дыра.
                for q in queue:
                    repo.save_result(ctl.scan_id, q["id"], service_id, ready.reason or "error")
                    ctl.advance(service_id)
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

                # Вкладка могла умереть (краш рендерера) — поднимаем новую и
                # заново открываем сессию, иначе весь остаток сервиса посыплется.
                if page.is_closed():
                    log.warning("Вкладка %s закрылась — открываю заново", service_id)
                    page = await context.new_page()
                    if not (await adapter.ensure_ready(page)).ok:
                        return None

                q = queue[0]
                status = await _run_one(
                    project, q, service_id, adapter, page, settings, speed,
                    api_key, llm_model, llm_mode, ctl,
                )

                if status == "captcha" and headless:
                    # Запрос остаётся в очереди и будет задан заново: результат
                    # «капча» уже записан, повтор его перезапишет. Счётчик
                    # прогресса не трогаем — проверка ещё не состоялась.
                    return page.url

                queue.pop(0)
                done += 1
                ctl.advance(service_id)

                if status == "unavailable":
                    strikes += 1
                    if strikes >= LIMIT_STRIKES:
                        _mark_limit_reached(ctl, service_id, pending, q)
                        queue = []
                        return None
                else:
                    strikes = 0

                # Паузы и длинные перерывы — по счётчику ЭТОГО сервиса: при
                # параллельном скане общий счётчик растёт в несколько раз быстрее,
                # и сервисы отдыхали бы не в свой ритм.
                if queue:
                    await humanize.between_queries(
                        done,
                        lo=delay_lo,
                        hi=delay_hi,
                        break_every=settings["break_every_n"],
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
            # Человек не пришёл: оставшиеся запросы заберёт дозапуск, а не
            # молчаливая запись «капча» по всему хвосту.
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
        ctl.advance(service_id)

    log.warning("Сервис %s упёрся в лимит, пропускаю оставшиеся %s запросов", service_id, len(rest))
    ctl.emit("service_limit", service=service_id, skipped=len(rest))


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
) -> str:
    """Одна пара «запрос × сервис». Возвращает записанный статус."""
    started = time.monotonic()
    try:
        await adapter.ask(page, query["text"], project.get("region_code"), speed=speed)
        cap = await adapter.capture(page)

        if not cap.shown:
            repo.save_result(ctl.scan_id, query["id"], service_id, "skipped",
                             error_message="AI-блок не показан")
            ctl.emit("query_result", query_id=query["id"], service=service_id, status="skipped")
            return "skipped"

        # Адаптеры отдают сырой PNG/JPEG (это всё, что умеет Playwright) —
        # в WebP конвертируем один раз здесь, а не в каждом адаптере.
        webp_bytes = imaging.to_webp(cap.screenshot_bytes)

        scan_date = ctl.scan_date
        shot_dir = config.screenshot_dir(project["id"], scan_date)
        shot_name = f"{query['id']}_{service_id}.webp"
        (shot_dir / shot_name).write_bytes(webp_bytes)
        rel_path = f"{project['id']}/{scan_date}/{shot_name}"

        # Адаптер, умеющий отделять карточки (источники, товары, организации),
        # отдаёт текст ответа и текст карточек порознь: бренд только в
        # карточке — упоминание своего типа «card», а не «text».
        extra = cap.extra or {}
        rule_verdict = rules.evaluate(
            extra.get("main_text", cap.answer_text), cap.sources, project["brand_name"],
            project["brand_aliases"], project["brand_domains"],
            card_text=extra.get("cards_text", ""),
        )

        llm_verdict = None
        llm_error_text = None
        if should_call_llm(rule_verdict, llm_mode):
            managed_check_id = (billing.check_id(ctl.billing_run_id, query["id"], service_id)
                                if settings.get("managed_llm") else None)
            llm_verdict = await llm_mod.evaluate(
                query=query["text"],
                brand_name=project["brand_name"],
                aliases=project["brand_aliases"],
                answer_text=cap.answer_text,
                sources=cap.sources,
                screenshot_bytes=webp_bytes,
                api_key=api_key,
                model=llm_model,
                managed_check_id=managed_check_id,
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
                       confidence_threshold=settings["llm_confidence_threshold"])

        # Последний рубеж: если ни правила, ни LLM не нашли бренд в самом
        # ответе, идём на процитированные страницы и ищем его там. Только для
        # not_found — по найденному искать нечего, а на ошибках и лимитах
        # источников попросту нет.
        depth = int(project.get("deep_check_depth") or 0)
        if result.status == "not_found" and depth > 0 and cap.sources:
            hit = await deep_mod.check_sources(
                cap.sources, project["brand_name"], project["brand_aliases"],
                project["brand_domains"], depth=depth,
            )
            if hit.found and hit.url:
                result = with_deep(result, hit.url, hit.quote)

        if llm_error_text and result.status == "not_found":
            result.status = "error"

        # Спорная строка (правила молчат, а модель нашла) — второй, более
        # сильный арбитр решает окончательно, вместо ручной проверки.
        if result.needs_review and settings.get("arbiter") and settings.get("managed_llm"):
            arbiter_check_id = billing.check_id(ctl.billing_run_id, query["id"], service_id)
            verdict = await llm_mod.arbitrate(
                brand_name=project["brand_name"],
                aliases=project["brand_aliases"],
                domains=project["brand_domains"],
                answer_text=cap.answer_text,
                sources=cap.sources,
                screenshot_bytes=webp_bytes,
                api_key=api_key,
                model=settings["arbiter_model"],
                first_verdict=llm_verdict,
                first_quote=result.evidence_quote or "",
                query=query["text"],
                managed_check_id=arbiter_check_id,
            )
            if verdict.error:
                # Арбитр не ответил — строка остаётся на ручную проверку, как
                # было раньше. Молча принимать вердикт первой модели нельзя.
                log.warning("Арбитр не ответил (%s, запрос %s): %s", service_id, query["id"], verdict.error)
                ctl.emit("llm_error", service=service_id, query_id=query["id"], error=verdict.error)
            else:
                result = with_arbiter(result, verdict)

        repo.save_result(
            ctl.scan_id, query["id"], service_id, result.status,
            mention_types=result.mention_types,
            confidence=result.confidence,
            evidence_quote=result.evidence_quote,
            answer_text=cap.answer_text,
            sources=cap.sources,
            screenshot_path=rel_path,
            detected_by=result.detected_by,
            needs_review=result.needs_review,
            llm_model=result.llm_model,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_message=llm_error_text if result.status == "error" else None,
        )
        if ctl.billing_run_id and result.status in ("found", "not_found"):
            check_key = billing.check_id(ctl.billing_run_id, query["id"], service_id)
            repo.queue_billing(check_key, result.status)
            repo.queue_screenshot(check_key, rel_path)
            try:
                await billing.flush_outbox()
                try:
                    await billing.flush_screenshot_outbox()
                except billing.ScreenshotError as exc:
                    log.warning("Скриншот ожидает повторной отправки: %s", exc)
            except billing.BillingError as exc:
                log.warning("Ответ сохранён, списание ожидает повторной отправки: %s", exc)
                ctl.emit("billing_error", error=str(exc))
                ctl.stop()
        ctl.emit("query_result", query_id=query["id"], service=service_id, status=result.status)
        return result.status

    except ServiceUnavailableError as exc:
        repo.save_result(ctl.scan_id, query["id"], service_id, "limit_reached", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="limit_reached")
        return "unavailable"
    except AuthRequiredError as exc:
        _record_auth_state(service_id, "auth_required")
        repo.save_result(ctl.scan_id, query["id"], service_id, "auth_required", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="auth_required")
        return "auth_required"
    except CaptchaError as exc:
        repo.save_result(ctl.scan_id, query["id"], service_id, "captcha", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="captcha")
        return "captcha"
    except AdapterError as exc:
        repo.save_result(ctl.scan_id, query["id"], service_id, "error", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="error")
        return "error"
    except Exception as exc:
        if "Target page, context or browser has been closed" in str(exc):
            # Весь браузер умер: внешний цикл поднимет новый профиль и
            # повторит текущий запрос. Не записываем ложный результат.
            raise
        log.exception("Ошибка на запросе %s / %s", query["text"], service_id)
        repo.save_result(ctl.scan_id, query["id"], service_id, "error", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="error")
        return "error"
