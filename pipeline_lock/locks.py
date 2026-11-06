import sqlite3
from datetime import UTC, datetime, timedelta

from pipeline_lock.models import Lock, LockEvent, ResourceRef

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
        project_id=row["project_id"],
        resource_path=row["resource_path"],
        owner=row["owner"],
        acquired_at=datetime.fromisoformat(row["acquired_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]),
    )

def _row_to_history_event(row: sqlite3.Row) -> LockEvent:
    """Convert a raw database row into a LockEvent object."""
    return LockEvent(
        event_id=row["event_id"],
        project_id=row["project_id"],
        resource_path=row["resource_path"],
        owner=row["owner"],
        event_type=row["event_type"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
    )

def _write_lock(conn: sqlite3.Connection, ref: ResourceRef, owner: str, duration: timedelta | None = None, acquired_at: datetime | None = None) -> Lock | None:
    """Helper function to write a lock to the database. Used by both 
    acquire_lock and refresh_lock to avoid code duplication."""
    now = datetime.now(UTC)
    actual_duration = duration if duration is not None else DEFAULT_LOCK_DURATION
    actual_acquired_at = acquired_at if acquired_at is not None else now
    new_lock = Lock(
        project_id=ref.project_id,
        resource_path=ref.resource_path,
        owner=owner,
        acquired_at=actual_acquired_at,
        expires_at=now + actual_duration,
    )
    cursor = conn.execute(
        """
        INSERT INTO locks (project_id, resource_path, owner, acquired_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(project_id, resource_path) DO UPDATE SET
            owner = excluded.owner,
            acquired_at = excluded.acquired_at,
            expires_at = excluded.expires_at
        WHERE locks.owner = excluded.owner OR locks.expires_at <= excluded.acquired_at
        """,
        (new_lock.project_id, new_lock.resource_path, new_lock.owner, new_lock.acquired_at.isoformat(), new_lock.expires_at.isoformat()),
    )
    if cursor.rowcount == 0:
        return None  # Lock was not acquired because it was held by someone else        
    return new_lock

def _write_to_history(conn: sqlite3.Connection, ref: ResourceRef, owner:str, event_type: str, timestamp: datetime) -> None:
    """write lock events to lock_history."""
    conn.execute(
        """
        INSERT INTO lock_history (project_id, resource_path, owner, event_type, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ref.project_id, ref.resource_path, owner, event_type, timestamp.isoformat())      
    )

def _lock_information_on_resource(conn: sqlite3.Connection, ref: ResourceRef) -> Lock | None:
    """Return the current Lock for a resource, even if it's expired. 
    Returns None if the resource was released or never locked at all."""
    row = conn.execute(
        "SELECT * FROM locks WHERE project_id = ? AND resource_path = ?", (ref.project_id, ref.resource_path)
    ).fetchone()
    if row is None:
        return None
    lock = _row_to_lock(row)
    return lock  # Return the lock even if it's expired, for informational purposes

def check_status(conn: sqlite3.Connection, ref: ResourceRef) -> Lock | None:
    """Return the current Lock for a resource, or None if it's unlocked 
    (or the lock has expired)."""
    lock = _lock_information_on_resource(conn, ref)
    if lock is None or lock.is_expired():
        return None
    return lock

def acquire_lock(conn: sqlite3.Connection, ref: ResourceRef, owner: str, duration: timedelta | None = None) -> Lock:
    """Acquire a lock on a resource. raises LockConflictError if someone 
    else already holds it."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")  # Start a transaction to prevent race conditions
        old_lock = _lock_information_on_resource(conn, ref)  # Check for existing lock, even if expired
        lock = _write_lock(conn, ref, owner, duration)
        if lock is None:
            existing = check_status(conn, ref)
            if existing is not None:
                raise LockConflictError(f"{ref.resource_path} is already locked by {existing.owner}.")
            lock = _write_lock(conn, ref, owner, duration)
            if lock is None:
                raise LockConflictError(f"{ref.resource_path} was briefly contested, please try again.")
        if old_lock is not None and old_lock.is_expired():
            _write_to_history(conn, ref, old_lock.owner, "expired", timestamp=old_lock.expires_at)
        _write_to_history(conn, ref, owner, "acquire", lock.acquired_at)
        return lock
   
def refresh_lock(conn: sqlite3.Connection, ref: ResourceRef, owner: str, duration: timedelta | None = None) -> Lock:
    """Extend the lease of an existing lock by 'owner'. Raises 
    ResourceNotLockedError if the resource is not currently locked or 
    LockNotOwnedError if the lock is held by someone else."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")  # Start a transaction to prevent race conditions
        existing = check_status(conn, ref)
        if existing is None:
            raise ResourceNotLockedError(f"{ref.resource_path} is not currently locked.")
        if existing.owner != owner:
            raise LockNotOwnedError(f"{ref.resource_path} is locked by {existing.owner}, not {owner}.")
        lock = _write_lock(conn, ref, owner, duration, acquired_at=existing.acquired_at)
        if lock is None:
            current = check_status(conn, ref)
            if current is not None:
                raise LockNotOwnedError(f"{ref.resource_path} is now locked by {current.owner}, not {owner}.")
            raise LockNotOwnedError(f"{ref.resource_path} is no longer owned by {owner}.")
        _write_to_history(conn, ref, owner, "refresh", timestamp=datetime.now(UTC))
        return lock

def release_lock(conn: sqlite3.Connection, ref: ResourceRef, owner: str) -> None:
    """Release a lock on a resource. Raises LockNotOwnedError if 
    the lock is held by someone else. No-op if the resource isn't locked."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")  # Start a transaction to prevent race conditions
        existing = check_status(conn, ref)
        if existing is None:
            return  # No lock to release
        if existing.owner != owner:
            raise LockNotOwnedError(f"{ref.resource_path} is locked by {existing.owner}, not {owner}.")
        cursor = conn.execute(
            "DELETE FROM locks WHERE project_id = ? AND resource_path = ? AND owner = ?",
            (ref.project_id, ref.resource_path, owner),
        )
        timestamp = datetime.now(UTC)
        if cursor.rowcount == 0:
            raise LockNotOwnedError(f"{ref.resource_path} is no longer owned by {owner}.")
        _write_to_history(conn, ref, owner, "release", timestamp)

def force_release_lock(conn: sqlite3.Connection, ref: ResourceRef) -> Lock | None:
    """Forcefully release a lock. Use with caution!"""
    with conn:    
        conn.execute("BEGIN IMMEDIATE")  # Start a transaction to prevent race conditions
        cursor = conn.execute(
            "DELETE FROM locks WHERE project_id = ? AND resource_path = ? RETURNING *",
            (ref.project_id, ref.resource_path),
        )
        old_lock = cursor.fetchone()  # Fetch the deleted row to ensure the operation succeeded
        if old_lock is None:
            return None  # No lock was present to release
        existing = _row_to_lock(old_lock)  
        timestamp = datetime.now(UTC)    
        _write_to_history(conn, ref, existing.owner, "force_release", timestamp)
        return existing

def list_active_locks(conn: sqlite3.Connection) -> list[Lock]:
    """Return a list of all currently active locks."""
    rows = conn.execute(
        """
        SELECT * FROM locks ORDER BY expires_at ASC,
        resource_path ASC
        """
        ).fetchall()
    active_locks = []
    for row in rows:
        lock = _row_to_lock(row)
        if not lock.is_expired():
            active_locks.append(lock)
    return active_locks

def get_resource_history(conn: sqlite3.Connection, ref: ResourceRef) -> list[LockEvent]:
    """Return a list of events for a resource."""
    rows = conn.execute(
        """
        SELECT * FROM lock_history WHERE project_id = ? AND resource_path = ?
        ORDER BY timestamp DESC
        """, (ref.project_id, ref.resource_path)
        ).fetchall()
    events = []
    for row in rows:
        event = _row_to_history_event(row)
        events.append(event)
    return events