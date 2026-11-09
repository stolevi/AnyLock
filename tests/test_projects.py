import sqlite3
from datetime import UTC, datetime

import pytest

from pipeline_lock.models import ResourceRef, StorageType
from pipeline_lock.permissions import NotAuthorizedError, add_admin
from pipeline_lock.projects import (
    ProjectExistsError,
    ProjectNotFoundError,
    create_project,
    get_project_by_name,
    is_resource_registered,
    list_resources_in_project,
    register_resource,
)


def _registration(conn, ref):
    """Return (registered_at, registered_by) for a registered resource."""
    row = conn.execute(
        "SELECT registered_at, registered_by FROM resources WHERE project_id = ? AND resource_path = ?",
        (ref.project_id, ref.resource_path),
    ).fetchone()
    return datetime.fromisoformat(row["registered_at"]), row["registered_by"]

# --- create_project ---

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


# --- get_project_by_name ---

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


# --- register_resource ---

def test_register_resource_success(conn):
    add_admin(conn, "Levi")
    project = create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    ref = ResourceRef(project_id=project.project_id, resource_path="shots/SQ01_SH010")
    assert register_resource(conn, ref, "Levi") is True  # First registration should succeed
    count = conn.execute("SELECT COUNT(*) FROM resources WHERE project_id = ? AND resource_path = ?", (project.project_id, ref.resource_path)).fetchone()[0]
    assert count == 1  # Ensure the resource was registered in the database

def test_register_resource_twice_false(conn):
    add_admin(conn, "Levi")
    project = create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    ref = ResourceRef(project_id=project.project_id, resource_path="shots/SQ01_SH010")
    assert register_resource(conn, ref, "Levi") is True  # First registration should succeed
    assert register_resource(conn, ref, "Levi") is False  # Second registration should return False
    count = conn.execute("SELECT COUNT(*) FROM resources WHERE project_id = ? AND resource_path = ?", (project.project_id, ref.resource_path)).fetchone()[0]
    assert count == 1  # Ensure only one entry exists in the database

def test_register_resource_same_path_in_different_projects_returns_true(conn):
    add_admin(conn, "Levi")
    project1 = create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")
    project2 = create_project(conn, "Drijf", StorageType.FILE_SYSTEM, "/drijf", "Levi")
    ref1 = ResourceRef(project_id=project1.project_id, resource_path="shots/SQ01_SH010")
    ref2 = ResourceRef(project_id=project2.project_id, resource_path="shots/SQ01_SH010")
    assert register_resource(conn, ref1, "Levi") is True  # First registration should succeed
    assert register_resource(conn, ref2, "Levi") is True  # Registration in a different project should also succeed
    count1 = conn.execute("SELECT COUNT(*) FROM resources WHERE project_id = ? AND resource_path = ?", (project1.project_id, ref1.resource_path)).fetchone()[0]
    count2 = conn.execute("SELECT COUNT(*) FROM resources WHERE project_id = ? AND resource_path = ?", (project2.project_id, ref2.resource_path)).fetchone()[0]
    assert count1 == 1  # Ensure the resource was registered in the first project
    assert count2 == 1  # Ensure the resource was registered in the second project

def test_register_resource_nonexistent_project_raises_error(conn):
    ref = ResourceRef(project_id=9999, resource_path="shots/SQ01_SH010")  # Non-existent project ID
    with pytest.raises(ProjectNotFoundError):
        register_resource(conn, ref, "Levi")

def test_register_resource_records_who_and_when(conn, project):
    ref = ResourceRef(project.project_id, "shots/SQ05_SH050")
    before = datetime.now(UTC)
    register_resource(conn, ref, "Levi")
    after = datetime.now(UTC)
    registered_at, registered_by = _registration(conn, ref)
    assert registered_by == "Levi"
    assert before <= registered_at <= after

def test_register_resource_first_registration_wins(conn, project):
    ref = ResourceRef(project.project_id, "shots/SQ05_SH050")
    register_resource(conn, ref, "Levi")
    first = _registration(conn, ref)
    assert register_resource(conn, ref, "Sarah") is False
    assert _registration(conn, ref) == first  # still Levi, still the original time

def test_register_resource_without_a_name_raises(conn, project):
    ref = ResourceRef(project.project_id, "shots/SQ05_SH050")
    with pytest.raises(sqlite3.IntegrityError):
        register_resource(conn, ref, None)


# --- is_resource_registered ---

def test_is_resource_registered_true_for_registered_resource(conn, ref):
    assert is_resource_registered(conn, ref) is True  # the ref fixture already registered it

def test_is_resource_registered_false_for_unregistered_resource(conn, project):
    unregistered = ResourceRef(project_id=project.project_id, resource_path="shots/SQ09_SH090")
    assert is_resource_registered(conn, unregistered) is False

def test_is_resource_registered_false_in_different_project(conn, ref):
    other = create_project(conn, "Drijf", StorageType.FILE_SYSTEM, "/drijf", "Levi")
    same_path_elsewhere = ResourceRef(project_id=other.project_id, resource_path=ref.resource_path)
    assert is_resource_registered(conn, same_path_elsewhere) is False  # never registered in Drijf


# --- list_resources_in_project ---

def test_list_resources_in_project_only_this_project_sorted(conn, project):
    register_resource(conn, ResourceRef(project_id=project.project_id, resource_path="shots/SQ03_SH030"), "Levi")
    register_resource(conn, ResourceRef(project_id=project.project_id, resource_path="shots/SQ01_SH010"), "Levi")
    register_resource(conn, ResourceRef(project_id=project.project_id, resource_path="shots/SQ02_SH020"), "Levi")
    other = create_project(conn, "Drijf", StorageType.FILE_SYSTEM, "/drijf", "Levi")
    register_resource(conn, ResourceRef(project_id=other.project_id, resource_path="shots/SQ00_DECOY"), "Levi")
    assert list_resources_in_project(conn, project.project_id) == [
        "shots/SQ01_SH010",
        "shots/SQ02_SH020",
        "shots/SQ03_SH030",
    ]

def test_list_resources_in_project_empty_project(conn, project):
    assert list_resources_in_project(conn, project.project_id) == []

