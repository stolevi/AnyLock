import sqlite3


class NotAuthorizedError(Exception):
    """Raised when the user is not an authorized supervisor."""

def _supervisors_empty(conn: sqlite3.Connection) -> bool:
    """Check if the supervisors table is empty."""
    row = conn.execute("SELECT 1 FROM supervisors LIMIT 1").fetchone()
    return row is None

def is_supervisor(conn: sqlite3.Connection, supervisor_name: str) -> bool:
    """Check if a given name is in the supervisors table."""
    row = conn.execute(
        "SELECT 1 FROM supervisors WHERE supervisor_name = ?", (supervisor_name,)
    ).fetchone()
    return row is not None

def require_supervisor_or_bootstrap(conn: sqlite3.Connection, initiated_by: str) -> None:
    """Trigger require_supervisor if the supervisors table is not empty."""
    if _supervisors_empty(conn):
        return
    require_supervisor(conn, initiated_by)

def require_supervisor(conn: sqlite3.Connection, supervisor_name: str) -> None:
    """Raise NotAuthorizedError if the given name is not a supervisor."""
    if not is_supervisor(conn, supervisor_name):
        raise NotAuthorizedError(f"{supervisor_name} is not on the list of supervisors.")

def add_supervisor(conn: sqlite3.Connection, supervisor_name: str) -> None:
    """Add a new supervisor to the supervisors table"""
    conn.execute(
        "INSERT OR IGNORE INTO supervisors (supervisor_name) VALUES (?)", (supervisor_name,)
    )
    conn.commit()

def add_supervisor_with_bootstrap(conn: sqlite3.Connection, supervisor_name: str, initiated_by: str) -> None:
    """Add a new supervisor, allowing the first one to be added without authorization."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        require_supervisor_or_bootstrap(conn, initiated_by)
        add_supervisor(conn, supervisor_name)

def remove_supervisor(conn: sqlite3.Connection, supervisor_name: str) -> None:
    """Remove a supervisor from the supervisors table"""
    conn.execute(
        "DELETE FROM supervisors WHERE supervisor_name = ?", (supervisor_name,)
    )
    conn.commit()

def remove_supervisor_with_lock(conn: sqlite3.Connection, supervisor_name: str, initiated_by: str) -> None:
    """Remove a supervisor, requiring authorization from another supervisor."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        require_supervisor(conn, initiated_by)
        remove_supervisor(conn, supervisor_name)