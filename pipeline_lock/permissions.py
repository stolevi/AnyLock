import sqlite3

def is_supervisor(conn: sqlite3.Connection, supervisor_name: str) -> bool:
    """Check if a given name is in the supervisors table."""
    row = conn.execute(
        "SELECT 1 FROM supervisors WHERE supervisor_name = ?", (supervisor_name,)
    ).fetchone()
    return row is not None

def add_supervisor(conn: sqlite3.Connection, supervisor_name: str) -> None:
    """Add a new supervisor to the supervisors table"""
    conn.execute(
        "INSERT OR IGNORE INTO supervisors (supervisor_name) VALUES (?)", (supervisor_name,)
    )
    conn.commit()

def remove_supervisor(conn: sqlite3.Connection, supervisor_name: str) -> None:
    """remove a supervisor from the supervisors table"""
    conn.execute(
        "DELETE FROM supervisors WHERE supervisor_name = ?", (supervisor_name,)
    )
    conn.commit()