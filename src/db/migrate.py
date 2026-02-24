from __future__ import annotations

from pathlib import Path

from src.db.connection import get_conn, is_postgres


def run_migrations() -> None:
    if is_postgres():
        migration_files = sorted(Path("migrations/postgres").glob("*.sql"))
    else:
        migration_files = sorted(Path("migrations").glob("*.sql"))
    with get_conn() as conn:
        for migration_file in migration_files:
            sql = migration_file.read_text(encoding="utf-8")
            conn.executescript(sql)


if __name__ == "__main__":
    run_migrations()
    print("Migrations applied.")
