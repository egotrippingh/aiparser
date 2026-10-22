# Правила Python

Обязательны для `app/`, `server/`, корневых `tests/` и `scripts/`, которые трогают
агент/сервер. Незаполненных разделов нет: ниже — проверяемые правила. Nested
`app/AGENTS.md` и `server/AGENTS.md` остаются источником инвариантов и команд
pytest; этот файл фиксирует язык и антипаттерны. Старый код правят при касании.

## Область применения

- Да: `app/**/*.py`, `server/**/*.py` (кроме сгенерированных миграционных
  артефактов, которые не правят руками), `tests/**/*.py`, `scripts/*.py`,
  `desktop.py`, `telemetry.py`.
- Нет: vendored/third-party деревья, разовые однострочники вне репозитория.
- Исключение: временные debug-логи в локальной ветке — не коммитить.

## Обязательные правила

1. **Event loop.** Не блокировать asyncio event loop синхронным I/O, долгим CPU
   или `time.sleep`. Для ожидания — `asyncio.sleep` / таймауты API. Проверка:
   nested agent checks + ревью изменённых async-путей.
2. **Отмена и границы.** Не глотать `CancelledError` / `asyncio.CancelledError`.
   Очереди и ретраи ограничены; cleanup ресурсов обязателен при stop/pause/cancel.
   Проверка: тесты durable capture / abandon / billing recovery.
3. **Деньги.** Суммы — целые копейки (`int`). Reserve/complete/release и webhooks
   идемпотентны при повторе; цена резерва не мутирует задним числом. Проверка:
   `server/test_coinso.py`, billing-тесты в `app/AGENTS.md`.
4. **Владение данными.** Lookup project/result/check/run/device всегда scoped к
   владельцу/сессии. Совпадение client check ID ≠ ownership. Проверка:
   forbidden-access тесты в `server/`.
5. **Секреты в логах.** Не логировать cookies, токены, `.env`, тела ответов
   провайдеров, plaintext ответов в diagnostics. Проверка: ревью diff + Sentry
   rules в `docs/sentry.md` при касании телеметрии.
6. **Тестовые данные.** Только временные каталоги и fake-провайдеры. Не читать и
   не писать реальные `data/`, `%LOCALAPPDATA%/AIParser`, production `.env` /
   `DATABASE_URL`. Проверка: команды из nested `AGENTS.md`.
7. **Схема.** Новые изменения БД сервера — новая Alembic revision; не править
   уже применённые. Проверка: `alembic heads` / review migration before release.

## Антипаттерны и замены

### Блокировка event loop

Не использовать:
```python
time.sleep(2)
raw = open(path).read()  # sync disk on the loop
```

Использовать:
```python
await asyncio.sleep(2)
raw = await asyncio.to_thread(Path(path).read_text, encoding="utf-8")
```

Причина: сканер и control loop живут на asyncio.
Исключения: синхронные CLI/`scripts/` без running loop.
Проверка: code review + agent timing tests.

### Глотание отмены

Не использовать:
```python
try:
    await work()
except Exception:
    return
```

Использовать:
```python
try:
    await work()
except asyncio.CancelledError:
    raise
except Exception as exc:
    log.warning("work failed: %s", type(exc).__name__)
    raise
```

Причина: stop/pause/cancel должны отличаться от обычных ошибок адаптера.
Исключения: нет.
Проверка: abandon/stop tests.

### Отрицательный бренд из сбоя адаптера

Не использовать:
```python
if adapter_failed:
    return BrandResult(mentioned=False)
```

Использовать:
```python
if adapter_failed:
    return unfinished_or_error_status(reason=adapter_reason)
```

Причина: auth/captcha/throttle ≠ «бренд не упомянут».
Исключения: нет.
Проверка: provider readiness / reporting tests.

### Деньги как float

Не использовать:
```python
amount_rub = 10.5
balance += amount_rub
```

Использовать:
```python
amount_kopecks = 1050
balance_kopecks += amount_kopecks
```

Причина: ledger и Coinso работают в целых копейках.
Исключения: отображение в UI после явного форматирования.
Проверка: server money tests.

## Асинхронность и конкурентное выполнение

- Один browser request на provider в текущей архитектуре; не добавлять
  speculative multi-account concurrency.
- Таймауты и очереди bounded; outbox retries once-only where settlement applies.
- `playwright<1.61` compatibility for the Windows agent.

## Ошибки и логирование

- Обычные ошибки запросов не маскировать под успех.
- В логах — тип ошибки и стабильные ID; без payload ответов и credentials.
- Collection failure оставляет check unfinished; отчёт хранит фактический ответ.

## Типизация и структура кода

- Новые публичные функции и модели — с аннотациями; переиспользуй существующие
  dataclass/Pydantic/SQLAlchemy модели вместо параллельных dict-контрактов.
- Чини shared callers вместе с интерфейсом адаптера/helper’а.
- Не вводи новые фреймворки и test runners.

## Работа с данными и ресурсами

- Capture durable до async analysis/upload.
- SQLAlchemy: существующие транзакции, constraints, revision CAS; SQLite-тесты
  не доказывают PostgreSQL concurrency.
- Screenshots owner-scoped; signed links expire; `Cache-Control: no-store` для
  private review.

## Тесты и инструменты проверки

- Ближайший `tests/test_*.py` / `server/test_*.py` сначала, затем группа из
  nested `AGENTS.md` отдельным процессом pytest.
- CI parity: Python 3.12, `.venv` + `scripts/requirements-ci.txt`.
- Не ослаблять тесты ради green; baseline failure — только после reproduce на base.

## Правила других языков

TypeScript/React: `frontend/AGENTS.md` (секция TypeScript). SQL migrations:
`server/AGENTS.md`. PowerShell delivery: `deploy/DELIVERY.md`, `docs/updater.md`.
