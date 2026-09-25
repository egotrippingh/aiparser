"""Upgrade fresh or legacy account databases without dropping existing data."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from server.models import Base

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "69338e58324c"
NEW_TABLES = {"auth_failures", "password_resets"}


def upgrade_database(database_url: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
            current = MigrationContext.configure(connection).get_current_revision()
            expected = set(Base.metadata.tables) - NEW_TABLES
            if current is None and "alembic_version" in tables:
                raise RuntimeError("Таблица версий миграций пуста: проверьте БД вручную")
            if current is None and tables:
                if tables != expected:
                    raise RuntimeError("Неизвестная схема БД: автоматическое принятие невозможно")
                for name in expected:
                    existing = {column["name"] for column in inspect(connection).get_columns(name)}
                    desired = {column.name for column in Base.metadata.tables[name].columns}
                    if name == "checks" and existing == desired - {"analysis_json"}:
                        continue
                    if existing != desired:
                        raise RuntimeError(f"Схема таблицы {name} отличается от исходной")
                command.stamp(config, BASELINE)
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            version = MigrationContext.configure(connection).get_current_revision()
        head = ScriptDirectory.from_config(config).get_current_head()
        if version != head:
            raise RuntimeError("База данных не обновлена до текущей версии")
    finally:
        engine.dispose()


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL не задан")
    upgrade_database(url)
