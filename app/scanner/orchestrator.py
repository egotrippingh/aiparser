"""Очередь «запрос × сервис»: сердце скана.

Один сервис за другим, внутри сервиса — один запрос за другим, строго
последовательно, с человекоподобными паузами.

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
from datetime import datetime

from app import config, imaging, services
from app.db import repo
from app.detect import llm as llm_mod
from app.detect import deep as deep_mod
from app.detect import rules
from app.detect.merge import merge, should_call_llm, with_deep
from app.scanner import humanize
from app.scanner.adapters import ADAPTERS, get_adapter
from app.scanner.adapters.base import (
    AdapterError,
    AuthRequiredError,
    CaptchaError,
    ServiceUnavailableError,
)
from app.scanner.browser import service_context

log = logging.getLogger("aiparser.orchestrator")

# Сколько «сервис не принимает запросы» подряд считаем стеной лимита.
# Единичный сбой бывает случайным (подвисла вёрстка), три подряд — это уже
# не совпадение, а состояние аккаунта.
LIMIT_STRIKES = 3


class ScanAlreadyRunning(RuntimeError):
    pass


class ScanController:
    """Состояние одного запущенного скана: события + прогресс + флаги управления."""

    def __init__(self, scan_id: int, project_id: int, total: int, scan_date: str) -> None:
        self.scan_id = scan_id
        self.project_id = project_id
        # Дата среза берётся из самого скана, а не из «сегодня»: при дозапуске
        # на следующий день результаты и скриншоты должны лечь к своему срезу.
        self.scan_date = scan_date
        self.total = total
        self.done = 0
        self.current_service: str | None = None
        self.state = "running"          # running | paused | stopping | finished
        self.started_at = time.time()

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
        self.emit("progress", service=service_id, **self.snapshot())

    def snapshot(self) -> dict:
        """Текущий прогресс + оценка остатка.

        Оценка считается по фактической средней скорости этого прогона, а не
        по нормативу: реальное время на запрос зависит от того, насколько
        долго думает конкретная нейросеть, и предсказать его заранее нельзя.
        """
        elapsed = time.time() - self.started_at
        eta = None
        if self.done and self.total > self.done:
            eta = int((elapsed / self.done) * (self.total - self.done))
        return {
            "scan_id": self.scan_id,
            "project_id": self.project_id,
            "done": self.done,
            "total": self.total,
            "percent": round(self.done * 100 / self.total, 1) if self.total else 0.0,
            "state": self.state,
            "current_service": self.current_service,
            "elapsed_sec": int(elapsed),
            "eta_sec": eta,
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
        "llm_mode": s.get("llm_mode", "smart"),
        "llm_confidence_threshold": float(s.get("llm_confidence_threshold", 0.6)),
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


async def start_scan(project_id: int, service_ids: list[str], *, resume: bool = True) -> int:
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

    snapshot = _settings_snapshot()
    scan_id, done_pairs = _open_scan(project_id, known, resume, snapshot)

    work = [(svc, q) for svc in known for q in queries if (q["id"], svc) not in done_pairs]
    if not work:
        # _open_scan уже перевёл найденный скан в "running" — возвращаем его в
        # завершённое состояние, иначе он навсегда остался бы «идущим».
        repo.finish_scan(scan_id, status="done")
        raise ValueError("Всё уже проверено — нечего досканировать")

    scan_row = repo.get_scan(scan_id)
    assert scan_row is not None  # только что создан или найден выше
    controller = ScanController(scan_id, project_id, total=len(work), scan_date=scan_row["scan_date"])
    _active[scan_id] = controller

    asyncio.create_task(_run_scan(project, known, queries, done_pairs, snapshot, controller))
    return scan_id


def _open_scan(project_id: int, services_used: list[str], resume: bool, snapshot: dict) -> tuple[int, set]:
    """Продолжает незаконченный скан или заводит новый.

    Продолжаем только если набор сервисов совпадает: скан с другим составом
    сервисов — это другой замер, дописывать в него чужие данные нельзя.
    """
    if resume:
        prev = repo.find_resumable_scan(project_id, scannable=set(ADAPTERS))
        # Достаточно, чтобы выбранные сервисы входили в состав того скана:
        # сканировать подмножество — это дозапуск, а вот сервис, которого там
        # не было, дописывать в чужой замер нельзя.
        if prev and set(services_used) <= set(json.loads(prev["services_json"])):
            repo.set_scan_status(prev["id"], "running")
            log.info("Продолжаю скан %s: осталось %s проверок", prev["id"], prev["remaining"])
            return prev["id"], repo.conclusive_pairs(prev["id"])

    return repo.create_scan(project_id, services_used, snapshot), set()


async def _run_scan(
    project: dict,
    service_ids: list[str],
    queries: list[dict],
    done_pairs: set,
    settings: dict,
    ctl: ScanController,
) -> None:
    api_key, llm_model = llm_mod.load_credentials()
    llm_mode = settings["llm_mode"] if api_key else "never"
    speed = settings["typing_speed"]

    ctl.emit("scan_started", **ctl.snapshot())

    try:
        for service_id in service_ids:
            if ctl.stop_requested:
                break

            pending = [q for q in queries if (q["id"], service_id) not in done_pairs]
            if not pending:
                continue

            ctl.current_service = service_id
            ctl.emit("service_started", service=service_id,
                     name=services.get(service_id).name, pending=len(pending))

            try:
                await _run_service(
                    project, service_id, pending, settings, speed,
                    api_key, llm_model, llm_mode, ctl,
                )
            except Exception as exc:
                log.exception("Сервис %s упал целиком", service_id)
                ctl.emit("service_error", service=service_id, error=str(exc))

            ctl.emit("service_finished", service=service_id)

        status = "stopped" if ctl.stop_requested else "done"
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
    """Один сервис целиком: одна вкладка, одна загрузка сайта, N запросов."""
    adapter = get_adapter(service_id)

    async with service_context(service_id) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        ready = await adapter.ensure_ready(page)
        _record_auth_state(service_id, "ok" if ready.ok else (ready.reason or "error"))

        if not ready.ok:
            # Сессия не открылась — записываем причину сразу всем запросам
            # сервиса, чтобы в таблице было видно «почему пусто», а не дыра.
            for q in pending:
                repo.save_result(ctl.scan_id, q["id"], service_id, ready.reason or "error")
                ctl.advance(service_id)
            ctl.emit("service_blocked", service=service_id, reason=ready.reason)
            return

        strikes = 0

        for q in pending:
            if ctl.stop_requested:
                break
            await ctl.paused.wait()
            if ctl.stop_requested:
                break

            # Вкладка могла умереть (краш рендерера) — поднимаем новую и
            # заново открываем сессию, иначе весь остаток сервиса посыплется.
            if page.is_closed():
                log.warning("Вкладка %s закрылась — открываю заново", service_id)
                page = await context.new_page()
                if not (await adapter.ensure_ready(page)).ok:
                    break

            status = await _run_one(
                project, q, service_id, adapter, page, settings, speed,
                api_key, llm_model, llm_mode, ctl,
            )
            ctl.advance(service_id)

            if status == "unavailable":
                strikes += 1
                if strikes >= LIMIT_STRIKES:
                    _mark_limit_reached(ctl, service_id, pending, q)
                    return
            else:
                strikes = 0

            if ctl.done < ctl.total:
                await humanize.between_queries(
                    ctl.done,
                    lo=settings["delay_min_sec"],
                    hi=settings["delay_max_sec"],
                    break_every=settings["break_every_n"],
                )


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

        rule_verdict = rules.evaluate(
            cap.answer_text, cap.sources, project["brand_name"],
            project["brand_aliases"], project["brand_domains"],
        )

        llm_verdict = None
        if should_call_llm(rule_verdict, llm_mode):
            llm_verdict = await llm_mod.evaluate(
                query=query["text"],
                brand_name=project["brand_name"],
                aliases=project["brand_aliases"],
                answer_text=cap.answer_text,
                sources=cap.sources,
                screenshot_bytes=webp_bytes,
                api_key=api_key,
                model=llm_model,
            )
            if llm_verdict.error:
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
        )
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
        log.exception("Ошибка на запросе %s / %s", query["text"], service_id)
        repo.save_result(ctl.scan_id, query["id"], service_id, "error", error_message=str(exc))
        ctl.emit("query_result", query_id=query["id"], service=service_id, status="error")
        return "error"
