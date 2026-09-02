import sqlite3
from datetime import datetime

from pipeline_lock.models import Lock

def _row_to_lock(row: sqlite3.Row) -> Lock:
    """Convert a raw database row into a Lock object."""
    return Lock(
        resource_id=row["resource_id"],
        owner=row["owner"],
        acquired_at=datetime.fromisoformat(row["acquired_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
    )

def check_status(conn: sqlite3.Connection, resource_id: str) -> Lock | None:
    """return the current Lock for a resource, or None if it's unlocked (or the lock has expired.)"""
    row = conn.execute(
        "SELECT * FROM locks WHERE resource_id = ?", (resource_id,)
    ).fetchone()

    if row is None:
        return None

    lock = _row_to_lock(row)
    if lock.is_expired():
        return None  # Treat expired locks as unlocked

    return lock