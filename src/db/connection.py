from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("APP_DB_PATH", "data/app.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def ensure_db_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")


def _convert_qmark_to_pyformat(sql: str) -> str:
    # Repository queries use sqlite-style placeholders.
    # For psycopg, convert '?' to '%s'.
    return sql.replace("?", "%s")


class PostgresAdapter:
    def __init__(self, conn: Any):
        self._conn = conn

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> Any:
        cur = self._conn.cursor()
        cur.execute(_convert_qmark_to_pyformat(sql), params)
        return cur

    def executescript(self, sql: str) -> None:
        cur = self._conn.cursor()
        cur.execute(sql)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


@contextmanager
def get_conn() -> Any:
    if is_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL is set to postgres but psycopg is not installed. "
                "Install dependencies from requirements.txt."
            ) from exc

        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        adapter = PostgresAdapter(conn)
        try:
            yield adapter
            adapter.commit()
        finally:
            adapter.close()
        return

    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
