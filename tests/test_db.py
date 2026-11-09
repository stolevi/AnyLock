from pipeline_lock import db
from pipeline_lock.db import open_and_close_connection


def test_anylock_db_env_var_picks_the_database(tmp_path, monkeypatch):
    target = tmp_path / "from_env.db"
    monkeypatch.setenv("ANYLOCK_DB", str(target))
    with open_and_close_connection() as conn:
        conn.execute("SELECT 1")
    assert target.exists()


def test_default_path_is_read_at_call_time(tmp_path, monkeypatch):
    target = tmp_path / "default.db"
    monkeypatch.delenv("ANYLOCK_DB", raising=False)
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", target)
    with open_and_close_connection() as conn:
        conn.execute("SELECT 1")
    assert target.exists()