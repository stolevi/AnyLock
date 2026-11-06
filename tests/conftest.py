import pytest

from pipeline_lock.db import get_connection
from pipeline_lock.models import ResourceRef, StorageType
from pipeline_lock.permissions import add_admin
from pipeline_lock.projects import create_project, register_resource


@pytest.fixture
def conn():
    """Provide a fresh in-memory database connection for each test."""
    conn = get_connection(":memory:")
    yield conn
    conn.close()

@pytest.fixture
def project(conn):
    """Provide a sample project for tests."""
    add_admin(conn, "Levi")  # Add an admin user
    return create_project(conn, "Klonter", StorageType.FILE_SYSTEM, "/klonter", "Levi")

@pytest.fixture
def ref(conn, project):
    """Provide a sample resource reference for tests."""
    ref = ResourceRef(project_id=project.project_id, resource_path="shots/SQ01_SH010")
    register_resource(conn, ref)
    return ref