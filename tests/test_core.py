import pytest
from pipeline_lock.db import get_connection
from pipeline_lock.core import check_status, acquire_lock, refresh_lock, release_lock, force_release_lock, list_active_locks, LockConflictError, LockNotOwnedError, ResourceNotLockedError
from datetime import datetime, timezone, timedelta

@pytest.fixture
def conn():
    """Provide a fresh in-memory database connection for each test."""
    conn = get_connection(":memory:")
    yield conn
    conn.close()

def test_acquire_lock(conn):
    lock = acquire_lock(conn, "resource_id", "owner")
    assert lock.resource_id == "resource_id"
    assert lock.owner == "owner"
    assert lock.expires_at > datetime.now(timezone.utc)
    assert check_status(conn, "resource_id") == lock

def test_acquire_lock_conflict(conn):
    acquire_lock(conn, "resource_id", "owner")
    with pytest.raises(LockConflictError):
        acquire_lock(conn, "resource_id", "another_owner")
    assert check_status(conn, "resource_id").owner == "owner"

def test_release_lock(conn):
    acquire_lock(conn, "resource_id", "owner")
    release_lock(conn, "resource_id", "owner")
    assert check_status(conn, "resource_id") is None

def test_release_lock_not_owned(conn):
    lock = acquire_lock(conn, "resource_id",  "owner")
    with pytest.raises(LockNotOwnedError):
        release_lock(conn, "resource_id", "another_owner")
    assert check_status(conn, "resource_id") == lock

def test_release_lock_noop(conn):
    release_lock(conn, "resource_id", "owner")
    assert check_status(conn, "resource_id") is None

def test_refresh_lock(conn):
    lock = acquire_lock(conn, "resource_id", "owner", duration=timedelta(hours=1))
    fresh_lock = refresh_lock(conn, "resource_id", "owner", duration=timedelta(hours=2))
    assert fresh_lock.expires_at > lock.expires_at
    assert fresh_lock.owner == lock.owner
    assert fresh_lock.resource_id == lock.resource_id

def test_refresh_resource_not_locked_error(conn):
    with pytest.raises(ResourceNotLockedError):
        refresh_lock(conn, "resource_id", "owner")
    assert check_status(conn, "resource_id") is None

def test_refresh_lock_not_owned_error(conn):
    lock = acquire_lock(conn, "resource_id", "owner")
    with pytest.raises(LockNotOwnedError):
        refresh_lock(conn, "resource_id", "another_owner")
    assert check_status(conn, "resource_id") == lock

def test_force_release_lock(conn):
    lock = acquire_lock(conn, "resource_id", "owner")
    released_lock = force_release_lock(conn, "resource_id")
    assert check_status(conn, "resource_id") is None
    assert released_lock == lock

def test_force_release_lock_noop(conn):
    released_lock  = force_release_lock(conn, "resource_id")
    assert check_status(conn, "resource_id") is None
    assert released_lock is None

def test_list_active_locks_empty(conn):
    active_locks = list_active_locks(conn)
    assert active_locks == []