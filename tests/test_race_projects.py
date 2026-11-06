import threading

from pipeline_lock.db import get_connection
from pipeline_lock.models import StorageType
from pipeline_lock.permissions import add_admin
from pipeline_lock.projects import (
    ProjectExistsError,
    ResourceRef,
    create_project,
    register_resource,
)


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

def test_only_one_concurrent_register_resource_wins(tmp_path):
    db_path = tmp_path / "race.db"
    setup = get_connection(db_path)
    add_admin(setup, "Ann")
    project = create_project(setup, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Ann")
    ref = ResourceRef(project_id=project.project_id, resource_path="shots/SQ01_SH010")
    setup.close()

    n = 8 # Number of concurrent threads
    barrier = threading.Barrier(n)
    results = []

    def worker():
        conn = get_connection(db_path)
        try:
            barrier.wait()
            results.append(register_resource(conn, ref))
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 1, "Only one thread should succeed in registering the resource."
    assert results.count(False) == n - 1, "All other threads should return False indicating the resource already exists."

    check = get_connection(db_path)
    count = check.execute(
        "SELECT COUNT(*) FROM resources WHERE project_id = ? AND resource_path = ?",
        (ref.project_id, ref.resource_path)
    ).fetchone()[0]
    check.close()
    assert count == 1, "There should be exactly one row."