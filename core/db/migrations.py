from pathlib import Path

from core.db.connection import get_connection


def run_migrations() -> None:
    project_root = Path(__file__).resolve().parents[2]
    migrations_dir = project_root / "migrations"

    if not migrations_dir.exists():
        return

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        applied = {
            row["filename"]
            for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }

        for migration_path in sorted(migrations_dir.glob("*.sql")):
            if migration_path.name in applied:
                continue

            conn.executescript(migration_path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)",
                (migration_path.name,),
            )

        conn.commit()
