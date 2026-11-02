import pytest

from pipeline_lock.permissions import (
    NotAuthorizedError,
    add_admin,
    is_admin,
    remove_admin,
    require_admin,
)


def test_is_admin(conn):
    add_admin(conn, "admin_name_1")
    assert is_admin(conn, "admin_name_1")
    assert not is_admin(conn, "admin_name_2")

def test_require_admin_passes_for_admin(conn):
    add_admin(conn, "admin_name_1")
    require_admin(conn, "admin_name_1")

def test_require_admin_raises_for_non_admin(conn):
    with pytest.raises(NotAuthorizedError):
        require_admin(conn, "admin_name")

def test_add_admin_ignore_double_name(conn):
    add_admin(conn, "Levi")
    add_admin(conn, "Levi")
    count = conn.execute(
        """
        SELECT COUNT(*) FROM admins
        WHERE admin_name = ?
        """,
        ("Levi",)
    ).fetchone()[0]
    assert is_admin(conn, "Levi")
    assert count == 1

def test_remove_admin(conn):
    add_admin(conn, "admin_name")
    remove_admin(conn, "admin_name")
    assert not is_admin(conn, "admin_name")

def test_remove_admin_noop(conn):
    remove_admin(conn, "admin_name")
    assert not is_admin(conn, "admin_name")