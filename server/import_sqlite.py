"""Import a consistent SQLite snapshot into an empty migrated PostgreSQL database.

Stop the web container first. Credentials are read from DATABASE_URL, not CLI flags.
The source is read-only; all inserts and verification share one transaction.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import Integer, create_engine, func, inspect, select, text

from server.migrate import upgrade_database
from server.models import Base


def fingerprint(rows: list[dict]) -> str:
    def encode(value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
        raise TypeError(type(value).__name__)

    canonical = sorted(json.dumps(row, sort_keys=True, default=encode, ensure_ascii=False)
                       for row in rows)
    return hashlib.sha256("\n".join(canonical).encode()).hexdigest()


def import_snapshot(source: Path, destination_url: str) -> dict[str, int]:
    if not source.is_file():
        raise RuntimeError("SQLite snapshot does not exist")
    destination = create_engine(destination_url)
    if destination.dialect.name != "postgresql":
        destination.dispose()
        raise RuntimeError("Destination must be PostgreSQL")
    source_engine = create_engine(f"sqlite:///file:{source.resolve().as_posix()}?mode=ro&uri=true")
    try:
        upgrade_database(destination_url)
        tables = Base.metadata.sorted_tables
        with source_engine.connect() as src, destination.begin() as dst:
            if set(inspect(src).get_table_names()) != {t.name for t in tables} | {"alembic_version"}:
                raise RuntimeError("Snapshot schema does not match the application")
            if src.execute(text("SELECT version_num FROM alembic_version")).scalar_one() != dst.execute(
                    text("SELECT version_num FROM alembic_version")).scalar_one():
                raise RuntimeError("Source and destination migration versions differ")
            # Prevent concurrent registration or scan writes during the import.
            dst.execute(text("LOCK TABLE " + ", ".join('"' + t.name + '"' for t in tables)
                             + " IN ACCESS EXCLUSIVE MODE"))
            if any(dst.scalar(select(func.count()).select_from(t)) for t in tables):
                raise RuntimeError("Destination is not empty; no data imported")
            counts = {}
            for table in tables:
                rows = [dict(row) for row in src.execute(select(table)).mappings()]
                for offset in range(0, len(rows), 250):
                    dst.execute(table.insert(), rows[offset:offset + 250])
                copied = [dict(row) for row in dst.execute(select(table)).mappings()]
                if len(rows) != len(copied) or fingerprint(rows) != fingerprint(copied):
                    raise RuntimeError(f"Verification failed for {table.name}; import rolled back")
                counts[table.name] = len(rows)
                for column in table.primary_key.columns:
                    if isinstance(column.type, Integer):
                        sequence = dst.scalar(text("SELECT pg_get_serial_sequence(:table, :column)"),
                                              {"table": table.name, "column": column.name})
                        maximum = dst.scalar(select(func.max(column)))
                        if sequence and maximum is not None:
                            dst.execute(text("SELECT setval(CAST(:sequence AS regclass), :value, true)"),
                                        {"sequence": sequence, "value": maximum})
        return counts
    finally:
        source_engine.dispose()
        destination.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    try:
        result = import_snapshot(args.snapshot, os.environ["DATABASE_URL"])
    except Exception as exc:
        # SQL exceptions can include account rows and password hashes in parameters.
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        raise SystemExit(f"Import failed; transaction rolled back: {message}") from None
    print(json.dumps({"verified_rows": result}, sort_keys=True))
