import sqlite3

from pipeline_lock import core
from pipeline_lock.db import get_connection


def test_two_people_cannot_both_acquire(tmp_path, monkeypatch):
    """Levi checks, finds the shot free, and before his write lands Sarah
    tries to take it. Exactly one of them may end up with the lock."""
    db = tmp_path / "locks.db"
    levi = get_connection(db)
    sarah = get_connection(db)
    sarah.execute("PRAGMA busy_timeout = 200")
    winners = []
    original_write = core._write_lock

    def write_after_sarah(conn, resource_id, owner, duration=None):
        # Levi's check already ran; Sarah slips in before his write.
        monkeypatch.setattr(core, "_write_lock", original_write)
        try:
            core.acquire_lock(sarah, resource_id, "Sarah")
            winners.append("Sarah")
        except (core.LockConflictError, sqlite3.OperationalError):
            pass  # Sarah was correctly kept out
        return original_write(conn, resource_id, owner, duration)

    monkeypatch.setattr(core, "_write_lock", write_after_sarah)
    try:
        core.acquire_lock(levi, "SQ01_SH070", "Levi")
        winners.append("Levi")
    except core.LockConflictError:
        pass

    assert len(winners) == 1, f"both got the lock: {winners}"
    assert core.check_status(levi, "SQ01_SH070").owner == winners[0]
