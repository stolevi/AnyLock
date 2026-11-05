import pytest

from pipeline_lock.models import StorageType
from pipeline_lock.permissions import NotAuthorizedError, add_admin
from pipeline_lock.projects import (
    ProjectExistsError,
    ProjectNotFoundError,
    create_project,
    get_project_by_name,
)


def test_create_project_as_admin(conn):
    add_admin(conn, "Levi")  # Add an admin user
    project = create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    assert project.project_name == "Klonter"
    assert project.storage_type == StorageType.FILE_SYSTEM
    assert project.root == "/klonter"
    assert project.enforcement_enabled is True
    assert project.created_at == project.updated_at  # Ensure created_at and updated_at are the same upon creation
    assert isinstance(project.project_id, int)  # Ensure project_id is assigned and is an integer

def test_create_project_refused_for_non_admin(conn):
    with pytest.raises(NotAuthorizedError):
        create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Neyrouz")  # "Neyrouz" is not an admin
    count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    assert count == 0  # Ensure no project was created

def test_create_duplicate_project_refused(conn):
    add_admin(conn, "Levi")  # Add an admin user
    create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    with pytest.raises(ProjectExistsError):
        create_project(conn, "klonter", StorageType.DROPBOX, "/klonter_dropbox", "Levi")  # Attempt to create a duplicate project
    count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    assert count == 1  # Ensure only one project exists

def test_get_project_by_name_exact(conn):
    add_admin(conn, "Levi") 
    create_project(conn, "Drijf", StorageType.FILE_SYSTEM, "/drijf", "Levi")
    klonter = create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    retrieved_project = get_project_by_name(conn, "Klonter")
    assert retrieved_project.project_id == klonter.project_id

def test_get_project_by_name_ignores_case(conn):
    add_admin(conn, "Levi")
    created_project = create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    retrieved_project = get_project_by_name(conn, "klonter")
    assert retrieved_project.project_id == created_project.project_id

def test_get_project_by_name_missing_raises_error(conn):
    with pytest.raises(ProjectNotFoundError):
        get_project_by_name(conn, "Klonter")