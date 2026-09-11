import pytest
from pipeline_lock.core import check_status, acquire_lock, refresh_lock, release_lock, force_release_lock, list_active_locks, LockConflictError, LockNotOwnedError, ResourceNotLockedError
from datetime import datetime, timezone, timedelta

def test_check_status_lock_not_existing(conn):
    assert check_status(conn, "resource_id") is None

def test_check_status_lock_active(conn):
    lock = acquire_lock(conn, "resource_id", "owner")
    assert check_status(conn, "resource_id") == lock

def test_check_status_lock_expired(conn):
    acquire_lock(conn, "resource_id", "owner", duration=timedelta(hours=-1))
    assert check_status(conn, "resource_id") is None

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

def test_list_active_locks_returns_all_active(conn):
    lock_1 = acquire_lock(conn, "SQ01_SH070", "Levi", duration=timedelta(hours=5))
    lock_2 = acquire_lock(conn, "SQ07_SH010", "Sarah", duration=timedelta(hours=8))
    lock_3 = acquire_lock(conn, "SQ04_SH050", "Camiel", duration=timedelta(minutes=45))
    lock_4 = acquire_lock(conn, "SQ03_SH090", "Karolien", duration=timedelta(days=7))
    lock_5 = acquire_lock(conn, "SQ06_SH030", "Neyrouz", duration=timedelta(hours=23))
    active_locks = list_active_locks(conn)
    assert active_locks == [lock_3, lock_1, lock_2, lock_5, lock_4]
    
def test_list_active_locks_filters_expired(conn):
    lock_1 = acquire_lock(conn, "SQ01_SH070", "Levi", duration=timedelta(hours=-5))
    lock_2 = acquire_lock(conn, "SQ07_SH010", "Sarah", duration=timedelta(hours=8))
    lock_3 = acquire_lock(conn, "SQ04_SH050", "Camiel", duration=timedelta(minutes=45))
    lock_4 = acquire_lock(conn, "SQ03_SH090", "Karolien", duration=timedelta(days=-7))
    lock_5 = acquire_lock(conn, "SQ06_SH030", "Neyrouz", duration=timedelta(hours=23))
    active_locks = list_active_locks(conn)
    assert lock_2 in active_locks
    assert lock_3 in active_locks
    assert lock_5 in active_locks
    assert lock_1 not in active_locks
    assert lock_4 not in active_locks
    

