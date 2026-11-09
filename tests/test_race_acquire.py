import sqlite3
import threading

from pipeline_lock import locks
from pipeline_lock.adapters.mock import MockAdapter
from pipeline_lock.db import get_connection
from pipeline_lock.models import ResourceRef, StorageType
from pipeline_lock.permissions import add_admin
from pipeline_lock.projects import create_project, register_resource


def test_two_people_cannot_both_acquire(tmp_path, monkeypatch):
    """Levi checks, finds the shot free, and before his write lands Sarah
    tries to take it. Exactly one of them may end up with the lock."""
    db = tmp_path / "locks.db"
    levi = get_connection(db)
    sarah = get_connection(db)
    sarah.execute("PRAGMA busy_timeout = 200")

    add_admin(levi, "Levi")
    project = create_project(levi, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    ref = ResourceRef(project_id=project.project_id, resource_path="shots/SQ01_SH070")
    register_resource(levi, ref, "Levi")

    winners = []
    original_write = locks._write_lock

    def write_after_sarah(conn, ref, owner, duration=None):
        # Levi's check already ran; Sarah slips in before his write.
        monkeypatch.setattr(locks, "_write_lock", original_write)
        try:
            locks.acquire_lock(sarah, ref, "Sarah")
            winners.append("Sarah")
        except (locks.LockConflictError, sqlite3.OperationalError):
            pass  # Sarah was correctly kept out
        return original_write(conn, ref, owner, duration)

    monkeypatch.setattr(locks, "_write_lock", write_after_sarah)
    try:
        locks.acquire_lock(levi, ref, "Levi")
        winners.append("Levi")
    except locks.LockConflictError:
        pass

    assert len(winners) == 1, f"both got the lock: {winners}"
    assert locks.check_status(levi, ref).owner == winners[0]

def test_only_one_concurrent_acquire_with_registration_wins(tmp_path):
    db_path = tmp_path / "race.db"
    setup = get_connection(db_path)
    add_admin(setup, "Levi")
    project = create_project(setup, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    setup.close()
    ref = ResourceRef(project.project_id, "shots/SQ01_SH010") # NOT added to the project yet
    adapter = MockAdapter({ref.resource_path}) # but the adapter knows it

    n = 8
    barrier = threading.Barrier(n)
    winners = []
    results = []

    def worker(i):
        conn = get_connection(db_path)
        try:
            barrier.wait()
            locks.acquire_with_registration(conn, adapter, ref, f"artist{i}")
            winners.append(f"artist{i}")
        except locks.LockConflictError:
            results.append("conflict")
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(winners) == 1, f"more than one artist acquired the resource: {winners}"
    assert results.count("conflict") == n - 1, "everyone else should be told there's a conflict"

    check = get_connection(db_path)
    rows = check.execute(
        "SELECT COUNT(*) FROM resources WHERE project_id = ? AND resource_path = ?",
        (ref.project_id, ref.resource_path),
    ).fetchone()[0]
    lock = locks.check_status(check, ref)
    acquire_events = [e for e in locks.get_resource_history(check, ref) if e.event_type == "acquire"]
    check.close()

    assert rows == 1, "the resource should be registered exactly once"
    assert lock.owner == winners[0], "the lock should belong to the winner"
    assert len(acquire_events) == 1, "exactly one acquire should be recorded"
