import pytest

from pipeline_lock.permissions import (
    NotAuthorizedError,
    add_supervisor,
    is_supervisor,
    remove_supervisor,
    require_supervisor,
)


def test_is_supervisor(conn):
    add_supervisor(conn, "supervisor_name_1")
    assert is_supervisor(conn, "supervisor_name_1")
    assert not is_supervisor(conn, "supervisor_name_2")

def test_require_supervisor_passes_for_supervisor(conn):
    add_supervisor(conn, "supervisor_name_1")
    require_supervisor(conn, "supervisor_name_1")

def test_require_supervisor_raises_for_non_supervisor(conn):
    with pytest.raises(NotAuthorizedError):
        require_supervisor(conn, "supervisor_name")

def test_add_supervisor_ignore_double_name(conn):
    add_supervisor(conn, "Levi")
    add_supervisor(conn, "Levi")
    count = conn.execute(
        """
        SELECT COUNT(*) FROM supervisors
        WHERE supervisor_name = ?
        """,
        ("Levi",)
    ).fetchone()[0]
    assert is_supervisor(conn, "Levi")
    assert count == 1

def test_remove_supervisor(conn):
    add_supervisor(conn, "supervisor_name")
    remove_supervisor(conn, "supervisor_name")
    assert not is_supervisor(conn, "supervisor_name")

def test_remove_supervisor_noop(conn):
    remove_supervisor(conn, "supervisor_name")
    assert not is_supervisor(conn, "supervisor_name")