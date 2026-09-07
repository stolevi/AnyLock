import sqlite3
from datetime import datetime, timedelta, timezone

from pipeline_lock.models import Lock

DEFAULT_LOCK_DURATION = timedelta(minutes=30)  # Default lock duration of 30 minutes

class LockConflictError(Exception):
    """raised when trying to acquire a resource that's already locked by someone else."""

class LockNotOwnedError(Exception):
    """raised when trying to release a resource that's not owned by the current owner."""

class ResourceNotLockedError(Exception):
    """raised when an operation requires a lock, but the resource is not locked."""

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

def _write_lock(conn: sqlite3.Connection, resource_id: str, owner: str, duration: timedelta | None = None) -> Lock:
    """Helper function to write a lock to the database. Used by both acquire_lock and refresh_lock to avoid code duplication."""
    now = datetime.now(timezone.utc)
    actual_duration = duration if duration is not None else DEFAULT_LOCK_DURATION
    new_lock = Lock(
        resource_id=resource_id,
        owner=owner,
        acquired_at=now,
        expires_at=now + actual_duration,
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

def acquire_lock(conn: sqlite3.Connection, resource_id: str, owner: str, duration: timedelta | None = None) -> Lock:
    """Acquire a lock on a resource. raises LockConflictError if someone else already holds it."""
    existing = check_status(conn, resource_id)
    if existing is not None and existing.owner != owner:
        raise LockConflictError(
            f"{resource_id} is already locked by {existing.owner} until {existing.expires_at}"
        )
    return _write_lock(conn, resource_id, owner, duration)
   
def refresh_lock(conn: sqlite3.Connection, resource_id: str, owner: str, duration: timedelta | None = None) -> Lock:
    """Extend the lease of an existing lock by 'owner'. Raises ResourceNotLockedError if the resource is not currently locked or LockNotOwnedError if the lock is held by someone else."""
    existing = check_status(conn, resource_id)
    if existing is None:
        raise ResourceNotLockedError(f"{resource_id} is not currently locked.")
    if existing.owner != owner:
        raise LockNotOwnedError(f"{resource_id} is locked by {existing.owner}, not {owner}.")
    return _write_lock(conn, resource_id, owner, duration)

def release_lock(conn: sqlite3.Connection, resource_id: str, owner: str) -> None:
    """Release a lock on a resource. Raises LockNotOwnedError if the lock is held by someone else. No-op if the resource isn't locked."""

    existing = check_status(conn, resource_id)

    if existing is None:
        return  # No lock to release

    if existing.owner != owner:
        raise LockNotOwnedError(f"{resource_id} is locked by {existing.owner}, not {owner}.")

    conn.execute("DELETE FROM locks WHERE resource_id = ?", (resource_id,))
    conn.commit()

def force_release_lock(conn: sqlite3.Connection, resource_id: str) -> Lock | None:
    """Forcefully release a lock. Use with caution!"""
    existing = check_status(conn, resource_id)
    if existing is None:
        return None  # No lock to release
    conn.execute("DELETE FROM locks WHERE resource_id = ?", (resource_id,))
    conn.commit()
    return existing


def list_active_locks(conn: sqlite3.Connection) -> list[Lock]:
    """return a list of all currently active locks"""
    rows = conn.execute("SELECT * FROM locks").fetchall()
    active_locks = []

    for row in rows:
        lock = _row_to_lock(row)
        if not lock.is_expired():
            active_locks.append(lock)

    return active_locks