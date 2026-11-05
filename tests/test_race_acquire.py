import sqlite3

from pipeline_lock import locks
from pipeline_lock.db import get_connection


def test_two_people_cannot_both_acquire(tmp_path, monkeypatch):
    """Levi checks, finds the shot free, and before his write lands Sarah
    tries to take it. Exactly one of them may end up with the lock."""
    db = tmp_path / "locks.db"
    levi = get_connection(db)
    sarah = get_connection(db)
    sarah.execute("PRAGMA busy_timeout = 200")
    winners = []
    original_write = locks._write_lock

    def write_after_sarah(conn, resource_path, owner, duration=None):
        # Levi's check already ran; Sarah slips in before his write.
        monkeypatch.setattr(locks, "_write_lock", original_write)
        try:
            locks.acquire_lock(sarah, resource_path, "Sarah")
            winners.append("Sarah")
        except (locks.LockConflictError, sqlite3.OperationalError):
            pass  # Sarah was correctly kept out
        return original_write(conn, resource_path, owner, duration)

    monkeypatch.setattr(locks, "_write_lock", write_after_sarah)
    try:
        locks.acquire_lock(levi, "SQ01_SH070", "Levi")
        winners.append("Levi")
    except locks.LockConflictError:
        pass

    assert len(winners) == 1, f"both got the lock: {winners}"
    assert locks.check_status(levi, "SQ01_SH070").owner == winners[0]
