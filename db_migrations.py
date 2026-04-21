from __future__ import annotations

import logging
from typing import Iterable, Tuple

from sqlalchemy import Engine


def _sqlite_table_has_column(engine: Engine, table: str, column: str) -> bool:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table});").fetchall()
    return any(r[1] == column for r in rows)


def _sqlite_add_column(engine: Engine, table: str, column: str, col_type: str) -> None:
    with engine.connect() as conn:
        conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
        conn.commit()


def ensure_sqlite_schema(engine: Engine) -> None:
    """
    SQLite-only lightweight migrations (no Alembic).
    Safe to call repeatedly.
    """
    # (table, column, sqlite_type)
    desired: Iterable[Tuple[str, str, str]] = (
        ("specialists", "phone_last4", "TEXT"),
        ("support_requests", "requester_phone_last4", "TEXT"),
        ("support_requests", "created_at", "INTEGER"),
        ("support_requests", "assigned_at", "INTEGER"),
        ("support_requests", "resolved_at", "INTEGER"),
    )

    for table, column, col_type in desired:
        try:
            if not _sqlite_table_has_column(engine, table, column):
                logging.info(f"DB MIGRATION: adding column {table}.{column}")
                _sqlite_add_column(engine, table, column, col_type)
        except Exception as e:
            logging.warning(f"DB MIGRATION WARNING for {table}.{column}: {e}")
