import pytest

from pipeline_lock.permissions import (
    LastAdminError,
    NotAuthorizedError,
    add_admin,
    add_admin_with_bootstrap,
    is_admin,
    remove_admin,
    remove_admin_with_lock,
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

def test_bootstrap_stays_closed_after_last_admin_tries_to_leave(conn):
    add_admin(conn, "Levi")
    with pytest.raises(LastAdminError):
        remove_admin_with_lock(conn, "Levi", "Levi")
    assert is_admin(conn, "Levi")
    with pytest.raises(NotAuthorizedError):
        add_admin_with_bootstrap(conn, "Camiel", "Camiel")

def test_one_of_two_admins_can_leave(conn):
    add_admin(conn, "Levi")
    add_admin(conn, "Sarah")
    remove_admin_with_lock(conn, "Sarah", "Sarah")
    assert not is_admin(conn, "Sarah")
    assert is_admin(conn, "Levi")