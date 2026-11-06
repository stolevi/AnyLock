import sqlite3

from pipeline_lock import locks
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
    register_resource(levi, ref)

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
