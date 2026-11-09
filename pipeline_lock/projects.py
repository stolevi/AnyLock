import sqlite3
from datetime import UTC, datetime

from pipeline_lock.models import Project, ResourceRef, StorageType
from pipeline_lock.permissions import require_admin


class ProjectExistsError(Exception):
    """Raised when a project with that name already exists."""

class ProjectNotFoundError(Exception):
    """Raised when a project doesn't exist."""

def _row_to_project(row: sqlite3.Row) -> Project:
    """Convert a database row to a Project."""
    return Project(
        project_id=row["project_id"],
        project_name=row["project_name"],
        storage_type=StorageType(row["storage_type"]),
        root=row["root"],
        enforcement_enabled=bool(row["enforcement_enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )

def create_project(conn: sqlite3.Connection, project_name: str, storage_type: StorageType, root: str, created_by: str) -> Project:
    """Create a new project. Only admin users can do this.
    Raises ProjectExistsError if a project with the same name already exists.
    Raises NotAuthorizedError if the user is not an admin.
    """
    now = datetime.now(UTC)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        require_admin(conn, created_by)
        try:
            row = conn.execute(
                "INSERT INTO projects (project_name, storage_type, root, created_at, updated_at) VALUES (?, ?, ?, ?, ?) RETURNING *",
                (project_name, storage_type.value, root, now.isoformat(), now.isoformat()),
            ).fetchone()
        except sqlite3.IntegrityError as e:
            raise ProjectExistsError(f"Project with name '{project_name}' already exists.") from e
        return _row_to_project(row)

def get_project_by_name(conn: sqlite3.Connection, project_name: str) -> Project:
    """Retrieve a project by its name. Raises ProjectNotFoundError if 
    the project does not exist."""
    row = conn.execute(
        "SELECT * FROM projects WHERE project_name = ?", (project_name,)
    ).fetchone()
    if row is None:
        raise ProjectNotFoundError(f"Project with name '{project_name}' does not exist.")
    return _row_to_project(row)

def register_resource(conn: sqlite3.Connection, ref: ResourceRef, registered_by: str) -> bool:
    """Register a resource under a project. Returns True if the resource
    was successfully registered, False if it already exists. The first 
    registration wins: a repeat doesn't change who added it or when.
    Raises ProjectNotFoundError if the project does not exist.
    """
    now = datetime.now(UTC)
    try:
        with conn:
            cursor = conn.execute(
                """INSERT INTO resources (project_id, resource_path, registered_at, registered_by) VALUES (?, ?, ?, ?)
                ON CONFLICT (project_id, resource_path) DO NOTHING""",
                (ref.project_id, ref.resource_path, now.isoformat(), registered_by)
            )
    except sqlite3.IntegrityError as e:
        if e.sqlite_errorname != "SQLITE_CONSTRAINT_FOREIGNKEY":    
            raise # some other rule was broken: let it surface as it is
        raise ProjectNotFoundError(f"Project with ID '{ref.project_id}' does not exist.") from e
    return cursor.rowcount == 1

def is_resource_registered(conn: sqlite3.Connection, ref: ResourceRef) -> bool:
    """Return True if the resource is registered under the project."""
    row = conn.execute(
        "SELECT 1 FROM resources WHERE project_id = ? AND resource_path = ?", (ref.project_id, ref.resource_path)
    ).fetchone()
    return row is not None

def list_resources_in_project(conn: sqlite3.Connection, project_id: int) -> list[str]:
    """Return the resource paths for all resources registered 
    on a project, ascending."""
    rows = conn.execute(
        "SELECT resource_path FROM resources WHERE project_id = ? ORDER BY resource_path ASC", (project_id,)
    ).fetchall()
    return [row["resource_path"] for row in rows]