import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "pipeline_lock.db"

@contextmanager
def open_and_close_connection(db_path: str | Path = DB_PATH):
    """Context manager to open and close a database connection."""
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()

def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign key support
    conn.row_factory = sqlite3.Row  # Access columns by name instead of index.
    init_db(conn)
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database schema if tables do not already exist."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_id INTEGER PRIMARY KEY,
            project_name TEXT COLLATE NOCASE NOT NULL UNIQUE,
            storage_type TEXT NOT NULL CHECK (storage_type IN ('file_system', 'dropbox', 'google_drive')),
            root TEXT NOT NULL,
            enforcement_enabled INTEGER NOT NULL DEFAULT 1 CHECK (enforcement_enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_members (
            project_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('personnel', 'supervisor')),
            PRIMARY KEY (project_id, member_name),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
            project_id INTEGER NOT NULL,
            resource_path TEXT NOT NULL,
            PRIMARY KEY (project_id, resource_path),
            FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS locks (
            project_id INTEGER NOT NULL,
            resource_path TEXT NOT NULL,
            owner TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            PRIMARY KEY (project_id, resource_path),
            FOREIGN KEY (project_id, resource_path) REFERENCES resources (project_id, resource_path) ON DELETE RESTRICT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lock_history (
            event_id INTEGER PRIMARY KEY,
            project_id INTEGER NOT NULL,
            resource_path TEXT NOT NULL,
            owner TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('acquire', 'refresh', 'release', 'force_release', 'expired')),
            timestamp TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (project_id) 
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admins (
        admin_name TEXT PRIMARY KEY
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS global_switch_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))            
        )
        """
    )

    with conn:
        # Ensure there's always one row in global_switch_state
        conn.execute(
            """
            INSERT OR IGNORE INTO global_switch_state (id) VALUES (1)
            """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS global_switch_history (
            event_id INTEGER PRIMARY KEY,
            toggled_by TEXT NOT NULL,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            timestamp TEXT NOT NULL
        )
        """        
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS global_switch_reasons (
            reason_id INTEGER PRIMARY KEY,
            event_id INTEGER NOT NULL,
            added_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES global_switch_history (event_id) ON DELETE RESTRICT
        )
        """
    )

    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current == 0:
        conn.execute("PRAGMA user_version = 1")