from __future__ import annotations

from pathlib import Path

from src.db.connection import get_conn, is_postgres


def run_migrations() -> None:
    if is_postgres():
        migration_files = sorted(Path("migrations/postgres").glob("*.sql"))
    else:
        migration_files = sorted(Path("migrations").glob("*.sql"))
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              name TEXT PRIMARY KEY,
              applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for migration_file in migration_files:
            already_applied = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE name = ? LIMIT 1",
                (migration_file.name,),
            ).fetchone()
            if already_applied is not None:
                continue
            sql = migration_file.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (name) VALUES (?)",
                (migration_file.name,),
            )


if __name__ == "__main__":
    run_migrations()
    print("Migrations applied.")
