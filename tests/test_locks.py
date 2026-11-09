from datetime import UTC, datetime, timedelta

import pytest

from pipeline_lock.adapters.mock import MockAdapter
from pipeline_lock.locks import (
    LockConflictError,
    LockNotOwnedError,
    ResourceNotFoundError,
    ResourceNotLockedError,
    acquire_lock,
    acquire_with_registration,
    check_status,
    force_release_lock,
    get_resource_history,
    list_active_locks,
    refresh_lock,
    release_lock,
)
from pipeline_lock.models import ResourceRef, StorageType
from pipeline_lock.projects import (
    create_project,
    is_resource_registered,
    register_resource,
)


def _register(conn, project_id: int, resource_path: str) -> ResourceRef:
    """Build a ResourceRef in an existing project and register it, so it can be locked."""
    ref = ResourceRef(project_id=project_id, resource_path=resource_path)
    register_resource(conn, ref, "Levi")
    return ref


def _same_path_in_second_project(conn, ref: ResourceRef) -> ResourceRef:
    """Create a second project ("Drijf") and register the same path in it.
    Relies on the admin "Levi" that the project fixture already added."""
    drijf = create_project(conn, "Drijf", StorageType.FILE_SYSTEM, "/drijf", "Levi")
    return _register(conn, drijf.project_id, ref.resource_path)


# --- check_status ---

def test_check_status_lock_not_existing(conn, ref):
    assert check_status(conn, ref) is None

def test_check_status_lock_active(conn, ref):
    lock = acquire_lock(conn, ref, "owner")
    assert check_status(conn, ref) == lock

def test_check_status_lock_expired(conn, ref):
    acquire_lock(conn, ref, "owner", duration=timedelta(hours=-1))
    assert check_status(conn, ref) is None


# --- acquire ---

def test_acquire_lock(conn, ref):
    lock = acquire_lock(conn, ref, "owner")
    assert lock.project_id == ref.project_id
    assert lock.resource_path == ref.resource_path
    assert lock.owner == "owner"
    assert lock.expires_at > datetime.now(UTC)
    assert check_status(conn, ref) == lock

def test_acquire_lock_conflict(conn, ref):
    acquire_lock(conn, ref, "owner")
    with pytest.raises(LockConflictError):
        acquire_lock(conn, ref, "another_owner")
    assert check_status(conn, ref).owner == "owner"

def test_acquire_writes_expired_lock_to_history(conn, ref):
    old_lock = acquire_lock(conn, ref, "old_owner", duration=timedelta(hours=-1))
    new_lock = acquire_lock(conn, ref, "new_owner")
    resource_history = get_resource_history(conn, ref)
    assert len(resource_history) == 3
    assert resource_history[0].event_type == "acquire"
    assert resource_history[1].event_type == "acquire"
    assert resource_history[2].event_type == "expired"
    assert resource_history[0].owner == "new_owner"
    assert resource_history[1].owner == "old_owner"
    assert resource_history[2].owner == "old_owner"
    assert old_lock.expires_at == resource_history[2].timestamp
    assert new_lock.acquired_at == resource_history[0].timestamp


# --- refresh ---

def test_refresh_lock(conn, ref):
    lock = acquire_lock(conn, ref, "owner", duration=timedelta(hours=1))
    fresh_lock = refresh_lock(conn, ref, "owner", duration=timedelta(hours=2))
    assert fresh_lock.expires_at > lock.expires_at
    assert fresh_lock.owner == lock.owner
    assert fresh_lock.resource_path == lock.resource_path
    assert fresh_lock.project_id == lock.project_id

def test_refresh_resource_not_locked_error(conn, ref):
    with pytest.raises(ResourceNotLockedError):
        refresh_lock(conn, ref, "owner")
    assert check_status(conn, ref) is None

def test_refresh_lock_not_owned_error(conn, ref):
    lock = acquire_lock(conn, ref, "owner")
    with pytest.raises(LockNotOwnedError):
        refresh_lock(conn, ref, "another_owner")
    assert check_status(conn, ref) == lock

def test_refresh_lock_preserves_acquired_at(conn, ref):
    original = acquire_lock(conn, ref, "owner", duration=timedelta(hours=1))
    refreshed = refresh_lock(conn, ref, "owner", duration=timedelta(hours=2))
    assert refreshed.acquired_at == original.acquired_at
    assert refreshed.expires_at > original.expires_at


# --- release ---

def test_release_lock(conn, ref):
    acquire_lock(conn, ref, "owner")
    release_lock(conn, ref, "owner")
    assert check_status(conn, ref) is None

def test_release_lock_not_owned(conn, ref):
    lock = acquire_lock(conn, ref, "owner")
    with pytest.raises(LockNotOwnedError):
        release_lock(conn, ref, "another_owner")
    assert check_status(conn, ref) == lock

def test_release_lock_noop(conn, ref):
    release_lock(conn, ref, "owner")
    assert check_status(conn, ref) is None


# --- force release ---

def test_force_release_lock(conn, ref):
    lock = acquire_lock(conn, ref, "owner")
    released_lock = force_release_lock(conn, ref)
    assert check_status(conn, ref) is None
    assert released_lock == lock

def test_force_release_lock_noop(conn, ref):
    released_lock = force_release_lock(conn, ref)
    assert check_status(conn, ref) is None
    assert released_lock is None

def test_force_release_lock_records_history_event(conn, ref):
    acquire_lock(conn, ref, "Levi", duration=timedelta(hours=1))
    force_release_lock(conn, ref)
    resource_history = get_resource_history(conn, ref)
    assert len(resource_history) == 2
    type_of_event = []
    for event in resource_history:
        type_of_event.append(event.event_type)
    assert type_of_event[0] == "force_release"
    assert resource_history[0].owner == "Levi"


# --- list_active_locks ---

def test_list_active_locks_empty(conn):
    active_locks = list_active_locks(conn)
    assert active_locks == []

def test_list_active_locks_returns_all_active(conn, project):
    ref_1 = _register(conn, project.project_id, "shots/SQ01_SH070")
    ref_2 = _register(conn, project.project_id, "shots/SQ07_SH010")
    ref_3 = _register(conn, project.project_id, "shots/SQ04_SH050")
    ref_4 = _register(conn, project.project_id, "shots/SQ03_SH090")
    ref_5 = _register(conn, project.project_id, "shots/SQ06_SH030")
    lock_1 = acquire_lock(conn, ref_1, "Levi", duration=timedelta(hours=5))
    lock_2 = acquire_lock(conn, ref_2, "Sarah", duration=timedelta(hours=8))
    lock_3 = acquire_lock(conn, ref_3, "Camiel", duration=timedelta(minutes=45))
    lock_4 = acquire_lock(conn, ref_4, "Karolien", duration=timedelta(days=7))
    lock_5 = acquire_lock(conn, ref_5, "Neyrouz", duration=timedelta(hours=23))
    active_locks = list_active_locks(conn)
    assert active_locks == [lock_3, lock_1, lock_2, lock_5, lock_4]

def test_list_active_locks_filters_expired(conn, project):
    ref_1 = _register(conn, project.project_id, "shots/SQ01_SH070")
    ref_2 = _register(conn, project.project_id, "shots/SQ07_SH010")
    ref_3 = _register(conn, project.project_id, "shots/SQ04_SH050")
    ref_4 = _register(conn, project.project_id, "shots/SQ03_SH090")
    ref_5 = _register(conn, project.project_id, "shots/SQ06_SH030")
    lock_1 = acquire_lock(conn, ref_1, "Levi", duration=timedelta(hours=-5))
    lock_2 = acquire_lock(conn, ref_2, "Sarah", duration=timedelta(hours=8))
    lock_3 = acquire_lock(conn, ref_3, "Camiel", duration=timedelta(minutes=45))
    lock_4 = acquire_lock(conn, ref_4, "Karolien", duration=timedelta(days=-7))
    lock_5 = acquire_lock(conn, ref_5, "Neyrouz", duration=timedelta(hours=23))
    active_locks = list_active_locks(conn)
    assert lock_2 in active_locks
    assert lock_3 in active_locks
    assert lock_5 in active_locks
    assert lock_1 not in active_locks
    assert lock_4 not in active_locks


# --- history ---

def test_get_resource_history_empty(conn, ref):
    resource_history = get_resource_history(conn, ref)
    assert resource_history == []

def test_get_resource_history_returns_events_in_order(conn, ref):
    acquire_lock(conn, ref, "Levi", duration=timedelta(hours=8))
    refresh_lock(conn, ref, "Levi", duration=timedelta(days=5))
    release_lock(conn, ref, "Levi")
    resource_history = get_resource_history(conn, ref)
    event_types = []
    for event in resource_history:
        event_types.append(event.event_type)
    assert event_types == ["release", "refresh", "acquire"]

def test_get_resource_history_multiple_resources(conn, ref):
    ref_2 = _register(conn, ref.project_id, "shots/SQ02_SH020")
    acquire_lock(conn, ref, "Levi", duration=timedelta(hours=1))
    acquire_lock(conn, ref_2, "levi", duration=timedelta(hours=2))
    resource_history_1 = get_resource_history(conn, ref)
    resource_history_2 = get_resource_history(conn, ref_2)
    assert len(resource_history_1) == 1
    assert resource_history_1[0].resource_path == ref.resource_path
    assert len(resource_history_2) == 1
    assert resource_history_2[0].resource_path == ref_2.resource_path


# --- the same path in two projects must stay independent ---

def test_same_path_can_be_locked_in_two_projects(conn, ref):
    other = _same_path_in_second_project(conn, ref)
    acquire_lock(conn, ref, "Levi")
    acquire_lock(conn, other, "Sarah")  # no LockConflictError: different project
    assert check_status(conn, ref).owner == "Levi"
    assert check_status(conn, other).owner == "Sarah"

def test_release_only_affects_its_own_project(conn, ref):
    other = _same_path_in_second_project(conn, ref)
    acquire_lock(conn, ref, "Levi")
    acquire_lock(conn, other, "Levi")
    release_lock(conn, ref, "Levi")
    assert check_status(conn, ref) is None
    assert check_status(conn, other).owner == "Levi"

def test_force_release_only_affects_its_own_project(conn, ref):
    other = _same_path_in_second_project(conn, ref)
    acquire_lock(conn, ref, "Levi")
    acquire_lock(conn, other, "Sarah")
    force_release_lock(conn, ref)
    assert check_status(conn, ref) is None
    assert check_status(conn, other).owner == "Sarah"
    other_events = [event.event_type for event in get_resource_history(conn, other)]
    assert "force_release" not in other_events

def test_history_is_kept_per_project(conn, ref):
    other = _same_path_in_second_project(conn, ref)
    acquire_lock(conn, ref, "Levi")
    acquire_lock(conn, other, "Sarah")
    history = get_resource_history(conn, ref)
    other_history = get_resource_history(conn, other)
    assert [event.owner for event in history] == ["Levi"]
    assert [event.owner for event in other_history] == ["Sarah"]
    assert history[0].project_id == ref.project_id
    assert other_history[0].project_id == other.project_id


# --- acquire_with_registration ---

def test_acquire_with_registration_known_resource_skips_adapter(conn, ref):
    adapter = MockAdapter(set()) # knows nothing: if it were asked, the lock would fail.
    lock = acquire_with_registration(conn, adapter, ref, "Levi")
    assert lock.resource_path == ref.resource_path

def test_acquire_with_registration_adds_resource_the_adapter_knows(conn, project):
    new = ResourceRef(project.project_id, "shots/SQ01_SH010")
    adapter = MockAdapter({"shots/SQ01_SH010"})
    acquire_with_registration(conn, adapter, new, "Levi")
    assert is_resource_registered(conn, new) is True
    assert check_status(conn, new).owner == "Levi"

def test_acquire_with_registration_unknown_resource_raises(conn, project):
    unknown = ResourceRef(project.project_id, "shots/SQ05_SH050")
    adapter = MockAdapter(set())
    with pytest.raises(ResourceNotFoundError):
        acquire_with_registration(conn, adapter, unknown, "Levi")
    assert is_resource_registered(conn, unknown) is False # nothing half-done left behind
    assert check_status(conn, unknown) is None

def test_acquire_with_registration_suggests_close_match(conn, ref):
    adapter = MockAdapter(set())
    typo = ResourceRef(ref.project_id, "sh0ts/SQ01_SH010") # one letter off from the real "shots/SQ01_SH010"
    with pytest.raises(ResourceNotFoundError) as exc_info:
        acquire_with_registration(conn, adapter, typo, "Levi")
    assert ref.resource_path in exc_info.value.suggestions

def test_acquire_with_registration_passes_duration(conn, ref):
    adapter = MockAdapter(set())  # ref is already registered, so the adapter isn't asked
    now = datetime.now(UTC)
    lock = acquire_with_registration(conn, adapter, ref, "Levi", duration=timedelta(hours=2))
    # Not the default 8 hours: a small window around 2 hours from now.
    assert now + timedelta(hours=1, minutes=59) < lock.expires_at < now + timedelta(hours=2, minutes=1)

def test_acquire_with_registration_records_the_locker_as_registrant(conn, project):
    ref = ResourceRef(project.project_id, "shots/SQ05_SH050")
    acquire_with_registration(conn, MockAdapter({ref.resource_path}), ref, "Sarah")
    registered_by = conn.execute(
        "SELECT registered_by FROM resources WHERE project_id = ? AND resource_path = ?",
        (ref.project_id, ref.resource_path),
    ).fetchone()[0]
    assert registered_by == "Sarah"