import sqlite3


class NotAuthorizedError(Exception):
    """Raised when the user is not an authorized admin."""

class LastAdminError(Exception):
    """Raised when removing an admin would leave no admins at all."""

def _admins_empty(conn: sqlite3.Connection) -> bool:
    """Check if the admins table is empty."""
    row = conn.execute("SELECT 1 FROM admins LIMIT 1").fetchone()
    return row is None

def is_admin(conn: sqlite3.Connection, admin_name: str) -> bool:
    """Check if a given name is in the admins table."""
    row = conn.execute(
        "SELECT 1 FROM admins WHERE admin_name = ?", (admin_name,)
    ).fetchone()
    return row is not None

def _admin_count(conn: sqlite3.Connection) -> int:
    """Count the admins in the admins table."""
    return conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]

def require_admin_or_bootstrap(conn: sqlite3.Connection, initiated_by: str) -> None:
    """Trigger require_admin if the admins table is not empty."""
    if _admins_empty(conn):
        return
    require_admin(conn, initiated_by)

def require_admin(conn: sqlite3.Connection, admin_name: str) -> None:
    """Raise NotAuthorizedError if the given name is not an admin."""
    if not is_admin(conn, admin_name):
        raise NotAuthorizedError(f"{admin_name} is not on the list of admins.")

def add_admin(conn: sqlite3.Connection, admin_name: str) -> None:
    """Add a new admin to the admins table"""
    conn.execute(
        "INSERT OR IGNORE INTO admins (admin_name) VALUES (?)", (admin_name,)
    )
    conn.commit()

def add_admin_with_bootstrap(conn: sqlite3.Connection, admin_name: str, initiated_by: str) -> None:
    """Add a new admin, allowing the first one to be added without authorization."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        require_admin_or_bootstrap(conn, initiated_by)
        add_admin(conn, admin_name)

def remove_admin(conn: sqlite3.Connection, admin_name: str) -> None:
    """Remove an admin from the admins table"""
    conn.execute(
        "DELETE FROM admins WHERE admin_name = ?", (admin_name,)
    )
    conn.commit()

def remove_admin_with_lock(conn: sqlite3.Connection, admin_name: str, initiated_by: str) -> None:
    """Remove an admin, requiring authorization from an admin.
    Refuses to remove the last admin, so the bootstrap can never reopen."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        require_admin(conn, initiated_by)
        if is_admin(conn, admin_name) and _admin_count(conn) <= 1:
            raise LastAdminError(f"{admin_name} is the last admin and can't be removed. Add another admin first.")
        remove_admin(conn, admin_name)