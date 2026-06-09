from pathlib import Path
import sqlite3


def get_db_path() -> Path:
    """Return absolute path to data/tess.db."""
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "data" / "tess.db"


def get_connection() -> sqlite3.Connection:
    """Create and return a SQLite connection to data/tess.db."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)
