import sqlite3

from pipeline_lock import locks
from pipeline_lock.db import get_connection
from pipeline_lock.models import ResourceRef, StorageType
from pipeline_lock.permissions import add_admin
from pipeline_lock.projects import create_project, register_resource


def test_refresh_cannot_resurrect_a_force_released_lock(tmp_path, monkeypatch):
    """Levi refreshes his lock. After his check passes but before his write
    lands, an admin force-releases it. Either the force-release has to wait
    (and Levi's refresh wins cleanly), or the refresh must fail. It may never
    bring a force-released lock back to life."""
    db = tmp_path / "locks.db"
    levi = get_connection(db)
    admin = get_connection(db)
    admin.execute("PRAGMA busy_timeout = 200")

    add_admin(levi, "Admin")
    project = create_project(levi, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Admin")
    ref = ResourceRef(project_id=project.project_id, resource_path="shots/SQ01_SH070")
    register_resource(levi, ref, "Admin")
    locks.acquire_lock(levi, ref, "Levi")

    force_released = []
    original_write = locks._write_lock

    def force_release_in_the_gap(conn, ref, owner, duration=None, acquired_at=None):
        # Levi's check already ran; the admin force-releases before his write.
        monkeypatch.setattr(locks, "_write_lock", original_write)
        try:
            if locks.force_release_lock(admin, ref) is not None:
                force_released.append(True)
        except sqlite3.OperationalError:
            pass  # the admin had to wait: Levi's refresh holds the write lock
        return original_write(conn, ref, owner, duration, acquired_at)

    monkeypatch.setattr(locks, "_write_lock", force_release_in_the_gap)
    try:
        locks.refresh_lock(levi, ref, "Levi")
        refreshed = True
    except locks.LockNotOwnedError:
        refreshed = False

    if force_released:
        assert not refreshed, "refresh succeeded after the lock was force-released"
        assert locks.check_status(levi, ref) is None, "a force-released lock came back to life"
    else:
        assert refreshed
        assert locks.check_status(levi, ref).owner == "Levi"
