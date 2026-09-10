-- Схема БД AI Mentions Tracker.
-- Версия схемы хранится в user_version; миграции см. app/db/migrations.py.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    brand_name          TEXT    NOT NULL,
    brand_aliases_json  TEXT    NOT NULL DEFAULT '[]',
    brand_domains_json  TEXT    NOT NULL DEFAULT '[]',
    region_code         TEXT,                       -- lr= для Яндекса, напр. '213' — Москва
    deep_check_depth    INTEGER NOT NULL DEFAULT 0, -- 0 = глубокая проверка источников выключена
    notes               TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS queries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    text        TEXT    NOT NULL,
    group_tag   TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, text)
);

CREATE TABLE IF NOT EXISTS scans (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id              INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scan_date               TEXT    NOT NULL,       -- YYYY-MM-DD, срез для динамики по дням
    started_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    finished_at             TEXT,
    status                  TEXT    NOT NULL DEFAULT 'running',
                            -- running | paused | done | stopped | failed
    services_json           TEXT    NOT NULL DEFAULT '[]',
    settings_snapshot_json  TEXT    NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS results (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id            INTEGER NOT NULL REFERENCES scans(id)   ON DELETE CASCADE,
    query_id           INTEGER NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    service            TEXT    NOT NULL,
    status             TEXT    NOT NULL,
                       -- found | not_found | error | auth_required | captcha
                       -- | skipped (AI-блок не показан) | limit_reached (квота тарифа)
    mention_types_json TEXT    NOT NULL DEFAULT '[]',  -- text | link | marketplace | indirect
    confidence         REAL,
    evidence_quote     TEXT,
    answer_text        TEXT,
    sources_json       TEXT    NOT NULL DEFAULT '[]',
    screenshot_path    TEXT,
    detected_by        TEXT,                           -- rules | llm | both | none
    needs_review       INTEGER NOT NULL DEFAULT 0,     -- расхождение правил и LLM
    llm_model          TEXT,
    duration_ms        INTEGER,
    error_message      TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (scan_id, query_id, service)
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    is_secret  INTEGER NOT NULL DEFAULT 0  -- значение зашифровано через DPAPI
);

CREATE INDEX IF NOT EXISTS idx_queries_project  ON queries(project_id, is_active);
CREATE INDEX IF NOT EXISTS idx_scans_project    ON scans(project_id, scan_date);
CREATE INDEX IF NOT EXISTS idx_results_scan     ON results(scan_id);
CREATE INDEX IF NOT EXISTS idx_results_query    ON results(query_id, service);
CREATE INDEX IF NOT EXISTS idx_results_status   ON results(scan_id, status);
