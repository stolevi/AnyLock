import threading

from pipeline_lock.db import get_connection
from pipeline_lock.models import StorageType
from pipeline_lock.permissions import add_admin
from pipeline_lock.projects import ProjectExistsError, create_project


def test_only_one_concurrent_create_wins(tmp_path):
    db_path = tmp_path / "race.db"
    setup = get_connection(db_path)
    add_admin(setup, "Levi")  # Add an admin user
    setup.close()

    n = 8 # Number of concurrent threads
    barrier = threading.Barrier(n)
    results = []

    def worker():
        conn = get_connection(db_path)
        try:
            barrier.wait() # Wait for all threads to be ready
            create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
            results.append("created")
        except ProjectExistsError:
            results.append("exists")
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("created") == 1, "Only one thread should succeed in creating the project."
    assert results.count("exists") == n - 1, "All other threads should raise ProjectExistsError."