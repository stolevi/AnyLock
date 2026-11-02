import sqlite3

from pipeline_lock import permissions
from pipeline_lock.db import get_connection


def test_no_two_admins_can_be_added_without_authorization(tmp_path, monkeypatch):
    """The first admin can be added without authorization, but the second cannot."""
    db = tmp_path / "locks.db"
    bob_conn = get_connection(db)
    alice_conn = get_connection(db)
    alice_conn.execute("PRAGMA busy_timeout = 200")
    winners = []
    original_add = permissions.add_admin

    def add_after_bob(conn, admin_name):
        # Bob's check already ran; Alice slips in before his write.
        monkeypatch.setattr(permissions, "add_admin", original_add)
        try:
            permissions.add_admin_with_bootstrap(alice_conn, admin_name="Alice", initiated_by="Alice")
            winners.append("Alice")
        except sqlite3.OperationalError:
            pass  # Alice was correctly kept out
        return original_add(conn, admin_name)

    monkeypatch.setattr(permissions, "add_admin", add_after_bob)
    permissions.add_admin_with_bootstrap(bob_conn, admin_name="Bob", initiated_by="Bob")
    winners.append("Bob")

    assert len(winners) == 1, f"both got added: {winners}"
    assert permissions.is_admin(bob_conn, "Bob")

    
