import pytest
from pipeline_lock.core import check_status, acquire_lock, refresh_lock, release_lock, force_release_lock, list_active_locks, get_resource_history, LockConflictError, LockNotOwnedError, ResourceNotLockedError
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

def test_acquire_writes_expired_lock_to_history(conn):
    old_lock = acquire_lock(conn, "resource_id", "old_owner", duration=timedelta(hours=-1))
    new_lock = acquire_lock(conn, "resource_id", "new_owner")
    resource_history = get_resource_history(conn, "resource_id")
    assert len(resource_history) == 3
    assert resource_history[0].event_type == "acquire"
    assert resource_history[1].event_type == "acquire"
    assert resource_history[2].event_type == "expired"
    assert resource_history[0].owner == "new_owner"
    assert resource_history[1].owner == "old_owner"
    assert resource_history[2].owner == "old_owner"

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

def test_refresh_lock_preserves_acquired_at(conn):
    original = acquire_lock(conn, "resource_id", "owner", duration=timedelta(hours=1))
    refreshed = refresh_lock(conn, "resource_id", "owner", duration=timedelta(hours=2))
    assert refreshed.acquired_at == original.acquired_at
    assert refreshed.expires_at > original.expires_at

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

def test_force_release_lock_records_history_event(conn):
    acquire_lock(conn, "SQ01_SH010", "Levi", duration=timedelta(hours=1))
    force_release_lock(conn, "SQ01_SH010")
    resource_history = get_resource_history(conn, "SQ01_SH010")
    assert len(resource_history) == 2
    type_of_event = []
    for event in resource_history:
        type_of_event.append(event.event_type)
    assert type_of_event[0] == "force_release"
    assert resource_history[0].owner == "Levi"
    
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

def test_get_resource_history_empty(conn):
    resource_history = get_resource_history(conn, "SQ01_SH010")
    assert resource_history == []

def test_get_resource_history_returns_events_in_order(conn):
    acquire_lock(conn, "SQ01_SH010", "Levi", duration=timedelta(hours=8))
    refresh_lock(conn, "SQ01_SH010", "Levi", duration=timedelta(days=5))
    release_lock(conn, "SQ01_SH010", "Levi")
    resource_history = get_resource_history(conn, "SQ01_SH010")
    event_types = []
    for event in resource_history:
        event_types.append(event.event_type)
    assert event_types == ["release", "refresh", "acquire"]
    
def test_get_resource_history_multiple_resources(conn):
    acquire_lock(conn, "SQ01_SH010", "Levi", duration=timedelta(hours=1))
    acquire_lock(conn, "SQ02_SH020", "levi", duration=timedelta(hours=2))
    resource_history_1 = get_resource_history(conn, "SQ01_SH010") 
    resource_history_2 = get_resource_history(conn, "SQ02_SH020")
    assert len(resource_history_1) == 1
    assert resource_history_1[0].resource_id == "SQ01_SH010"
    assert len(resource_history_2) == 1
    assert resource_history_2[0].resource_id == "SQ02_SH020"
