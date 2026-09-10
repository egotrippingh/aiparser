"""Тонкий слой доступа к SQLite.

ORM здесь был бы лишним: таблиц пять, запросы простые, а лишняя зависимость в
portable-сборке стоит мегабайт. Соединение держим по одному на поток —
сканер живёт в своём потоке, FastAPI в своём, а sqlite-объекты между потоками
таскать нельзя.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from app import config

_local = threading.local()
_SCHEMA = Path(__file__).with_name("schema.sql")


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(config.DB_PATH, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        _local.conn = c
    return c


def init_db() -> None:
    c = conn()
    c.executescript(_SCHEMA.read_text(encoding="utf-8"))
    _migrate(c)


def _migrate(c: sqlite3.Connection) -> None:
    """Колонки, появившиеся после первых версий.

    CREATE TABLE IF NOT EXISTS уже существующую таблицу не трогает, а база
    переезжает между компьютерами вместе с проектом — без этой доводки старая
    база упала бы на первом же обращении к новой колонке.
    """
    cols = {r[1] for r in c.execute("PRAGMA table_info(projects)")}
    if "parallel_scan" not in cols:
        c.execute("ALTER TABLE projects ADD COLUMN parallel_scan INTEGER NOT NULL DEFAULT 0")


def _rows(sql: str, args: Iterable = ()) -> list[dict]:
    return [dict(r) for r in conn().execute(sql, tuple(args)).fetchall()]


def _row(sql: str, args: Iterable = ()) -> dict | None:
    r = conn().execute(sql, tuple(args)).fetchone()
    return dict(r) if r else None


def _exec(sql: str, args: Iterable = ()) -> sqlite3.Cursor:
    return conn().execute(sql, tuple(args))


# --------------------------------------------------------------------------
# проекты
# --------------------------------------------------------------------------

def _decode_project(p: dict) -> dict:
    p["brand_aliases"] = json.loads(p.pop("brand_aliases_json"))
    p["brand_domains"] = json.loads(p.pop("brand_domains_json"))
    p["parallel_scan"] = bool(p.get("parallel_scan"))
    return p


def list_projects() -> list[dict]:
    return [_decode_project(p) for p in _rows("SELECT * FROM projects ORDER BY name")]


def get_project(project_id: int) -> dict | None:
    p = _row("SELECT * FROM projects WHERE id = ?", (project_id,))
    return _decode_project(p) if p else None


def create_project(
    name: str,
    brand_name: str,
    brand_aliases: list[str] | None = None,
    brand_domains: list[str] | None = None,
    region_code: str | None = None,
    deep_check_depth: int = 0,
    notes: str | None = None,
    parallel_scan: bool = False,
) -> int:
    cur = _exec(
        """INSERT INTO projects
             (name, brand_name, brand_aliases_json, brand_domains_json,
              region_code, deep_check_depth, notes, parallel_scan)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            name,
            brand_name,
            json.dumps(brand_aliases or [], ensure_ascii=False),
            json.dumps(brand_domains or [], ensure_ascii=False),
            region_code,
            deep_check_depth,
            notes,
            1 if parallel_scan else 0,
        ),
    )
    return int(cur.lastrowid)


def update_project(project_id: int, **fields: Any) -> None:
    if "brand_aliases" in fields:
        fields["brand_aliases_json"] = json.dumps(fields.pop("brand_aliases"), ensure_ascii=False)
    if "brand_domains" in fields:
        fields["brand_domains_json"] = json.dumps(fields.pop("brand_domains"), ensure_ascii=False)
    if "parallel_scan" in fields:
        fields["parallel_scan"] = 1 if fields["parallel_scan"] else 0
    allowed = {
        "name", "brand_name", "brand_aliases_json", "brand_domains_json",
        "region_code", "deep_check_depth", "notes", "parallel_scan",
    }
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    _exec(f"UPDATE projects SET {sets} WHERE id = ?", (*fields.values(), project_id))


def delete_project(project_id: int) -> None:
    _exec("DELETE FROM projects WHERE id = ?", (project_id,))


# --------------------------------------------------------------------------
# запросы
# --------------------------------------------------------------------------

def list_queries(project_id: int, only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM queries WHERE project_id = ?"
    if only_active:
        sql += " AND is_active = 1"
    return _rows(sql + " ORDER BY id", (project_id,))


def add_queries(project_id: int, texts: Iterable[str], group_tag: str | None = None) -> int:
    """Возвращает число реально добавленных строк: дубликаты внутри проекта отсеиваются."""
    added = 0
    for t in texts:
        t = " ".join(t.split())
        if not t:
            continue
        cur = _exec(
            "INSERT OR IGNORE INTO queries (project_id, text, group_tag) VALUES (?,?,?)",
            (project_id, t, group_tag),
        )
        added += cur.rowcount or 0
    return added


def set_query_active(query_id: int, active: bool) -> None:
    _exec("UPDATE queries SET is_active = ? WHERE id = ?", (1 if active else 0, query_id))


def delete_query(query_id: int) -> None:
    _exec("DELETE FROM queries WHERE id = ?", (query_id,))


# --------------------------------------------------------------------------
# сканы
# --------------------------------------------------------------------------

def create_scan(project_id: int, services: list[str], settings_snapshot: dict) -> int:
    cur = _exec(
        """INSERT INTO scans (project_id, scan_date, services_json, settings_snapshot_json)
           VALUES (?,?,?,?)""",
        (
            project_id,
            date.today().isoformat(),
            json.dumps(services),
            json.dumps(settings_snapshot, ensure_ascii=False),
        ),
    )
    return int(cur.lastrowid)


def finish_scan(scan_id: int, status: str = "done") -> None:
    _exec(
        "UPDATE scans SET status = ?, finished_at = ? WHERE id = ?",
        (status, datetime.now().isoformat(timespec="seconds"), scan_id),
    )


def set_scan_status(scan_id: int, status: str) -> None:
    _exec("UPDATE scans SET status = ? WHERE id = ?", (status, scan_id))


def get_scan(scan_id: int) -> dict | None:
    return _row("SELECT * FROM scans WHERE id = ?", (scan_id,))


def list_scans(project_id: int, limit: int = 60) -> list[dict]:
    return _rows(
        "SELECT * FROM scans WHERE project_id = ? ORDER BY started_at DESC LIMIT ?",
        (project_id, limit),
    )


def latest_scan(project_id: int) -> dict | None:
    return _row(
        "SELECT * FROM scans WHERE project_id = ? ORDER BY started_at DESC LIMIT 1",
        (project_id,),
    )


# --------------------------------------------------------------------------
# результаты
# --------------------------------------------------------------------------

def save_result(
    scan_id: int,
    query_id: int,
    service: str,
    status: str,
    *,
    mention_types: list[str] | None = None,
    confidence: float | None = None,
    evidence_quote: str | None = None,
    answer_text: str | None = None,
    sources: list[str] | None = None,
    screenshot_path: str | None = None,
    detected_by: str | None = None,
    needs_review: bool = False,
    llm_model: str | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    """Перезаписывает результат для пары «запрос × сервис» в рамках одного скана.

    REPLACE нужен для повторной проверки: пользователь может перезапустить
    отдельный запрос после того, как вручную решил капчу.
    """
    _exec(
        """INSERT OR REPLACE INTO results
             (scan_id, query_id, service, status, mention_types_json, confidence,
              evidence_quote, answer_text, sources_json, screenshot_path,
              detected_by, needs_review, llm_model, duration_ms, error_message)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scan_id, query_id, service, status,
            json.dumps(mention_types or [], ensure_ascii=False),
            confidence, evidence_quote, answer_text,
            json.dumps(sources or [], ensure_ascii=False),
            screenshot_path, detected_by, 1 if needs_review else 0,
            llm_model, duration_ms, error_message,
        ),
    )


# Статусы, означающие «по этой паре запрос×сервис данные получены и
# переспрашивать нечего». Всё остальное (error, captcha, auth_required,
# limit_reached) — временные помехи, и при дозапуске такие пары берутся заново.
CONCLUSIVE_STATUSES = ("found", "not_found", "skipped")


def conclusive_pairs(scan_id: int) -> set[tuple[int, str]]:
    """Пары (query_id, service), по которым в этом скане уже есть годный результат."""
    placeholders = ",".join("?" * len(CONCLUSIVE_STATUSES))
    rows = _rows(
        f"SELECT query_id, service FROM results WHERE scan_id = ? AND status IN ({placeholders})",
        (scan_id, *CONCLUSIVE_STATUSES),
    )
    return {(r["query_id"], r["service"]) for r in rows}


def find_resumable_scan(project_id: int, scannable: set[str] | None = None) -> dict | None:
    """Последний скан проекта, в котором остались непройденные пары «запрос × сервис».

    Нужен для дозапуска: бесплатные тарифы ChatGPT/Perplexity упираются в
    лимит примерно на сороковом запросе, и база в сотню запросов физически не
    проходит за один прогон. Продолжаем в ТОТ ЖЕ скан, а не создаём новый:
    иначе дашборд, который показывает последний скан за день, увидел бы только
    хвост базы вместо полной картины.

    `scannable` — сервисы, для которых вообще есть адаптер. Без этого фильтра
    скан, в котором был выбран сервис без адаптера, навсегда числился бы
    незавершённым: ожидаемое число проверок никогда не сошлось бы с
    фактическим.
    """
    scan = _row(
        "SELECT * FROM scans WHERE project_id = ? ORDER BY started_at DESC LIMIT 1",
        (project_id,),
    )
    if not scan:
        return None

    services_in_scan = json.loads(scan["services_json"])
    if scannable is not None:
        services_in_scan = [s for s in services_in_scan if s in scannable]

    active_queries = len(list_queries(project_id, only_active=True))
    expected = active_queries * len(services_in_scan)
    done = len(conclusive_pairs(scan["id"]))

    if expected == 0 or done >= expected:
        return None

    scan["scannable_services"] = services_in_scan
    scan["expected"] = expected
    scan["conclusive"] = done
    scan["remaining"] = expected - done
    return scan


def results_for_scan(scan_id: int) -> list[dict]:
    return _rows(
        """SELECT r.*, q.text AS query_text, q.group_tag
             FROM results r JOIN queries q ON q.id = r.query_id
            WHERE r.scan_id = ?
            ORDER BY q.id""",
        (scan_id,),
    )


def pick_result(current: dict | None, candidate: dict) -> dict:
    """Какой из двух результатов одной пары «запрос × сервис × дата» показывать.

    За день бывает несколько сканов: дозапуск после лимита тарифа,
    перепроверка. Берём последний конклюзивный (found / not_found / skipped):
    свежая ошибка не должна затирать уже полученный ответ. Если конклюзивных
    нет — последний вообще. Кандидаты подаются по возрастанию времени.
    """
    if current is None:
        return candidate
    if candidate["status"] in CONCLUSIVE_STATUSES or current["status"] not in CONCLUSIVE_STATUSES:
        return candidate
    return current


def query_history(query_id: int, service: str | None = None, limit: int = 30) -> list[dict]:
    """По одному результату на дату (и сервис) — см. pick_result."""
    sql = """SELECT s.scan_date, r.service, r.status, r.confidence
               FROM results r JOIN scans s ON s.id = r.scan_id
              WHERE r.query_id = ?"""
    args: list[Any] = [query_id]
    if service:
        sql += " AND r.service = ?"
        args.append(service)
    sql += " ORDER BY s.scan_date, r.created_at, r.id"
    picked: dict[tuple[str, str], dict] = {}
    for r in _rows(sql, args):
        key = (r["scan_date"], r["service"])
        picked[key] = pick_result(picked.get(key), r)
    return sorted(picked.values(), key=lambda r: (r["scan_date"], r["service"]))[-limit:]


def project_dates(project_id: int, days: int) -> list[str]:
    """Последние `days` дат, в которые по проекту были сканы, по возрастанию."""
    rows = _rows(
        "SELECT DISTINCT scan_date FROM scans WHERE project_id = ? ORDER BY scan_date DESC LIMIT ?",
        (project_id, days),
    )
    return sorted(r["scan_date"] for r in rows)


def scan_dates(project_id: int) -> list[dict]:
    """Все даты со сканами — для календаря: сколько проверок и какими сервисами."""
    rows = _rows(
        """SELECT s.scan_date AS date,
                  COUNT(r.id) AS checks,
                  GROUP_CONCAT(DISTINCT r.service) AS services
             FROM scans s LEFT JOIN results r ON r.scan_id = s.id
            WHERE s.project_id = ?
            GROUP BY s.scan_date
            ORDER BY s.scan_date""",
        (project_id,),
    )
    for r in rows:
        r["services"] = sorted(r["services"].split(",")) if r["services"] else []
    return rows


def results_by_date(project_id: int, dates: list[str]) -> list[dict]:
    """Результаты проекта за даты — ровно один на (запрос, сервис, дата).

    Раньше видимость за день считалась по всем сканам этого дня сразу, и
    повторная проверка того же запроса удваивала и числитель, и знаменатель.
    """
    if not dates:
        return []
    marks = ",".join("?" * len(dates))
    rows = _rows(
        f"""SELECT r.id, r.query_id, r.service, r.status, r.needs_review,
                   s.scan_date, s.id AS scan_id
              FROM results r JOIN scans s ON s.id = r.scan_id
             WHERE s.project_id = ? AND s.scan_date IN ({marks})
             ORDER BY r.created_at, r.id""",
        (project_id, *dates),
    )
    picked: dict[tuple[int, str, str], dict] = {}
    for r in rows:
        key = (r["query_id"], r["service"], r["scan_date"])
        picked[key] = pick_result(picked.get(key), r)
    return list(picked.values())


def query_results_on_date(query_id: int, scan_date: str) -> list[dict]:
    """Полные результаты запроса за дату — по одному на сервис, см. pick_result."""
    rows = _rows(
        """SELECT r.*, q.text AS query_text, s.scan_date
             FROM results r
             JOIN scans s ON s.id = r.scan_id
             JOIN queries q ON q.id = r.query_id
            WHERE r.query_id = ? AND s.scan_date = ?
            ORDER BY r.created_at, r.id""",
        (query_id, scan_date),
    )
    picked: dict[str, dict] = {}
    for r in rows:
        picked[r["service"]] = pick_result(picked.get(r["service"]), r)
    return list(picked.values())


def visibility_by_day(project_id: int, days: int = 30) -> list[dict]:
    """Доля запросов с упоминанием по дням и сервисам — данные для графика.

    Знаменатель считаем только по проверкам, которые реально состоялись:
    ошибки и «AI-блок не показан» не должны занижать видимость.
    """
    return _rows(
        """SELECT s.scan_date,
                  r.service,
                  SUM(CASE WHEN r.status = 'found' THEN 1 ELSE 0 END)   AS found,
                  SUM(CASE WHEN r.status IN ('found','not_found') THEN 1 ELSE 0 END) AS checked
             FROM results r
             JOIN scans s ON s.id = r.scan_id
            WHERE s.project_id = ?
            GROUP BY s.scan_date, r.service
            ORDER BY s.scan_date
            LIMIT ?""",
        (project_id, days * 8),
    )


# --------------------------------------------------------------------------
# настройки
# --------------------------------------------------------------------------

def get_setting(key: str, default: str | None = None) -> str | None:
    r = _row("SELECT value FROM settings WHERE key = ?", (key,))
    return r["value"] if r else default


def set_setting(key: str, value: str | None, is_secret: bool = False) -> None:
    _exec(
        "INSERT OR REPLACE INTO settings (key, value, is_secret) VALUES (?,?,?)",
        (key, value, 1 if is_secret else 0),
    )


def all_settings() -> dict[str, str]:
    return {r["key"]: r["value"] for r in _rows("SELECT key, value FROM settings WHERE is_secret = 0")}
