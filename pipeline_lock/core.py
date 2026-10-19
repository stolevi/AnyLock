import sqlite3
from datetime import datetime, timedelta, timezone
from pipeline_lock.models import Lock, LockEvent

DEFAULT_LOCK_DURATION = timedelta(hours=8)  # Default lock duration of 8 hours

class LockConflictError(Exception):
    """Raised when trying to acquire a resource that's already 
    locked by someone else."""

class LockNotOwnedError(Exception):
    """Raised when trying to release a resource that's not owned 
    by the current owner."""

class ResourceNotLockedError(Exception):
    """Raised when an operation requires a lock, but the resource 
    is not locked."""

def _row_to_lock(row: sqlite3.Row) -> Lock:
    """Convert a raw database row into a Lock object."""
    return Lock(
        resource_id=row["resource_id"],
        owner=row["owner"],
        acquired_at=datetime.fromisoformat(row["acquired_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
    )

def _row_to_history_event(row: sqlite3.Row) -> LockEvent:
    """Convert a raw database row into a LockEvent object."""
    return LockEvent(
        event_id=row["event_id"],
        resource_id=row["resource_id"],
        owner=row["owner"],
        event_type=row["event_type"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
    )

def _write_lock(conn: sqlite3.Connection, resource_id: str, owner: str, duration: timedelta | None = None) -> Lock | None:
    """Helper function to write a lock to the database. Used by both 
    acquire_lock and refresh_lock to avoid code duplication."""
    now = datetime.now(timezone.utc)
    actual_duration = duration if duration is not None else DEFAULT_LOCK_DURATION
    new_lock = Lock(
        resource_id=resource_id,
        owner=owner,
        acquired_at=now,
        expires_at=now + actual_duration,
    )
    cursor = conn.execute(
        """
        INSERT INTO locks (resource_id, owner, acquired_at, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(resource_id) DO UPDATE SET
            owner = excluded.owner,
            acquired_at = excluded.acquired_at,
            expires_at = excluded.expires_at
        WHERE locks.owner = excluded.owner OR locks.expires_at <= excluded.acquired_at
        """,
        (new_lock.resource_id, new_lock.owner, new_lock.acquired_at.isoformat(), new_lock.expires_at.isoformat()),
    )
    if cursor.rowcount == 0:
        return None  # Lock was not acquired because it was held by someone else        
    return new_lock

def _write_to_history(conn: sqlite3.Connection, resource_id: str, owner:str, event_type: str, timestamp: datetime) -> None:
    """write lock events to lock_history."""
    conn.execute(
        """
        INSERT INTO lock_history (resource_id, owner, event_type, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (resource_id, owner, event_type, timestamp.isoformat())      
    )

def _lock_information_on_resource(conn: sqlite3.Connection, resource_id: str) -> Lock | None:
    """Return the current Lock for a resource, even if it's expired. 
    Returns None if the resource was released or never locked at all."""
    row = conn.execute(
        "SELECT * FROM locks WHERE resource_id = ?", (resource_id,)
    ).fetchone()
    if row is None:
        return None
    lock = _row_to_lock(row)
    return lock  # Return the lock even if it's expired, for informational purposes

def check_status(conn: sqlite3.Connection, resource_id: str) -> Lock | None:
    """Return the current Lock for a resource, or None if it's unlocked 
    (or the lock has expired)."""
    row = conn.execute(
        "SELECT * FROM locks WHERE resource_id = ?", (resource_id,)
    ).fetchone()
    if row is None:
        return None
    lock = _row_to_lock(row)
    if lock.is_expired():
        return None  # Treat expired locks as unlocked
    return lock

def acquire_lock(conn: sqlite3.Connection, resource_id: str, owner: str, duration: timedelta | None = None) -> Lock:
    """Acquire a lock on a resource. raises LockConflictError if someone 
    else already holds it."""
    with conn:
        old_lock = _lock_information_on_resource(conn, resource_id)  # Check for existing lock, even if expired
        lock = _write_lock(conn, resource_id, owner, duration)
        if lock is None:
            existing = check_status(conn, resource_id)
            if existing is not None:
                raise LockConflictError(f"{resource_id} is already locked by {existing.owner}.")
            lock = _write_lock(conn, resource_id, owner, duration)
            if lock is None:
                raise LockConflictError(f"{resource_id} was briefly contested, please try again.")
        if old_lock is not None and old_lock.is_expired():
            _write_to_history(conn, resource_id, old_lock.owner, "expired", timestamp=old_lock.expires_at)
        _write_to_history(conn, resource_id, owner, "acquire", lock.acquired_at)
        return lock
   
def refresh_lock(conn: sqlite3.Connection, resource_id: str, owner: str, duration: timedelta | None = None) -> Lock:
    """Extend the lease of an existing lock by 'owner'. Raises 
    ResourceNotLockedError if the resource is not currently locked or 
    LockNotOwnedError if the lock is held by someone else."""
    with conn:
        existing = check_status(conn, resource_id)
        if existing is None:
            raise ResourceNotLockedError(f"{resource_id} is not currently locked.")
        if existing.owner != owner:
            raise LockNotOwnedError(f"{resource_id} is locked by {existing.owner}, not {owner}.")
        lock = _write_lock(conn, resource_id, owner, duration)
        if lock is None:
            current = check_status(conn, resource_id)
            if current is not None:
                raise LockNotOwnedError(f"{resource_id} is now locked by {current.owner}, not {owner}.")
            raise LockNotOwnedError(f"{resource_id} is no longer owned by {owner}.")
        _write_to_history(conn, resource_id, owner, "refresh", lock.acquired_at)
        return lock

def release_lock(conn: sqlite3.Connection, resource_id: str, owner: str) -> None:
    """Release a lock on a resource. Raises LockNotOwnedError if 
    the lock is held by someone else. No-op if the resource isn't locked."""
    with conn:
        existing = check_status(conn, resource_id)
        if existing is None:
            return  # No lock to release
        if existing.owner != owner:
            raise LockNotOwnedError(f"{resource_id} is locked by {existing.owner}, not {owner}.")
        cursor = conn.execute("DELETE FROM locks WHERE resource_id = ? AND owner = ?", (resource_id, owner))
        timestamp = datetime.now(timezone.utc)
        if cursor.rowcount == 0:
            raise LockNotOwnedError(f"{resource_id} is no longer owned by {owner}.")
        _write_to_history(conn, resource_id, owner, "release", timestamp)

def force_release_lock(conn: sqlite3.Connection, resource_id: str) -> Lock | None:
    """Forcefully release a lock. Use with caution!"""
    with conn:    
        cursor = conn.execute("DELETE FROM locks WHERE resource_id = ? RETURNING *", (resource_id,))
        old_lock = cursor.fetchone()  # Fetch the deleted row to ensure the operation succeeded
        if old_lock is None:
            return None  # No lock was present to release
        existing = _row_to_lock(old_lock)  
        timestamp = datetime.now(timezone.utc)    
        _write_to_history(conn, resource_id, existing.owner, "force_release", timestamp)
        return existing

def list_active_locks(conn: sqlite3.Connection) -> list[Lock]:
    """Return a list of all currently active locks."""
    rows = conn.execute(
        """
        SELECT * FROM locks ORDER BY expires_at ASC,
        resource_id ASC
        """
        ).fetchall()
    active_locks = []
    for row in rows:
        lock = _row_to_lock(row)
        if not lock.is_expired():
            active_locks.append(lock)
    return active_locks

def get_resource_history(conn: sqlite3.Connection, resource_id: str) -> list[LockEvent]:
    """Return a list of events for a resource."""
    rows = conn.execute(
        """
        SELECT * FROM lock_history WHERE resource_id = ?
        ORDER BY timestamp DESC
        """, (resource_id,)
        ).fetchall()
    events = []
    for row in rows:
        event = _row_to_history_event(row)
        events.append(event)
    return events