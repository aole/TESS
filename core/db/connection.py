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
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    conn.execute('PRAGMA busy_timeout = 5000')

    return conn
