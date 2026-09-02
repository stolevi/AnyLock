import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "pipeline_lock.db"

def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row # Access columns by name instead of index
    init_db(conn)
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database schema if tables do not already exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS locks (
            resource_id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

