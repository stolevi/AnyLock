import sqlite3
from datetime import datetime, timedelta, timezone

from pipeline_lock.models import Lock

DEFAULT_LOCK_DURATION = timedelta(minutes=30)  # Default lock duration of 30 minutes

class LockConflictError(Exception):
    """raised when trying to acquire a resource that's already locked by someone else."""

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

def acquire_lock(conn: sqlite3.Connection, resource_id: str, owner: str) -> Lock:
    """Acquire a lock on a resource. raises LockConflictError if someone else already holds it."""
    existing = check_status(conn, resource_id)

    if existing is not None and existing.owner != owner:
        raise LockConflictError(
            f"{resource_id} is already locked by {existing.owner} until {existing.expires_at}"
        )

    now = datetime.now(timezone.utc)
    new_lock = Lock(
        resource_id=resource_id,
        owner=owner,
        acquired_at=now,
        expires_at=now + DEFAULT_LOCK_DURATION,
    )

    conn.execute(
        """
        INSERT INTO locks (resource_id, owner, acquired_at, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(resource_id) DO UPDATE SET
            owner = excluded.owner,
            acquired_at = excluded.acquired_at,
            expires_at = excluded.expires_at
        """,
        (new_lock.resource_id, new_lock.owner, new_lock.acquired_at.isoformat(), new_lock.expires_at.isoformat()),
    )
    conn.commit()

    return new_lock
    